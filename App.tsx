import 'react-native-gesture-handler';
import React, { useEffect } from 'react';
import { Platform } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from './src/api/auth-context';
import { ContentProvider } from './src/content/useContent';
import { FabMenuProvider } from './src/menu/fabMenu';
import { ensureAdmobInitialized } from './src/utils/ads';
import { checkForUpdate } from './src/utils/update';
import RootNavigator from './src/navigation';
import { colors } from './src/theme';

export default function App() {
  useEffect(() => {
    ensureAdmobInitialized().catch(() => undefined);
    // Silent in-app update check on every cold start (Android only).
    if (Platform.OS === 'android') {
      checkForUpdate(true).catch(() => undefined);
    }
  }, []);

  return (
    <SafeAreaProvider>
      <AuthProvider>
        <ContentProvider>
          <FabMenuProvider>
          <StatusBar style="light" backgroundColor={colors.primary} />
          <RootNavigator />
          </FabMenuProvider>
        </ContentProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
