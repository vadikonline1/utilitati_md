import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../api/auth-context';
import { colors, spacing } from '../theme';
import { RootStackParamList } from '../navigation';

export default function AppHeader() {
  const { user } = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.safe}>
      <View style={styles.wrap}>
        <View style={styles.row}>
          <View style={styles.badge}>🇲🇩</View>
          <View style={styles.textCol}>
            <Text style={styles.logo}>UTILITĂȚI.MD</Text>
            {user?.full_name ? (
              <Text style={styles.name} numberOfLines={1}>{user.full_name}</Text>
            ) : null}
          </View>
          <TouchableOpacity
            style={styles.bell}
            onPress={() => navigation.navigate('Notifications')}
            accessibilityLabel="Notificări"
          >
            <Ionicons name="notifications-outline" size={24} color="#fff" />
          </TouchableOpacity>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    backgroundColor: colors.primary,
  },
  wrap: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
  },
  badge: { fontSize: 26, marginRight: spacing.md },
  textCol: { flex: 1 },
  logo: { color: '#fff', fontSize: 19, fontWeight: '800', letterSpacing: 0.5 },
  name: { color: 'rgba(255,255,255,0.82)', fontSize: 13, marginTop: 2 },
  bell: { padding: spacing.sm },
});