/**
 * Smoke: Provider hierarchy
 *
 * Verifies that the core context providers (MutationBusProvider,
 * ToastProvider) mount correctly and their hooks return valid
 * context values. AuthProvider and DataProvider require deeper
 * mocking of Amplify/API, so they are tested indirectly via the
 * Layout and ProtectedRoute smoke tests.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MutationBusProvider } from '../hooks/MutationBusContext';
import { useMutationBus } from '../hooks/useMutationBus';
import { ToastProvider, useToast } from '../components/ui';

// -- MutationBus --

function MutationBusConsumer() {
  const { emit, subscribe } = useMutationBus();
  return (
    <div>
      <span data-testid="emit-type">{typeof emit}</span>
      <span data-testid="subscribe-type">{typeof subscribe}</span>
    </div>
  );
}

// -- Toast --

function ToastConsumer() {
  const { toast, dismiss } = useToast();
  return (
    <div>
      <span data-testid="toast-type">{typeof toast}</span>
      <span data-testid="dismiss-type">{typeof dismiss}</span>
    </div>
  );
}

describe('Smoke: MutationBusProvider', () => {
  it('mounts without crashing and provides emit + subscribe', () => {
    // Confirms the event bus context is accessible to children
    render(
      <MutationBusProvider>
        <MutationBusConsumer />
      </MutationBusProvider>,
    );

    expect(screen.getByTestId('emit-type').textContent).toBe('function');
    expect(screen.getByTestId('subscribe-type').textContent).toBe('function');
  });

  it('emit and subscribe round-trip works', () => {
    // Verifies the bus actually delivers events to subscribers
    const callback = vi.fn();
    let emitFn: ReturnType<typeof useMutationBus>['emit'];
    let subscribeFn: ReturnType<typeof useMutationBus>['subscribe'];

    function BusCapture() {
      const { emit, subscribe } = useMutationBus();
      emitFn = emit;
      subscribeFn = subscribe;
      return null;
    }

    render(
      <MutationBusProvider>
        <BusCapture />
      </MutationBusProvider>,
    );

    const unsub = subscribeFn!('mission:completed', callback);
    emitFn!({ type: 'mission:completed' });

    expect(callback).toHaveBeenCalledOnce();
    unsub();
  });
});

describe('Smoke: ToastProvider', () => {
  it('mounts without crashing and provides toast + dismiss', () => {
    // Confirms the toast context is accessible to children
    render(
      <ToastProvider>
        <ToastConsumer />
      </ToastProvider>,
    );

    expect(screen.getByTestId('toast-type').textContent).toBe('function');
    expect(screen.getByTestId('dismiss-type').textContent).toBe('function');
  });

  it('toast function returns a string id', () => {
    // Confirms toast() returns an id for later dismissal
    let toastFn: ReturnType<typeof useToast>['toast'];

    function ToastCapture() {
      const { toast } = useToast();
      toastFn = toast;
      return null;
    }

    render(
      <ToastProvider>
        <ToastCapture />
      </ToastProvider>,
    );

    let toastId: string = '';
    act(() => {
      toastId = toastFn!({ message: 'Smoke test toast' });
    });

    expect(typeof toastId).toBe('string');
    expect(toastId.length).toBeGreaterThan(0);
  });
});
