import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuth } from './useAuth';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface StreamEvent {
  type: 'delta' | 'done' | 'error' | 'thinking';
  text?: string;
  message?: string;
  tool?: string;
}

/** Human-readable labels for tool names sent by the backend. */
const TOOL_LABELS: Record<string, string> = {
  read_user_profile: 'Reviewing your profile',
  update_user_profile: 'Updating profile',
  get_campaign_status: 'Checking campaign status',
  create_campaign: 'Setting up campaign',
  get_current_mission: 'Looking up missions',
  generate_mission: 'Creating a mission',
  complete_mission: 'Completing mission',
  log_evidence: 'Recording evidence',
  get_evidence_summary: 'Analyzing evidence',
  get_market_insights: 'Researching market data',
  get_alignment: 'Evaluating alignment',
  recall_memory: 'Recalling conversation',
  store_memory: 'Saving notes',
};

const WS_URL = import.meta.env.VITE_CHAT_WS_URL as string | undefined;
const MAX_RECONNECT_DELAY = 16000;

/** Seconds of total silence before the frontend gives up. */
const STREAM_TIMEOUT_MS = 90_000;

export function useStreamingCoaching() {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [thinking, setThinking] = useState(false);
  const [thinkingLabel, setThinkingLabel] = useState('');
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const streamTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  /** Reset the safety timeout — called whenever we receive any message. */
  const resetStreamTimeout = useCallback(() => {
    clearTimeout(streamTimeoutRef.current);
    streamTimeoutRef.current = setTimeout(() => {
      setError('Response timed out. Please try again.');
      setStreaming(false);
      setStreamingText('');
      setThinking(false);
      setThinkingLabel('');
    }, STREAM_TIMEOUT_MS);
  }, []);

  const clearStreamTimeout = useCallback(() => {
    clearTimeout(streamTimeoutRef.current);
  }, []);

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
            setThinking(false);
            setThinkingLabel('');
            setStreamingText((prev) => prev + data.text);
            resetStreamTimeout();
          } else if (data.type === 'thinking') {
            setThinking(true);
            const label = (data.tool && TOOL_LABELS[data.tool]) || 'Thinking';
            setThinkingLabel(label);
            resetStreamTimeout();
          } else if (data.type === 'done') {
            const finalText = data.text || '';
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: finalText },
            ]);
            setStreamingText('');
            setStreaming(false);
            setThinking(false);
            setThinkingLabel('');
            clearStreamTimeout();
          } else if (data.type === 'error') {
            setError(data.message || 'An error occurred');
            setStreamingText('');
            setStreaming(false);
            setThinking(false);
            setThinkingLabel('');
            clearStreamTimeout();
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
  }, [getToken, resetStreamTimeout, clearStreamTimeout]);

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
      clearStreamTimeout();
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, clearStreamTimeout]);

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
      setThinking(false);
      setThinkingLabel('');
      resetStreamTimeout();

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
    [connect, getToken, resetStreamTimeout],
  );

  return { messages, streaming, streamingText, thinking, thinkingLabel, error, sendMessage };
}
