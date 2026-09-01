import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../api/auth-context';
import Button from '../components/Button';
import Card from '../components/Card';
import { colors, spacing } from '../theme';

export default function ProfileScreen() {
  const { user, signOut } = useAuth();

  return (
    <View style={styles.container}>
      <Card>
        <Text style={styles.name}>{user?.full_name || user?.username}</Text>
        <Text style={styles.muted}>@{user?.username}</Text>
        {user?.email ? <Text style={styles.muted}>{user.email}</Text> : null}
      </Card>
      <Button title="Deconectare" variant="danger" onPress={signOut} style={styles.logout} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, padding: spacing.xl },
  name: { fontSize: 22, fontWeight: '800', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  logout: { marginTop: spacing.xl },
});
