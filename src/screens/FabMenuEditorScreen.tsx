import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import Button from '../components/Button';
import Input from '../components/Input';
import {
  FAB_ACTIONS,
  FAB_ICONS,
  FabAction,
  FabItem,
  fabActionLabel,
  newFabItemId,
  useFabMenu,
} from '../menu/fabMenu';
import { colors, fontFamily, radii, spacing } from '../theme';

interface Draft {
  id?: string;
  label: string;
  icon: string;
  action: FabAction;
  url: string;
}

function normalizeUrl(raw: string): string {
  const v = raw.trim();
  if (!v) return '';
  return /^https?:\/\//i.test(v) ? v : `https://${v}`;
}

export default function FabMenuEditorScreen() {
  const { items, save, reset } = useFabMenu();
  const [modal, setModal] = useState(false);
  const [draft, setDraft] = useState<Draft>({ label: '', icon: 'star-outline', action: 'link', url: '' });
  const [error, setError] = useState('');

  const openAdd = () => {
    setDraft({ label: '', icon: 'star-outline', action: 'link', url: '' });
    setError('');
    setModal(true);
  };

  const openEdit = (item: FabItem) => {
    setDraft({ id: item.id, label: item.label, icon: item.icon, action: item.action, url: item.url });
    setError('');
    setModal(true);
  };

  const submit = async () => {
    const label = draft.label.trim();
    if (!label) {
      setError('Completează denumirea elementului.');
      return;
    }
    const needsUrl = draft.action === 'telegram' || draft.action === 'link';
    const url = needsUrl ? normalizeUrl(draft.url) : '';
    if (needsUrl && !url) {
      setError('Completează linkul pentru această acțiune.');
      return;
    }
    if (draft.id) {
      await save(items.map((i) => (i.id === draft.id ? { ...i, label, icon: draft.icon, action: draft.action, url } : i)));
    } else {
      await save([...items, { id: newFabItemId(), label, icon: draft.icon, action: draft.action, url, visible: true }]);
    }
    setModal(false);
  };

  const toggle = async (item: FabItem, visible: boolean) => {
    await save(items.map((i) => (i.id === item.id ? { ...i, visible } : i)));
  };

  const remove = (item: FabItem) => {
    Alert.alert('Șterge elementul', `Sigur vrei să ștergi „${item.label}" din meniul rapid?`, [
      { text: 'Anulează', style: 'cancel' },
      {
        text: 'Șterge',
        style: 'destructive',
        onPress: async () => save(items.filter((i) => i.id !== item.id)),
      },
    ]);
  };

  const confirmReset = () => {
    Alert.alert('Resetează meniul', 'Revii la cele 3 elemente implicite (Locuință, Utilități, BOT Telegram)?', [
      { text: 'Anulează', style: 'cancel' },
      { text: 'Resetează', style: 'destructive', onPress: reset },
    ]);
  };

  return (
    <View style={styles.screen}>
      <FlatList
        data={items}
        keyExtractor={(i) => i.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <View style={styles.rowIcon}>
              <Ionicons name={item.icon as any} size={22} color={colors.primary} />
            </View>
            <View style={styles.rowBody}>
              <Text style={styles.rowTitle}>{item.label}</Text>
              <Text style={styles.muted}>{fabActionLabel(item.action)}</Text>
            </View>
            <Switch
              value={item.visible}
              onValueChange={(v) => toggle(item, v)}
              trackColor={{ false: colors.border, true: colors.primary }}
            />
            <Pressable
              style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
              android_ripple={{ color: 'rgba(15,118,110,0.15)', borderless: true }}
              onPress={() => openEdit(item)}
              accessibilityLabel={`Editează ${item.label}`}
            >
              <Ionicons name="pencil-outline" size={20} color={colors.primary} />
            </Pressable>
            <Pressable
              style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
              android_ripple={{ color: 'rgba(220,38,38,0.12)', borderless: true }}
              onPress={() => remove(item)}
              accessibilityLabel={`Șterge ${item.label}`}
            >
              <Ionicons name="trash-outline" size={20} color={colors.danger} />
            </Pressable>
          </View>
        )}
        ListEmptyComponent={<Text style={styles.empty}>Niciun element în meniul rapid. Adaugă primul element.</Text>}
        ListFooterComponent={
          <View style={styles.footer}>
            <Button title="Adaugă element" onPress={openAdd} />
            <Button title="Resetează la valorile implicite" variant="ghost" onPress={confirmReset} />
          </View>
        }
      />

      <Modal visible={modal} transparent animationType="slide" onRequestClose={() => setModal(false)}>
        <KeyboardAvoidingView style={styles.modalWrap} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>{draft.id ? 'Editează elementul' : 'Element nou'}</Text>
            <Input label="Denumire *" value={draft.label} onChangeText={(v) => setDraft((d) => ({ ...d, label: v }))} maxLength={40} />
            <Text style={styles.sectionLabel}>Pictogramă</Text>
            <View style={styles.iconGrid}>
              {FAB_ICONS.map((name) => (
                <Pressable
                  key={name}
                  style={({ pressed }) => [styles.iconPick, draft.icon === name && styles.iconPickActive, pressed && styles.pressed]}
                  onPress={() => setDraft((d) => ({ ...d, icon: name }))}
                >
                  <Ionicons name={name as any} size={22} color={draft.icon === name ? '#fff' : colors.primary} />
                </Pressable>
              ))}
            </View>
            <Text style={styles.sectionLabel}>Acțiune *</Text>
            {FAB_ACTIONS.map((a) => (
              <Pressable
                key={a.value}
                style={({ pressed }) => [styles.actionRow, draft.action === a.value && styles.actionRowActive, pressed && styles.pressed]}
                onPress={() => setDraft((d) => ({ ...d, action: a.value }))}
              >
                <View style={styles.radio}>
                  {draft.action === a.value ? <View style={styles.radioDot} /> : null}
                </View>
                <View style={styles.flex}>
                  <Text style={styles.actionLabel}>{a.label}</Text>
                  <Text style={styles.muted}>{a.hint}</Text>
                </View>
              </Pressable>
            ))}
            {draft.action === 'telegram' || draft.action === 'link' ? (
              <Input
                label="Link *"
                value={draft.url}
                onChangeText={(v) => setDraft((d) => ({ ...d, url: v }))}
                placeholder="https://…"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
              />
            ) : null}
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Button title="Salvează" onPress={submit} />
            <Button title="Anulează" variant="ghost" onPress={() => setModal(false)} />
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 40 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowBody: { flex: 1, marginLeft: spacing.md },
  rowTitle: { fontSize: 16, fontWeight: '700', color: colors.text, fontFamily },
  muted: { color: colors.muted, fontSize: 13, marginTop: 2, fontFamily },
  iconBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 22 },
  pressed: { opacity: 0.8, transform: [{ scale: 0.96 }] },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl, fontFamily },
  footer: { marginTop: spacing.md },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  modal: { backgroundColor: colors.card, borderTopLeftRadius: radii.dialog, borderTopRightRadius: radii.dialog, padding: spacing.xl, maxHeight: '92%' },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, fontFamily, marginBottom: spacing.md },
  sectionLabel: { fontSize: 14, fontWeight: '600', color: colors.text, fontFamily, marginTop: spacing.md, marginBottom: spacing.sm },
  iconGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  iconPick: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconPickActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.card,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  actionRowActive: { borderColor: colors.primary, borderWidth: 2 },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary },
  actionLabel: { fontSize: 15, fontWeight: '600', color: colors.text, fontFamily },
  flex: { flex: 1 },
  error: { color: colors.danger, textAlign: 'center', marginVertical: spacing.sm, fontFamily },
});
