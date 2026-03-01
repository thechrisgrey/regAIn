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
  resendSignUpCode as amplifyResendSignUpCode,
  signOut as amplifySignOut,
  getCurrentUser,
  fetchAuthSession,
} from 'aws-amplify/auth';

interface AuthUser {
  userId: string;
  username: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  confirmSignUp: (email: string, code: string) => Promise<void>;
  resendConfirmationCode: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

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
    <AuthContext.Provider value={{ user, loading, signIn, signUp, confirmSignUp, resendConfirmationCode, signOut, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export { AuthContext };
