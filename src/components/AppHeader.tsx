import React, { useCallback, useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../api/auth-context';
import { getUnreadNotificationsCount } from '../api/client';
import { colors, fontFamily, spacing } from '../theme';
import { RootStackParamList } from '../navigation';

// Top app bar, 64dp, background extended behind status bar
// (SafeArea top inset padded). Title = app name, right = notifications bell.
export default function AppHeader() {
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();

  useFocusEffect(
    useCallback(() => {
      getUnreadNotificationsCount()
        .then((r) => setUnread(r.count))
        .catch(() => undefined);
    }, []),
  );

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.safe}>
      <View style={[styles.bar, { paddingTop: Math.max(insets.top > 0 ? 0 : spacing.sm, 0) }]}>
        <View style={styles.row}>
          <View style={styles.badge}>🇲🇩</View>
          <View style={styles.textCol}>
            <Text style={styles.title}>Utilitati.MD</Text>
            {user?.full_name ? (
              <Text style={styles.name} numberOfLines={1}>{user.full_name}</Text>
            ) : null}
          </View>
          <Pressable
            style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
            android_ripple={{ color: 'rgba(255,255,255,0.25)', borderless: true }}
            onPress={() => navigation.navigate('Notifications')}
            accessibilityLabel="Notificări"
          >
            <Ionicons name="notifications-outline" size={24} color="#fff" />
            {unread > 0 ? (
              <View style={styles.badgeDot}>
                <Text style={styles.badgeText}>{unread > 99 ? '99+' : unread}</Text>
              </View>
            ) : null}
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { backgroundColor: colors.primary },
  bar: {
    minHeight: 64,
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', minHeight: 48 },
  badge: { fontSize: 26, marginRight: spacing.md },
  textCol: { flex: 1 },
  title: { color: '#fff', fontSize: 22, fontWeight: '700', fontFamily, letterSpacing: 0.3 },
  name: { color: 'rgba(255,255,255,0.82)', fontSize: 13, marginTop: 2, fontFamily },
  iconBtn: {
    width: 48,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 24,
  },
  pressed: { opacity: 0.8, transform: [{ scale: 0.96 }] },
  badgeDot: {
    position: 'absolute',
    top: 4,
    right: 4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
});
