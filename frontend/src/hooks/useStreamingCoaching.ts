import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuth } from './useAuth';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface StreamEvent {
  type: 'delta' | 'done' | 'error';
  text?: string;
  message?: string;
}

const WS_URL = import.meta.env.VITE_CHAT_WS_URL as string | undefined;
const MAX_RECONNECT_DELAY = 16000;

export function useStreamingCoaching() {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectRef = useRef<(() => Promise<void>) | undefined>(undefined);

  const connect = useCallback(async () => {
    if (!WS_URL) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const token = await getToken();
      const ws = new WebSocket(`${WS_URL}?token=${token}`);

      ws.onopen = () => {
        reconnectAttempt.current = 0;
        setError(null);
      };

      ws.onmessage = (evt) => {
        try {
          const data: StreamEvent = JSON.parse(evt.data);

          if (data.type === 'delta' && data.text) {
            setStreamingText((prev) => prev + data.text);
          } else if (data.type === 'done') {
            const finalText = data.text || '';
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: finalText },
            ]);
            setStreamingText('');
            setStreaming(false);
          } else if (data.type === 'error') {
            setError(data.message || 'An error occurred');
            setStreamingText('');
            setStreaming(false);
          }
        } catch {
          // Ignore non-JSON messages.
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        // Auto-reconnect with exponential backoff.
        const delay = Math.min(
          1000 * 2 ** reconnectAttempt.current,
          MAX_RECONNECT_DELAY,
        );
        reconnectAttempt.current += 1;
        reconnectTimer.current = setTimeout(() => {
          void connectRef.current?.();
        }, delay);
      };

      ws.onerror = () => {
        // onclose will fire after onerror, triggering reconnect.
      };

      wsRef.current = ws;
    } catch {
      setError('Failed to connect to coaching session');
    }
  }, [getToken]);

  // Keep connectRef in sync so the onclose handler always calls the latest version.
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Connect on mount — subscribes to the external WebSocket system.
  // setState calls within connect() execute in async event handlers, not synchronously.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const sendMessage = useCallback(
    async (message: string, sessionType: string) => {
      setError(null);

      // Ensure connection is open.
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        await connect();
        // Brief wait for the connection to establish.
        await new Promise((r) => setTimeout(r, 500));
      }

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setError('Connection not available. Retrying...');
        return;
      }

      // Add user message immediately.
      setMessages((prev) => [...prev, { role: 'user', content: message }]);
      setStreaming(true);
      setStreamingText('');

      const token = await getToken();
      wsRef.current.send(
        JSON.stringify({
          action: 'sendmessage',
          message,
          session_type: sessionType,
          token,
        }),
      );
    },
    [connect, getToken],
  );

  return { messages, streaming, streamingText, error, sendMessage };
}
