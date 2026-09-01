import React from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';

import { colors, spacing } from '../theme';

interface Props {
  title?: string;
  children: React.ReactNode;
  style?: ViewStyle;
}

export default function Card({ title, children, style }: Props) {
  return (
    <View style={[styles.card, style]}>
      {title ? <Text style={styles.title}>{title}</Text> : null}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    padding: spacing.lg,
    marginVertical: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
  },
});
