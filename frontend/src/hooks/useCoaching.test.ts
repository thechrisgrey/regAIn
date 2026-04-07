import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { useCoaching } from './useCoaching';
import { CoachingProvider } from './CoachingContext';
import { MutationBusProvider } from './MutationBusContext';

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

function wrapper({ children }: { children: ReactNode }) {
  return createElement(MutationBusProvider, null,
    createElement(CoachingProvider, null, children),
  );
}

describe('useCoaching', () => {
  it('throws when used outside CoachingProvider', () => {
    // Suppress console.error for the expected error boundary log.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useCoaching())).toThrow(
      'useCoaching must be used within CoachingProvider',
    );
    spy.mockRestore();
  });

  it('returns default context values when wrapped in CoachingProvider', () => {
    const { result } = renderHook(() => useCoaching(), { wrapper });

    expect(result.current.messages).toEqual([]);
    expect(result.current.streaming).toBe(false);
    expect(result.current.streamingText).toBe('');
    expect(result.current.thinking).toBe(false);
    expect(result.current.toolSteps).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.sendMessage).toBe('function');
    expect(typeof result.current.clearConversation).toBe('function');
  });
});
