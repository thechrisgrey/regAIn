import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MutationBusProvider } from '../../hooks/MutationBusContext';
import { useMutationBus } from '../../hooks/useMutationBus';

describe('Page snapshot (MutationBus)', () => {
  it('returns null when no snapshot has been set', () => {
    const { result } = renderHook(() => useMutationBus(), {
      wrapper: MutationBusProvider,
    });

    expect(result.current.getPageSnapshot()).toBeNull();
  });

  it('stores and retrieves a snapshot', () => {
    const { result } = renderHook(() => useMutationBus(), {
      wrapper: MutationBusProvider,
    });

    act(() => {
      result.current.setPageSnapshot({ page: 'dashboard', activeMissions: 3 });
    });

    expect(result.current.getPageSnapshot()).toEqual({
      page: 'dashboard',
      activeMissions: 3,
    });
  });

  it('overwrites previous snapshot', () => {
    const { result } = renderHook(() => useMutationBus(), {
      wrapper: MutationBusProvider,
    });

    act(() => {
      result.current.setPageSnapshot({ page: 'missions', count: 5 });
    });

    act(() => {
      result.current.setPageSnapshot({ page: 'evidence', skills: ['Python'] });
    });

    expect(result.current.getPageSnapshot()).toEqual({
      page: 'evidence',
      skills: ['Python'],
    });
  });
});
