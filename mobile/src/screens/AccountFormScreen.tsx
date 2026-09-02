import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { RouteProp } from '@react-navigation/native';

import {
  Account,
  ApiError,
  createAccount,
  listAccounts,
  listHomes,
  listProviders,
  Provider,
  updateAccount,
} from '../api/client';
import Button from '../components/Button';
import Input from '../components/Input';
import { colors, spacing } from '../theme';

type ParamList = {
  AccountForm: { id?: number; homeId?: number; provider?: string };
};

interface Props {
  navigation: { goBack: () => void };
  route: RouteProp<ParamList, 'AccountForm'>;
}

export default function AccountFormScreen({ navigation, route }: Props) {
  const accountId = route.params?.id;
  const isEdit = accountId != null;
  const fixedHomeId = route.params?.homeId;

  const [homeId, setHomeId] = useState<string>(fixedHomeId != null ? String(fixedHomeId) : '');
  const [provider, setProvider] = useState(route.params?.provider || '');
  const [providerModal, setProviderModal] = useState(false);
  const [contractNumber, setContractNumber] = useState('');
  const [providers, setProviders] = useState<Provider[]>([]);
  const [homes, setHomes] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const allHomes = await listHomes();
        setHomes(allHomes);
        if (fixedHomeId == null && allHomes.length === 1) setHomeId(String(allHomes[0].id));

        const provs = await listProviders();
        setProviders(provs);
      } catch {
        Alert.alert('Eroare', 'Datele de formular nu au putut fi încărcate.');
      } finally {
        setLoading(false);
      }

      if (isEdit) {
        try {
          const accounts = await listAccounts();
          const acc = accounts.find((a) => a.id === accountId);
          if (acc) {
            setHomeId(acc.home_id != null ? String(acc.home_id) : '');
            setProvider(acc.provider);
            setContractNumber(acc.contract_number);
          }
        } catch {
          /* ignore */
        }
      }
    })();
  }, [isEdit, accountId, fixedHomeId]);

  const selectedProvider = providers.find((p) => p.id === provider);

  const chooseProvider = (id: string) => {
    setProvider(id);
    setProviderModal(false);
  };

  const save = async () => {
    if (!provider.trim()) {
      Alert.alert('Atenție', 'Selectează un furnizor.');
      return;
    }
    if (!contractNumber.trim()) {
      Alert.alert('Atenție', 'Completează numărul de contract / identificatorul.');
      return;
    }
    if (!homeId.trim()) {
      Alert.alert('Atenție', 'Selectează locuința.');
      return;
    }
    setSaving(true);
    const payload = {
      home_id: Number(homeId),
      provider,
      label: selectedProvider?.name || provider,
      icon: selectedProvider?.icon || '📄',
      contract_number: contractNumber,
      status: 'enabled',
    };
    try {
      if (isEdit) {
        await updateAccount(accountId, payload);
      } else {
        await createAccount(payload);
      }
      navigation.goBack();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Salvarea a eșuat.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>{isEdit ? 'Editează contul' : 'Utilitate nouă'}</Text>

        <Text style={styles.section}>Locuință *</Text>
        {homes.length > 0 ? (
          <View style={styles.chipWrap}>
            {homes.map((h) => (
              <TouchableChip
                key={h.id}
                label={h.name}
                selected={homeId === String(h.id)}
                onPress={() => setHomeId(String(h.id))}
              />
            ))}
          </View>
        ) : (
          <Text style={styles.mutedInline}>Nu ai nicio locuință. Creează întâi o locuință.</Text>
        )}

        <Text style={styles.section}>Furnizor *</Text>
        <TouchableOpacity style={styles.picker} onPress={() => setProviderModal(true)}>
          <Text style={provider ? styles.pickerValue : styles.pickerPlaceholder}>
            {selectedProvider ? `${selectedProvider.icon || ''}  ${selectedProvider.name || 'Furnizor'}` : 'Selectează furnizorul'}
          </Text>
          <Text style={styles.pickerCaret}>▾</Text>
        </TouchableOpacity>
        {isEdit ? (
          <Text style={styles.readonlyNote}>Furnizorul nu poate fi schimbat după creare.</Text>
        ) : null}

        <Input
          label="Număr contract / identificator *"
          value={contractNumber}
          onChangeText={setContractNumber}
          placeholder={selectedProvider?.placeholder}
        />

        <Button title="Salvează" onPress={save} loading={saving} />
        {loading ? <Text style={styles.muted}>Se încarcă…</Text> : null}
      </ScrollView>

      <Modal visible={providerModal} transparent animationType="slide">
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Furnizor</Text>
            <ScrollView style={styles.modalScroll}>
              {providers
                .map((p) => ({ id: p.id, name: p.name || p.label || p.id, icon: p.icon }))
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((p) => (
                  <TouchableOpacity
                    key={p.id}
                    style={styles.providerRow}
                    onPress={() => chooseProvider(p.id)}
                  >
                    <Text style={styles.providerLabel}>
                      {p.icon ? `${p.icon}  ` : ''}
                      {p.name}
                    </Text>
                    {provider === p.id ? <Text style={styles.check}>✓</Text> : null}
                  </TouchableOpacity>
                ))}
            </ScrollView>
            <Button title="Anulează" variant="ghost" onPress={() => setProviderModal(false)} />
          </View>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

function TouchableChip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={[styles.chip, selected && styles.chipSelected]} onPress={onPress}>
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl },
  title: { fontSize: 24, fontWeight: '800', color: colors.text, marginBottom: spacing.lg },
  section: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.muted,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap' },
  muted: { color: colors.muted, textAlign: 'center', marginTop: spacing.lg },
  mutedInline: { color: colors.muted, fontSize: 14 },
  picker: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    minHeight: 48,
    backgroundColor: colors.card,
  },
  pickerValue: { fontSize: 16, color: colors.text },
  pickerPlaceholder: { fontSize: 16, color: colors.muted },
  pickerCaret: { fontSize: 18, color: colors.muted },
  readonlyNote: { fontSize: 12, color: colors.muted, marginTop: spacing.xs },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    marginVertical: spacing.xs,
    marginRight: spacing.sm,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text },
  chipTextSelected: { color: '#fff', fontWeight: '600' },
  modalWrap: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  modal: { backgroundColor: colors.card, borderRadius: 16, padding: spacing.xl, maxHeight: '70%' },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: spacing.md },
  modalScroll: { marginBottom: spacing.sm },
  providerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  providerLabel: { fontSize: 15, color: colors.text },
  check: { color: colors.primary, fontWeight: '800' },
});
