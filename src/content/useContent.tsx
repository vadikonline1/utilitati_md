import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { getAppContent } from '../api/client';
import { DEFAULT_SCREENS, ScreenContent } from './defaults';

export const LANG_KEY = 'utilitati.language';

export const APP_LANGS = ['ro', 'ru', 'en'];

const PLACEHOLDER = (str: string, vars?: Record<string, string | number>) => {
  if (!vars) return str;
  return str.replace(/\{(\w+)\}/g, (_, k) =>
    k in vars ? String(vars[k]) : `{${k}}`,
  );
};

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Recursively merge `over` on top of `base`, keeping unknown keys. */
function deepMerge(base: ScreenContent, over: ScreenContent): ScreenContent {
  const out: ScreenContent = { ...base };
  for (const key of Object.keys(over)) {
    const bv = out[key];
    const ov = over[key];
    if (isPlainObject(bv) && isPlainObject(ov)) {
      out[key] = deepMerge(bv, ov);
    } else {
      out[key] = ov;
    }
  }
  return out;
}

export type AnyScreenContent = ScreenContent & {
  badge?: Record<string, { label?: string; color?: string }>;
};

interface ContentContextValue {
  lang: string;
  setLang: (lang: string) => Promise<void>;
  refetch: () => Promise<void>;
  loading: boolean;
  /** Dotted-path lookup on the merged screens, e.g. t('notifications','badge.invoice'). */
  content: Record<string, ScreenContent>;
  t: (
    screen: string,
    path: string,
    vars?: Record<string, string | number>,
  ) => string;
}

const ContentContext = createContext<ContentContextValue | null>(null);

export function ContentProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState('ro');
  const [screens, setScreens] = useState<Record<string, ScreenContent>>(
    DEFAULT_SCREENS,
  );
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const applyServer = useCallback((serverLang: string, serverScreens: unknown) => {
    if (!mounted.current) return;
    setScreens((current) => {
      const merged: Record<string, ScreenContent> = { ...current };
      if (isPlainObject(serverScreens)) {
        for (const screen of Object.keys(serverScreens)) {
          const sv = serverScreens[screen];
          if (isPlainObject(sv)) {
            merged[screen] = deepMerge(current[screen] || {}, sv);
          }
        }
      }
      return merged;
    });
    if (serverLang && APP_LANGS.includes(serverLang)) {
      setLangState(serverLang);
    }
  }, []);

  const refetch = useCallback(async () => {
    const saved = (await AsyncStorage.getItem(LANG_KEY)) || 'ro';
    let resolvedLang = APP_LANGS.includes(saved as any) ? saved : 'ro';
    try {
      const data = await getAppContent(resolvedLang);
      applyServer(data.lang || resolvedLang, data.screens);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, [applyServer]);

  useEffect(() => {
    mounted.current = true;
    refetch().catch(() => setLoading(false));
    return () => {
      mounted.current = false;
    };
  }, [refetch]);

  const setLang = useCallback(
    async (code: string) => {
      if (!APP_LANGS.includes(code as any)) return;
      setLangState(code);
      await AsyncStorage.setItem(LANG_KEY, code);
      await refetch();
    },
    [refetch],
  );

  const t = useCallback(
    (screen: string, path: string, vars?: Record<string, string | number>) => {
      let cursor: unknown = screens[screen];
      for (const part of path.split('.')) {
        if (isPlainObject(cursor)) cursor = cursor[part];
        else return PLACEHOLDER(path, vars);
      }
      return PLACEHOLDER(typeof cursor === 'string' ? cursor : path, vars);
    },
    [screens],
  );

  const value = useMemo<ContentContextValue>(
    () => ({ lang, setLang, refetch, loading, content: screens, t }),
    [lang, setLang, refetch, loading, screens, t],
  );

  return (
    <ContentContext.Provider value={value}>{children}</ContentContext.Provider>
  );
}

export function useContent(): ContentContextValue {
  const ctx = useContext(ContentContext);
  if (!ctx) {
    throw new Error('useContent trebuie folosit în interiorul ContentProvider');
  }
  return ctx;
}

export { PLACEHOLDER };