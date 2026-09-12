import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ApiClient, ApiError } from '@/services/api/client';
import { config } from '@/config/env';

describe('ApiClient (M16 REST Client)', () => {
  let client: ApiClient;
  const originalFetch = global.fetch;

  beforeEach(() => {
    client = new ApiClient('http://test-server:8000/api/v1');
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('uses configured base URL and trims trailing slashes', () => {
    const customClient = new ApiClient('http://localhost:8000/api/v1///');
    expect(customClient.getBaseUrl()).toBe('http://localhost:8000/api/v1');
  });

  it('falls back to default config.apiBaseUrl when no URL is provided', () => {
    const defaultClient = new ApiClient();
    expect(defaultClient.getBaseUrl()).toBe(config.apiBaseUrl.replace(/\/+$/, ''));
  });

  it('performs GET request with query parameters properly encoded', async () => {
    const mockData = { items: [{ id: 1, camera_id: 'CAM-01' }], total: 1, page: 1, page_size: 10, total_pages: 1 };
    
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response);

    const result = await client.getCameras({ page: 2, page_size: 20, status: 'ONLINE' });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const calledUrl = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(calledUrl).toContain('/cameras?page=2&page_size=20&status=ONLINE');
    expect(result).toEqual(mockData);
  });

  it('performs PATCH request with JSON body', async () => {
    const mockAlert = { id: 1, alert_id: 'ALT-01', status: 'ACKNOWLEDGED' };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockAlert,
    } as Response);

    const result = await client.patchAlertStatus('ALT-01', {
      status: 'ACKNOWLEDGED',
      acknowledged_by: 'operator1',
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [calledUrl, options] = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(calledUrl).toBe('http://test-server:8000/api/v1/alerts/ALT-01');
    expect(options.method).toBe('PATCH');
    expect(options.body).toBe(JSON.stringify({ status: 'ACKNOWLEDGED', acknowledged_by: 'operator1' }));
    expect(result).toEqual(mockAlert);
  });

  it('throws ApiError with sanitized message when response is not ok', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Camera not found' }),
    } as Response);

    await expect(client.getCamera('INVALID')).rejects.toThrow('Camera not found');
    try {
      await client.getCamera('INVALID');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    }
  });

  it('fetches platform stats correctly', async () => {
    const mockStats = {
      cameras: 4,
      tracks: 12,
      events: 25,
      alerts: 3,
      evidence: 2,
      alerts_by_status: { ACTIVE: 3 },
      alerts_by_severity: { CRITICAL: 1 },
      cameras_by_status: { ONLINE: 4 },
      tracks_by_status: { ACTIVE: 12 },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockStats,
    } as Response);

    const stats = await client.getStats();
    expect(stats).toEqual(mockStats);
  });
});
