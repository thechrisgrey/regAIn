import {
  createContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from 'react';
import { useAuth } from './useAuth';
import { useAgentEventBridge } from './useAgentEventBridge';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ToolStep {
  tool: string;
  label: string;
  status: 'active' | 'done';
}

export interface SearchSource {
  title: string;
  url: string;
}

export interface SearchTrace {
  query: string;
  result_count: number;
  sources: SearchSource[];
  error?: string;
}

interface StreamEvent {
  type: 'delta' | 'done' | 'error' | 'thinking' | 'thinking_complete' | 'heartbeat' | 'auth_success' | 'proactive' | 'thread_meta' | 'debug' | 'search_trace';
  text?: string;
  message?: string;
  tool?: string;
  tokenEstimate?: number;
  tokenBudget?: number;
  attentionMode?: 'explore' | 'dnd';
  pendingMessages?: Array<{ type: string; text: string }>;
  query?: string;
  result_count?: number;
  sources?: SearchSource[];
  error?: string;
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
  compact_thread: 'Compacting conversation',
  web_search: 'Searching the web',
  read_calendar: 'Checking your calendar',
  write_calendar_entry: 'Updating your calendar',
  onet_search_careers: 'Searching O*NET careers',
  onet_career_detail: 'Reading O*NET career detail',
  generate_resume: 'Drafting resume',
  get_resume: 'Loading resume',
};

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export interface CoachingContextType {
  messages: ChatMessage[];
  streaming: boolean;
  streamingText: string;
  thinking: boolean;
  toolSteps: ToolStep[];
  searchTrace: SearchTrace | null;
  error: string | null;
  connectionStatus: ConnectionStatus;
  streamHint: string | null;
  sendMessage: (message: string, sessionType: string) => Promise<boolean>;
  clearConversation: () => void;
  setSessionType: (st: string) => void;
  tokenEstimate: number;
  tokenBudget: number;
  attentionMode: 'explore' | 'dnd';
  sendActionEvent: (action: string, payload: Record<string, unknown>) => void;
  sendCompact: () => Promise<void>;
  changeAttentionMode: (mode: 'explore' | 'dnd') => Promise<void>;
}

const WS_URL = import.meta.env.VITE_CHAT_WS_URL as string | undefined;
const MAX_RECONNECT_DELAY = 16000;
const MAX_RECONNECT_ATTEMPTS = 5;
const STREAM_TIMEOUT_MS = 90_000;
const INTERMEDIATE_TIMEOUT_MS = 45_000;
const SESSION_STORAGE_KEY = 'regain-coaching-messages';
const MAX_PERSISTED_MESSAGES = 100;

function loadPersistedMessages(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatMessage[];
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(-MAX_PERSISTED_MESSAGES);
  } catch {
    return [];
  }
}

function persistMessages(messages: ChatMessage[]) {
  try {
    sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify(messages.slice(-MAX_PERSISTED_MESSAGES)),
    );
  } catch {
    // Storage full or unavailable — ignore.
  }
}

const CoachingContext = createContext<CoachingContextType | undefined>(undefined);

export { CoachingContext };

