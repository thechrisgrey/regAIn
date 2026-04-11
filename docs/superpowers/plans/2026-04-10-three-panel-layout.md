# Three-Panel Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the floating CoachModal + wide sidebar with a three-panel CSS grid layout (narrow icon sidebar | page content | persistent chat panel) to make the coaching chat a first-class UI citizen.

**Architecture:** Extract sidebar nav into `Sidebar.tsx`, extract chat UI into `ChatPanel.tsx`, create a `DrawerHandle.tsx` toggle, rewrite `Layout.tsx` as a CSS grid that composes these three panels. Voice practice routes bypass the grid and render full-screen. Mobile layout unchanged.

**Tech Stack:** React 19, Tailwind v4 (`@theme` tokens in `index.css`), React Router v7, existing `CoachingContext` (unchanged).

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/components/Sidebar.tsx` | Narrow icon+label nav column |
| Create | `frontend/src/components/ChatPanel.tsx` | Grid-embedded coaching chat |
| Create | `frontend/src/components/DrawerHandle.tsx` | Toggle strip between content and chat |
| Modify | `frontend/src/components/Layout.tsx` | CSS grid composition, voice route detection, chat toggle state |
| Modify | `frontend/src/App.tsx:55` | Remove coaching route redirect |
| Modify | `frontend/src/index.css:27-139` | Add layout CSS tokens |
| Modify | `frontend/src/__tests__/components/CoachModalSnapshot.test.tsx` | Rename to ChatPanel tests |
| Delete | `frontend/src/components/CoachModal.tsx` | Replaced by ChatPanel |
| Delete | `frontend/src/pages/CoachingPage.tsx` | No longer needed |

---

### Task 1: Add CSS tokens for the three-panel grid

**Files:**
- Modify: `frontend/src/index.css:116-119` (after `--radius-badge`)

- [ ] **Step 1: Add layout tokens to `@theme` block**

In `frontend/src/index.css`, add these tokens after the `/* Radii */` section (after line 119, before `/* Animations */`):

```css
  /* Layout — three-panel grid */
  --nav-w: clamp(64px, 10vw, 88px);
  --chat-w-open: 40vw;
  --chat-w-closed: 0px;
```

- [ ] **Step 2: Verify the dev server picks up the tokens**

Run: `cd frontend && npm run dev`

Open the browser, inspect `<html>`, confirm the three custom properties appear in computed styles. No visual changes yet.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat: add CSS tokens for three-panel layout grid"
```

---

### Task 2: Create DrawerHandle component

**Files:**
- Create: `frontend/src/components/DrawerHandle.tsx`

- [ ] **Step 1: Write the DrawerHandle component**

Create `frontend/src/components/DrawerHandle.tsx`:

```tsx
interface DrawerHandleProps {
  open: boolean;
  onToggle: () => void;
}

export default function DrawerHandle({ open, onToggle }: DrawerHandleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={open ? 'Close chat panel' : 'Open chat panel'}
      className="flex w-[3px] cursor-pointer items-center justify-center bg-neutral-200 transition-colors hover:bg-neutral-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
    >
      <span className="h-[30px] w-[3px] rounded-full bg-accent-400 opacity-60 transition-opacity group-hover:opacity-100 hover:opacity-100" />
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/DrawerHandle.tsx
git commit -m "feat: add DrawerHandle toggle component"
```

---

