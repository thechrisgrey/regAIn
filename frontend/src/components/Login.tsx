import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { Button, Input } from './ui';

type Mode = 'signin' | 'signup' | 'confirm';

export default function Login() {
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const { signIn, signUp, confirmSignUp, resendConfirmationCode } = useAuth();
  const navigate = useNavigate();

  function switchMode(next: Mode) {
    setError('');
    setSuccess('');
    setMode(next);
  }

  async function handleSignIn(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      await signIn(email, password);
      navigate('/dashboard');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '';
      const name = (err as { name?: string })?.name ?? '';
      if (name === 'UserNotConfirmedException' || msg.includes('not confirmed')) {
        setMode('confirm');
        setError('');
      } else {
        setError(msg || 'Sign in failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSignUp(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }

    try {
      await signUp(email, password, name);
      setMode('confirm');
      setError('');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Sign up failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await confirmSignUp(email, code);
      setCode('');
      setSuccess('Account confirmed. You can now sign in.');
      setMode('signin');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Confirmation failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setError('');
    setSuccess('');
    try {
      await resendConfirmationCode(email);
      setSuccess('A new code has been sent to your email.');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not resend code. Please try again.'
      );
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Brand panel -- left 60% on desktop, hidden on mobile */}
      <div className="hidden lg:flex lg:w-[60%] flex-col justify-center bg-neutral-900 px-16 xl:px-24">
        <span className="text-4xl font-bold tracking-tight text-white">
          REGAIN
        </span>
        <p className="mt-4 max-w-md text-lg leading-relaxed text-neutral-400">
          Build documented evidence of your capabilities. Complete missions,
          track your progress, and land your next role.
        </p>
      </div>

      {/* Form panel -- right 40% on desktop, full on mobile */}
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
          {/* ---------- SIGN IN ---------- */}
          {mode === 'signin' && (
            <>
              <h1 className="text-2xl font-bold text-neutral-900">Sign in</h1>
              <p className="mt-1 text-sm text-neutral-500">
                Enter your credentials to continue.
              </p>

              {error && (
                <div role="alert" className="mt-4 rounded-[var(--radius-button)] bg-error-50 border border-error-100 p-3 text-sm text-error-700">
                  {error}
                </div>
              )}
              {success && (
                <div role="status" className="mt-4 rounded-[var(--radius-button)] bg-success-50 border border-success-100 p-3 text-sm text-success-700">
                  {success}
                </div>
              )}

              <form onSubmit={handleSignIn} className="mt-6 space-y-4">
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
                <Button type="submit" disabled={loading} size="lg" className="w-full">
                  {loading ? 'Signing in...' : 'Sign in'}
                </Button>
              </form>

              <p className="mt-6 text-center text-sm text-neutral-500">
                Don't have an account?{' '}
                <button
                  type="button"
                  onClick={() => switchMode('signup')}
                  className="font-medium text-primary-600 hover:text-primary-700 transition-colors"
                >
                  Sign up
                </button>
              </p>
            </>
          )}

          {/* ---------- SIGN UP ---------- */}
          {mode === 'signup' && (
            <>
              <h1 className="text-2xl font-bold text-neutral-900">Create account</h1>
              <p className="mt-1 text-sm text-neutral-500">
                Start your career transition today.
              </p>

              {error && (
                <div role="alert" className="mt-4 rounded-[var(--radius-button)] bg-error-50 border border-error-100 p-3 text-sm text-error-700">
                  {error}
                </div>
              )}

              <form onSubmit={handleSignUp} className="mt-6 space-y-4">
                <Input
                  id="name"
                  type="text"
                  label="Full name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <Input
                  id="signup-email"
                  type="email"
                  label="Email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
                <Input
                  id="signup-password"
                  type="password"
                  label="Password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <Input
                  id="confirm-password"
                  type="password"
                  label="Confirm password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
                <Button type="submit" disabled={loading} size="lg" className="w-full">
                  {loading ? 'Creating account...' : 'Sign up'}
                </Button>
              </form>

              <p className="mt-6 text-center text-sm text-neutral-500">
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="font-medium text-primary-600 hover:text-primary-700 transition-colors"
                >
                  Sign in
                </button>
              </p>
            </>
          )}

          {/* ---------- CONFIRM ---------- */}
          {mode === 'confirm' && (
            <>
              <h1 className="text-2xl font-bold text-neutral-900">Confirm your email</h1>
              <p className="mt-1 text-sm text-neutral-500">
                We sent a 6-digit code to <span className="font-medium text-neutral-700">{email}</span>.
                Enter it below to verify your account.
              </p>

              {error && (
                <div role="alert" className="mt-4 rounded-[var(--radius-button)] bg-error-50 border border-error-100 p-3 text-sm text-error-700">
                  {error}
                </div>
              )}
              {success && (
                <div role="status" className="mt-4 rounded-[var(--radius-button)] bg-success-50 border border-success-100 p-3 text-sm text-success-700">
                  {success}
                </div>
              )}

              <form onSubmit={handleConfirm} className="mt-6 space-y-4">
                <Input
                  id="code"
                  type="text"
                  label="Confirmation code"
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="123456"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={6}
                />
                <Button type="submit" disabled={loading} size="lg" className="w-full">
                  {loading ? 'Confirming...' : 'Confirm'}
                </Button>
              </form>

              <p className="mt-4 text-center text-sm text-neutral-500">
                Didn't receive a code?{' '}
                <button
                  type="button"
                  onClick={handleResend}
                  className="font-medium text-primary-600 hover:text-primary-700 transition-colors"
                >
                  Resend code
                </button>
              </p>

              <p className="mt-3 text-center text-sm text-neutral-500">
                <button
                  type="button"
                  onClick={() => switchMode('signin')}
                  className="font-medium text-primary-600 hover:text-primary-700 transition-colors"
                >
                  Back to sign in
                </button>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