export function CoachingProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>(loadPersistedMessages);
  const [streaming, setStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [toolSteps, setToolSteps] = useState<ToolStep[]>([]);
  const [searchTrace, setSearchTrace] = useState<SearchTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(
    WS_URL ? 'reconnecting' : 'disconnected',
  );
  const [streamHint, setStreamHint] = useState<string | null>(null);
  const [tokenEstimate, setTokenEstimate] = useState(0);
  const [tokenBudget, setTokenBudget] = useState(27_000);
  const [attentionMode, setAttentionMode] = useState<'explore' | 'dnd'>('explore');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const streamTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const intermediateTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const hasStepsRef = useRef(false);
  const deltaBufferRef = useRef('');
  const rafIdRef = useRef<number | undefined>(undefined);

  // Stable ref to getToken — ensures reconnection always uses fresh token
  // after 55-min Cognito refresh (Part C: stale closure fix).
  const getTokenRef = useRef(getToken);

  // Tracks the last user message that failed due to stream error or disconnect
  // so it can be auto-resent on reconnect.
  const lastFailedMessageRef = useRef<{ message: string; sessionType: string } | null>(null);
  const activeMessageRef = useRef<{ message: string; sessionType: string } | null>(null);
  const sendMessageRef = useRef<((message: string, sessionType: string) => Promise<boolean>) | undefined>(undefined);

  // Resolve/reject for the connect() promise — settled by auth_success / onclose.
  const connectResolveRef = useRef<{ resolve: () => void; reject: (e: Error) => void } | null>(null);

  // Proactive greeting: prevent double-sends on reconnect and track session type.
  const greetingSentRef = useRef(false);
  const sessionTypeRef = useRef('checkin');

  // Persist messages to sessionStorage whenever they change.
  useEffect(() => {
    persistMessages(messages);
  }, [messages]);

  // Keep getTokenRef in sync so reconnection always uses a fresh token.
  useEffect(() => {
    getTokenRef.current = getToken;
  }, [getToken]);

  const thinking = toolSteps.some(s => s.status === 'active');

  const clearToolSteps = useCallback(() => {
    setToolSteps([]);
    setSearchTrace(null);
    hasStepsRef.current = false;
    clearTimeout(fadeTimerRef.current);
    fadeTimerRef.current = undefined;
  }, []);

  const flushDeltaBuffer = useCallback(() => {
    rafIdRef.current = undefined;
    const buffered = deltaBufferRef.current;
    if (buffered) {
      deltaBufferRef.current = '';
      setStreamingText((prev) => prev + buffered);
    }
  }, []);

  const cancelAndFlushBuffer = useCallback(() => {
    if (rafIdRef.current !== undefined) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = undefined;
    }
    deltaBufferRef.current = '';
  }, []);

  const resetStreamTimeout = useCallback(() => {
    clearTimeout(streamTimeoutRef.current);
    clearTimeout(intermediateTimeoutRef.current);
    streamTimeoutRef.current = setTimeout(() => {
      setError('Response timed out. Please try again.');
      if (activeMessageRef.current) {
        lastFailedMessageRef.current = activeMessageRef.current;
        activeMessageRef.current = null;
      }
      setStreaming(false);
      setStreamingText('');
      setStreamHint(null);
      clearToolSteps();
    }, STREAM_TIMEOUT_MS);
    intermediateTimeoutRef.current = setTimeout(() => {
      setStreamHint('Still working on it...');
    }, INTERMEDIATE_TIMEOUT_MS);
  }, [clearToolSteps]);

  const clearStreamTimeout = useCallback(() => {
    clearTimeout(streamTimeoutRef.current);
    clearTimeout(intermediateTimeoutRef.current);
    setStreamHint(null);
  }, []);

  const connect = useCallback((): Promise<void> => {
    if (!WS_URL) return Promise.resolve();
    if (wsRef.current?.readyState === WebSocket.OPEN) return Promise.resolve();

    return new Promise<void>((resolve, reject) => {
      connectResolveRef.current = { resolve, reject };

      // Timeout fallback — reject if auth_success never arrives.
      const authTimeout = setTimeout(() => {
        connectResolveRef.current = null;
        reject(new Error('Auth timeout'));
      }, 10_000);

      const settleConnect = (settler: 'resolve' | 'reject', err?: Error) => {
        clearTimeout(authTimeout);
        const ref = connectResolveRef.current;
        connectResolveRef.current = null;
        if (!ref) return;
        if (settler === 'resolve') ref.resolve();
        else ref.reject(err || new Error('Connection failed'));
      };

      void (async () => {
    try {
      // Use getTokenRef to avoid stale closure over getToken (Part C).
      const token = await getTokenRef.current();
      // Connect without token in URL — send auth as first message (Part A).
      const ws = new WebSocket(WS_URL);

      ws.onopen = async () => {
        // Send auth as first WebSocket message instead of query param.
        ws.send(JSON.stringify({ type: 'auth', token }));
      };

      ws.onmessage = (evt) => {
        try {
          const data: StreamEvent = JSON.parse(evt.data);

          // Handle auth success — connection is now authenticated.
          if (data.type === 'auth_success') {
            reconnectAttempt.current = 0;
            setConnectionStatus('connected');
            setError(null);
            settleConnect('resolve');

            // Sync thread state on reconnect.
            ws.send(JSON.stringify({ type: 'sync' }));

            // Auto-resend the last failed message on reconnect.
            const failed = lastFailedMessageRef.current;
            if (failed) {
              lastFailedMessageRef.current = null;
              setTimeout(() => {
                void sendMessageRef.current?.(failed.message, failed.sessionType);
              }, 0);
            } else if (!greetingSentRef.current && loadPersistedMessages().length === 0) {
              // First connection with no prior messages — trigger proactive greeting.
              greetingSentRef.current = true;
              setTimeout(() => {
                void sendMessageRef.current?.('[greeting_request]', sessionTypeRef.current);
              }, 0);
            }
            return;
          }

          // Handle heartbeat — reset stream timeout to keep connection alive (Part D).
          if (data.type === 'heartbeat') {
            resetStreamTimeout();
            return;
          }

          if (data.type === 'debug') {
            // eslint-disable-next-line no-console
            console.log('[REGAIN debug]', data);
            return;
          }

          if (data.type === 'proactive') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: data.text || '' },
            ]);
            return;
          }

          if (data.type === 'thread_meta') {
            if (data.tokenEstimate !== undefined) setTokenEstimate(data.tokenEstimate);
            if (data.tokenBudget !== undefined) setTokenBudget(data.tokenBudget);
            if (data.attentionMode) setAttentionMode(data.attentionMode);
            if (data.pendingMessages?.length) {
              for (const msg of data.pendingMessages) {
                setMessages((prev) => [...prev, { role: 'assistant', content: msg.text }]);
              }
            }
            return;
          }

          if (data.type === 'delta' && data.text) {
            setStreamHint(null);
            clearTimeout(intermediateTimeoutRef.current);
            if (hasStepsRef.current && !fadeTimerRef.current) {
              hasStepsRef.current = false;
              setToolSteps(prev =>
                prev.map(s => s.status === 'active' ? { ...s, status: 'done' as const } : s),
              );
              fadeTimerRef.current = setTimeout(() => {
                setToolSteps([]);
                fadeTimerRef.current = undefined;
              }, 600);
            }
            deltaBufferRef.current += data.text;
            if (rafIdRef.current === undefined) {
              rafIdRef.current = requestAnimationFrame(flushDeltaBuffer);
            }
            resetStreamTimeout();
          } else if (data.type === 'thinking') {
            const toolName = data.tool || '';
            const label = TOOL_LABELS[toolName] || 'Thinking';
            setToolSteps(prev => [...prev, { tool: toolName, label, status: 'active' }]);
            hasStepsRef.current = true;
            resetStreamTimeout();
          } else if (data.type === 'thinking_complete') {
            const toolName = data.tool || '';
            setToolSteps(prev => {
              const idx = prev.findIndex(s => s.tool === toolName && s.status === 'active');
              if (idx === -1) return prev;
              const next = [...prev];
              next[idx] = { ...next[idx], status: 'done' };
              return next;
            });
            resetStreamTimeout();
          } else if (data.type === 'search_trace') {
            setSearchTrace({
              query: data.query || '',
              result_count: data.result_count || 0,
              sources: data.sources || [],
              error: data.error,
            });
          } else if (data.type === 'done') {
            cancelAndFlushBuffer();
            const finalText = data.text || '';
            activeMessageRef.current = null;
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: finalText },
            ]);
            setStreamingText('');
            setStreaming(false);
            clearToolSteps();
            clearStreamTimeout();
          } else if (data.type === 'error') {
            cancelAndFlushBuffer();
            setError(data.message || 'An error occurred');
            if (activeMessageRef.current) {
              lastFailedMessageRef.current = activeMessageRef.current;
              activeMessageRef.current = null;
            }
            setStreamingText('');
            setStreaming(false);
            clearToolSteps();
            clearStreamTimeout();
          }
        } catch {
          // Ignore non-JSON messages.
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        settleConnect('reject', new Error('Connection closed'));
        // If we were streaming when the connection dropped, save the
        // active message for auto-resend on reconnect.
        if (activeMessageRef.current) {
          cancelAndFlushBuffer();
          lastFailedMessageRef.current = activeMessageRef.current;
          activeMessageRef.current = null;
          setStreamingText('');
          setStreaming(false);
          clearToolSteps();
          clearStreamTimeout();
        }
        if (reconnectAttempt.current >= MAX_RECONNECT_ATTEMPTS) {
          setConnectionStatus('disconnected');
          return;
        }
        setConnectionStatus('reconnecting');
        const delay = Math.min(
          1000 * 2 ** reconnectAttempt.current,
          MAX_RECONNECT_DELAY,
        );
        reconnectAttempt.current += 1;
        reconnectTimer.current = setTimeout(() => {
          connectRef.current?.().catch(() => {});
        }, delay);
      };

      ws.onerror = () => {
        // onclose will fire after onerror, triggering reconnect.
      };

      wsRef.current = ws;
    } catch (err) {
      settleConnect('reject', err instanceof Error ? err : new Error('Connection failed'));
      setError('Failed to connect to coaching session');
    }
      })();
    });
  }, [resetStreamTimeout, clearStreamTimeout, clearToolSteps, flushDeltaBuffer, cancelAndFlushBuffer]);

  // Keep connectRef in sync so the onclose handler always calls the latest version.
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // Connect on mount — subscribes to the external WebSocket system.
  // setState calls within connect() execute in async event handlers, not synchronously.
  useEffect(() => {
    connect().catch(() => {});
    return () => {
      clearTimeout(reconnectTimer.current);
      clearStreamTimeout();
      cancelAndFlushBuffer();
      clearTimeout(fadeTimerRef.current);
      clearTimeout(intermediateTimeoutRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, clearStreamTimeout, cancelAndFlushBuffer]);

  const sendMessage = useCallback(
    async (message: string, sessionType: string): Promise<boolean> => {
      setError(null);

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        try {
          await connect();
        } catch {
          setError('Connection not available. Retrying...');
          return false;
        }
      }

      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        setError('Connection not available. Retrying...');
        return false;
      }

      // Skip user bubble for internal greeting requests.
      if (!message.startsWith('[greeting_request]')) {
        setMessages((prev) => [...prev, { role: 'user', content: message }]);
      }
      cancelAndFlushBuffer();
      setStreaming(true);
      setStreamingText('');
      setStreamHint(null);
      clearToolSteps();
      resetStreamTimeout();
      activeMessageRef.current = { message, sessionType };

      const token = await getTokenRef.current();
      wsRef.current.send(
        JSON.stringify({
          action: 'sendmessage',
          message,
          session_type: sessionType,
          token,
        }),
      );
      return true;
    },
    [connect, resetStreamTimeout, clearToolSteps, cancelAndFlushBuffer],
  );

  // Keep sendMessageRef in sync so the onopen auto-resend uses the latest version.
  useEffect(() => {
    sendMessageRef.current = sendMessage;
  }, [sendMessage]);

  const clearConversation = useCallback(() => {
    cancelAndFlushBuffer();
    setMessages([]);
    setStreamingText('');
    setError(null);
    clearToolSteps();
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    // Prevent re-greeting after manual clear.
    greetingSentRef.current = true;
  }, [clearToolSteps, cancelAndFlushBuffer]);

  const setSessionType = useCallback((st: string) => {
    sessionTypeRef.current = st;
  }, []);

  const sendActionEvent = useCallback((action: string, payload: Record<string, unknown>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    getTokenRef.current().then(token => {
      wsRef.current?.send(JSON.stringify({ type: 'action_event', action, payload, token }));
    });
  }, []);

  const sendCompact = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    const token = await getTokenRef.current();
    wsRef.current.send(JSON.stringify({ type: 'compact', token }));
  }, []);

  const changeAttentionMode = useCallback(async (mode: 'explore' | 'dnd') => {
    setAttentionMode(mode);
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'attention_mode', mode }));
  }, []);

  const sendWsRaw = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // Stable wrapper that defers ref access to call time (not render time),
  // satisfying the react-hooks/refs lint rule.
  const getTokenStable = useCallback(() => getTokenRef.current(), []);

  useAgentEventBridge(
    connectionStatus === 'connected' ? sendWsRaw : null,
    getTokenStable,
  );

  return (
    <CoachingContext.Provider
      value={{
        messages,
        streaming,
        streamingText,
        thinking,
        toolSteps,
        searchTrace,
        error,
        connectionStatus,
        streamHint,
        sendMessage,
        clearConversation,
        setSessionType,
        tokenEstimate,
        tokenBudget,
        attentionMode,
        sendActionEvent,
        sendCompact,
        changeAttentionMode,
      }}
    >
      {children}
    </CoachingContext.Provider>
  );
}
