import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { VoicePracticeSession, VoiceSessionDetailResponse } from '../types';

export function useVoiceSessions() {
  const { getToken } = useAuth();
  const [sessions, setSessions] = useState<VoicePracticeSession[]>([]);
  const [sessionDetail, setSessionDetail] = useState<VoiceSessionDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await api.voicePractice.listSessions(token);
      setSessions(data.sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const fetchSessionDetail = useCallback(async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const data = await api.voicePractice.getSession(sessionId, token);
      setSessionDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  return { sessions, sessionDetail, loading, error, fetchSessions, fetchSessionDetail };
}
