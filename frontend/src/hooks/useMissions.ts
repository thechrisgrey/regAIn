import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { Mission, CompleteData, CompleteResponse, GenerateResponse } from '../types';

export function useMissions() {
  const { getToken } = useAuth();
  const [missions, setMissions] = useState<Mission[]>([]);
  const [dailyRemaining, setDailyRemaining] = useState<number | null>(null);
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMissions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.missions.list(token);
      setMissions(result.missions);
      setNextCursor(result.nextCursor);
      setDailyRemaining(result.dailyRemaining);
      setDailyLimit(result.dailyLimit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    setLoading(true);
    try {
      const token = await getToken();
      const result = await api.missions.list(token, 50, nextCursor);
      setMissions((prev) => [...prev, ...result.missions]);
      setNextCursor(result.nextCursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [getToken, nextCursor]);

  const completeMission = useCallback(
    async (missionId: string, data: CompleteData): Promise<CompleteResponse | null> => {
      setLoading(true);
      setError(null);

      // Optimistic update: immediately mark mission as completed.
      const previousMissions = missions;
      setMissions((prev) =>
        prev.map((m) =>
          m.missionId === missionId ? { ...m, status: 'completed' as const } : m,
        ),
      );

      try {
        const token = await getToken();
        const result = await api.missions.complete(missionId, data, token);
        return result;
      } catch (err) {
        // Rollback optimistic update on failure.
        setMissions(previousMissions);
        setError(err instanceof Error ? err.message : 'An error occurred');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [getToken, missions],
  );

  const generateMission = useCallback(async (): Promise<GenerateResponse | null> => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.missions.generate(token);

      // Engine may return an error dict (200 with {error: ...}) instead of a mission.
      if ('error' in result && !('mission' in result)) {
        setError((result as Record<string, string>).message || 'Could not generate a mission.');
        return null;
      }

      if (result.dailyRemaining !== undefined) setDailyRemaining(result.dailyRemaining);
      if (result.dailyLimit !== undefined) setDailyLimit(result.dailyLimit);

      // Re-fetch full mission list to stay in sync.
      const updated = await api.missions.list(token);
      setMissions(updated.missions);
      setDailyRemaining(updated.dailyRemaining);
      setDailyLimit(updated.dailyLimit);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      return null;
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  return {
    missions,
    dailyRemaining,
    dailyLimit,
    nextCursor,
    loading,
    error,
    fetchMissions,
    loadMore,
    completeMission,
    generateMission,
  };
}
