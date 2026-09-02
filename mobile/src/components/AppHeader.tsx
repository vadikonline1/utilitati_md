import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../api/auth-context';
import { colors, spacing } from '../theme';

export default function AppHeader() {
  const { user } = useAuth();
  return (
    <View style={styles.wrap}>
      <Text style={styles.logo}>🇲🇩 UTILITĂȚI.MD</Text>
      {user?.full_name ? <Text style={styles.name} numberOfLines={1}>{user.full_name}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.primary,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  logo: { color: '#fff', fontSize: 17, fontWeight: '800', letterSpacing: 0.5 },
  name: { color: 'rgba(255,255,255,0.85)', fontSize: 13, marginTop: 2 },
});
