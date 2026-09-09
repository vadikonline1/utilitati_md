import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

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
  const [items, setItems] = useState<FabItem[]>(defaultFabItems());
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FAB_MENU_KEY);
        if (raw) setItems(sanitizeFabItems(JSON.parse(raw)));
      } catch {
        /* keep defaults */
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

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
    const defs = defaultFabItems();
    setItems(defs);
    try {
      await AsyncStorage.setItem(FAB_MENU_KEY, JSON.stringify(defs));
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => ({ items, loaded, save, reset }), [items, loaded, save, reset]);
  return <FabMenuContext.Provider value={value}>{children}</FabMenuContext.Provider>;
}

export function useFabMenu(): FabMenuContextValue {
  const ctx = useContext(FabMenuContext);
  if (!ctx) throw new Error('useFabMenu trebuie folosit în interiorul FabMenuProvider');
  return ctx;
}
