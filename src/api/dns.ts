import AsyncStorage from '@react-native-async-storage/async-storage';

// The API DNS is no longer baked in permanently: it is resolved at every app
// launch from a version-controlled source repo, so that when the current
// server DNS expires it can be swapped without shipping a new build.
//
// Source: https://raw.githubusercontent.com/vadikonline1/pi.hole/.../hosts_app_dns
// The file is a plain-text list of `key=host` (Pi-hole hosts style) lines; we
// pick the value of `md.utilitati.app` and use `<host>` as the API origin.
const DNS_SOURCE_URL =
  'https://raw.githubusercontent.com/vadikonline1/pi.hole/refs/heads/main/hosts_app_dns';
const HOST_KEY = 'md.utilitati.app';
const CACHE_KEY = 'utilitati.api_dns';
const FETCH_TIMEOUT_MS = 5000;

let cachedBase: string | null = null;
let resolving: Promise<string | null> | null = null;

/** Normalize a `host`/`host:port` (optionally with scheme/path) into `https://<host>/api`. */
function normalizeBaseUrl(value: string): string {
  let host = value.trim();
  if (!host) return '';
  if (host.startsWith('http://')) host = host.slice('http://'.length);
  else if (host.startsWith('https://')) host = host.slice('https://'.length);
  host = host.split('/')[0].trim();
  if (!host) return '';
  return `https://${host}/api`;
}

/** Extract the `md.utilitati.app` entry from the DNS source file (or null). */
export function parseDnsSource(text: string): string | null {
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.split('#')[0].trim();
    const match = line.match(
      new RegExp(`^${HOST_KEY.replace(/\./g, '\\.')}[=\\s]+(\\S+)\\s*$`),
    );
    if (match) {
      const base = normalizeBaseUrl(match[1]);
      if (base) return base;
    }
  }
  return null;
}

/** Fetch the source file, remember the result in memory + AsyncStorage. */
async function fetchFromSource(): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(DNS_SOURCE_URL, {
      headers: { Accept: 'text/plain' },
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const base = parseDnsSource(await res.text());
    if (base) {
      cachedBase = base;
      await AsyncStorage.setItem(CACHE_KEY, base).catch(() => undefined);
    }
    return base;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Resolve the API base URL for the session.
 *
 * Precedence: live DNS source > previously stored value > `configured` (built
 * into app.json / default constant). The first call performs the network
 * lookup; subsequent calls reuse the in-memory result.
 */
export async function resolveApiBase(configured: string): Promise<string> {
  if (cachedBase) return cachedBase;
  if (!resolving) {
    resolving = (async () => {
      const fresh = await fetchFromSource();
      if (fresh) return fresh;
      const stored = await AsyncStorage.getItem(CACHE_KEY).catch(() => null);
      if (stored) {
        cachedBase = stored;
        return stored;
      }
      return null;
    })().finally(() => {
      resolving = null;
    });
  }
  return (await resolving) || configured;
}