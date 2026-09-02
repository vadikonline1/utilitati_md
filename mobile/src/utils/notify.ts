import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

let permissionPromise: Promise<boolean> | null = null;

async function ensurePermission(): Promise<boolean> {
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

export async function notifyNewInvoice(title: string, body: string): Promise<void> {
  if (Platform.OS === 'web') return;
  const granted = await ensurePermission();
  if (!granted) return;
  await Notifications.scheduleNotificationAsync({
    content: { title, body },
    trigger: null,
  }).catch(() => undefined);
}