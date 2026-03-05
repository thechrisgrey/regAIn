/**
 * Smoke: GlobalErrorHandler
 *
 * Verifies the component mounts and listens for unhandled rejections.
 * It renders null (invisible) and shows toast on errors.
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ToastProvider } from '../components/ui';
import GlobalErrorHandler from '../components/GlobalErrorHandler';

describe('Smoke: GlobalErrorHandler', () => {
  it('renders without crashing (returns null)', () => {
    // The component should mount invisibly inside ToastProvider
    const { container } = render(
      <ToastProvider>
        <GlobalErrorHandler />
      </ToastProvider>,
    );

    // GlobalErrorHandler renders null, so the provider wrapper is the only child
    expect(container).toBeTruthy();
  });

  it('registers the unhandledrejection listener on mount', () => {
    // Confirms the error handler actually attaches to the window
    const addSpy = vi.spyOn(window, 'addEventListener');

    render(
      <ToastProvider>
        <GlobalErrorHandler />
      </ToastProvider>,
    );

    const calls = addSpy.mock.calls.filter(
      ([event]) => event === 'unhandledrejection',
    );
    expect(calls.length).toBeGreaterThanOrEqual(1);

    addSpy.mockRestore();
  });
});
