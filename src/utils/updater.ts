import Constants from 'expo-constants';
import * as Linking from 'expo-linking';
import { ActivityAction, startActivityAsync } from 'expo-intent-launcher';
import * as FileSystem from 'expo-file-system/legacy';
import { Platform } from 'react-native';

import { ReleaseChannel } from '../api/client';

const GITHUB_OWNER = 'vadikonline1';
const GITHUB_REPO = 'utilitati_md';
const PLAY_PACKAGE_ID = 'md.utilitati.app';

const CHANNEL_BRANCH: Record<ReleaseChannel, string> = {
  beta: 'deploy',
  stable: 'main',
  play: '',
};

// GitHub Release tag prefixes produced by .github/workflows/build-apk.yml
// (tag cadence: apk-<branch>-<sha>). The app reads these as update feeds.
const CHANNEL_TAG_PREFIX: Partial<Record<ReleaseChannel, string>> = {
  beta: 'apk-deploy-',
  stable: 'apk-main-',
};

export function getLocalVersion(): string {
  return String(Constants.expoConfig?.version || '0.0.0');
}

function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map((n) => parseInt(n, 10) || 0);
  const pb = b.split('.').map((n) => parseInt(n, 10) || 0);
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i++) {
    const x = pa[i] || 0;
    const y = pb[i] || 0;
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

async function fetchRemoteVersion(channel: ReleaseChannel): Promise<string | null> {
  const branch = CHANNEL_BRANCH[channel];
  if (!branch) return null;
  try {
    const res = await fetch(
      `https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${branch}/app.json`,
    );
    if (!res.ok) return null;
    const cfg = (await res.json()) as { expo?: { version?: string } };
    return cfg.expo?.version || null;
  } catch {
    return null;
  }
}

interface ApkRelease {
  tag_name: string;
  browser_download_url: string;
  size: number;
}

async function fetchLatestApk(channel: ReleaseChannel): Promise<ApkRelease | null> {
  const prefix = CHANNEL_TAG_PREFIX[channel];
  if (!prefix) return null;
  try {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases?per_page=50`,
    );
    if (!res.ok) return null;
    const releases = (await res.json()) as Array<{
      tag_name: string;
      assets: Array<{
        name: string;
        browser_download_url: string;
        size: number;
      }>;
    }>;
    if (!Array.isArray(releases)) return null;
    for (const release of releases) {
      // beta accepts the legacy `apk-<sha>` tags from builds before the
      // branch-prefixed tag scheme was introduced.
      if (!release.tag_name.startsWith(prefix)) continue;
      if (prefix === 'apk-deploy-' && release.tag_name.includes('-main-')) continue;
      if (prefix === 'apk-main-' && release.tag_name.includes('-deploy-')) continue;
      const asset = release.assets.find((a) => a.name.endsWith('.apk'));
      if (asset) {
        return {
          tag_name: release.tag_name,
          browser_download_url: asset.browser_download_url,
          size: asset.size,
        };
      }
    }
    return null;
  } catch {
    return null;
  }
}

export interface UpdateInfo {
  available: boolean;
  localVersion: string;
  remoteVersion?: string;
  apkUrl?: string;
}

/** Check whether a newer build exists on the chosen channel. */
export async function checkForUpdate(
  channel: ReleaseChannel,
): Promise<UpdateInfo> {
  const localVersion = getLocalVersion();
  if (channel === 'play') {
    return { available: true, localVersion };
  }
  const [remoteVersion, apk] = await Promise.all([
    fetchRemoteVersion(channel),
    fetchLatestApk(channel),
  ]);
  if (!remoteVersion || !apk) {
    return { available: false, localVersion };
  }
  const available = compareVersions(remoteVersion, localVersion) > 0;
  return { available, localVersion, remoteVersion, apkUrl: apk.browser_download_url };
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

export function openPlayStore(): Promise<void> {
  return Linking.openURL(`market://details?id=${PLAY_PACKAGE_ID}`).catch(async () => {
    await Linking.openURL(
      `https://play.google.com/store/apps/details?id=${PLAY_PACKAGE_ID}`,
    );
  });
}