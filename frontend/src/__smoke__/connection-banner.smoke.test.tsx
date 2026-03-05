/**
 * Smoke: ConnectionBanner
 *
 * Verifies the network status banner:
 * - Returns null when online and not reconnecting
 * - Shows offline message when not online
 * - Shows reconnecting message when reconnecting
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ConnectionBanner from '../components/ConnectionBanner';

vi.mock('../hooks/useNetworkStatusHook', () => ({
  useNetworkStatus: vi.fn(() => ({ isOnline: true, isReconnecting: false })),
}));

import { useNetworkStatus } from '../hooks/useNetworkStatusHook';

const mockedUseNetworkStatus = vi.mocked(useNetworkStatus);

describe('Smoke: ConnectionBanner', () => {
  it('renders nothing when online and not reconnecting', () => {
    // Normal state: no banner should appear
    mockedUseNetworkStatus.mockReturnValue({
      isOnline: true,
      isReconnecting: false,
    });

    const { container } = render(<ConnectionBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('shows offline message when not online', () => {
    // Users must know they lost connectivity
    mockedUseNetworkStatus.mockReturnValue({
      isOnline: false,
      isReconnecting: false,
    });

    render(<ConnectionBanner />);
    expect(screen.getByText(/you are offline/i)).toBeTruthy();
  });

  it('shows reconnecting message when reconnecting', () => {
    // Users must know the app is trying to reconnect
    mockedUseNetworkStatus.mockReturnValue({
      isOnline: true,
      isReconnecting: true,
    });

    render(<ConnectionBanner />);
    expect(screen.getByText(/reconnecting/i)).toBeTruthy();
  });
});
