import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useOnMutation } from './useMutationBus';
import { api } from '../services/api';
import type { AnalyticsResponse } from '../types';

export function useAnalytics() {
  const { getToken } = useAuth();
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.analytics.get(token);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useOnMutation('mission:completed', fetchAnalytics);

  return { data, loading, error, fetchAnalytics };
}
