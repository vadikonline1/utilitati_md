import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import { registerDeviceToken } from '../api/client';

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
 * Provider selection:
 *  - Android -> raw Firebase (FCM) registration token from
 *               `getDevicePushTokenAsync`, delivered server-side via FCM HTTP v1
 *               (direct Google Firebase, no Expo relay).
 *  - iOS     -> Expo push token (delivered via the Expo relay -> APNs/FCM).
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
  if (Platform.OS === 'android') {
    // Raw Firebase Cloud Messaging registration token (direct Google push).
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
  // iOS -> Expo push token (Expo relay).
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