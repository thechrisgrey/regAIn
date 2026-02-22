import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api, ApiError } from '../services/api';
import type { ResumeResponse } from '../types/resume';

export function useResume() {
  const { getToken } = useAuth();
  const [resume, setResume] = useState<ResumeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchResume = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.resume.get(token);
      setResume(result);
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 404) {
        setResume(null);
      } else {
        setError(err instanceof Error ? err.message : 'An error occurred');
      }
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const regenerateResume = useCallback(async () => {
    setRegenerating(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.resume.generate(token);
      setResume(result);
    } catch (err) {
      if (err instanceof ApiError && err.statusCode === 429) {
        setError('Daily generation limit reached (3/day). Resume regenerates automatically on mission completion.');
      } else {
        setError(err instanceof Error ? err.message : 'An error occurred');
      }
    } finally {
      setRegenerating(false);
    }
  }, [getToken]);

  return { resume, loading, regenerating, error, fetchResume, regenerateResume };
}
