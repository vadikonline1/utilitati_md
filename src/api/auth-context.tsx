import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { PublicUser, clearToken, getToken, login as apiLogin, me as apiMe, registerInvite, saveToken } from './client';
import { registerPushTokenResult } from '../utils/notify';

interface AuthState {
  user: PublicUser | null;
  initializing: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (username: string, first_name: string, last_name: string, email: string) => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (user: PublicUser | null) => void;
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
    async (username: string, first_name: string, last_name: string, email: string) => {
      // Web-identical email-invitation flow: creates an inactive account and
      // emails a confirmation link. No session is created here.
      await registerInvite(username, first_name, last_name, email);
    },
    [],
  );

  const signOut = useCallback(async () => {
    await clearToken();
    setUser(null);
  }, []);

  useEffect(() => {
    if (user && !initializing) {
      // Register this device for server→push notifications automatically on
      // every launch / login. Notifications are ON by default (server flag
      // `notifications_enabled` defaults to true); we only skip when the user
      // explicitly turned them OFF (local switch 'utilitati.notifications' = '0'
      // or the server reports the account has them disabled).
      (async () => {
        try {
          const { default: AsyncStorage } = await import('@react-native-async-storage/async-storage');
          const pref = await AsyncStorage.getItem('utilitati.notifications');
          const explicitlyOff = pref === '0' || user.notifications_enabled === false;
          if (explicitlyOff) return;
          const res = await registerPushTokenResult();
          if (res.ok) {
            await AsyncStorage.setItem('utilitati.notifications', '1');
          }
        } catch {
          // best-effort: never block the app on push registration
        }
      })();
    }
  }, [user, initializing]);

  const value = useMemo(
    () => ({ user, initializing, signIn, signUp, signOut, setUser }),
    [user, initializing, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
