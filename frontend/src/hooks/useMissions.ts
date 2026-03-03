import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useSharedData } from './useSharedData';
import { api } from '../services/api';
import type { Mission, CompleteData, CompleteResponse, GenerateResponse } from '../types';

export function useMissions() {
  const { getToken } = useAuth();
  const { missions: shared, refreshMissions } = useSharedData();

  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Local missions override for optimistic updates and pagination appends
  const [localMissions, setLocalMissions] = useState<Mission[] | null>(null);
  const [localDailyRemaining, setLocalDailyRemaining] = useState<number | null>(null);
  const [localDailyLimit, setLocalDailyLimit] = useState<number | null>(null);

  const missions = localMissions ?? shared.data;
  const dailyRemaining = localDailyRemaining ?? shared.dailyRemaining;
  const dailyLimit = localDailyLimit ?? shared.dailyLimit;

  const fetchMissions = useCallback(async () => {
    setLocalMissions(null);
    setLocalDailyRemaining(null);
    setLocalDailyLimit(null);
    setActionError(null);
    await refreshMissions();
  }, [refreshMissions]);

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    setActionLoading(true);
    try {
      const token = await getToken();
      const result = await api.missions.list(token, 50, nextCursor);
      setLocalMissions((prev) => [...(prev ?? shared.data), ...result.missions]);
      setNextCursor(result.nextCursor);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setActionLoading(false);
    }
  }, [getToken, nextCursor, shared.data]);

  const completeMission = useCallback(
    async (missionId: string, data: CompleteData): Promise<CompleteResponse | null> => {
      setActionLoading(true);
      setActionError(null);

      // Optimistic update: immediately mark mission as completed.
      const previousMissions = localMissions ?? shared.data;
      setLocalMissions(
        previousMissions.map((m) =>
          m.missionId === missionId ? { ...m, status: 'completed' as const } : m,
        ),
      );

      try {
        const token = await getToken();
        const result = await api.missions.complete(missionId, data, token);
        return result;
      } catch (err) {
        // Rollback optimistic update on failure.
        setLocalMissions(previousMissions);
        setActionError(err instanceof Error ? err.message : 'An error occurred');
        return null;
      } finally {
        setActionLoading(false);
      }
    },
    [getToken, localMissions, shared.data],
  );

  const generateMission = useCallback(async (): Promise<GenerateResponse | null> => {
    setActionLoading(true);
    setActionError(null);
    try {
      const token = await getToken();
      const result = await api.missions.generate(token);

      // Engine may return an error dict (200 with {error: ...}) instead of a mission.
      if ('error' in result && !('mission' in result)) {
        setActionError((result as Record<string, string>).message || 'Could not generate a mission.');
        return null;
      }

      if (result.dailyRemaining !== undefined) setLocalDailyRemaining(result.dailyRemaining);
      if (result.dailyLimit !== undefined) setLocalDailyLimit(result.dailyLimit);

      // Re-fetch full mission list to stay in sync.
      const updated = await api.missions.list(token);
      setLocalMissions(updated.missions);
      setLocalDailyRemaining(updated.dailyRemaining);
      setLocalDailyLimit(updated.dailyLimit);
      return result;
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'An error occurred');
      return null;
    } finally {
      setActionLoading(false);
    }
  }, [getToken]);

  return {
    missions,
    dailyRemaining,
    dailyLimit,
    nextCursor,
    loading: shared.loading || actionLoading,
    error: shared.error || actionError,
    fetchMissions,
    loadMore,
    completeMission,
    generateMission,
  };
}
