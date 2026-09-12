import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from '@/App';
import { Shell } from '@/components/layout/Shell';
import { config } from '@/config/env';

describe('Application & Shell Foundation', () => {
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

  it('renders full application with foundation overview', () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: /ibvap/i })).toBeInTheDocument();
    expect(screen.getByText(/frontend foundation & infrastructure/i)).toBeInTheDocument();
    expect(screen.getByText(/backend integration contracts/i)).toBeInTheDocument();
    expect(screen.getByText(/reusable foundation ui components/i)).toBeInTheDocument();
  });
});
