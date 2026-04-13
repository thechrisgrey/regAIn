import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useCalendar } from '../../hooks/useCalendar';
import { requestCache } from '../../services/cache';

const mockEmit = vi.fn();
const mockGetToken = vi.fn().mockResolvedValue('mock-token');
const mockList = vi.fn().mockResolvedValue({ entries: [] });
const mockCreate = vi.fn().mockResolvedValue({ dateEntryId: '2026-04-12#abc' });
const mockUpdate = vi.fn().mockResolvedValue({ status: 'updated' });
const mockDelete = vi.fn().mockResolvedValue({ status: 'deleted' });
const mockHeatmap = vi.fn().mockResolvedValue({ heatmap: { '2026-04-10': 3 } });

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ getToken: mockGetToken }),
}));

vi.mock('../../services/api', () => ({
  api: {
    calendar: {
      list: (...args: unknown[]) => mockList(...args),
      create: (...args: unknown[]) => mockCreate(...args),
      update: (...args: unknown[]) => mockUpdate(...args),
      delete: (...args: unknown[]) => mockDelete(...args),
      heatmap: (...args: unknown[]) => mockHeatmap(...args),
    },
  },
}));

vi.mock('../../hooks/useMutationBus', () => ({
  useMutationBus: () => ({ emit: mockEmit }),
}));

describe('useCalendar', () => {
  beforeEach(() => {
    requestCache.clear();
    vi.clearAllMocks();
    mockList.mockResolvedValue({ entries: [] });
  });

  afterEach(() => {
    requestCache.clear();
  });

  it('fetches entries on mount', async () => {
    const { result } = renderHook(() => useCalendar('2026-04-01', '2026-04-30'));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.entries).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(mockList).toHaveBeenCalledWith('2026-04-01', '2026-04-30', 'mock-token');
  });

  it('creates an entry with optimistic update and emits event', async () => {
    const { result } = renderHook(() => useCalendar('2026-04-01', '2026-04-30'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.createEntry('2026-04-12', 'task', 'Test task');
    });

    expect(mockCreate).toHaveBeenCalledWith(
      { date: '2026-04-12', category: 'task', content: 'Test task' },
      'mock-token',
    );
    expect(mockEmit).toHaveBeenCalledWith({ type: 'calendar:updated' });
    // Entry should exist with the real ID after API resolves
    expect(result.current.entries.some((e) => e.dateEntryId === '2026-04-12#abc')).toBe(true);
  });

  it('deletes an entry and emits event', async () => {
    mockList.mockResolvedValue({
      entries: [
        {
          dateEntryId: '2026-04-12#abc',
          date: '2026-04-12',
          category: 'task',
          author: 'user',
          content: 'To delete',
          createdAt: '2026-04-12T00:00:00Z',
          updatedAt: '2026-04-12T00:00:00Z',
        },
      ],
    });
    const { result } = renderHook(() => useCalendar('2026-04-01', '2026-04-30'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entries).toHaveLength(1);

    await act(async () => {
      await result.current.deleteEntry('2026-04-12#abc');
    });

    expect(mockDelete).toHaveBeenCalledWith('2026-04-12#abc', 'mock-token');
    expect(mockEmit).toHaveBeenCalledWith({ type: 'calendar:updated' });
    expect(result.current.entries).toHaveLength(0);
  });

  it('fetches heatmap data', async () => {
    const { result } = renderHook(() => useCalendar('2026-04-01', '2026-04-30'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.fetchHeatmap('2026');
    });

    expect(mockHeatmap).toHaveBeenCalledWith('2026', 'mock-token');
    expect(result.current.heatmapData).toEqual({ '2026-04-10': 3 });
  });
});
