import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMissions } from './useMissions';
import { api } from '../services/api';

const mockRefreshMissions = vi.fn();

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    missions: {
      list: vi.fn(),
      complete: vi.fn(),
      generate: vi.fn(),
    },
  },
}));

vi.mock('./useSharedData', () => ({
  useSharedData: vi.fn(() => ({
    dashboard: { data: null, loading: false, error: null },
    missions: { data: [], loading: false, error: null, dailyRemaining: null, dailyLimit: null },
    evidence: { data: [], loading: false, error: null },
    refreshDashboard: vi.fn(),
    refreshMissions: mockRefreshMissions,
    refreshEvidence: vi.fn(),
  })),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMissions', () => {
  describe('initial state', () => {
    it('initializes with empty missions array', () => {
      const { result } = renderHook(() => useMissions());
      expect(result.current.missions).toEqual([]);
    });

    it('initializes with null dailyRemaining', () => {
      const { result } = renderHook(() => useMissions());
      expect(result.current.dailyRemaining).toBeNull();
    });

    it('initializes with no loading and no error', () => {
      const { result } = renderHook(() => useMissions());
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });

  describe('fetchMissions', () => {
    it('delegates to refreshMissions', async () => {
      const { result } = renderHook(() => useMissions());

      await act(async () => {
        await result.current.fetchMissions();
      });

      expect(mockRefreshMissions).toHaveBeenCalledTimes(1);
    });
  });

  describe('completeMission', () => {
    it('calls api with correct arguments', async () => {
      const mockResponse = { success: true, evidenceId: 'e1' };
      (api.missions.complete as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useMissions());

      const data = { reflection: 'Done well', skillTags: ['python'] };
      let response: unknown;
      await act(async () => {
        response = await result.current.completeMission('m1', data);
      });

      expect(api.missions.complete).toHaveBeenCalledWith('m1', data, 'mock-token');
      expect(response).toEqual(mockResponse);
    });

    it('returns null on failure', async () => {
      (api.missions.complete as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('Server error'),
      );

      const { result } = renderHook(() => useMissions());

      let response: unknown;
      await act(async () => {
        response = await result.current.completeMission('m1', { reflection: 'test', skillTags: [] });
      });

      expect(response).toBeNull();
      expect(result.current.error).toBe('Server error');
    });

    it('sets loading during operation', async () => {
      let resolveApi: (value: unknown) => void;
      (api.missions.complete as ReturnType<typeof vi.fn>).mockImplementation(
        () => new Promise((resolve) => { resolveApi = resolve; }),
      );

      const { result } = renderHook(() => useMissions());

      let completePromise: Promise<unknown>;
      await act(async () => {
        completePromise = result.current.completeMission('m1', { reflection: 'r', skillTags: [] });
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.loading).toBe(true);

      await act(async () => {
        resolveApi!({ success: true, evidenceId: 'e1' });
        await completePromise!;
      });

      expect(result.current.loading).toBe(false);
    });
  });

  describe('generateMission', () => {
    it('calls generate and re-fetches mission list', async () => {
      const newMission = { userId: 'u1', missionId: 'm2', campaignId: 'c1', title: 'New', description: 'New desc', status: 'pending' as const };
      (api.missions.generate as ReturnType<typeof vi.fn>).mockResolvedValue({
        mission: newMission,
        dailyRemaining: 4,
        dailyLimit: 6,
      });
      (api.missions.list as ReturnType<typeof vi.fn>).mockResolvedValue({
        missions: [newMission],
        dailyRemaining: 4,
        dailyLimit: 6,
      });

      const { result } = renderHook(() => useMissions());

      let response: unknown;
      await act(async () => {
        response = await result.current.generateMission();
      });

      expect(api.missions.generate).toHaveBeenCalledWith('mock-token');
      expect(api.missions.list).toHaveBeenCalledWith('mock-token');
      expect(response).toEqual(expect.objectContaining({ mission: newMission }));
      expect(result.current.missions).toEqual([newMission]);
    });

    it('handles engine error response (200 with error object)', async () => {
      (api.missions.generate as ReturnType<typeof vi.fn>).mockResolvedValue({
        error: 'rate_limit',
        message: 'Daily limit reached',
      });

      const { result } = renderHook(() => useMissions());

      let response: unknown;
      await act(async () => {
        response = await result.current.generateMission();
      });

      expect(response).toBeNull();
      expect(result.current.error).toBe('Daily limit reached');
    });

    it('updates dailyRemaining from generate response', async () => {
      const newMission = { userId: 'u1', missionId: 'm3', campaignId: 'c1', title: 'Gen', description: 'D', status: 'pending' as const };
      (api.missions.generate as ReturnType<typeof vi.fn>).mockResolvedValue({
        mission: newMission,
        dailyRemaining: 2,
        dailyLimit: 6,
      });
      (api.missions.list as ReturnType<typeof vi.fn>).mockResolvedValue({
        missions: [newMission],
        dailyRemaining: 2,
        dailyLimit: 6,
      });

      const { result } = renderHook(() => useMissions());

      await act(async () => {
        await result.current.generateMission();
      });

      expect(result.current.dailyRemaining).toBe(2);
    });

    it('returns null on network failure', async () => {
      (api.missions.generate as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('Network failure'),
      );

      const { result } = renderHook(() => useMissions());

      let response: unknown;
      await act(async () => {
        response = await result.current.generateMission();
      });

      expect(response).toBeNull();
      expect(result.current.error).toBe('Network failure');
    });

    it('sets loading during generation', async () => {
      let resolveApi: (value: unknown) => void;
      (api.missions.generate as ReturnType<typeof vi.fn>).mockImplementation(
        () => new Promise((resolve) => { resolveApi = resolve; }),
      );

      const { result } = renderHook(() => useMissions());

      let genPromise: Promise<unknown>;
      await act(async () => {
        genPromise = result.current.generateMission();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.loading).toBe(true);

      await act(async () => {
        resolveApi!({ error: 'rate_limit', message: 'Limit' });
        await genPromise!;
      });

      expect(result.current.loading).toBe(false);
    });
  });
});
