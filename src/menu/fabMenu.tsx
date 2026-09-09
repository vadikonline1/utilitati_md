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

import { ServerFabItem, getConfig } from '../api/client';
import { useContent } from '../content/useContent';

export const FAB_MENU_KEY = 'utilitati.fabmenu.v1';
export const TELEGRAM_BOT_URL = 'https://t.me/utilitati_md_bot';

export type FabAction = 'home' | 'utility' | 'telegram' | 'link';

export interface FabItem {
  id: string;
  label: string;
  icon: string;
  action: FabAction;
  /** Used by `telegram` and `link` actions. */
  url: string;
  visible: boolean;
}

export const FAB_ACTIONS: { value: FabAction; label: string; hint: string }[] = [
  { value: 'home', label: 'Locuință nouă', hint: 'Deschide formularul de locuință' },
  { value: 'utility', label: 'Utilitate nouă', hint: 'Deschide formularul de cont' },
  { value: 'telegram', label: 'BOT Telegram', hint: 'Deschide linkul botului' },
  { value: 'link', label: 'Link personalizat', hint: 'Deschide orice pagină web' },
];

export const FAB_ICONS = [
  'home-outline',
  'receipt-outline',
  'send-outline',
  'add',
  'star-outline',
  'globe-outline',
  'call-outline',
  'mail-outline',
  'card-outline',
  'notifications-outline',
  'person-outline',
  'settings-outline',
];

export function fabActionLabel(action: FabAction): string {
  return FAB_ACTIONS.find((a) => a.value === action)?.label || action;
}

export function defaultFabItems(): FabItem[] {
  return [
    { id: 'home', label: 'Locuință', icon: 'home-outline', action: 'home', url: '', visible: true },
    { id: 'utility', label: 'Utilități', icon: 'receipt-outline', action: 'utility', url: '', visible: true },
    { id: 'telegram', label: 'BOT Telegram', icon: 'send-outline', action: 'telegram', url: TELEGRAM_BOT_URL, visible: true },
  ];
}

function isAction(v: unknown): v is FabAction {
  return v === 'home' || v === 'utility' || v === 'telegram' || v === 'link';
}

/** Drop malformed entries so a bad stored payload can never break the menu. */
export function sanitizeFabItems(raw: unknown): FabItem[] {
  if (!Array.isArray(raw)) return defaultFabItems();
  const seen = new Set<string>();
  const out: FabItem[] = [];
  for (const e of raw) {
    if (typeof e !== 'object' || e === null) continue;
    const r = e as Record<string, unknown>;
    const id = typeof r.id === 'string' && r.id ? r.id : '';
    if (!id || seen.has(id)) continue;
    if (!isAction(r.action)) continue;
    seen.add(id);
    out.push({
      id,
      label: typeof r.label === 'string' && r.label.trim() ? r.label.trim().slice(0, 40) : fabActionLabel(r.action),
      icon: typeof r.icon === 'string' && r.icon ? r.icon : 'ellipse-outline',
      action: r.action,
      url: typeof r.url === 'string' ? r.url.trim().slice(0, 500) : '',
      visible: r.visible !== false,
    });
  }
  return out.length > 0 ? out : defaultFabItems();
}

/** Map the server menu (/admin?tab=fab) to local items in the given language. */
export function serverToLocal(raw: unknown, lang: string): FabItem[] | null {
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const l = lang === 'ru' ? 'label_ru' : lang === 'en' ? 'label_en' : 'label_ro';
  const mapped = (raw as ServerFabItem[]).map((e) => ({
    id: e.id,
    label: (e[l] || e.label_ro || e.label_en || e.id) as string,
    icon: e.icon,
    action: e.action,
    url: e.url || '',
    visible: e.visible,
  }));
  const clean = sanitizeFabItems(mapped);
  // sanitize falls back to hardcoded defaults when everything is invalid —
  // distinguish "server sent garbage" (ignore it) from real items.
  return clean.length > 0 && (raw as unknown[]).length > 0 ? clean : null;
}

export function newFabItemId(): string {
  return `f${Date.now().toString(36)}${Math.floor(Math.random() * 10000)}`;
}

interface FabMenuContextValue {
  items: FabItem[];
  loaded: boolean;
  save: (items: FabItem[]) => Promise<void>;
  reset: () => Promise<void>;
}

const FabMenuContext = createContext<FabMenuContextValue | null>(null);

export function FabMenuProvider({ children }: { children: React.ReactNode }) {
  const { lang } = useContent();
  const [items, setItems] = useState<FabItem[]>(defaultFabItems());
  const [loaded, setLoaded] = useState(false);
  const [serverRaw, setServerRaw] = useState<ServerFabItem[] | null>(null);
  const customized = useRef(false);

  // Local menu first (instant), then the server menu unless the user
  // personalized it on this device (their explicit edits always win).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FAB_MENU_KEY);
        if (cancelled) return;
        if (raw) {
          customized.current = true;
          setItems(sanitizeFabItems(JSON.parse(raw)));
        }
      } catch {
        /* keep defaults */
      } finally {
        if (!cancelled) setLoaded(true);
      }
      try {
        const cfg = await getConfig();
        if (cancelled) return;
        if (cfg && Array.isArray(cfg.fab_menu) && cfg.fab_menu.length > 0) {
          setServerRaw(cfg.fab_menu);
          if (!customized.current) {
            const mapped = serverToLocal(cfg.fab_menu, lang);
            if (mapped) setItems(mapped);
          }
        }
      } catch {
        /* offline / logged out: keep local menu */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-resolve server labels when the app language changes (server menu only).
  useEffect(() => {
    if (!customized.current && serverRaw) {
      const mapped = serverToLocal(serverRaw, lang);
      if (mapped) setItems(mapped);
    }
  }, [lang, serverRaw]);

  const save = useCallback(async (next: FabItem[]) => {
    const clean = sanitizeFabItems(next);
    customized.current = true;
    setItems(clean);
    try {
      await AsyncStorage.setItem(FAB_MENU_KEY, JSON.stringify(clean));
    } catch {
      /* storage failure: keep in-memory state */
    }
  }, []);

  const reset = useCallback(async () => {
    customized.current = false;
    try {
      await AsyncStorage.removeItem(FAB_MENU_KEY);
    } catch {
      /* ignore */
    }
    if (serverRaw) {
      const mapped = serverToLocal(serverRaw, lang);
      if (mapped) {
        setItems(mapped);
        return;
      }
    }
    setItems(defaultFabItems());
  }, [lang, serverRaw]);

  const value = useMemo(() => ({ items, loaded, save, reset }), [items, loaded, save, reset]);
  return <FabMenuContext.Provider value={value}>{children}</FabMenuContext.Provider>;
}

export function useFabMenu(): FabMenuContextValue {
  const ctx = useContext(FabMenuContext);
  if (!ctx) throw new Error('useFabMenu trebuie folosit în interiorul FabMenuProvider');
  return ctx;
}
