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
import type { ChatMessage, ToolStep, SearchTrace } from '../hooks/useCoaching';
import { useMutationBus } from '../hooks/useMutationBus';
import { MarkdownMessage, AgentActivityFeed } from './ui';

// ---------------------------------------------------------------------------
// Route -> page context mapping
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
  searchTrace,
}: {
  text: string;
  toolSteps: ToolStep[];
  thinking: boolean;
  streamHint: string | null;
  searchTrace: SearchTrace | null;
}) {
  const labeledSteps = toolSteps.map(s => ({
    ...s,
    label: TOOL_LABELS[s.tool] || s.tool,
  }));

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        <AgentActivityFeed steps={labeledSteps} visible={!text && thinking} />
        {searchTrace && searchTrace.sources.length > 0 && (
          <div className="mb-2 rounded-[var(--radius-button)] bg-surface-2 border border-neutral-200 px-3 py-2 text-[11px]">
            <p className="font-medium text-neutral-500 uppercase tracking-widest mb-1">
              Sources found for &ldquo;{searchTrace.query}&rdquo;
            </p>
            <ul className="space-y-0.5">
              {searchTrace.sources.map((s, i) => (
                <li key={i}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 underline underline-offset-2 hover:text-primary-700 break-all"
                  >
                    {s.title || s.url}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
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
// ChatPanel
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  visible: boolean;
}

export default function ChatPanel({ visible }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const proactiveCheckedRef = useRef(new Set<string>());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const location = useLocation();
  const {
    messages,
    streaming,
    streamingText,
    thinking,
    toolSteps,
    searchTrace,
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

  const { getPageSnapshot } = useMutationBus();
  const pageContext = getPageContext(location.pathname);

  const buildPrefix = useCallback(() => {
    const snapshot = getPageSnapshot();
    const parts = [`[page_context: ${pageContext}]`];
    if (snapshot) {
      parts.push(`[page_data: ${JSON.stringify(snapshot)}]`);
    }
    return parts.join(' ');
  }, [pageContext, getPageSnapshot]);

  const tokenPct = tokenBudget > 0 ? Math.round((tokenEstimate / tokenBudget) * 100) : 0;
  const tokenColor = tokenPct >= 90 ? 'var(--color-error-500)' : tokenPct >= 75 ? 'var(--color-warning-500)' : 'var(--color-success-500)';

  // Focus input when panel becomes visible
  useEffect(() => {
    if (visible) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [visible]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (visible) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingText, visible]);

  // Proactive check on page navigation (skipped in DnD)
  useEffect(() => {
    if (attentionMode === 'dnd') return;
    if (proactiveCheckedRef.current.has(pageContext)) return;
    if (streaming) return;

    const timer = setTimeout(() => {
      if (proactiveCheckedRef.current.has(pageContext)) return;
      proactiveCheckedRef.current.add(pageContext);
      void sendMessage(`${buildPrefix()} [proactive_check]`, 'general');
    }, 2000);

    return () => clearTimeout(timer);
  }, [pageContext, streaming, sendMessage, buildPrefix, attentionMode]);

  // Filter and clean messages for display
  const visibleMessages = messages
    .filter(m => !m.content.includes('[no_suggestion]'))
    .filter(m => !(m.role === 'assistant' && /^Action:\s/.test(m.content.trim())))
    .map(m => {
      if (m.role === 'user') {
        const cleaned = m.content
          .replace(/\[page_context:\s*\w+\]\s*/g, '')
          .replace(/\[page_data:\s*\{[^]*\}\]\s*/g, '')
          .replace(/\[proactive_check\]\s*/g, '')
          .trim();
        return { ...m, content: cleaned };
      }
      if (m.role === 'assistant') {
        const cleaned = m.content.replace(/\[\w+\]\s*/g, '').trim();
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

      const isFirstMessage = visibleMessages.length === 0;
      const sessionType = isFirstMessage ? 'checkin' : 'general';

      setInput('');
      await sendMessage(`${buildPrefix()} ${text}`, sessionType);
    },
    [input, streaming, visibleMessages.length, sendMessage, buildPrefix],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div
      className="flex h-screen flex-col overflow-hidden bg-surface-1"
    >
      {/* Toolbar — compact row with token budget, attention mode, clear */}
      <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => { if (tokenPct > 0) sendCompact(); }}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] hover:bg-neutral-100 transition-colors"
            title={`${tokenPct}% context used. Click to compact.`}
            disabled={tokenPct === 0}
          >
            <span style={{ color: tokenColor }} className="font-mono tabular-nums">{tokenPct}%</span>
          </button>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-[var(--radius-button)] border border-neutral-200 text-[10px]">
            {(['dnd', 'explore'] as const).map((mode) => (
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
                {mode === 'dnd' ? 'DnD' : 'Explore'}
              </button>
            ))}
          </div>
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
            searchTrace={searchTrace}
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
  );
}
