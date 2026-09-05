import Constants from 'expo-constants';
import { ActivityAction, startActivityAsync } from 'expo-intent-launcher';
import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';

const GITHUB_OWNER = 'vadikonline1';
const GITHUB_REPO = 'utilitati_md';

// Beta updates are served from the `deploy` branch. The official Play Store
// build is installed from the market and does not use in-app updates.
const BETA_BRANCH = 'deploy';
const BETA_TAG_PREFIX = 'apk-deploy-';

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
  tag_name: string;
  browser_download_url: string;
  sha: string;
}

async function fetchLatestApk(): Promise<ApkRelease | null> {
  try {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases?per_page=50`,
    );
    if (!res.ok) return null;
    const releases = (await res.json()) as Array<{
      tag_name: string;
      assets: Array<{ name: string; browser_download_url: string }>;
    }>;
    if (!Array.isArray(releases)) return null;
    for (const release of releases) {
      // Accept current `apk-deploy-<sha>` tags and the legacy `apk-<sha>` tags
      // from builds created before the branch-prefixed scheme. Never pick the
      // `apk-main-<sha>` (stable) feed — stable ships through Play Market only.
      if (!release.tag_name.startsWith(BETA_TAG_PREFIX) && !release.tag_name.startsWith('apk-')) continue;
      if (release.tag_name.includes('-main-')) continue;
      const asset = release.assets.find((a) => a.name.endsWith('.apk'));
      if (!asset) continue;
      const sha = release.tag_name.slice(release.tag_name.lastIndexOf('-') + 1);
      if (!sha) continue;
      return {
        tag_name: release.tag_name,
        browser_download_url: asset.browser_download_url,
        sha,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export interface UpdateInfo {
  available: boolean;
  localVersion: string;
  localSha?: string;
  remoteSha?: string;
  apkUrl?: string;
}

/**
 * Check for a newer beta build. The update is detected by the deploy SHA
 * (a freshly built APK from the `deploy` branch), NOT by the app version —
 * two consecutive builds may share the same version.
 */
export async function checkForUpdate(): Promise<UpdateInfo> {
  const localVersion = getLocalVersion();
  const localSha = getLocalBuildSha();
  const apk = await fetchLatestApk();
  if (!apk) {
    return { available: false, localVersion, localSha };
  }
  if (localSha && apk.sha !== localSha) {
    return {
      available: true,
      localVersion,
      localSha,
      remoteSha: apk.sha,
      apkUrl: apk.browser_download_url,
    };
  }
  // Same SHA (already the latest deploy) or a build without an embedded SHA.
  return {
    available: false,
    localVersion,
    localSha,
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
  if (download.status !== 200) {
    throw new Error('Descărcarea APK a eșuat');
  }
  const contentUri = await FileSystem.getContentUriAsync(fileUri);
  await startActivityAsync(ActivityAction.VIEW, {
    data: contentUri,
    type: 'application/vnd.android.package-archive',
    flags: 1, // FLAG_GRANT_READ_URI_PERMISSION
  });
}