### Task 3: Create Sidebar component

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/ui/NavIcon.tsx` (no changes to the component itself, just confirming it's reused)

- [ ] **Step 1: Write the Sidebar component**

Create `frontend/src/components/Sidebar.tsx`. This extracts the nav structure from `Layout.tsx` but renders it in the narrow icon+label stacked format:

```tsx
import { NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { cachedGet } from '../services/api';
import NavIcon from './ui/NavIcon';
import { useCallback } from 'react';

const navItems = [
  { to: '/dashboard', label: 'Home', icon: 'dashboard' },
  { to: '/missions', label: 'Missions', icon: 'missions' },
  { to: '/evidence', label: 'Evidence', icon: 'evidence' },
  { to: '/voice-practice', label: 'Voice', icon: 'voice-practice' },
  { to: '/scorecard', label: 'Score', icon: 'scorecard' },
  { to: '/analytics', label: 'Analytics', icon: 'analytics' },
  { to: '/resume', label: 'Resume', icon: 'resume' },
  { to: '/onet', label: 'Careers', icon: 'onet' },
];

const prefetchRoutes: Record<string, string[]> = {
  '/dashboard': ['/dashboard'],
  '/missions': ['/missions'],
  '/evidence': ['/evidence'],
  '/analytics': ['/analytics'],
};

export default function Sidebar() {
  const { user, signOut, getToken } = useAuth();

  const handlePrefetch = useCallback(
    (to: string) => {
      const endpoints = prefetchRoutes[to];
      if (!endpoints) return;
      void getToken().then((token) => {
        for (const endpoint of endpoints) {
          void cachedGet(endpoint, token);
        }
      });
    },
    [getToken],
  );

  return (
    <nav
      className="flex flex-col items-center border-r border-white/[0.06] py-4"
      style={{ background: 'linear-gradient(180deg, #4A3A50 0%, #2E1F33 100%)' }}
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="mb-6 px-2" title="Regain">
        <img
          src="/regain-type.png"
          alt="Regain"
          className="h-5 w-auto brightness-0 invert"
        />
      </div>

      {/* Nav items */}
      <div className="flex flex-1 flex-col items-center gap-1 px-1">
        {navItems.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            onMouseEnter={() => handlePrefetch(to)}
            className={({ isActive }) =>
              `relative flex flex-col items-center gap-0.5 rounded-[var(--radius-button)] px-2 py-1.5 transition-colors duration-150 ${
                isActive
                  ? 'bg-white/[0.08] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-full before:bg-primary-400 before:animate-glow-pulse'
                  : 'hover:bg-white/[0.04]'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={isActive ? 'text-white' : 'text-neutral-400'}>
                  <NavIcon name={icon} />
                </span>
                <span
                  className={`text-[10px] tracking-wide ${
                    isActive ? 'text-accent-400' : 'text-neutral-400'
                  }`}
                >
                  {label}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </div>

      {/* Profile + Sign-out (pinned bottom) */}
      <div className="mt-auto flex flex-col items-center gap-1 border-t border-white/[0.06] px-1 pt-3">
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            `relative flex flex-col items-center gap-0.5 rounded-[var(--radius-button)] px-2 py-1.5 transition-colors duration-150 ${
              isActive
                ? 'bg-white/[0.08] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-full before:bg-primary-400 before:animate-glow-pulse'
                : 'hover:bg-white/[0.04]'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <span className={isActive ? 'text-white' : 'text-neutral-400'}>
                <NavIcon name="profile" />
              </span>
              <span
                className={`text-[10px] tracking-wide ${
                  isActive ? 'text-accent-400' : 'text-neutral-400'
                }`}
              >
                Profile
              </span>
            </>
          )}
        </NavLink>
        <button
          onClick={() => void signOut()}
          className="mt-1 rounded-[var(--radius-button)] bg-white/[0.04] px-2 py-1 text-[10px] text-neutral-400 hover:bg-white/[0.08] hover:text-white transition-colors duration-150"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: add narrow Sidebar component with icon+label nav"
```

---

### Task 4: Create ChatPanel component

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`

This is the core component. It extracts all the message display, streaming, input, and controls from `CoachModal.tsx` into a grid-embedded panel.

- [ ] **Step 1: Write the ChatPanel component**

Create `frontend/src/components/ChatPanel.tsx`:

```tsx
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

  // Connection status border color
  const statusBorderColor =
    connectionStatus === 'connected'
      ? 'var(--color-primary-500)'
      : connectionStatus === 'reconnecting'
        ? 'var(--color-warning-400)'
        : 'var(--color-neutral-300)';

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
      style={{ borderTop: `2px solid ${statusBorderColor}` }}
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatPanel.tsx
git commit -m "feat: add ChatPanel component for grid-embedded coaching chat"
```

---

### Task 5: Rewrite Layout.tsx with CSS grid

**Files:**
- Modify: `frontend/src/components/Layout.tsx` (full rewrite)

- [ ] **Step 1: Rewrite Layout.tsx**

Replace the entire contents of `frontend/src/components/Layout.tsx` with the three-panel grid layout. The mobile header + sidebar overlay stays for mobile, but the desktop view becomes a CSS grid:

```tsx
import { Suspense, useState, useEffect, useCallback } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useSharedData } from '../hooks/useSharedData';
import { useMutationBus } from '../hooks/useMutationBus';
import { api } from '../services/api';
import NavIcon from './ui/NavIcon';
import ErrorBoundary from './ErrorBoundary';
import RouteLoader from './RouteLoader';
import ConnectionBanner from './ConnectionBanner';
import Sidebar from './Sidebar';
import ChatPanel from './ChatPanel';
import DrawerHandle from './DrawerHandle';

const VOICE_ROUTES = ['/voice-practice'];

function isVoiceRoute(pathname: string): boolean {
  return VOICE_ROUTES.some(r => pathname === r || pathname.startsWith(r + '/'));
}

const MOBILE_NAV_GROUPS = [
  {
    label: 'Orient',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
    ],
  },
  {
    label: 'Act',
    items: [
      { to: '/missions', label: 'Missions', icon: 'missions' },
      { to: '/voice-practice', label: 'Voice Practice', icon: 'voice-practice' },
    ],
  },
  {
    label: 'Prove',
    items: [
      { to: '/evidence', label: 'Evidence', icon: 'evidence' },
      { to: '/scorecard', label: 'Scorecard', icon: 'scorecard' },
    ],
  },
  {
    label: 'Leverage',
    items: [
      { to: '/analytics', label: 'Analytics', icon: 'analytics' },
      { to: '/resume', label: 'Resume', icon: 'resume' },
      { to: '/onet', label: 'Careers', icon: 'onet' },
    ],
  },
];

function RecoveryBanner() {
  const { getToken } = useAuth();
  const { dashboard, refreshDashboard } = useSharedData();
  const [recovering, setRecovering] = useState(false);

  const deletedAt = dashboard.data?.deletedAt;
  const deletionScheduledFor = dashboard.data?.deletionScheduledFor;

  if (!deletedAt) return null;

  const formattedDate = deletionScheduledFor
    ? new Date(deletionScheduledFor).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : 'soon';

  const handleRecover = async () => {
    setRecovering(true);
    try {
      const token = await getToken();
      await api.profile.recover(token);
      await refreshDashboard();
    } catch {
      setRecovering(false);
    }
  };

  return (
    <div className="mb-4 rounded-[var(--radius-card)] border border-warning-200 bg-warning-50 px-4 py-3">
      <p className="text-sm text-warning-700">
        Your account is scheduled for deletion on {formattedDate}.{' '}
        <button
          type="button"
          onClick={() => void handleRecover()}
          disabled={recovering}
          className="font-medium text-primary-600 hover:text-primary-700 transition-colors disabled:opacity-50"
        >
          {recovering ? 'Recovering...' : 'Recover account'}
        </button>
      </p>
    </div>
  );
}

export default function Layout() {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const { emit } = useMutationBus();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Chat panel toggle — persisted in localStorage, defaults to open
  const [chatOpen, setChatOpen] = useState(() => {
    const stored = localStorage.getItem('regain-chat-open');
    return stored === null ? true : stored === 'true';
  });

  const toggleChat = useCallback(() => {
    setChatOpen(prev => {
      const next = !prev;
      localStorage.setItem('regain-chat-open', String(next));
      return next;
    });
  }, []);

  // Emit page navigation event
  useEffect(() => {
    emit({ type: 'page:navigated', payload: { route: location.pathname } });
  }, [location.pathname, emit]);

  // Mobile sidebar: Escape key closes
  useEffect(() => {
    if (!sidebarOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarOpen(false);
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [sidebarOpen]);

  // Lock body scroll when mobile sidebar is open
  useEffect(() => {
    document.body.style.overflow = sidebarOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [sidebarOpen]);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  const voice = isVoiceRoute(location.pathname);

  // Voice routes: full-screen layout, no three-panel grid
  if (voice) {
    return (
      <div className="flex min-h-screen">
        {/* Mobile header */}
        <div className="fixed inset-x-0 top-0 z-30 flex h-[60px] items-center justify-between border-b border-neutral-200/60 bg-surface-1 px-4 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation"
            className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-button)] text-neutral-600 hover:bg-neutral-100 transition-colors"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>
          <img src="/regain-type.png" alt="Regain" className="h-6 w-auto" />
          <div className="h-10 w-10" aria-hidden="true" />
        </div>

        <main className="flex-1 overflow-y-auto bg-surface-2 pt-[60px] md:pt-0">
          <ErrorBoundary>
            <Suspense fallback={<RouteLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    );
  }

  // Desktop: three-panel CSS grid
  // Mobile: standard hamburger sidebar + full-width content (no chat panel)
  return (
    <>
      {/* Mobile header bar */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-[60px] items-center justify-between border-b border-neutral-200/60 bg-surface-1 px-4 md:hidden">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open navigation"
          className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-button)] text-neutral-600 hover:bg-neutral-100 transition-colors"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
          </svg>
        </button>
        <img src="/regain-type.png" alt="Regain" className="h-6 w-auto" />
        <div className="h-10 w-10" aria-hidden="true" />
      </div>

      {/* Mobile backdrop overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-neutral-900/40 md:hidden animate-fade-in"
          onClick={closeSidebar}
          aria-hidden="true"
        />
      )}

      {/* Mobile sidebar drawer (full labels, same as before) */}
      <nav
        className={`fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-white/[0.06] transition-transform duration-300 ease-out md:hidden ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{ background: 'linear-gradient(180deg, #4A3A50 0%, #2E1F33 100%)' }}
        aria-label="Main navigation"
      >
        <div className="flex items-center justify-between px-5 py-6">
          <img src="/regain-type.png" alt="Regain" className="h-7 w-auto brightness-0 invert" />
          <button
            type="button"
            onClick={closeSidebar}
            aria-label="Close navigation"
            className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-button)] text-neutral-400 hover:text-white hover:bg-white/[0.08] transition-colors"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-1">
          {MOBILE_NAV_GROUPS.map((group, gi) => (
            <div key={group.label} className={gi > 0 ? 'mt-5' : ''}>
              <span className="block px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-500/60">
                {group.label}
              </span>
              <ul className="space-y-0.5">
                {group.items.map(({ to, label, icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      onClick={closeSidebar}
                      className={({ isActive }) =>
                        `relative flex items-center gap-3 rounded-[var(--radius-button)] pl-4 pr-3 py-2 min-h-[40px] text-[13px] font-medium transition-colors duration-150 ${
                          isActive
                            ? 'bg-white/[0.08] text-white before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-full before:bg-primary-400 before:animate-glow-pulse'
                            : 'text-neutral-400 hover:text-white hover:bg-white/[0.04]'
                        }`
                      }
                    >
                      <NavIcon name={icon} />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-t border-white/[0.06] px-3 pt-2 pb-4">
          <NavLink
            to="/profile"
            onClick={closeSidebar}
            className={({ isActive }) =>
              `relative flex items-center gap-3 rounded-[var(--radius-button)] pl-4 pr-3 py-2 min-h-[40px] text-[13px] font-medium transition-colors duration-150 ${
                isActive
                  ? 'bg-white/[0.08] text-white before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-full before:bg-primary-400 before:animate-glow-pulse'
                  : 'text-neutral-400 hover:text-white hover:bg-white/[0.04]'
              }`
            }
          >
            <NavIcon name="profile" />
            Profile
          </NavLink>
          {user?.username && (
            <p className="mt-1 truncate px-4 text-[11px] text-neutral-500">
              {user.username}
            </p>
          )}
          <button
            onClick={() => void signOut()}
            className="mt-2 w-full rounded-[var(--radius-button)] bg-white/[0.04] px-3 py-2 text-[13px] text-neutral-400 hover:bg-white/[0.08] hover:text-white transition-colors duration-150"
          >
            Sign out
          </button>
        </div>
      </nav>

      {/* Desktop three-panel grid */}
      <div
        className="hidden md:grid min-h-screen"
        style={{
          gridTemplateColumns: `var(--nav-w) 1fr 3px ${chatOpen ? 'var(--chat-w-open)' : 'var(--chat-w-closed)'}`,
          transition: 'grid-template-columns 300ms ease',
        }}
      >
        <Sidebar />

        <main className="overflow-y-auto bg-surface-2">
          <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
            <ConnectionBanner />
            <RecoveryBanner />
            <ErrorBoundary>
              <Suspense fallback={<RouteLoader />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>

        <DrawerHandle open={chatOpen} onToggle={toggleChat} />

        <div className={`overflow-hidden ${chatOpen ? '' : 'w-0'}`}>
          <ChatPanel visible={chatOpen} />
        </div>
      </div>

      {/* Mobile content (no chat panel, below the fixed header) */}
      <main className="flex-1 overflow-y-auto bg-surface-2 pt-[60px] md:hidden">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
          <ConnectionBanner />
          <RecoveryBanner />
          <ErrorBoundary>
            <Suspense fallback={<RouteLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
    </>
  );
}
```

- [ ] **Step 2: Verify in browser**

Run `cd frontend && npm run dev`. Open the app on desktop width (>768px). Confirm:
- Three-panel grid renders: narrow sidebar | page content | chat panel
- Chat panel shows messages and input
- Drawer handle is visible between content and chat
- Clicking the handle collapses/expands the chat panel
- Refresh the page — chat state persists via localStorage
- Navigate to `/voice-practice` — full-screen layout, no sidebar/chat

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat: rewrite Layout.tsx as three-panel CSS grid"
```

---

### Task 6: Remove CoachModal and CoachingPage

**Files:**
- Delete: `frontend/src/components/CoachModal.tsx`
- Delete: `frontend/src/pages/CoachingPage.tsx`
- Modify: `frontend/src/App.tsx:55` (remove coaching route)

- [ ] **Step 1: Remove the coaching route redirect from App.tsx**

In `frontend/src/App.tsx`, delete line 55:

```tsx
// DELETE this line:
      { path: 'coaching', element: <Navigate to="/dashboard" /> },
```

- [ ] **Step 2: Delete CoachModal.tsx**

```bash
rm frontend/src/components/CoachModal.tsx
```

- [ ] **Step 3: Delete CoachingPage.tsx**

```bash
rm frontend/src/pages/CoachingPage.tsx
```

- [ ] **Step 4: Verify build compiles**

Run: `cd frontend && npm run build`

Expected: Build succeeds with no import errors. If there are dangling imports to `CoachModal` or `CoachingPage`, fix them.

- [ ] **Step 5: Commit**

```bash
git add -u frontend/src/components/CoachModal.tsx frontend/src/pages/CoachingPage.tsx frontend/src/App.tsx
git commit -m "feat: remove CoachModal and CoachingPage, replaced by ChatPanel"
```

---

### Task 7: Update tests

**Files:**
- Modify: `frontend/src/__tests__/components/CoachModalSnapshot.test.tsx` (rename + update descriptions)

- [ ] **Step 1: Rename the test file to reflect ChatPanel**

```bash
mv frontend/src/__tests__/components/CoachModalSnapshot.test.tsx frontend/src/__tests__/components/ChatPanelSnapshot.test.tsx
```

- [ ] **Step 2: Update describe block names**

In the renamed file, update the two `describe` block names:

Replace `'CoachModal snapshot formatting'` with `'ChatPanel snapshot formatting'`.

Replace `'CoachModal page_data stripping'` with `'ChatPanel page_data stripping'`.

The test logic itself is unchanged — it tests pure functions (`buildPrefix` and `cleanUserMessage`) that are mirrored in ChatPanel.

- [ ] **Step 3: Run tests**

Run: `cd frontend && npx vitest --run`

Expected: All tests pass. The renamed file should still be discovered by vitest.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/components/
git commit -m "test: rename CoachModal tests to ChatPanel"
```

---

### Task 8: Final verification

- [ ] **Step 1: Full build check**

Run: `cd frontend && npm run build`

Expected: Build succeeds, no warnings about missing imports.

- [ ] **Step 2: Lint check**

Run: `cd frontend && npm run lint`

Expected: No new lint errors. Fix any that appear.

- [ ] **Step 3: Test suite**

Run: `cd frontend && npx vitest --run`

Expected: All tests pass.

- [ ] **Step 4: Manual smoke test**

Open the app in the browser:
1. Desktop (>768px): three-panel layout renders correctly
2. Sidebar shows icons + labels, active state with accent indicator
3. Chat panel shows messages, streaming works, tool activity feed shows
4. Drawer handle toggles chat open/closed with smooth animation
5. Refresh: chat state persists
6. Navigate between pages: proactive checks fire, page context updates
7. `/voice-practice`: full-screen layout, no three-panel grid
8. Mobile (<768px): hamburger menu + full-width content, no chat panel
9. Attention mode toggle works in chat panel
10. Clear conversation button works

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address layout smoke test findings"
```
