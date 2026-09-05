import 'react-native-gesture-handler';
import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from './src/api/auth-context';
import { ContentProvider } from './src/content/useContent';
import { ensureAdmobInitialized } from './src/utils/ads';
import RootNavigator from './src/navigation';
import { colors } from './src/theme';

export default function App() {
  useEffect(() => {
    ensureAdmobInitialized().catch(() => undefined);
  }, []);

  return (
    <SafeAreaProvider>
      <AuthProvider>
        <ContentProvider>
          <StatusBar style="light" backgroundColor={colors.primary} />
          <RootNavigator />
        </ContentProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
