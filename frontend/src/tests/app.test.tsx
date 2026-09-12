import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '@/App';
import { Shell } from '@/components/layout/Shell';
import { config } from '@/config/env';

describe('Application & Shell Foundation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }),
    } as unknown as Response);
  });

  it('reads environment configuration with defaults', () => {
    expect(config.apiBaseUrl).toBeDefined();
    expect(config.apiBaseUrl).toContain('/api/v1');
    expect(config.wsBaseUrl).toBeDefined();
    expect(config.wsBaseUrl).toContain('/api/v1');
  });

  it('renders application shell with branding and identity', () => {
    render(
      <Shell>
        <div>Test Page Content</div>
      </Shell>
    );

    expect(screen.getByRole('heading', { name: /ibvap/i })).toBeInTheDocument();
    expect(screen.getByText(/intelligent border video analysis platform/i)).toBeInTheDocument();
    expect(screen.getByText('Test Page Content')).toBeInTheDocument();
    expect(screen.getByText(/ibvap surveillance foundation — operational/i)).toBeInTheDocument();
  });

  it('renders full application with Live CCTV Monitoring by default', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /ibvap/i })).toBeInTheDocument();
      expect(screen.getByText(/live cctv monitoring/i)).toBeInTheDocument();
      expect(screen.getByTestId('cctv-monitoring-page')).toBeInTheDocument();
    });
  });

  it('allows navigation to Foundation Overview and back to Live CCTV', async () => {
    render(<App />);

    // Click Overview nav item
    const overviewButton = screen.getByRole('button', { name: /overview/i });
    fireEvent.click(overviewButton);

    await waitFor(() => {
      expect(screen.getByText(/frontend foundation & infrastructure/i)).toBeInTheDocument();
    });

    // Click Live CCTV nav item
    const cctvButton = screen.getByRole('button', { name: /live cctv/i });
    fireEvent.click(cctvButton);

    await waitFor(() => {
      expect(screen.getByText(/live cctv monitoring/i)).toBeInTheDocument();
    });
  });
});
