import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { ActivityIndicator, StyleSheet } from 'react-native';
import * as Linking from 'expo-linking';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../api/auth-context';
import { colors } from '../theme';
import LoginScreen from '../screens/LoginScreen';
import ForgotPasswordScreen from '../screens/ForgotPasswordScreen';
import ResetPasswordScreen from '../screens/ResetPasswordScreen';
import DashboardScreen from '../screens/DashboardScreen';
import HomesScreen from '../screens/HomesScreen';
import FacturiScreen from '../screens/FacturiScreen';
import ProfileScreen from '../screens/ProfileScreen';
import HomeDetailScreen from '../screens/HomeDetailScreen';
import HomeFormScreen from '../screens/HomeFormScreen';
import AccountFormScreen from '../screens/AccountFormScreen';
import AccountDetailScreen from '../screens/AccountDetailScreen';
import NotificationsScreen from '../screens/NotificationsScreen';

export type RootStackParamList = {
  Login: undefined;
  ForgotPassword: undefined;
  ResetPassword: { token?: string } | undefined;
  MainTabs: undefined;
  HomeDetail: { id: number; name: string };
  HomeForm: { id?: number };
  AccountForm: { id?: number; homeId?: number; provider?: string; label?: string };
  AccountDetail: { id: number; label: string };
  Notifications: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator();

type TabIcon =
  | 'apps'
  | 'apps-outline'
  | 'home'
  | 'home-outline'
  | 'receipt'
  | 'receipt-outline'
  | 'person'
  | 'person-outline'
  | 'pie-chart'
  | 'pie-chart-outline';

const TAB_ICONS: Record<string, { active: TabIcon; inactive: TabIcon }> = {
  Dashboard: { active: 'pie-chart', inactive: 'pie-chart-outline' },
  Locuințe: { active: 'home', inactive: 'home-outline' },
  Facturi: { active: 'receipt', inactive: 'receipt-outline' },
  Profil: { active: 'person', inactive: 'person-outline' },
};

function HomeTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarActiveTintColor: colors.primary,
        headerShown: false,
        tabBarIcon: ({ focused, color, size }) => {
          const icons = TAB_ICONS[route.name];
          return (
            <Ionicons
              name={focused ? icons.active : icons.inactive}
              size={size}
              color={color}
            />
          );
        },
      })}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} />
      <Tab.Screen name="Locuințe" component={HomesScreen} />
      <Tab.Screen name="Facturi" component={FacturiScreen} />
      <Tab.Screen name="Profil" component={ProfileScreen} />
    </Tab.Navigator>
  );
}

function HomesStack() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="MainTabs" component={HomeTabs} options={{ headerShown: false }} />
      <Stack.Screen name="HomeDetail" component={HomeDetailScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="HomeForm" component={HomeFormScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="AccountForm" component={AccountFormScreen} options={{ title: 'Cont' }} />
      <Stack.Screen name="AccountDetail" component={AccountDetailScreen} options={{ title: 'Cont' }} />
      <Stack.Screen name="Notifications" component={NotificationsScreen} options={{ title: 'Notificări' }} />
    </Stack.Navigator>
  );
}

export default function RootNavigator() {
  const { user, initializing } = useAuth();

  if (initializing) {
    return <ActivityIndicator style={styles.loading} size="large" color={colors.primary} />;
  }

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
