/**
 * Smoke: ErrorBoundary
 *
 * Verifies the ErrorBoundary component:
 * - Renders children normally when no error occurs
 * - Catches render errors and displays recovery UI
 */
import { type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from '../components/ErrorBoundary';

// Suppress console.error from React and ErrorBoundary during error tests
const originalConsoleError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});
afterEach(() => {
  console.error = originalConsoleError;
});

function GoodChild() {
  return <p>Everything is fine</p>;
}

function BadChild(): ReactNode {
  throw new Error('Test explosion');
}

describe('Smoke: ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    // Normal rendering should pass through without interference
    render(
      <ErrorBoundary>
        <GoodChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Everything is fine')).toBeTruthy();
  });

  it('catches errors and displays recovery UI', () => {
    // When a child throws, users should see a clear recovery message
    render(
      <ErrorBoundary>
        <BadChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(screen.getByText(/an unexpected error occurred/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /reload page/i })).toBeTruthy();
  });

  it('does not render children after catching an error', () => {
    // Confirms the error state replaces children entirely
    render(
      <ErrorBoundary>
        <BadChild />
      </ErrorBoundary>,
    );

    // The BadChild content should not be rendered
    expect(screen.queryByText('Test explosion')).toBeNull();
  });
});
