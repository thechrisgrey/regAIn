import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const navItems = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/missions', label: 'Missions' },
  { to: '/evidence', label: 'Evidence' },
  { to: '/onboarding', label: 'Onboarding' },
  { to: '/profile', label: 'Profile' },
];

export default function Layout() {
  const { signOut } = useAuth();

  return (
    <div className="flex min-h-screen">
      <nav className="w-56 bg-gray-900 text-white flex flex-col" aria-label="Main navigation">
        <div className="p-4 text-xl font-bold border-b border-gray-700">
          REGAIN
        </div>
        <ul className="flex-1 py-4 space-y-1">
          {navItems.map(({ to, label }) => (
            <li key={to}>
              <NavLink
                to={to}
                className={({ isActive }) =>
                  `block px-4 py-2 text-sm ${isActive ? 'bg-gray-700 font-medium' : 'hover:bg-gray-800'}`
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="p-4 border-t border-gray-700">
          <button
            onClick={() => void signOut()}
            className="w-full rounded bg-gray-700 px-3 py-2 text-sm hover:bg-gray-600"
          >
            Sign out
          </button>
        </div>
      </nav>
      <main className="flex-1 p-6 bg-gray-50">
        <Outlet />
      </main>
    </div>
  );
}
