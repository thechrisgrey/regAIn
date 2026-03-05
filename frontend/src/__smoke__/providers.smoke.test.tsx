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
import { renderHook, act } from '@testing-library/react';
import { MutationBusProvider } from '../hooks/MutationBusContext';
import { useMutationBus } from '../hooks/useMutationBus';
import { ToastProvider, useToast } from '../components/ui';

describe('Smoke: MutationBusProvider', () => {
  it('mounts without crashing and provides emit + subscribe', () => {
    const { result } = renderHook(() => useMutationBus(), {
      wrapper: MutationBusProvider,
    });

    expect(typeof result.current.emit).toBe('function');
    expect(typeof result.current.subscribe).toBe('function');
  });

  it('emit and subscribe round-trip works', () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useMutationBus(), {
      wrapper: MutationBusProvider,
    });

    const unsub = result.current.subscribe('mission:completed', callback);
    result.current.emit({ type: 'mission:completed' });

    expect(callback).toHaveBeenCalledOnce();
    unsub();
  });
});

describe('Smoke: ToastProvider', () => {
  it('mounts without crashing and provides toast + dismiss', () => {
    const { result } = renderHook(() => useToast(), {
      wrapper: ToastProvider,
    });

    expect(typeof result.current.toast).toBe('function');
    expect(typeof result.current.dismiss).toBe('function');
  });

  it('toast function returns a string id', () => {
    const { result } = renderHook(() => useToast(), {
      wrapper: ToastProvider,
    });

    let toastId: string = '';
    act(() => {
      toastId = result.current.toast({ message: 'Smoke test toast' });
    });

    expect(typeof toastId).toBe('string');
    expect(toastId.length).toBeGreaterThan(0);
  });
});
