import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { colors, fontFamily, radii, spacing } from '../theme';
import { FabItem } from '../menu/fabMenu';

interface Props {
  items: FabItem[];
  onPressItem: (item: FabItem) => void;
}

// Expandable FAB menu:
// closed = normal FAB; tap reveals the visible items upward one after
// another and the FAB icon becomes close.
// Each item is 56dp tall, fully rounded, right-aligned with icon + label.
export default function FabMenu({ items, onPressItem }: Props) {
  const [open, setOpen] = useState(false);
  const visible = items.filter((i) => i.visible);
  if (visible.length === 0) return null;

  return (
    <View style={styles.wrap} pointerEvents="box-none">
      {open ? (
        <View style={styles.items}>
          {visible.map((item) => (
            <Pressable
              key={item.id}
              style={({ pressed }) => [styles.item, pressed && styles.itemPressed]}
              android_ripple={{ color: 'rgba(15,118,110,0.15)' }}
              onPress={() => {
                setOpen(false);
                onPressItem(item);
              }}
            >
              <Text style={styles.itemLabel}>{item.label}</Text>
              <View style={styles.itemIcon}>
                <Ionicons name={item.icon as any} size={22} color={colors.primary} />
              </View>
            </Pressable>
          ))}
        </View>
      ) : null}
      <Pressable
        style={({ pressed }) => [styles.fab, pressed && styles.fabPressed]}
        android_ripple={{ color: 'rgba(255,255,255,0.3)' }}
        onPress={() => setOpen((v) => !v)}
        accessibilityLabel={open ? 'Închide meniul' : 'Deschide meniul'}
      >
        <Ionicons name={open ? 'close' : 'add'} size={30} color="#fff" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', right: spacing.lg, bottom: spacing.lg, alignItems: 'flex-end' },
  items: { alignItems: 'flex-end', marginBottom: spacing.md, gap: spacing.sm },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 56,
    borderRadius: radii.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    paddingLeft: spacing.lg,
    paddingRight: spacing.sm,
    elevation: 4,
    minWidth: 190,
    justifyContent: 'flex-end',
  },
  itemPressed: { opacity: 0.9, transform: [{ scale: 0.97 }] },
  itemLabel: { fontSize: 15, fontWeight: '600', color: colors.text, fontFamily, marginRight: spacing.md },
  itemIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fab: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 6,
  },
  fabPressed: { opacity: 0.9, transform: [{ scale: 0.95 }] },
});
