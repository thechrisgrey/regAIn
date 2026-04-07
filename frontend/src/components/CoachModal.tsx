import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { useLocation } from 'react-router-dom';
import { useCoaching, TOOL_LABELS } from '../hooks/useCoaching';
import type { ChatMessage, ToolStep } from '../hooks/useCoaching';
import { MarkdownMessage, AgentActivityFeed } from './ui';

// ---------------------------------------------------------------------------
// Route → page context mapping
// ---------------------------------------------------------------------------

const ROUTE_CONTEXT: Record<string, string> = {
  '/dashboard': 'dashboard',
  '/missions': 'missions',
  '/evidence': 'evidence',
  '/scorecard': 'scorecard',
  '/analytics': 'analytics',
  '/resume': 'resume',
  '/onet': 'careers',
  '/profile': 'profile',
};

function getPageContext(pathname: string): string {
  return ROUTE_CONTEXT[pathname] || 'dashboard';
}

// ---------------------------------------------------------------------------
// Floating button
// ---------------------------------------------------------------------------

function CoachButton({
  onClick,
  hasNotification,
  pulsing,
}: {
  onClick: () => void;
  hasNotification: boolean;
  pulsing: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Open coach"
      className={`fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full shadow-elevated transition-all duration-300 hover:scale-105 hover:shadow-glow focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2 ${
        pulsing ? 'animate-voice-pulse' : ''
      }`}
      style={{
        background: 'linear-gradient(135deg, #916D65 0%, #7A5A52 100%)',
      }}
    >
      {/* Chat icon */}
      <svg
        className="h-6 w-6 text-white"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"
        />
      </svg>

      {/* Notification dot */}
      {hasNotification && (
        <span className="absolute -top-0.5 -right-0.5 flex h-3.5 w-3.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
          <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-accent-400" />
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-scale-in`}
    >
      <div
        className={`max-w-[85%] rounded-[var(--radius-card)] px-3.5 py-2.5 text-[13px] leading-relaxed ${
          isUser
            ? 'bg-primary-500 text-white'
            : 'bg-surface-3 text-neutral-800'
        }`}
      >
        {isUser ? (
          message.content
        ) : (
          <MarkdownMessage content={message.content} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Streaming indicator
// ---------------------------------------------------------------------------

function StreamingBubble({
  text,
  toolSteps,
  thinking,
  streamHint,
}: {
  text: string;
  toolSteps: ToolStep[];
  thinking: boolean;
  streamHint: string | null;
}) {
  const labeledSteps = toolSteps.map(s => ({
    ...s,
    label: TOOL_LABELS[s.tool] || s.tool,
  }));

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        <AgentActivityFeed steps={labeledSteps} visible={!text && thinking} />
        {text ? (
          <div className="rounded-[var(--radius-card)] bg-surface-3 px-3.5 py-2.5 text-[13px] leading-relaxed text-neutral-800">
            <MarkdownMessage content={text} />
            <span className="inline-block h-3.5 w-1.5 animate-pulse bg-primary-400 ml-0.5 rounded-sm" />
          </div>
        ) : !thinking ? (
          <div className="rounded-[var(--radius-card)] bg-surface-3 px-3.5 py-2.5">
            <div className="flex gap-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-neutral-400 animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          </div>
        ) : null}
        {streamHint && (
          <p className="mt-1 text-[10px] text-neutral-400">{streamHint}</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main CoachModal
// ---------------------------------------------------------------------------

export default function CoachModal() {
  const [open, setOpen] = useState(false);
  const [hasNotification, setHasNotification] = useState(false);
  const [pulsing, setPulsing] = useState(false);
  const [input, setInput] = useState('');

  const proactiveCheckedRef = useRef(new Set<string>());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messageCountRef = useRef(0);

  const location = useLocation();
  const {
    messages,
    streaming,
    streamingText,
    thinking,
    toolSteps,
    connectionStatus,
    streamHint,
    sendMessage,
    clearConversation,
    tokenEstimate,
    tokenBudget,
    attentionMode,
    changeAttentionMode,
    sendCompact,
  } = useCoaching();

  const pageContext = getPageContext(location.pathname);

  const tokenPct = tokenBudget > 0 ? Math.round((tokenEstimate / tokenBudget) * 100) : 0;
  const tokenColor = tokenPct >= 90 ? 'var(--color-error-500)' : tokenPct >= 75 ? 'var(--color-warning-500)' : 'var(--color-success-500)';

  // Lazy connect: mark as opened on first toggle
  const handleOpen = useCallback(() => {
    setOpen(true);
    setHasNotification(false);
    setPulsing(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  const handleClose = useCallback(() => {
    setOpen(false);
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    if (open) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingText, open]);

  // Detect new assistant messages when modal is closed → show notification
  // Uses setTimeout to avoid synchronous setState in effect (React 19 lint rule)
  useEffect(() => {
    if (!open && messages.length > messageCountRef.current) {
      const latest = messages[messages.length - 1];
      if (latest?.role === 'assistant' && !latest.content.includes('[no_suggestion]')) {
        const id = setTimeout(() => {
          setHasNotification(true);
          setPulsing(true);
          setTimeout(() => setPulsing(false), 3000);
        }, 0);
        messageCountRef.current = messages.length;
        return () => clearTimeout(id);
      }
    }
    messageCountRef.current = messages.length;
  }, [messages, open]);

  // Proactive check on page navigation
  useEffect(() => {
    if (proactiveCheckedRef.current.has(pageContext)) return;
    if (streaming) return; // don't interrupt active streaming

    // Delay to avoid firing during rapid navigation
    const timer = setTimeout(() => {
      if (proactiveCheckedRef.current.has(pageContext)) return;
      proactiveCheckedRef.current.add(pageContext);

      // Send proactive check via the existing WebSocket
      void sendMessage(
        `[page_context: ${pageContext}] [proactive_check]`,
        'general',
      );
    }, 2000);

    return () => clearTimeout(timer);
  }, [pageContext, streaming, sendMessage]);

  // Filter and clean messages for display
  const visibleMessages = messages
    .filter(m => !m.content.includes('[no_suggestion]'))
    .filter(m => !(m.role === 'assistant' && /^Action:\s/.test(m.content.trim())))
    .map(m => {
      if (m.role === 'user') {
        // Strip [page_context: ...] and [proactive_check] tags from display
        const cleaned = m.content
          .replace(/\[page_context:\s*\w+\]\s*/g, '')
          .replace(/\[proactive_check\]\s*/g, '')
          .trim();
        return { ...m, content: cleaned };
      }
      return m;
    })
    .filter(m => m.content.length > 0);

  // Send handler
  const handleSend = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const text = input.trim();
      if (!text || streaming) return;

      // Determine session type automatically
      const isFirstMessage = visibleMessages.length === 0;
      const sessionType = isFirstMessage ? 'checkin' : 'general';

      setInput('');
      await sendMessage(
        `[page_context: ${pageContext}] ${text}`,
        sessionType,
      );
    },
    [input, streaming, visibleMessages.length, sendMessage, pageContext],
  );

  // Enter to send, Shift+Enter for newline
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  // Escape to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, handleClose]);

  // Collapsed state
  if (!open) {
    return (
      <CoachButton
        onClick={handleOpen}
        hasNotification={hasNotification}
        pulsing={pulsing}
      />
    );
  }

  // Expanded panel
  return (
    <>
      {/* Floating button (still visible, acts as close) */}
      <CoachButton
        onClick={handleClose}
        hasNotification={false}
        pulsing={false}
      />

      {/* Panel */}
      <div
        className="fixed bottom-24 right-6 z-50 flex w-[400px] flex-col rounded-[var(--radius-card)] border border-neutral-100 bg-surface-1 shadow-elevated animate-scale-in"
        style={{ height: 'min(500px, 70vh)' }}
        role="dialog"
        aria-label="Coach"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <div
              className="h-2 w-2 rounded-full"
              style={{
                backgroundColor:
                  connectionStatus === 'connected'
                    ? 'var(--color-success-400)'
                    : connectionStatus === 'reconnecting'
                      ? 'var(--color-warning-400)'
                      : 'var(--color-neutral-300)',
              }}
            />
            {/* Token budget indicator */}
            <button
              type="button"
              onClick={() => { if (tokenPct > 0) sendCompact(); }}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] hover:bg-neutral-100 transition-colors"
              title={`${tokenPct}% context used. Click to compact.`}
              disabled={tokenPct === 0}
            >
              <span style={{ color: tokenColor }} className="font-mono tabular-nums">{tokenPct}%</span>
            </button>
            <span className="text-sm font-semibold text-neutral-900">
              Coach
            </span>
            <span className="text-[10px] text-neutral-400">Nova Pro</span>
          </div>
          <div className="flex items-center gap-2">
            {/* Attention mode toggle */}
            <div className="flex rounded-[var(--radius-button)] border border-neutral-200 text-[10px]">
              {(['dnd', 'focus', 'explore'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => changeAttentionMode(mode)}
                  className={`px-2 py-0.5 transition-colors first:rounded-l-[var(--radius-button)] last:rounded-r-[var(--radius-button)] ${
                    attentionMode === mode
                      ? 'bg-primary-500 text-white'
                      : 'text-neutral-500 hover:bg-neutral-100'
                  }`}
                >
                  {mode === 'dnd' ? 'DnD' : mode === 'focus' ? 'Focus' : 'Explore'}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1">
              {/* Clear conversation (subtle) */}
              <button
                type="button"
                onClick={clearConversation}
                className="rounded p-1 text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition-colors"
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M6.5 1h3a.5.5 0 01.5.5v1H6v-1a.5.5 0 01.5-.5zM11 2.5v-1A1.5 1.5 0 009.5 0h-3A1.5 1.5 0 005 1.5v1H1.5a.5.5 0 000 1h.538l.853 10.66A2 2 0 004.885 16h6.23a2 2 0 001.994-1.84l.853-10.66h.538a.5.5 0 000-1H11zm1.958 1l-.846 10.58a1 1 0 01-.997.92h-6.23a1 1 0 01-.997-.92L3.042 3.5h9.916z" />
                </svg>
              </button>
              {/* Close */}
              <button
                type="button"
                onClick={handleClose}
                className="rounded p-1 text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition-colors"
                aria-label="Close coach"
              >
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {visibleMessages.length === 0 && !streaming && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <p className="text-sm font-medium text-neutral-500">
                  Your coach is here
                </p>
                <p className="mt-1 text-xs text-neutral-400">
                  Ask anything about your career transition
                </p>
              </div>
            </div>
          )}

          {visibleMessages.map((msg, i) => (
            <MessageBubble key={`${msg.role}-${i}`} message={msg} />
          ))}

          {streaming && (
            <StreamingBubble
              text={streamingText}
              toolSteps={toolSteps}
              thinking={thinking}
              streamHint={streamHint}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Connection banner */}
        {connectionStatus === 'disconnected' && (
          <div className="border-t border-error-100 bg-error-50 px-4 py-1.5 text-center text-[11px] text-error-600">
            Disconnected. Reconnecting...
          </div>
        )}

        {/* Input */}
        <form
          onSubmit={handleSend}
          className="border-t border-neutral-100 px-3 py-2.5"
        >
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask your coach..."
              disabled={streaming || connectionStatus === 'disconnected'}
              className="flex-1 rounded-[var(--radius-button)] border border-neutral-200 bg-surface-2 px-3 py-2 text-[13px] text-neutral-900 placeholder:text-neutral-400 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300 disabled:opacity-50 transition-colors"
            />
            <button
              type="submit"
              disabled={!input.trim() || streaming}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-button)] bg-primary-500 text-white transition-colors hover:bg-primary-600 disabled:opacity-40 disabled:hover:bg-primary-500"
              aria-label="Send"
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
