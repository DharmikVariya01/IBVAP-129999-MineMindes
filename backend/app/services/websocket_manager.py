"""WebSocket Connection Manager for IBVAP Module 17.

Provides a robust, thread-safe, and concurrency-safe connection manager for
real-time video streaming, AI detection events, alerts, and camera status updates.

Features:
- Subscriptions grouped by camera_id
- Slow-client backpressure protection with bounded queues and stale-frame dropping
- Guaranteed priority delivery for critical security alerts and lifecycle events
- Automatic stale connection cleanup and graceful disconnect handling
- Clean decoupling of raw WebSocket objects from callers
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import WebSocket, WebSocketDisconnect

from app.schemas.websocket import (
    ConnectionData,
    WebSocketMessage,
    WebSocketMessageType,
)

logger = logging.getLogger("ibvap.websocket_manager")

# Backpressure configuration
DEFAULT_CLIENT_QUEUE_MAXSIZE = 30
FRAME_DROP_QUEUE_THRESHOLD = 3  # Drop stale video frames if client queue exceeds this size


class ClientSubscription:
    """Encapsulates a connected WebSocket client subscription for a specific camera."""

    def __init__(
        self,
        camera_id: str,
        websocket: WebSocket,
        client_id: Optional[str] = None,
        queue_maxsize: int = DEFAULT_CLIENT_QUEUE_MAXSIZE,
    ) -> None:
        self.camera_id: str = camera_id
        self.websocket: WebSocket = websocket
        self.client_id: str = client_id or str(uuid.uuid4())[:8]
        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=queue_maxsize)
        self.is_alive: bool = True
        self.send_task: Optional[asyncio.Task] = None

    def start_sender(self, on_disconnect_callback) -> None:
        """Start the background consumer task that drains the queue and sends to the client."""
        self.send_task = asyncio.create_task(self._send_loop(on_disconnect_callback))

    async def _send_loop(self, on_disconnect_callback) -> None:
        """Background loop continuously sending queued messages to the WebSocket."""
        try:
            while self.is_alive:
                message_dict = await self.queue.get()
                try:
                    payload_json = json.dumps(message_dict)
                    await self.websocket.send_text(payload_json)
                except (WebSocketDisconnect, ConnectionResetError, RuntimeError) as exc:
                    logger.debug(
                        "Client %s on camera %s disconnected during send: %s",
                        self.client_id,
                        self.camera_id,
                        exc,
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "Unexpected error sending to client %s on camera %s: %s",
                        self.client_id,
                        self.camera_id,
                        exc,
                    )
                    break
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            self.is_alive = False
            # Trigger cleanup in manager
            asyncio.create_task(on_disconnect_callback(self))

    async def enqueue(self, message_dict: Dict[str, Any]) -> bool:
        """Enqueue a message with backpressure protection and frame dropping."""
        if not self.is_alive:
            return False

        msg_type = message_dict.get("type")

        # Backpressure strategy for high-frequency video frames
        if msg_type == WebSocketMessageType.FRAME.value:
            # If the client queue is lagging, drop the frame to preserve real-time low latency
            if self.queue.qsize() >= FRAME_DROP_QUEUE_THRESHOLD:
                logger.debug(
                    "Backpressure: Dropping stale frame for slow client %s on camera %s (queue depth: %d)",
                    self.client_id,
                    self.camera_id,
                    self.queue.qsize(),
                )
                return False

        # High priority messages (alerts, status, connection, heartbeat)
        if self.queue.full():
            # If full, evict an older frame if possible to guarantee room for critical alerts
            try:
                dropped = self.queue.get_nowait()
                self.queue.task_done()
                logger.debug(
                    "Evicted older message of type %s to accommodate priority message of type %s for client %s",
                    dropped.get("type"),
                    msg_type,
                    self.client_id,
                )
            except asyncio.QueueEmpty:
                pass

        try:
            self.queue.put_nowait(message_dict)
            return True
        except asyncio.QueueFull:
            logger.warning(
                "Client queue full for %s on camera %s. Dropping message of type %s",
                self.client_id,
                self.camera_id,
                msg_type,
            )
            return False

    async def close(self) -> None:
        """Safely terminate sender loop and close WebSocket connection."""
        self.is_alive = False
        if self.send_task and not self.send_task.done():
            self.send_task.cancel()
            try:
                await self.send_task
            except asyncio.CancelledError:
                pass

        # Drain any lingering messages
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break

        try:
            await self.websocket.close()
        except Exception:
            pass


class WebSocketConnectionManager:
    """Manages active WebSocket subscriptions organized by camera stream."""

    def __init__(self) -> None:
        # Maps camera_id -> set of ClientSubscription objects
        self._cameras: Dict[str, Set[ClientSubscription]] = {}
        # Maps raw websocket object -> ClientSubscription (for O(1) lookup during disconnect)
        self._ws_map: Dict[WebSocket, ClientSubscription] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def connect(self, camera_id: str, websocket: WebSocket) -> ClientSubscription:
        """Register a new client WebSocket connection for a given camera stream."""
        await websocket.accept()

        async with self._lock:
            # Prevent duplicate registration
            if websocket in self._ws_map:
                existing = self._ws_map[websocket]
                logger.info("Client %s already registered for camera %s", existing.client_id, camera_id)
                return existing

            subscription = ClientSubscription(camera_id=camera_id, websocket=websocket)
            subscription.start_sender(self._handle_client_disconnect)

            if camera_id not in self._cameras:
                self._cameras[camera_id] = set()

            self._cameras[camera_id].add(subscription)
            self._ws_map[websocket] = subscription

            logger.info(
                "Registered client %s for camera %s. Active camera clients: %d, Total clients: %d",
                subscription.client_id,
                camera_id,
                len(self._cameras[camera_id]),
                len(self._ws_map),
            )

        # Send initial connection acknowledgement handshake
        conn_msg = WebSocketMessage(
            type=WebSocketMessageType.CONNECTION,
            camera_id=camera_id,
            data=ConnectionData(
                status="connected",
                client_id=subscription.client_id,
                message=f"Connected to camera stream {camera_id}",
            ).model_dump(),
        )
        await subscription.enqueue(conn_msg.model_dump())

        return subscription

    async def disconnect(self, camera_id: str, websocket: WebSocket) -> None:
        """Explicitly disconnect and clean up a client WebSocket."""
        subscription: Optional[ClientSubscription] = None
        async with self._lock:
            subscription = self._ws_map.pop(websocket, None)
            if subscription:
                cam_set = self._cameras.get(camera_id)
                if cam_set:
                    cam_set.discard(subscription)
                    if not cam_set:
                        self._cameras.pop(camera_id, None)

        if subscription:
            await subscription.close()
            logger.info(
                "Disconnected client %s from camera %s. Total remaining clients: %d",
                subscription.client_id,
                camera_id,
                len(self._ws_map),
            )

    async def _handle_client_disconnect(self, subscription: ClientSubscription) -> None:
        """Callback invoked when client's sender loop terminates unexpectedly."""
        async with self._lock:
            self._ws_map.pop(subscription.websocket, None)
            cam_set = self._cameras.get(subscription.camera_id)
            if cam_set:
                cam_set.discard(subscription)
                if not cam_set:
                    self._cameras.pop(subscription.camera_id, None)

        await subscription.close()
        logger.debug(
            "Cleaned up disconnected client %s for camera %s",
            subscription.client_id,
            subscription.camera_id,
        )

    def _normalize_message(self, message: Union[WebSocketMessage, Dict[str, Any]]) -> Dict[str, Any]:
        """Convert a WebSocketMessage or dictionary into a serializable dictionary."""
        if isinstance(message, WebSocketMessage):
            return message.model_dump()
        elif hasattr(message, "model_dump"):
            return message.model_dump()
        elif isinstance(message, dict):
            # Validate essential structure
            if "type" not in message or "camera_id" not in message:
                raise ValueError("Message dictionary must contain 'type' and 'camera_id'.")
            return message
        else:
            raise TypeError(f"Unsupported message type for WebSocket broadcast: {type(message)}")

    async def broadcast_to_camera(
        self,
        camera_id: str,
        message: Union[WebSocketMessage, Dict[str, Any]],
    ) -> int:
        """Deliver a message to all active subscribers of a specific camera stream.

        Returns the number of clients to which the message was successfully dispatched.
        """
        payload = self._normalize_message(message)

        # Snapshot active subscriptions under lock
        async with self._lock:
            subscribers = list(self._cameras.get(camera_id, set()))

        if not subscribers:
            return 0

        dispatched_count = 0
        stale_clients: List[ClientSubscription] = []

        for sub in subscribers:
            if not sub.is_alive:
                stale_clients.append(sub)
                continue
            queued = await sub.enqueue(payload)
            if queued:
                dispatched_count += 1

        # Clean up any stale clients discovered during broadcast
        for stale in stale_clients:
            await self._handle_client_disconnect(stale)

        return dispatched_count

    async def broadcast_all(
        self,
        message: Union[WebSocketMessage, Dict[str, Any]],
    ) -> int:
        """Deliver a message to all active subscribers across all cameras.

        Returns the total number of clients to which the message was successfully dispatched.
        """
        payload = self._normalize_message(message)

        async with self._lock:
            all_subscribers = list(self._ws_map.values())

        if not all_subscribers:
            return 0

        dispatched_count = 0
        stale_clients: List[ClientSubscription] = []

        for sub in all_subscribers:
            if not sub.is_alive:
                stale_clients.append(sub)
                continue
            queued = await sub.enqueue(payload)
            if queued:
                dispatched_count += 1

        for stale in stale_clients:
            await self._handle_client_disconnect(stale)

        return dispatched_count

    def get_connection_count(self) -> int:
        """Return the total number of active WebSocket connections across all cameras."""
        return len(self._ws_map)

    def get_camera_connection_count(self, camera_id: str) -> int:
        """Return the number of active subscribers for a specific camera."""
        return len(self._cameras.get(camera_id, set()))

    def get_active_cameras(self) -> List[str]:
        """Return the list of camera IDs that currently have active subscribers."""
        return list(self._cameras.keys())


# Global singleton instance for application use
websocket_manager = WebSocketConnectionManager()
