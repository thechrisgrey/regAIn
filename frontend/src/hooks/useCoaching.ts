import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { CoachingRequest } from '../types';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function useCoaching() {
  const { getToken } = useAuth();
  const [response, setResponse] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (message: string, sessionType: string) => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const data: CoachingRequest = {
          message,
          session_type: sessionType as CoachingRequest['session_type'],
        };
        const result = await api.coaching.checkin(data, token);

        setMessages((prev) => [
          ...prev,
          { role: 'user', content: message },
          { role: 'assistant', content: result.response },
        ]);
        setResponse(result.response);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  return { response, messages, loading, error, sendMessage };
}
