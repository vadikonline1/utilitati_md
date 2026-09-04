import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import { registerDeviceToken, getConfig } from '../api/client';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

let permissionPromise: Promise<boolean> | null = null;

export async function ensurePermission(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  if (!permissionPromise) {
    permissionPromise = (async () => {
      let status = await Notifications.getPermissionsAsync();
      if (status.status !== 'granted' && status.canAskAgain) {
        const req = await Notifications.requestPermissionsAsync();
        status = req;
      }
      return status.status === 'granted';
    })().catch(() => false);
  }
  return permissionPromise;
}

async function ensureChannel(): Promise<void> {
  try {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Facturi',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#0f766e',
    });
  } catch {
    // channel creation is best-effort
  }
}

export type PushActivationError = {
  ok: false;
  reason:
    | 'unsupported-platform'
    | 'permission-denied'
    | 'missing-project-id'
    | 'token-unavailable'
    | 'registration-failed';
  detail?: string;
};

export type PushActivationResult =
  | { ok: true }
  | PushActivationError;

function resolveProjectId(): string | undefined {
  const plan = Constants.easConfig?.projectId;
  if (plan) return plan;
  const extra = Constants.expoConfig?.extra as Record<string, any> | undefined;
  return (extra?.eas?.projectId as string | undefined) || (extra?.expo?.projectId as string | undefined);
}

/**
 * Activate push for this device and register the token with the backend.
 *
 * The server-side global setting ``push_provider`` determines the mode:
 *  - ``expo`` → both platforms register Expo push tokens (Expo relay).
 *  - ``fcm``  (default) → Android registers a raw FCM token (direct Google
 *               push via FCM HTTP v1); iOS registers an Expo push token
 *               (Expo relay).
 * Returns a diagnostic result so the UI can show the precise reason on failure.
 */
export async function registerPushTokenResult(): Promise<PushActivationResult> {
  if (Platform.OS === 'web') {
    return { ok: false, reason: 'unsupported-platform' };
  }
  const granted = await ensurePermission();
  if (!granted) {
    return {
      ok: false,
      reason: 'permission-denied',
      detail: 'Permisiunea de notificare nu a fost acordată pentru această aplicare.',
    };
  }

  // Read the global push-provider mode from the server.
  let mode: 'fcm' | 'expo' = 'fcm';
  try {
    const cfg = await getConfig();
    if (cfg?.push?.provider === 'expo' || cfg?.push?.provider === 'fcm') {
      mode = cfg.push.provider;
    }
  } catch {
    // Config fetch failed: use the platform default (Android=FCM, iOS=Expo).
  }

  // --- Expo mode: both platforms use the Expo relay ---
  if (mode === 'expo') {
    const projectId = resolveProjectId();
    if (!projectId) {
      return {
        ok: false,
        reason: 'missing-project-id',
        detail: 'Build-ul instalat nu conține projectId-ul Expo (extra.eas.projectId). Rebuild trebuie.',
      };
    }
    let data: string | undefined;
    try {
      const res = await Notifications.getExpoPushTokenAsync({ projectId });
      data = res.data;
    } catch (e) {
      return {
        ok: false,
        reason: 'token-unavailable',
        detail: e instanceof Error ? e.message : String(e),
      };
    }
    if (!data) {
      return {
        ok: false,
        reason: 'token-unavailable',
        detail: 'Expo nu a returnat un push token pentru projectId-ul dat.',
      };
    }
    try {
      await registerDeviceToken(data, 'expo', Platform.OS as 'android' | 'ios');
    } catch (e) {
      return {
        ok: false,
        reason: 'registration-failed',
        detail: e instanceof Error ? e.message : String(e),
      };
    }
    return { ok: true };
  }

  // --- FCM mode (default) ---
  // Android → raw FCM registration token (direct Google push).
  // iOS     → Expo push token (Expo relay, since APNs device tokens cannot be
  //           delivered directly via FCM without Firebase iOS setup).
  if (Platform.OS === 'android') {
    let data: string | undefined;
    try {
      const res = await Notifications.getDevicePushTokenAsync();
      data = typeof res.data === 'string' ? res.data : undefined;
    } catch (e) {
      return {
        ok: false,
        reason: 'token-unavailable',
        detail: e instanceof Error ? e.message : String(e),
      };
    }
    if (!data) {
      return {
        ok: false,
        reason: 'token-unavailable',
        detail: 'Firebase nu a returnat un token FCM pentru acest dispozitiv.',
      };
    }
    try {
      await registerDeviceToken(data, 'fcm', 'android');
    } catch (e) {
      return {
        ok: false,
        reason: 'registration-failed',
        detail: e instanceof Error ? e.message : String(e),
      };
    }
    return { ok: true };
  }
  // iOS in FCM mode falls back to Expo relay.
  const projectId = resolveProjectId();
  if (!projectId) {
    return {
      ok: false,
      reason: 'missing-project-id',
      detail: 'Build-ul instalat nu conține projectId-ul Expo (extra.eas.projectId). Rebuild trebuie.',
    };
  }
  let data: string | undefined;
  try {
    const res = await Notifications.getExpoPushTokenAsync({ projectId });
    data = res.data;
  } catch (e) {
    return {
      ok: false,
      reason: 'token-unavailable',
      detail: e instanceof Error ? e.message : String(e),
    };
  }
  if (!data) {
    return {
      ok: false,
      reason: 'token-unavailable',
      detail: 'Expo nu a returnat un push token pentru projectId-ul dat.',
    };
  }
  try {
    await registerDeviceToken(data, 'expo', 'ios');
  } catch (e) {
    return {
      ok: false,
      reason: 'registration-failed',
      detail: e instanceof Error ? e.message : String(e),
    };
  }
  return { ok: true };
}

export async function registerPushToken(): Promise<boolean> {
  return (await registerPushTokenResult()).ok;
}

export async function notifyNewInvoice(title: string, body: string): Promise<void> {
  if (Platform.OS === 'web') return;
  await ensureChannel();
  const granted = await ensurePermission();
  if (!granted) return;
  await Notifications.scheduleNotificationAsync({
    content: { title, body, sound: 'default' },
    trigger: null,
  }).catch(() => undefined);
}