import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useContent } from '../content/useContent';
import { colors, fontFamily, radii, spacing } from '../theme';

/** Slim banner shown when the screen renders cached (offline) data. */
export default function OfflineBar() {
  const { t } = useContent();
  return (
    <View style={styles.bar}>
      <Ionicons name="cloud-offline-outline" size={16} color={colors.warning} />
      <Text style={styles.text}>{t('common', 'offline')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.warning,
    borderRadius: radii.pill,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
  },
  text: { color: colors.text, fontSize: 13, fontWeight: '600', fontFamily, marginLeft: spacing.xs },
});
