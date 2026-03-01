import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDashboard } from './useDashboard';
import { api } from '../services/api';
import { useOnMutation } from './useMutationBus';

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    dashboard: {
      get: vi.fn(),
    },
  },
}));

vi.mock('./useMutationBus', () => ({
  useOnMutation: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDashboard', () => {
  describe('fetchDashboard', () => {
    it('initializes with null data, no loading, no error', () => {
      const { result } = renderHook(() => useDashboard());

      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('fetches and populates data on success', async () => {
      const mockData = {
        campaign: {
          userId: 'u1',
          campaignId: 'c1',
          title: 'Test Campaign',
          phase: 'foundation' as const,
          status: 'active' as const,
          startDate: '2025-01-01',
          targetRole: 'Engineer',
          skillsFocus: ['python'],
        },
        stats: {
          missionsCompleted: 5,
          evidenceCount: 3,
          currentPhase: 'foundation' as const,
        },
      };
      (api.dashboard.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);

      const { result } = renderHook(() => useDashboard());

      await act(async () => {
        await result.current.fetchDashboard();
      });

      expect(result.current.data).toEqual(mockData);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('handles Error objects', async () => {
      (api.dashboard.get as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('API unavailable'),
      );

      const { result } = renderHook(() => useDashboard());

      await act(async () => {
        await result.current.fetchDashboard();
      });

      expect(result.current.error).toBe('API unavailable');
      expect(result.current.loading).toBe(false);
    });

    it('handles non-Error thrown values', async () => {
      (api.dashboard.get as ReturnType<typeof vi.fn>).mockRejectedValue('string error');

      const { result } = renderHook(() => useDashboard());

      await act(async () => {
        await result.current.fetchDashboard();
      });

      expect(result.current.error).toBe('An error occurred');
    });

    it('sets loading during fetch', async () => {
      let resolveApi: (value: unknown) => void;
      (api.dashboard.get as ReturnType<typeof vi.fn>).mockImplementation(
        () => new Promise((resolve) => { resolveApi = resolve; }),
      );

      const { result } = renderHook(() => useDashboard());

      let fetchPromise: Promise<void>;
      await act(async () => {
        fetchPromise = result.current.fetchDashboard();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.loading).toBe(true);

      await act(async () => {
        resolveApi!({ campaign: {}, stats: {} });
        await fetchPromise!;
      });

      expect(result.current.loading).toBe(false);
    });
  });

  describe('mutation bus integration', () => {
    it('registers mission:completed listener', () => {
      renderHook(() => useDashboard());

      expect(useOnMutation).toHaveBeenCalledWith(
        'mission:completed',
        expect.any(Function),
      );
    });

    it('callback triggers fetchDashboard', async () => {
      const mockData = {
        campaign: {
          userId: 'u1',
          campaignId: 'c1',
          title: 'Test',
          phase: 'foundation' as const,
          status: 'active' as const,
          startDate: '2025-01-01',
          targetRole: 'Engineer',
          skillsFocus: [],
        },
        stats: { missionsCompleted: 1, evidenceCount: 0, currentPhase: 'foundation' as const },
      };
      (api.dashboard.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockData);

      renderHook(() => useDashboard());

      // Extract the callback registered with useOnMutation
      const registeredCallback = (useOnMutation as ReturnType<typeof vi.fn>).mock.calls[0][1] as () => void;

      await act(async () => {
        registeredCallback();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(api.dashboard.get).toHaveBeenCalledWith('mock-token');
    });

    it('re-fetches dashboard data when mutation fires', async () => {
      const initialData = {
        campaign: {
          userId: 'u1', campaignId: 'c1', title: 'Init', phase: 'foundation' as const,
          status: 'active' as const, startDate: '2025-01-01', targetRole: 'Eng', skillsFocus: [],
        },
        stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: 'foundation' as const },
      };
      const updatedData = {
        ...initialData,
        stats: { missionsCompleted: 1, evidenceCount: 1, currentPhase: 'foundation' as const },
      };

      (api.dashboard.get as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce(initialData)
        .mockResolvedValueOnce(updatedData);

      const { result } = renderHook(() => useDashboard());

      // Initial fetch
      await act(async () => {
        await result.current.fetchDashboard();
      });
      expect(result.current.data).toEqual(initialData);

      // Mutation triggers re-fetch
      const registeredCallback = (useOnMutation as ReturnType<typeof vi.fn>).mock.calls[0][1] as () => void;
      await act(async () => {
        registeredCallback();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(api.dashboard.get).toHaveBeenCalledTimes(2);
    });
  });
});
