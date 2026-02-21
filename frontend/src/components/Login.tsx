import { useState, useMemo, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { Button, Input } from './ui';

type Mode = 'signin' | 'signup' | 'confirm';

// ---------------------------------------------------------------------------
// Password strength helpers
// ---------------------------------------------------------------------------

interface PasswordRule {
  label: string;
  test: (pw: string) => boolean;
}

const PASSWORD_RULES: PasswordRule[] = [
  { label: 'At least 8 characters', test: (pw) => pw.length >= 8 },
  { label: 'Uppercase letter', test: (pw) => /[A-Z]/.test(pw) },
  { label: 'Lowercase letter', test: (pw) => /[a-z]/.test(pw) },
  { label: 'Number', test: (pw) => /\d/.test(pw) },
  { label: 'Special character', test: (pw) => /[^A-Za-z0-9]/.test(pw) },
];

function PasswordChecklist({ password }: { password: string }) {
  if (!password) return null;
  return (
    <ul className="mt-2 space-y-1">
      {PASSWORD_RULES.map((rule) => {
        const passed = rule.test(password);
        return (
          <li key={rule.label} className="flex items-center gap-2 text-xs">
            <svg
              className={`h-3.5 w-3.5 shrink-0 transition-colors ${passed ? 'text-success-500' : 'text-neutral-300'}`}
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              {passed ? (
                <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm3.22 4.72a.75.75 0 0 0-1.06-1.06L7 7.82 5.84 6.66a.75.75 0 0 0-1.06 1.06l1.7 1.7a.75.75 0 0 0 1.06 0l3.68-3.7Z" />
              ) : (
                <circle cx="8" cy="8" r="6" strokeWidth="1.5" stroke="currentColor" fill="none" />
              )}
            </svg>
            <span className={passed ? 'text-success-600' : 'text-neutral-400'}>{rule.label}</span>
          </li>
        );
      })}
    </ul>
  );
}

function PasswordMatchIndicator({ password, confirm }: { password: string; confirm: string }) {
  if (!confirm) return null;
  const matches = password === confirm;
  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-xs">
      <svg
        className={`h-3.5 w-3.5 shrink-0 transition-colors ${matches ? 'text-success-500' : 'text-error-400'}`}
        viewBox="0 0 16 16"
        fill="currentColor"
      >
        {matches ? (
          <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm3.22 4.72a.75.75 0 0 0-1.06-1.06L7 7.82 5.84 6.66a.75.75 0 0 0-1.06 1.06l1.7 1.7a.75.75 0 0 0 1.06 0l3.68-3.7Z" />
        ) : (
          <path d="M8 1a7 7 0 1 1 0 14A7 7 0 0 1 8 1Zm2.47 4.47a.75.75 0 0 0-1.06 0L8 6.88 6.59 5.47a.75.75 0 1 0-1.06 1.06L6.94 8l-1.41 1.47a.75.75 0 1 0 1.06 1.06L8 9.12l1.41 1.41a.75.75 0 1 0 1.06-1.06L9.06 8l1.41-1.47a.75.75 0 0 0 0-1.06Z" />
        )}
      </svg>
      <span className={matches ? 'text-success-600' : 'text-error-500'}>
        {matches ? 'Passwords match' : 'Passwords do not match'}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Password input with visibility toggle
// ---------------------------------------------------------------------------

function PasswordInput({
  id,
  label,
  value,
  onChange,
  ...rest
}: {
  id: string;
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [visible, setVisible] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-neutral-700">
        {label}
      </label>
      <div className="relative mt-1.5">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          className="block w-full rounded-[var(--radius-button)] border border-neutral-200 bg-white px-3.5 py-2.5 pr-10 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow"
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 transition-colors"
          tabIndex={-1}
          aria-label={visible ? 'Hide password' : 'Show password'}
        >
          {visible ? (
            // Eye-off icon
            <svg className="h-4.5 w-4.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3l14 14M10 5c4 0 7 3 8 5-.4.8-1 1.6-1.8 2.3M14 14.2A8.7 8.7 0 0 1 10 15c-4 0-7-3-8-5 .7-1.3 2-2.7 3.5-3.6" />
              <path d="M10 8a2 2 0 0 1 2 2" />
            </svg>
          ) : (
            // Eye icon
            <svg className="h-4.5 w-4.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5Z" />
              <circle cx="10" cy="10" r="2.5" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Login() {
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const { signIn, signUp, confirmSignUp, resendConfirmationCode } = useAuth();
  const navigate = useNavigate();

  const allPasswordRulesPassed = useMemo(
    () => PASSWORD_RULES.every((r) => r.test(password)),
    [password],
  );
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;
  const signUpReady = firstName.trim() && lastName.trim() && email && allPasswordRulesPassed && passwordsMatch;

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

    if (!allPasswordRulesPassed) {
      setError('Password does not meet all requirements.');
      setLoading(false);
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setLoading(false);
      return;
    }

    const fullName = `${firstName.trim()} ${lastName.trim()}`;
    try {
      await signUp(email, password, fullName);
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
                  autoComplete="email"
                />
                <PasswordInput
                  id="password"
                  label="Password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
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
                {/* First / Last name side by side */}
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    id="first-name"
                    type="text"
                    label="First name"
                    required
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    autoComplete="given-name"
                  />
                  <Input
                    id="last-name"
                    type="text"
                    label="Last name"
                    required
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    autoComplete="family-name"
                  />
                </div>

                <Input
                  id="signup-email"
                  type="email"
                  label="Email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                />

                {/* Password with visibility toggle + strength checklist */}
                <div>
                  <PasswordInput
                    id="signup-password"
                    label="Password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                  <PasswordChecklist password={password} />
                </div>

                {/* Confirm password with visibility toggle + match indicator */}
                <div>
                  <PasswordInput
                    id="confirm-password"
                    label="Confirm password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                  <PasswordMatchIndicator password={password} confirm={confirmPassword} />
                </div>

                <Button
                  type="submit"
                  disabled={loading || !signUpReady}
                  size="lg"
                  className="w-full"
                >
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
