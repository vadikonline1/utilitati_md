import { Alert, Linking, Platform } from 'react-native';
import Constants from 'expo-constants';

// Verify GitHub Releases for combined-release tags (our update feed) and,
// when the embedded build sha differs from the latest published release, propose
// downloading the new APK. Combined releases are tagged `release-<sha>`
// (see .github/workflows/release-all.yml); `apk-main-<sha>` is the legacy
// per-push format, still recognized for older installs.
const REPO = 'vadikonline1/utilitati_md';

function shaFromTag(tag: string): string | null {
  let m = tag.match(/^release-(.+)$/);
  if (m) return m[1];
  m = tag.match(/^apk-main-(.+)$/);
  return m ? m[1] : null;
}

async function latestPublished(): Promise<{ sha: string; tag: string } | null> {
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=20`);
  if (!res.ok) return null;
  const releases: any[] = await res.json();
  const latest = releases.find(
    (r) => r && !r.draft && shaFromTag(String(r.tag_name || '')) !== null,
  );
  if (!latest) return null;
  return { sha: shaFromTag(String(latest.tag_name)) as string, tag: String(latest.tag_name) };
}

function currentBuildSha(): string | undefined {
  const extra = Constants.expoConfig?.extra as Record<string, any> | undefined;
  return extra?.build_sha as string | undefined;
}

/**
 * Check whether a newer Android build has been published and, if so, surface an
 * in-app alert with a download link. Only acts on Android (iOS updates ship via
 * the App Store).
 *
 * @param silent  when true, only returns whether an update is available without
 *                showing a dialog.
 */
export async function checkForUpdate(silent = true): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  try {
    const current = currentBuildSha();
    const latest = await latestPublished();
    // No published release yet, or this build is already the latest.
    if (!latest) return false;
    if (current && latest.sha === current) return false;

    if (!silent) {
      const res = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/${latest.tag}`);
      const url = res.ok
        ? ((await res.json()) as any).assets?.[0]?.browser_download_url
        : undefined;
      Alert.alert(
        'Actualizare disponibilă',
        'A apărut o versiune nouă a aplicației Utilități.MD.',
        [
          { text: 'Mai târziu', style: 'cancel' },
          {
            text: 'Descarcă',
            onPress: () => {
              if (url) Linking.openURL(url).catch(() => undefined);
            },
          },
        ],
      );
    }
    return true;
  } catch {
    return false;
  }
}