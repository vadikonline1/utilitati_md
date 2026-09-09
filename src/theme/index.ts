import { useColorScheme } from 'react-native';

// M3 Expressive adaptation for React Native (paper: no custom drawing,
// standard roles referenced everywhere, no hard-coded values in screens).
// Brand stays Utilitati.MD teal (#0f766e) in both schemes.

const light = {
  primary: '#0f766e',
  onPrimary: '#ffffff',
  primaryContainer: '#a7f3d0',
  onPrimaryContainer: '#00201c',
  secondary: '#4d635e',
  surface: '#f4f6f8',
  onSurface: '#0f172a',
  surfaceContainer: '#e8edf1',
  surfaceContainerHigh: '#ffffff',
  outlineVariant: '#d7dee3',
  error: '#dc2626',
  success: '#16a34a',
  warning: '#d97706',
};

const dark = {
  primary: '#5eead4',
  onPrimary: '#00332d',
  primaryContainer: '#115e59',
  onPrimaryContainer: '#ccfbf1',
  secondary: '#b0ccc6',
  surface: '#0b1514',
  onSurface: '#e2e8f0',
  surfaceContainer: '#12211f',
  surfaceContainerHigh: '#1a2e2b',
  outlineVariant: '#334155',
  error: '#f87171',
  success: '#4ade80',
  warning: '#fbbf24',
};

export type Scheme = typeof light;

export function getScheme(mode: 'light' | 'dark'): Scheme {
  return mode === 'dark' ? dark : light;
}

export function useScheme(): Scheme {
  const mode = useColorScheme();
  return getScheme(mode === 'dark' ? 'dark' : 'light');
}

// Back-compat: old `colors.*` imports keep working (light scheme).
export const colors = {
  primary: light.primary,
  primaryDark: '#115e59',
  background: light.surface,
  card: light.surfaceContainerHigh,
  text: light.onSurface,
  muted: '#64748b',
  border: light.outlineVariant,
  danger: light.error,
  success: light.success,
  warning: light.warning,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
};

// M3 Expressive shape scale (pill max, cards 28-32dp, sheets/dialogs ~40dp).
// 32dp cards break on small content, so 28dp is used as working default.
export const radii = {
  pill: 999,
  card: 28,
  dialog: 40,
  sheet: 40,
  field: 999,
  chip: 999,
};

export const fontFamily = 'Roboto';
