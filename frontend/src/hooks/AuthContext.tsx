import {
  createContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import {
  signIn as amplifySignIn,
  signUp as amplifySignUp,
  confirmSignUp as amplifyConfirmSignUp,
  confirmSignIn as amplifyConfirmSignIn,
  resendSignUpCode as amplifyResendSignUpCode,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
} from 'aws-amplify/auth';
import { requestCache } from '../services/cache';

interface AuthUser {
  userId: string;
  username: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  mfaPending: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  confirmMfa: (code: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  resendConfirmationCode: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string>;
}

export class MfaRequiredError extends Error {
  constructor() {
    super('MFA verification required');
    this.name = 'MfaRequiredError';
  }
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [mfaPending, setMfaPending] = useState(false);

  const checkAuth = useCallback(async () => {
    try {
      const currentUser = await getCurrentUser();
      setUser({
        userId: currentUser.userId,
        username: currentUser.username,
      });
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await amplifySignIn({ username: email, password });
    if (result.isSignedIn) {
      const currentUser = await getCurrentUser();
      setUser({
        userId: currentUser.userId,
        username: currentUser.username,
      });
      setMfaPending(false);
    } else if (
      result.nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_TOTP_CODE'
    ) {
      setMfaPending(true);
      throw new MfaRequiredError();
    }
  }, []);

  const confirmMfa = useCallback(async (code: string) => {
    const result = await amplifyConfirmSignIn({ challengeResponse: code });
    if (result.isSignedIn) {
      const currentUser = await getCurrentUser();
      setUser({
        userId: currentUser.userId,
        username: currentUser.username,
      });
      setMfaPending(false);
    }
  }, []);

  const signUp = useCallback(async (email: string, password: string, name: string) => {
    await amplifySignUp({
      username: email,
      password,
      options: {
        userAttributes: { email, name },
      },
    });
  }, []);

  const confirmSignUp = useCallback(async (email: string, code: string) => {
    await amplifyConfirmSignUp({ username: email, confirmationCode: code });
  }, []);

  const resendConfirmationCode = useCallback(async (email: string) => {
    await amplifyResendSignUpCode({ username: email });
  }, []);

  const signOut = useCallback(async () => {
    await amplifySignOut();
    tokenCache.current = null;
    requestCache.clear();
    setUser(null);
  }, []);

  const tokenCache = useRef<{ token: string; expiresAt: number } | null>(null);

  const getToken = useCallback(async (): Promise<string> => {
    const cached = tokenCache.current;
    if (cached && Date.now() < cached.expiresAt - 60_000) {
      return cached.token;
    }

    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (!token) {
      throw new Error('No access token available');
    }

    // Cognito tokens expire in 1 hour; cache for 55 minutes
    tokenCache.current = { token, expiresAt: Date.now() + 55 * 60 * 1000 };
    return token;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, mfaPending, signIn, confirmMfa, signUp, confirmSignUp, resendConfirmationCode, signOut, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export { AuthContext };
