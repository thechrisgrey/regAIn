import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDashboard } from './useDashboard';

const mockRefreshDashboard = vi.fn();

vi.mock('./useSharedData', () => ({
  useSharedData: vi.fn(() => ({
    dashboard: {
      data: null,
      loading: false,
      error: null,
    },
    missions: { data: [], loading: false, error: null, dailyRemaining: null, dailyLimit: null },
    evidence: { data: [], loading: false, error: null },
    refreshDashboard: mockRefreshDashboard,
    refreshMissions: vi.fn(),
    refreshEvidence: vi.fn(),
  })),
}));

import { useSharedData } from './useSharedData';

const mockedUseSharedData = vi.mocked(useSharedData);

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

    it('delegates data from shared context', () => {
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

      mockedUseSharedData.mockReturnValue({
        dashboard: { data: mockData, loading: false, error: null },
        missions: { data: [], loading: false, error: null, dailyRemaining: null, dailyLimit: null },
        evidence: { data: [], loading: false, error: null },
        refreshDashboard: mockRefreshDashboard,
        refreshMissions: vi.fn(),
        refreshEvidence: vi.fn(),
      });

      const { result } = renderHook(() => useDashboard());

      expect(result.current.data).toEqual(mockData);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('delegates error from shared context', () => {
      mockedUseSharedData.mockReturnValue({
        dashboard: { data: null, loading: false, error: 'API unavailable' },
        missions: { data: [], loading: false, error: null, dailyRemaining: null, dailyLimit: null },
        evidence: { data: [], loading: false, error: null },
        refreshDashboard: mockRefreshDashboard,
        refreshMissions: vi.fn(),
        refreshEvidence: vi.fn(),
      });

      const { result } = renderHook(() => useDashboard());

      expect(result.current.error).toBe('API unavailable');
      expect(result.current.loading).toBe(false);
    });

    it('delegates loading from shared context', () => {
      mockedUseSharedData.mockReturnValue({
        dashboard: { data: null, loading: true, error: null },
        missions: { data: [], loading: false, error: null, dailyRemaining: null, dailyLimit: null },
        evidence: { data: [], loading: false, error: null },
        refreshDashboard: mockRefreshDashboard,
        refreshMissions: vi.fn(),
        refreshEvidence: vi.fn(),
      });

      const { result } = renderHook(() => useDashboard());

      expect(result.current.loading).toBe(true);
    });

    it('fetchDashboard delegates to refreshDashboard', async () => {
      const { result } = renderHook(() => useDashboard());

      await act(async () => {
        await result.current.fetchDashboard();
      });

      expect(mockRefreshDashboard).toHaveBeenCalledTimes(1);
    });
  });
});
