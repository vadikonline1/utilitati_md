import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
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
  return clean.length > 0 ? clean : null;
}

export interface ServerPayloadItem {
  id: string;
  label_ro: string;
  label_ru: string;
  label_en: string;
  icon: string;
  action: string;
  url: string;
  visible: boolean;
}

/**
 * Build the server payload from local items, preserving the other languages
 * of server-known items and using the edited label everywhere for new ones.
 */
export function toServerPayload(
  items: FabItem[],
  serverRaw: ServerFabItem[] | null,
  lang: string,
): ServerPayloadItem[] {
  const byId = new Map((serverRaw || []).map((s) => [s.id, s]));
  return items.map((i) => {
    const s = byId.get(i.id);
    const label = i.label.trim();
    return {
      id: i.id,
      label_ro: lang === 'ro' ? label : s?.label_ro || label,
      label_ru: lang === 'ru' ? label : s?.label_ru || label,
      label_en: lang === 'en' ? label : s?.label_en || label,
      icon: i.icon,
      action: i.action,
      url: i.url,
      visible: i.visible,
    };
  });
}

export function newFabItemId(): string {
  return `f${Date.now().toString(36)}${Math.floor(Math.random() * 10000)}`;
}

interface FabMenuContextValue {
  items: FabItem[];
  loaded: boolean;
  serverRaw: ServerFabItem[] | null;
  save: (items: FabItem[]) => Promise<void>;
  reset: () => Promise<void>;
  refresh: () => Promise<boolean>;
}

const FabMenuContext = createContext<FabMenuContextValue | null>(null);

export function FabMenuProvider({ children }: { children: React.ReactNode }) {
  const { lang } = useContent();
  const [items, setItems] = useState<FabItem[]>(defaultFabItems());
  const [loaded, setLoaded] = useState(false);
  const [serverRaw, setServerRaw] = useState<ServerFabItem[] | null>(null);

  const applyServer = useCallback(
    (raw: ServerFabItem[] | null | undefined, language: string): boolean => {
      if (!raw || raw.length === 0) return false;
      const mapped = serverToLocal(raw, language);
      if (!mapped) return false;
      setServerRaw(raw);
      setItems(mapped);
      AsyncStorage.setItem(FAB_MENU_KEY, JSON.stringify(mapped)).catch(() => undefined);
      return true;
    },
    [],
  );

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      const cfg = await getConfig();
      if (cfg && Array.isArray(cfg.fab_menu) && cfg.fab_menu.length > 0) {
        return applyServer(cfg.fab_menu, lang);
      }
    } catch {
      /* offline / logged out: keep cached menu */
    }
    return false;
  }, [applyServer, lang]);

  // Local cache first (instant), then the server menu — the server is always
  // the source of truth, so the app and /admin always show the same menu.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FAB_MENU_KEY);
        if (!cancelled && raw) setItems(sanitizeFabItems(JSON.parse(raw)));
      } catch {
        /* keep defaults */
      } finally {
        if (!cancelled) setLoaded(true);
      }
      try {
        const cfg = await getConfig();
        if (!cancelled && cfg && Array.isArray(cfg.fab_menu) && cfg.fab_menu.length > 0) {
          applyServer(cfg.fab_menu, lang);
        }
      } catch {
        /* offline / logged out: keep cached menu */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-resolve server labels when the app language changes.
  useEffect(() => {
    if (serverRaw) {
      const mapped = serverToLocal(serverRaw, lang);
      if (mapped) setItems(mapped);
    }
  }, [lang, serverRaw]);

  const save = useCallback(async (next: FabItem[]) => {
    const clean = sanitizeFabItems(next);
    setItems(clean);
    try {
      await AsyncStorage.setItem(FAB_MENU_KEY, JSON.stringify(clean));
    } catch {
      /* storage failure: keep in-memory state */
    }
  }, []);

  const reset = useCallback(async () => {
    const ok = await refresh();
    if (!ok) setItems(defaultFabItems());
  }, [refresh]);

  const value = useMemo(
    () => ({ items, loaded, serverRaw, save, reset, refresh }),
    [items, loaded, serverRaw, save, reset, refresh],
  );
  return <FabMenuContext.Provider value={value}>{children}</FabMenuContext.Provider>;
}

export function useFabMenu(): FabMenuContextValue {
  const ctx = useContext(FabMenuContext);
  if (!ctx) throw new Error('useFabMenu trebuie folosit în interiorul FabMenuProvider');
  return ctx;
}
