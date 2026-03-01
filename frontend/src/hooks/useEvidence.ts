import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useOnMutation } from './useMutationBus';
import { api } from '../services/api';
import type { Evidence } from '../types';

export function useEvidence() {
  const { getToken } = useAuth();
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = useCallback(
    async (skillTag?: string) => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const result = await api.evidence.list(token, skillTag);
        setEvidence(result.evidence);
        setNextCursor(result.nextCursor);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  const loadMore = useCallback(
    async (skillTag?: string) => {
      if (!nextCursor) return;
      setLoading(true);
      try {
        const token = await getToken();
        const result = await api.evidence.list(token, skillTag, 50, nextCursor);
        setEvidence((prev) => [...prev, ...result.evidence]);
        setNextCursor(result.nextCursor);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    },
    [getToken, nextCursor],
  );

  useOnMutation('mission:completed', fetchEvidence);

  return { evidence, nextCursor, loading, error, fetchEvidence, loadMore };
}
