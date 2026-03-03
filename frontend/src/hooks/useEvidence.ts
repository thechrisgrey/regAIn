import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { useSharedData } from './useSharedData';
import { api } from '../services/api';
import type { Evidence } from '../types';

export function useEvidence() {
  const { getToken } = useAuth();
  const { evidence: shared, refreshEvidence } = useSharedData();

  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Local evidence override for filtered fetches and pagination appends
  const [localEvidence, setLocalEvidence] = useState<Evidence[] | null>(null);

  const evidence = localEvidence ?? shared.data;

  const fetchEvidence = useCallback(
    async (skillTag?: string) => {
      if (skillTag) {
        // Filtered fetch is local-only — shared context holds the unfiltered list.
        setActionLoading(true);
        setActionError(null);
        try {
          const token = await getToken();
          const result = await api.evidence.list(token, skillTag);
          setLocalEvidence(result.evidence);
          setNextCursor(result.nextCursor);
        } catch (err) {
          setActionError(err instanceof Error ? err.message : 'An error occurred');
        } finally {
          setActionLoading(false);
        }
      } else {
        setLocalEvidence(null);
        setActionError(null);
        await refreshEvidence();
      }
    },
    [getToken, refreshEvidence],
  );

  const loadMore = useCallback(
    async (skillTag?: string) => {
      if (!nextCursor) return;
      setActionLoading(true);
      try {
        const token = await getToken();
        const result = await api.evidence.list(token, skillTag, 50, nextCursor);
        setLocalEvidence((prev) => [...(prev ?? shared.data), ...result.evidence]);
        setNextCursor(result.nextCursor);
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setActionLoading(false);
      }
    },
    [getToken, nextCursor, shared.data],
  );

  return {
    evidence,
    nextCursor,
    loading: shared.loading || actionLoading,
    error: shared.error || actionError,
    fetchEvidence,
    loadMore,
  };
}
