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
      { to: '/calendar', label: 'Calendar', icon: 'calendar' },
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

  // Desktop: CSS grid — voice routes use sidebar + full content; others add chat panel
  // Mobile: hamburger sidebar + full-width content
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
          gridTemplateColumns: voice
            ? 'var(--nav-w) 1fr'
            : `var(--nav-w) 1fr 1rem ${chatOpen ? 'var(--chat-w-open)' : 'var(--chat-w-closed)'}`,
          transition: 'grid-template-columns 300ms ease',
        }}
      >
        <Sidebar />

        <main className="overflow-y-auto bg-surface-2">
          {voice ? (
            <ErrorBoundary>
              <Suspense fallback={<RouteLoader />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          ) : (
            <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
              <ConnectionBanner />
              <RecoveryBanner />
              <ErrorBoundary>
                <Suspense fallback={<RouteLoader />}>
                  <Outlet />
                </Suspense>
              </ErrorBoundary>
            </div>
          )}
        </main>

        {!voice && <DrawerHandle open={chatOpen} onToggle={toggleChat} />}

        {!voice && (
          <div className={`overflow-hidden ${chatOpen ? '' : 'w-0'}`}>
            <ChatPanel visible={chatOpen} />
          </div>
        )}
      </div>

      {/* Mobile content (no chat panel, below the fixed header) */}
      <main className="flex-1 overflow-y-auto bg-surface-2 pt-[60px] md:hidden">
        {voice ? (
          <ErrorBoundary>
            <Suspense fallback={<RouteLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        ) : (
          <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
            <ConnectionBanner />
            <RecoveryBanner />
            <ErrorBoundary>
              <Suspense fallback={<RouteLoader />}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        )}
      </main>
    </>
  );
}
