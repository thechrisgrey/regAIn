import { Suspense, useState, useEffect, useCallback } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { cachedGet } from '../services/api';
import NavIcon from './ui/NavIcon';
import ErrorBoundary from './ErrorBoundary';
import RouteLoader from './RouteLoader';
import ConnectionBanner from './ConnectionBanner';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { to: '/coaching', label: 'Coaching', icon: 'coaching' },
  { to: '/voice-practice', label: 'Voice Practice', icon: 'voice-practice' },
  { to: '/missions', label: 'Missions', icon: 'missions' },
  { to: '/evidence', label: 'Evidence', icon: 'evidence' },
  { to: '/analytics', label: 'Analytics', icon: 'analytics' },
  { to: '/resume', label: 'Resume', icon: 'resume' },
  { to: '/onet', label: 'ONET', icon: 'onet' },
  { to: '/onboarding', label: 'Onboarding', icon: 'onboarding' },
  { to: '/profile', label: 'Profile', icon: 'profile' },
];

const prefetchRoutes: Record<string, string[]> = {
  '/dashboard': ['/dashboard'],
  '/missions': ['/missions'],
  '/evidence': ['/evidence'],
  '/analytics': ['/analytics'],
};

export default function Layout() {
  const { user, signOut, getToken } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Escape key closes sidebar
  useEffect(() => {
    if (!sidebarOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarOpen(false);
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [sidebarOpen]);

  // Lock body scroll when sidebar is open
  useEffect(() => {
    document.body.style.overflow = sidebarOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [sidebarOpen]);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

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
    <div className="flex min-h-screen">
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
        <img
          src="/regain-type.png"
          alt="Regain"
          className="h-6 w-auto"
        />
        <div className="h-10 w-10" aria-hidden="true" />
      </div>

      {/* Backdrop overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-neutral-900/40 md:hidden animate-fade-in"
          onClick={closeSidebar}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <nav
        className={`fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-white/[0.06] transition-transform duration-300 ease-out md:static md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{ background: 'linear-gradient(180deg, #4A3A50 0%, #2E1F33 100%)' }}
        aria-label="Main navigation"
      >
        {/* Logo + close button */}
        <div className="flex items-center justify-between px-5 py-6">
          <img
            src="/regain-type.png"
            alt="Regain"
            className="h-7 w-auto brightness-0 invert"
          />
          <button
            type="button"
            onClick={closeSidebar}
            aria-label="Close navigation"
            className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-button)] text-neutral-400 hover:text-white hover:bg-white/[0.08] transition-colors md:hidden"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Nav items */}
        <ul className="flex-1 space-y-0.5 px-3">
          {navItems.map(({ to, label, icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                onClick={closeSidebar}
                onMouseEnter={() => handlePrefetch(to)}
                className={({ isActive }) =>
                  `relative flex items-center gap-3 rounded-[var(--radius-button)] px-3 py-2 min-h-[44px] text-sm font-medium transition-colors duration-150 ${
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

        {/* Sign-out */}
        <div className="border-t border-white/[0.06] px-5 py-4">
          {user?.username && (
            <p className="mb-2 truncate text-xs text-neutral-500">
              {user.username}
            </p>
          )}
          <button
            onClick={() => void signOut()}
            className="w-full rounded-[var(--radius-button)] bg-white/[0.04] px-3 py-2 text-sm text-neutral-400 hover:bg-white/[0.08] hover:text-white transition-colors duration-150"
          >
            Sign out
          </button>
        </div>
      </nav>

      <main className="flex-1 overflow-y-auto bg-surface-2 pt-[60px] md:pt-0">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
          <ConnectionBanner />
          <ErrorBoundary>
            <Suspense fallback={<RouteLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
