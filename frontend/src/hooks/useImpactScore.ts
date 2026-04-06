import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useOnMutation } from './useMutationBus';
import { api } from '../services/api';
import type { ScoreResponse } from '../types';

export function useImpactScore() {
  const { getToken } = useAuth();
  const [data, setData] = useState<ScoreResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchScore = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.score.get(token);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scorecard');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  // Auto-refresh when missions are completed or evidence is logged
  useOnMutation('mission:completed', () => void fetchScore());
  useOnMutation('evidence:logged', () => void fetchScore());

  return { data, loading, error, fetchScore };
}
