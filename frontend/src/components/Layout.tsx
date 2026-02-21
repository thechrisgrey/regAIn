import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import NavIcon from './ui/NavIcon';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
  { to: '/coaching', label: 'Coaching', icon: 'coaching' },
  { to: '/missions', label: 'Missions', icon: 'missions' },
  { to: '/evidence', label: 'Evidence', icon: 'evidence' },
  { to: '/onboarding', label: 'Onboarding', icon: 'onboarding' },
  { to: '/profile', label: 'Profile', icon: 'profile' },
];

export default function Layout() {
  const { user, signOut } = useAuth();

  return (
    <div className="flex min-h-screen">
      <nav
        className="flex w-60 flex-col bg-neutral-900"
        aria-label="Main navigation"
      >
        {/* Wordmark */}
        <div className="px-5 py-6">
          <span className="text-xl font-bold tracking-tight text-white">
            REGAIN
          </span>
        </div>

        {/* Nav items */}
        <ul className="flex-1 space-y-0.5 px-3">
          {navItems.map(({ to, label, icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  `relative flex items-center gap-3 rounded-[var(--radius-button)] px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                    isActive
                      ? 'bg-white/10 text-white before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-0.5 before:rounded-full before:bg-primary-400'
                      : 'text-neutral-400 hover:text-white hover:bg-white/5'
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
        <div className="border-t border-white/10 px-5 py-4">
          {user?.username && (
            <p className="mb-2 truncate text-xs text-neutral-500">
              {user.username}
            </p>
          )}
          <button
            onClick={() => void signOut()}
            className="w-full rounded-[var(--radius-button)] bg-white/5 px-3 py-2 text-sm text-neutral-400 hover:bg-white/10 hover:text-white transition-colors duration-150"
          >
            Sign out
          </button>
        </div>
      </nav>

      <main className="flex-1 overflow-y-auto bg-surface-2">
        <div className="mx-auto max-w-5xl px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
