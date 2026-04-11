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
  const { signOut, getToken } = useAuth();

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
          className="h-10 w-auto brightness-0 invert"
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
