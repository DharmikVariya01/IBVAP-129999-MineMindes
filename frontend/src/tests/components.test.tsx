import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  Button,
  Card,
  Badge,
  Panel,
  StatusIndicator,
  LoadingState,
  ErrorState,
  EmptyState,
} from '@/components/common';

describe('Reusable UI Foundation Components', () => {
  describe('Button', () => {
    it('renders with children and handles click events', () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Acknowledge Alert</Button>);

      const btn = screen.getByRole('button', { name: /acknowledge alert/i });
      expect(btn).toBeInTheDocument();
      fireEvent.click(btn);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('renders loading spinner and disables click when isLoading is true', () => {
      const handleClick = vi.fn();
      render(
        <Button isLoading onClick={handleClick}>
          Submit
        </Button>
      );

      const btn = screen.getByRole('button');
      expect(btn).toBeDisabled();
      fireEvent.click(btn);
      expect(handleClick).not.toHaveBeenCalled();
    });

    it('renders different variants and sizes', () => {
      const { rerender } = render(<Button variant="danger" size="sm">Delete</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-tactical-rose');

      rerender(<Button variant="secondary" size="lg">Cancel</Button>);
      expect(screen.getByRole('button')).toHaveClass('bg-surveillance-800');
    });
  });

  describe('Card', () => {
    it('renders title, subtitle, action, content, and footer', () => {
      render(
        <Card
          title="Camera Stream Info"
          subtitle="Sector Alpha"
          action={<button>Refresh</button>}
          footer={<span>Last sync: 2m ago</span>}
        >
          <p>Card body content</p>
        </Card>
      );

      expect(screen.getByText('Camera Stream Info')).toBeInTheDocument();
      expect(screen.getByText('Sector Alpha')).toBeInTheDocument();
      expect(screen.getByText('Refresh')).toBeInTheDocument();
      expect(screen.getByText('Card body content')).toBeInTheDocument();
      expect(screen.getByText('Last sync: 2m ago')).toBeInTheDocument();
    });
  });

  describe('Badge', () => {
    it('renders badge with appropriate variant classes', () => {
      const { rerender } = render(<Badge variant="critical">CRITICAL</Badge>);
      expect(screen.getByText('CRITICAL')).toHaveClass('text-rose-300');

      rerender(<Badge variant="success">RESOLVED</Badge>);
      expect(screen.getByText('RESOLVED')).toHaveClass('text-emerald-300');
    });
  });

  describe('Panel', () => {
    it('renders panel with title, badge, and content', () => {
      render(
        <Panel title="Surveillance Dock" badge={<Badge>Active</Badge>}>
          <div>Panel Inner Content</div>
        </Panel>
      );

      expect(screen.getByText('Surveillance Dock')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Panel Inner Content')).toBeInTheDocument();
    });
  });

  describe('StatusIndicator', () => {
    it('renders status indicator with accessible label', () => {
      render(<StatusIndicator status="online" label="Online Stream" />);
      const indicator = screen.getByRole('status');
      expect(indicator).toHaveAttribute('aria-label', 'Status: Online Stream');
      expect(screen.getByText('Online Stream')).toBeInTheDocument();
    });
  });

  describe('LoadingState', () => {
    it('renders loading state with accessible aria-live region', () => {
      render(<LoadingState message="Connecting to telemetry..." />);
      const loading = screen.getByRole('status');
      expect(loading).toHaveAttribute('aria-live', 'polite');
      expect(screen.getByText('Connecting to telemetry...')).toBeInTheDocument();
    });
  });

  describe('ErrorState', () => {
    it('renders sanitized error message with retry trigger', () => {
      const handleRetry = vi.fn();
      render(
        <ErrorState
          title="Network Failure"
          message="Server is unreachable"
          onRetry={handleRetry}
        />
      );

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Network Failure')).toBeInTheDocument();
      expect(screen.getByText('Server is unreachable')).toBeInTheDocument();

      const retryBtn = screen.getByRole('button', { name: /retry/i });
      fireEvent.click(retryBtn);
      expect(handleRetry).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyState', () => {
    it('renders empty state placeholder and custom message', () => {
      render(
        <EmptyState
          title="No Alerts"
          message="No active incidents recorded"
          action={<Button size="sm">Refresh</Button>}
        />
      );

      expect(screen.getByText('No Alerts')).toBeInTheDocument();
      expect(screen.getByText('No active incidents recorded')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
    });
  });
});
