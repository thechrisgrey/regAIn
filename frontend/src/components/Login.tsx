import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { Button, Input } from './ui';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { signIn } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await signIn(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Sign in failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel — left 60% on desktop, top banner on mobile */}
      <div className="hidden lg:flex lg:w-[60%] flex-col justify-center bg-neutral-900 px-16 xl:px-24">
        <span className="text-4xl font-bold tracking-tight text-white">
          REGAIN
        </span>
        <p className="mt-4 max-w-md text-lg leading-relaxed text-neutral-400">
          Build documented evidence of your capabilities. Complete missions,
          track your progress, and land your next role.
        </p>
      </div>

      {/* Sign-in form — right 40% on desktop, full on mobile */}
      <div className="flex flex-1 flex-col items-center justify-center bg-surface-2 px-6">
        {/* Mobile brand header */}
        <div className="mb-8 text-center lg:hidden">
          <span className="text-3xl font-bold tracking-tight text-neutral-900">
            REGAIN
          </span>
          <p className="mt-2 text-sm text-neutral-500">
            Build evidence. Complete missions. Land your next role.
          </p>
        </div>

        <div className="w-full max-w-sm animate-scale-in">
          <h1 className="text-2xl font-bold text-neutral-900">
            Sign in
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            Enter your credentials to continue.
          </p>

          {error && (
            <div role="alert" className="mt-4 rounded-[var(--radius-button)] bg-error-50 border border-error-100 p-3 text-sm text-error-700">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <Input
              id="email"
              type="email"
              label="Email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />

            <Input
              id="password"
              type="password"
              label="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            <Button
              type="submit"
              disabled={loading}
              size="lg"
              className="w-full"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
