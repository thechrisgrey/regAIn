import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { OnetSearchResult, OnetCareerReport } from '../types';

export function useOnet() {
  const { getToken } = useAuth();
  const [results, setResults] = useState<OnetSearchResult[]>([]);
  const [careerDetail, setCareerDetail] = useState<OnetCareerReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchCareers = useCallback(async (keyword: string) => {
    setLoading(true);
    setError(null);
    setCareerDetail(null);
    try {
      const token = await getToken();
      const data = await api.onet.search(keyword, token);
      setResults(data.career ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const fetchCareerDetail = useCallback(async (socCode: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await api.onet.careerDetail(socCode, token);
      setCareerDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load career details');
    } finally {
      setDetailLoading(false);
    }
  }, [getToken]);

  const clearDetail = useCallback(() => {
    setCareerDetail(null);
  }, []);

  return {
    results,
    careerDetail,
    loading,
    detailLoading,
    error,
    searchCareers,
    fetchCareerDetail,
    clearDetail,
  };
}
