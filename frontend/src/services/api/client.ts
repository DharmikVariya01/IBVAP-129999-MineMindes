/**
 * REST API client for IBVAP backend services (M16).
 */

import { config } from '@/config/env';
import type {
  Alert,
  AlertUpdatePayload,
  Camera,
  Event,
  Evidence,
  PaginatedResponse,
  PaginationParams,
  PlatformStats,
  Track,
} from '@/types/api';

export class ApiError extends Error {
  public status: number;
  public details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = config.apiBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  private buildUrl(path: string, params?: object): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const url = new URL(`${this.baseUrl}${cleanPath}`);

    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    return url.toString();
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (options.body && typeof options.body === 'string' && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    try {
      const response = await fetch(endpoint, {
        ...options,
        headers,
      });

      if (!response.ok) {
        let safeMessage = `Request failed with status ${response.status}`;
        let details: unknown = undefined;

        try {
          const errorData = await response.json();
          if (errorData && typeof errorData.detail === 'string') {
            safeMessage = errorData.detail;
          } else if (errorData && typeof errorData.message === 'string') {
            safeMessage = errorData.message;
          }
          details = errorData;
        } catch {
          // If response body is not JSON, retain default safeMessage
        }

        throw new ApiError(safeMessage, response.status, details);
      }

      return (await response.json()) as T;
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        throw err;
      }
      const message = err instanceof Error ? err.message : 'Network error or server unreachable';
      throw new ApiError(message, 0);
    }
  }

  public async get<T>(path: string, params?: object): Promise<T> {
    const url = this.buildUrl(path, params);
    return this.request<T>(url, { method: 'GET' });
  }

  public async patch<T>(path: string, body: unknown): Promise<T> {
    const url = this.buildUrl(path);
    return this.request<T>(url, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  // --- Specific M16 Resources ---

  // Cameras
  public async getCameras(params?: PaginationParams & { status?: string; source_type?: string }): Promise<PaginatedResponse<Camera>> {
    return this.get<PaginatedResponse<Camera>>('/cameras', params);
  }

  public async getCamera(cameraId: string | number): Promise<Camera> {
    return this.get<Camera>(`/cameras/${cameraId}`);
  }

  // Alerts
  public async getAlerts(
    params?: PaginationParams & { status?: string; severity?: string; alert_type?: string; camera_id?: number }
  ): Promise<PaginatedResponse<Alert>> {
    return this.get<PaginatedResponse<Alert>>('/alerts', params);
  }

  public async getAlert(alertId: string | number): Promise<Alert> {
    return this.get<Alert>(`/alerts/${alertId}`);
  }

  public async patchAlertStatus(alertId: string | number, payload: AlertUpdatePayload): Promise<Alert> {
    return this.patch<Alert>(`/alerts/${alertId}`, payload);
  }

  // Tracks
  public async getTracks(
    params?: PaginationParams & { status?: string; camera_id?: number; class_name?: string }
  ): Promise<PaginatedResponse<Track>> {
    return this.get<PaginatedResponse<Track>>('/tracks', params);
  }

  public async getTrack(trackId: number): Promise<Track> {
    return this.get<Track>(`/tracks/${trackId}`);
  }

  // Events
  public async getEvents(
    params?: PaginationParams & { event_type?: string; camera_id?: number }
  ): Promise<PaginatedResponse<Event>> {
    return this.get<PaginatedResponse<Event>>('/events', params);
  }

  // Evidence
  public async getEvidence(
    params?: PaginationParams & { alert_id?: number; camera_id?: number }
  ): Promise<PaginatedResponse<Evidence>> {
    return this.get<PaginatedResponse<Evidence>>('/evidence', params);
  }

  public async getEvidenceById(evidenceId: string | number): Promise<Evidence> {
    return this.get<Evidence>(`/evidence/${evidenceId}`);
  }

  // Stats
  public async getStats(): Promise<PlatformStats> {
    return this.get<PlatformStats>('/stats');
  }
}

export const apiClient = new ApiClient();
