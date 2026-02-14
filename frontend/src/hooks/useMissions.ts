import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { Mission, CompleteData, CompleteResponse } from '../types';

export function useMissions() {
  const { getToken } = useAuth();
  const [missions, setMissions] = useState<Mission[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMissions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.missions.list(token);
      setMissions(result.missions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const completeMission = useCallback(
    async (missionId: string, data: CompleteData): Promise<CompleteResponse | null> => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const result = await api.missions.complete(missionId, data, token);
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  return { missions, loading, error, fetchMissions, completeMission };
}
