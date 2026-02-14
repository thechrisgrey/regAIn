import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { DashboardResponse } from '../types';

export function useDashboard() {
  const { getToken } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.dashboard.get(token);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  return { data, loading, error, fetchDashboard };
}
