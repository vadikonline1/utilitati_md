import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { ActivityIndicator, StyleSheet } from 'react-native';
import * as Linking from 'expo-linking';

import { useAuth } from '../api/auth-context';
import { colors } from '../theme';
import LoginScreen from '../screens/LoginScreen';
import ForgotPasswordScreen from '../screens/ForgotPasswordScreen';
import ResetPasswordScreen from '../screens/ResetPasswordScreen';
import HomesScreen from '../screens/HomesScreen';
import HomeDetailScreen from '../screens/HomeDetailScreen';
import HomeFormScreen from '../screens/HomeFormScreen';
import AccountFormScreen from '../screens/AccountFormScreen';
import AccountDetailScreen from '../screens/AccountDetailScreen';
import ProfileScreen from '../screens/ProfileScreen';

export type RootStackParamList = {
  Login: undefined;
  ForgotPassword: undefined;
  ResetPassword: { token?: string } | undefined;
  MainTabs: undefined;
  HomeDetail: { id: number; name: string };
  HomeForm: { id?: number };
  AccountForm: { id?: number; homeId?: number; provider?: string; label?: string };
  AccountDetail: { id: number; label: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator();

function HomesStack() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="MainTabs" component={HomeTabs} options={{ headerShown: false }} />
      <Stack.Screen name="HomeDetail" component={HomeDetailScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="HomeForm" component={HomeFormScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="AccountForm" component={AccountFormScreen} options={{ title: 'Cont' }} />
      <Stack.Screen name="AccountDetail" component={AccountDetailScreen} options={{ title: 'Cont' }} />
    </Stack.Navigator>
  );
}

function HomeTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        headerShown: false,
      }}
    >
      <Tab.Screen name="Locuințe" component={HomesScreen} />
      <Tab.Screen name="Profil" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

export default function RootNavigator() {
  const { user, initializing } = useAuth();

  if (initializing) {
    return <ActivityIndicator style={styles.loading} size="large" color={colors.primary} />;
  }

  // Allow the emailed reset link to open straight into the reset screen:
  //   utilitati://reset-password/<token>  (or https://utilitati.nistorlazar.md/reset-password/<token>)
  const linking = {
    prefixes: [Linking.createURL('/'), 'utilitati://'],
    config: {
      screens: {
        Login: '',
        ResetPassword: 'reset-password/:token',
      },
    },
  };

  return (
    <NavigationContainer linking={linking}>
      {user == null ? (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="ForgotPassword" component={ForgotPasswordScreen} />
          <Stack.Screen name="ResetPassword" component={ResetPasswordScreen} />
        </Stack.Navigator>
      ) : (
        <HomesStack />
      )}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: colors.background },
});
