# IBVAP V1 — SIH DEMONSTRATION RUNBOOK

This runbook provides step-by-step instructions to initialize, execute, and validate the **Intelligent Border Video Analysis Platform (IBVAP)** V1 system for Smart India Hackathon (SIH) demonstrations. All procedures and commands are verified directly against repository code from **Module 1 (M1) through Module 25 (M25)**.

---

## 1. System Prerequisites

Ensure the host workstation meets the following requirements:

| Component | Required Version | Verification Command |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11, Ubuntu 22.04+, or macOS 13+ | `systeminfo` / `uname -a` |
| **Python** | Python 3.11.x (64-bit) | `python -V` (must output `Python 3.11.x`) |
| **Node.js** | Node.js v18.x or v20.x | `node -v` |
| **npm** | npm v9.x or v10.x | `npm -v` |
| **PostgreSQL** (Optional) | PostgreSQL 15+ (Local or Remote) | `psql -V` or check Windows service |
| **YOLO Model Weights** | YOLOv8 Nano (`yolov8n.pt`) | Located in project root |

---

## 2. Environment Setup

### 2.1 Backend Environment Setup

Open PowerShell or terminal in the repository root directory:

```powershell
# Navigate to project root
cd c:\Users\123\OneDrive\Desktop\IBVAP

# Activate Python Virtual Environment
.\.venv\Scripts\Activate.ps1

# Verify installed backend dependencies
pip install -r backend\requirements.txt
```

### 2.2 Frontend Environment Setup

```powershell
# Navigate to frontend directory
cd c:\Users\123\OneDrive\Desktop\IBVAP\frontend

# Install dependencies (already installed if node_modules exists)
npm install
```

---

## 3. Database Setup (PostgreSQL)

IBVAP uses SQLAlchemy 2.0 with a PostgreSQL backend (driver: `psycopg2-binary`).

1. **Configure Environment Variables**:
   Copy the example environment template into `backend/.env`:
   ```powershell
   cd c:\Users\123\OneDrive\Desktop\IBVAP\backend
   cp .env.example .env
   ```

2. **Configure Connection String**:
   Edit `backend/.env` with your PostgreSQL database credentials:
   ```ini
   DATABASE_URL=postgresql+psycopg2://ibvap_user:ibvap_password@localhost:5432/ibvap
   DB_POOL_SIZE=5
   DB_MAX_OVERFLOW=10
   DB_POOL_TIMEOUT=30
   DB_POOL_RECYCLE=1800
   VIDEOS_DIR=../videos
   EVIDENCE_DIR=../evidence
   ```

3. **Initialize Database Tables**:
   If PostgreSQL is running, tables (`cameras`, `tracks`, `zones`, `events`, `alerts`, `evidence`) are automatically initialized on application startup via SQLAlchemy metadata.
   *(Note: If PostgreSQL is not configured, backend test suites and verification scripts run using isolated in-memory engines).*

---

## 4. Backend Startup

Run the FastAPI backend server using `uvicorn`:

