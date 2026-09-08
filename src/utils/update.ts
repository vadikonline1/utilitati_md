import { Alert, Linking, Platform } from 'react-native';
import Constants from 'expo-constants';

// Verify GitHub Releases for `apk-<branch>-<sha>` tags (our update feed) and,
// when the embedded build sha differs from the latest published release, propose
// downloading the new APK. Importantda: la fiecare push pe `main` workflow-ul
// build-apk publică un Release `apk-main-<sha>`.
const REPO = 'vadikonline1/utilitati_md';

async function latestPublishedSha(): Promise<string | null> {
  const res = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=20`);
  if (!res.ok) return null;
  const releases: any[] = await res.json();
  // Build releases are tagged apk-main-<sha> (see .github/workflows/build-apk.yml).
  const latest = releases.find((r) => r && !r.draft && String(r.tag_name || '').startsWith('apk-main-'));
  if (!latest) return null;
  const m = String(latest.tag_name).match(/^apk-main-(.+)$/);
  return m ? m[1] : null;
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
    const latest = await latestPublishedSha();
    // No published release yet, or this build is already the latest.
    if (!latest) return false;
    if (current && latest === current) return false;

    if (!silent) {
      const res = await fetch(`https://api.github.com/repos/${REPO}/releases/tags/apk-main-${latest}`);
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