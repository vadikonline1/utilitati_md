import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { PublicUser, clearToken, getToken, login as apiLogin, me as apiMe, register as apiRegister, saveToken } from './client';

interface AuthState {
  user: PublicUser | null;
  initializing: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (username: string, password: string, email: string, fullName: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        if (token) {
          const u = await apiMe();
          setUser(u);
        }
      } catch {
        await clearToken();
      } finally {
        setInitializing(false);
      }
    })();
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const { token, user: u } = await apiLogin(username, password);
    await saveToken(token);
    setUser(u);
  }, []);

  const signUp = useCallback(
    async (username: string, password: string, email: string, fullName: string) => {
      const { token, user: u } = await apiRegister(username, password, email, fullName);
      await saveToken(token);
      setUser(u);
    },
    [],
  );

  const signOut = useCallback(async () => {
    await clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, initializing, signIn, signUp, signOut }),
    [user, initializing, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