```powershell
# From project root
cd c:\Users\123\OneDrive\Desktop\IBVAP
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

### Verification:
- **API Root**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) (returns application name and version)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) (reports uptime, memory, and database status)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (full OpenAPI interactive UI)

---

## 5. Frontend Startup

In a separate terminal, launch the Vite React dashboard:

```powershell
cd c:\Users\123\OneDrive\Desktop\IBVAP\frontend
npm run dev
```

### Verification:
- Dashboard will be available at [http://localhost:5173/](http://localhost:5173/)
- Open Chrome, Edge, or Firefox and navigate to the dashboard.

---

## 6. Live Laptop Webcam Demo

To demonstrate real-time AI ingestion directly from an integrated or USB laptop camera:

```powershell
cd c:\Users\123\OneDrive\Desktop\IBVAP
.\.venv\Scripts\python.exe run_video_input_demo.py
```

*Expected behavior*:
- Connects to hardware video device `0`.
- Captures and displays live webcam frames with frame rate, resolution, and timestamp metadata.
- Cleanly closes capture upon pressing `q` or completing standard frame count.

---

## 7. Real Video Processing Demo (`videos/test.mp4`)

To demonstrate the full sequential AI Pipeline (M1 through M11) processing real border surveillance video:

```powershell
cd c:\Users\123\OneDrive\Desktop\IBVAP
.\.venv\Scripts\python.exe run_pipeline_demo.py --source videos/test.mp4 --max-frames 102
```

*Pipeline Execution Sequence*:
1. **VideoSource (M1)**: Ingests `test.mp4` (256x144 @ 6.0 FPS).
2. **FramePreprocessor (M2)**: Performs adaptive contrast enhancement and normalization.
3. **YOLODetector (M3)**: Executes YOLOv8n object detection (person, vehicle).
4. **ByteTrackTracker (M4)**: Associates detections across frames with persistent track IDs.
5. **EventMemory (M5)**: Records spatial-temporal coordinate history per track.
6. **MovementAnalyzer (M6)**: Calculates velocity vectors, trajectory angle, and displacement.
7. **ZoneManager (M7)**: Performs point-in-polygon geofence evaluation.
8. **FenceBreachDetector (M8)**: Evaluates state transitions across virtual perimeter fences.
9. **LoiteringDetector (M9)**: Checks spatial dwell thresholds inside restricted zones.
10. **AlertEngine (M10)**: Deduplicates incidents and ranks alerts by severity.
11. **EvidenceCapture (M11)**: Generates annotated cryptographic-friendly JPEG evidence.

---

## 8. Tactical Dashboard Demonstration Flow

The IBVAP frontend operator dashboard supports continuous cross-module tactical navigation:

```
[Live CCTV (M19)] ──> [Alert Center (M20)] ──> [Alert Detail Drawer]
       │                        │                       │
       ▼                        ▼                       ▼
