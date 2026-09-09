import React from 'react';
import { Alert, StyleSheet, View } from 'react-native';
import { NavigationContainer, useNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createMaterialTopTabNavigator } from '@react-navigation/material-top-tabs';
import { ActivityIndicator } from 'react-native';
import * as Linking from 'expo-linking';

import { useAuth } from '../api/auth-context';
import { colors, fontFamily } from '../theme';
import { FabItem, TELEGRAM_BOT_URL, useFabMenu } from '../menu/fabMenu';
import AppHeader from '../components/AppHeader';
import FabMenu from '../components/FabMenu';
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
import FabMenuEditorScreen from '../screens/FabMenuEditorScreen';

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
  FabMenuEditor: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const TopTab = createMaterialTopTabNavigator();

function MainTabsWithChrome() {
  const stackNav = useNavigation<any>();
  const { items } = useFabMenu();

  const onPressItem = (item: FabItem) => {
    if (item.action === 'home') {
      stackNav.navigate('HomeForm', {});
    } else if (item.action === 'utility') {
      stackNav.navigate('AccountForm', {});
    } else {
      const url = item.url || TELEGRAM_BOT_URL;
      Linking.openURL(url).catch(() => Alert.alert('Eroare', 'Nu s-a putut deschide linkul.'));
    }
  };

  return (
    <View style={styles.tabsRoot}>
      <AppHeader />
      <TopTab.Navigator
        screenOptions={{
          swipeEnabled: true,
          animationEnabled: true,
          lazy: true,
          tabBarActiveTintColor: colors.primary,
          tabBarInactiveTintColor: colors.muted,
          tabBarIndicatorStyle: styles.indicator,
          tabBarStyle: styles.tabBar,
          tabBarLabelStyle: styles.tabLabel,
          tabBarPressColor: 'rgba(15,118,110,0.12)',
        }}
      >
        <TopTab.Screen name="Dashboard" component={DashboardScreen} />
        <TopTab.Screen name="Locuința" component={HomesScreen} />
        <TopTab.Screen name="Facturi" component={FacturiScreen} />
        <TopTab.Screen name="Profil" component={ProfileScreen} />
      </TopTab.Navigator>
      <FabMenu items={items} onPressItem={onPressItem} />
    </View>
  );
}

function HomesStack() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="MainTabs" component={MainTabsWithChrome} options={{ headerShown: false }} />
      <Stack.Screen name="HomeDetail" component={HomeDetailScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="HomeForm" component={HomeFormScreen} options={{ title: 'Locuință' }} />
      <Stack.Screen name="AccountForm" component={AccountFormScreen} options={{ title: 'Cont' }} />
      <Stack.Screen name="AccountDetail" component={AccountDetailScreen} options={{ title: 'Cont' }} />
      <Stack.Screen name="Notifications" component={NotificationsScreen} options={{ title: 'Notificări' }} />
      <Stack.Screen name="FabMenuEditor" component={FabMenuEditorScreen} options={{ title: 'Meniu rapid' }} />
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
  tabsRoot: { flex: 1, backgroundColor: colors.background },
  tabBar: {
    backgroundColor: colors.card,
    height: 48,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    elevation: 0,
  },
  tabLabel: { fontSize: 14, fontWeight: '600', fontFamily, textTransform: 'none' },
  indicator: {
    backgroundColor: colors.primary,
    height: 3,
    borderTopLeftRadius: 3,
    borderTopRightRadius: 3,
  },
});
