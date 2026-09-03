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

export async function registerPushToken(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  const granted = await ensurePermission();
  if (!granted) return false;
  // Prefer the linked EAS project id; fall back to the explicit config value.
  const projectId =
    Constants.easConfig?.projectId ||
    ((Constants.expoConfig?.extra as Record<string, any> | undefined)?.eas?.projectId as string | undefined) ||
    ((Constants.expoConfig?.extra as Record<string, any> | undefined)?.expo?.projectId as string | undefined);
  if (!projectId) return false;
  const { data } = await Notifications.getExpoPushTokenAsync({ projectId });
  if (!data) return false;
  await registerDeviceToken(data, Platform.OS === 'ios' ? 'ios' : 'android');
  return true;
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