[Tactical Map (M21)] ──> [Timeline (M22)] ──> [Analytics (M23)] ──> [Priority Matrix (M24)]
```

### Guided Operator Walkthrough:
1. **Live CCTV (M19)**:
   - View the active video feed, camera selector (`CAM_01`, `CAM_02`), live FPS counter, and detection overlays.
   - Click **"Camera Prioritization"** to inspect automated threat-ranking scores (M24).
2. **Alert Center (M20)**:
   - Click **"Alert Center"** in the top navigation bar.
   - Filter alerts by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) or status (`ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`).
   - Click on an alert card to open the **Alert Detail Drawer**.
   - Click **"Acknowledge"** button — triggers immediate `PATCH /api/v1/alerts/{id}` updating status in real-time.
3. **Tactical Border Map (M21)**:
   - Click **"Tactical Map"** in the navigation bar.
   - View Leaflet geospatial perimeter map with camera markers colored by threat status.
   - Click a camera marker on the map to inspect status and click **"View Live Stream"** to jump back into CCTV monitoring.
4. **Event Timeline (M22)**:
   - Click **"Timeline"** to inspect chronological detection event logs.
   - Filter by Track ID to inspect the full trajectory lifecycle of any specific target.
5. **Statistics & Analytics (M23)**:
   - Click **"Analytics"** to view real-time incident distribution charts, severity breakdown, and 24-hour activity trends.

---

## 9. Deterministic Synthetic Event Demonstration

Because recorded sample video (`test.mp4`) captures natural pedestrian movement without illegal fence breaches, deterministic synthetic scenarios are provided to reliably demonstrate high-severity security incidents during an evaluation:

```powershell
cd c:\Users\123\OneDrive\Desktop\IBVAP
.\.venv\Scripts\python.exe verify_module_25.py
```

*What this demonstrates*:
- **Scenario A (Virtual Fence Breach)**:
  - Track #505 crosses `ZONE_PERIMETER_FENCE` (`OUTSIDE` -> `INSIDE`).
  - M8 creates `FenceBreachEvent`.
  - M10 generates `CRITICAL` alert `ALT-SYNTH-505`.
  - M11 saves evidence image `evidence/ev_ALT_SYNTH_505.jpg`.
  - M25 persists camera, track, event, alert, and evidence to the database.
  - M17 delivers real-time priority notification to WebSocket subscribers.
- **Scenario B (Restricted Zone Loitering)**:
  - Track #506 dwells in `ZONE_RESTRICTED` exceeding 30.0s threshold.
  - M9 creates `LoiteringEvent` (duration: 35.5s).
  - M10 generates `HIGH` alert `ALT-SYNTH-506`.
  - Full relational persistence and WebSocket broadcast verified.
- **Alert Lifecycle State Machine**:
  - `ACTIVE` -> `ACKNOWLEDGED` (by Duty Officer) -> `RESOLVED` (by Commander).
- **Failure Handling & Rollback**:
  - Validates atomic database rollback on engine exceptions without orphan rows.

---

## 10. Evidence Inspection Demonstration

1. **Filesystem Inspection**:
   Evidence captures are saved as standalone JPEG images in the `evidence/` directory:
   ```powershell
   ls .\evidence\
   ```
2. **REST API Streaming**:
   Evidence records and image files can be retrieved via REST endpoints:
   ```powershell
   # Retrieve metadata
   curl http://127.0.0.1:8000/api/v1/evidence/EVD-SYNTH-505

   # Download image file
   curl http://127.0.0.1:8000/api/v1/evidence/EVD-SYNTH-505/file --output evidence_demo.jpg
   ```
   *Security Note*: Path traversal attempts (e.g. `../../secret`) are strictly rejected with HTTP 403/404.

---

## 11. Clean Shutdown Procedure

To cleanly stop the IBVAP demonstration:

1. **Stop Frontend**:
   In the frontend terminal window, press `Ctrl + C` and confirm termination (`Y`).
2. **Stop Backend**:
   In the backend terminal window, press `Ctrl + C`. FastAPI's lifespan context manager will cleanly:
   - Disconnect active WebSocket clients.
   - Dispose database connection pools (`dispose_engine()`).
   - Flush pending logs.
3. **Release Video/Camera Resources**:
   All OpenCV video captures and background pipelines are automatically released upon process exit.

---

## 12. Troubleshooting Guide

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| **Port 8000 already in use** | Stale uvicorn or python process running | Run `Get-Process python \| Stop-Process -Force` (PowerShell) or change port via `--port 8001`. |
| **Port 5173 already in use** | Another Vite instance active | Vite will automatically prompt or select `5174`. Update `backend/.env` CORS origins if needed. |
| **Webcam cannot open (Device 0)** | Camera in use by another app or permissions denied | Close apps using the webcam (e.g., Zoom, Teams, Camera app) and check Windows Privacy Settings. |
| **PostgreSQL Connection Error** | Service stopped or credentials incorrect | Check service status (`Get-Service postgresql*`). Verify username/password in `backend/.env`. |
| **Missing `yolov8n.pt`** | Model weight file not downloaded | Ensure `yolov8n.pt` is present in project root (automatically downloaded by Ultralytics if missing). |

---

## 13. Known Operational Limitations (V1 Scope)

1. **Real-Video Event Content**: `videos/test.mp4` contains normal pedestrian walking sequences. Natural fence breach and loitering events do not occur in this clip; deterministic synthetic scenarios (`verify_module_25.py`) must be used to demonstrate security alerts.
2. **RTSP Hardware Ingestion**: Physical RTSP cameras require access to a local streaming RTSP server/NVR. In offline environments, video file emulation (`videos/test.mp4`) and webcam capture (`device 0`) are the validated inputs.
3. **Single Active Video Stream**: The V1 operator UI intentionally binds to one primary live stream at a time to prevent WebSocket congestion and client thread exhaustion.
4. **Database Dependency**: Full relational audit logs require an active PostgreSQL instance; when PostgreSQL is not configured, backend tests fall back to isolated SQLite test fixtures.
