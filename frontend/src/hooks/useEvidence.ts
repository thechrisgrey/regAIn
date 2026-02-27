import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useOnMutation } from './useMutationBus';
import { api } from '../services/api';
import type { Evidence } from '../types';

export function useEvidence() {
  const { getToken } = useAuth();
  const [evidence, setEvidence] = useState<Evidence[]>([]);
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
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  useOnMutation('mission:completed', fetchEvidence);

  return { evidence, loading, error, fetchEvidence };
}
