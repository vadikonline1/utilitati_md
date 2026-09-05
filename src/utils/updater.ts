import Constants from 'expo-constants';
import { startActivityAsync } from 'expo-intent-launcher';
import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';

const GITHUB_OWNER = 'vadikonline1';
const GITHUB_REPO = 'utilitati_md';

// Beta updates are served from the `deploy` branch. The official Play Store
// build is installed from the market and does not use in-app updates.
const BETA_TAG_PREFIX = 'apk-deploy-';
const BETA_BRANCH = 'deploy';

export function getLocalVersion(): string {
  return String(Constants.expoConfig?.version || '0.0.0');
}

/** Git SHA the installed APK was built from (embedded by the CI, e.g. `extra.build_sha`). */
export function getLocalBuildSha(): string {
  const extra = Constants.expoConfig?.extra;
  return typeof extra === 'object' && extra !== null && extra
    ? String((extra as Record<string, unknown>).build_sha || '')
    : '';
}

interface ApkRelease {
  browser_download_url: string;
  sha: string;
}

interface RawRelease {
  tag_name: string;
  draft: boolean;
  published_at: string | null;
  created_at: string;
  assets: Array<{ name: string; browser_download_url: string }>;
}

/** Tags canonice: `apk-deploy-<sha>` (beta), `apk-main-<sha>` (stable, exclus), `ios-<sha>`. */
function isBetaTag(tag: string): boolean {
  if (!tag.startsWith(BETA_TAG_PREFIX) && !tag.startsWith('apk-')) return false;
  if (tag.includes('-main-')) return false;
  return true;
}

function tagSha(tag: string): string {
  return tag.slice(tag.lastIndexOf('-') + 1);
}

async function fetchBetaRelease(): Promise<ApkRelease | null> {
  try {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases?per_page=100`,
    );
    if (!res.ok) return null;
    const releases = (await res.json()) as RawRelease[];
    if (!Array.isArray(releases)) return null;

    const fresh = releases.filter((r) => !r.draft);
    // GitHub orders by creation date, but timestamps can shift between
    // consecutive runs — sort explicitly so we always pick the newest build.
    fresh.sort((a, b) => {
      const ta = a.published_at || a.created_at;
      const tb = b.published_at || b.created_at;
      return tb.localeCompare(ta);
    });

    const pick = (list: RawRelease[]): ApkRelease | null => {
      for (const r of list) {
        if (!isBetaTag(r.tag_name)) continue;
        const asset = r.assets.find((a) => a.name.endsWith('.apk'));
        if (!asset) continue;
        const sha = tagSha(r.tag_name);
        if (!sha) continue;
        return { browser_download_url: asset.browser_download_url, sha };
      }
      return null;
    };

    // Prefer the canonical `apk-deploy-<sha>` feed; fall back to legacy
    // `apk-<sha>` tags from builds made before the branch-prefixed scheme.
    const exact = fresh.filter((r) => r.tag_name.startsWith(BETA_TAG_PREFIX));
    return pick(exact) || pick(fresh);
  } catch {
    return null;
  }
}

/** Versiunea app.json de pe ramura beta (ultimul commit), pentru verificare în plus. */
async function fetchBetaVersion(): Promise<string | null> {
  try {
    const res = await fetch(
      `https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${BETA_BRANCH}/app.json`,
    );
    if (!res.ok) return null;
    const cfg = (await res.json()) as { expo?: { version?: unknown } };
    return typeof cfg?.expo?.version === 'string' ? cfg.expo.version : null;
  } catch {
    return null;
  }
}

function parseVersion(v: string): number[] {
  return String(v || '')
    .split('.')
    .map((n) => parseInt(n, 10) || 0);
}

function isNewer(a: string, b: string): boolean {
  const A = parseVersion(a);
  const B = parseVersion(b);
  for (let i = 0; i < Math.max(A.length, B.length); i++) {
    const x = A[i] || 0;
    const y = B[i] || 0;
    if (x !== y) return x > y;
  }
  return false;
}

export interface UpdateInfo {
  available: boolean;
  localVersion: string;
  /** Ultimul commit de pe ramura deploy (app.json). */
  remoteVersion?: string;
  localSha?: string;
  remoteSha?: string;
  apkUrl?: string;
}

/**
 * Rezultat pe baza commit-ului (SHA) celui mai recent build Beta, cu o
 * verificare în plus a versiunii pentru build-urile vechi care nu au SHA
 * încorporat. Actualizarea se consideră disponibilă atunci când există un
 * build mai nou decât cel instalat.
 */
export async function checkForUpdate(): Promise<UpdateInfo> {
  const localVersion = getLocalVersion();
  const localSha = getLocalBuildSha();
  const [apk, remoteVersion] = await Promise.all([
    fetchBetaRelease(),
    fetchBetaVersion(),
  ]);
  const base: UpdateInfo = { available: false, localVersion, localSha, remoteVersion };

  if (!apk) {
    // Niciun build publicat (ex. am șters release-urile) -> nicio actualizare.
    return base;
  }

  const sameSha = !!localSha && localSha === apk.sha;
  const newerVersion = !!remoteVersion && isNewer(remoteVersion, localVersion);
  // Build-urile vechi (fără SHA) se consideră depășite — se oferă ultimul build.
  const available = !sameSha || newerVersion;

  return {
    ...base,
    available,
    remoteSha: apk.sha,
    apkUrl: apk.browser_download_url,
  };
}

/**
 * Download the APK into the app cache and hand it to the Android package
 * installer via a content:// URI. Only works on Android (iOS updates come
 * from the App Store / TestFlight instead).
 */
export async function installUpdate(apkUrl: string): Promise<void> {
  if (Platform.OS !== 'android') {
    throw new Error('Actualizarea APK este disponibilă doar pe Android.');
  }
  const fileUri = `${FileSystem.cacheDirectory}utilitati-md-update.apk`;
  const existing = await FileSystem.getInfoAsync(fileUri);
  if (existing.exists) {
    await FileSystem.deleteAsync(fileUri, { idempotent: true });
  }
  const download = await FileSystem.downloadAsync(apkUrl, fileUri);
  if (download.status < 200 || download.status >= 300) {
    throw new Error(
      `Descărcarea APK a eșuat (HTTP ${download.status}). Verifică sau descarcă manual build-ul din GitHub Release.`,
    );
  }
  const contentUri = await FileSystem.getContentUriAsync(fileUri);
  if (!contentUri) {
    throw new Error('Nu am putut accesa fișierul APK descărcat.');
  }
  // ActivityAction.VIEW doesn't exist in this expo-intent-launcher version,
  // so we pass the raw Android action string. See expo/expo#20949.
  await startActivityAsync('android.intent.action.VIEW', {
    data: contentUri,
    type: 'application/vnd.android.package-archive',
    flags: 1, // FLAG_GRANT_READ_URI_PERMISSION
  });
}