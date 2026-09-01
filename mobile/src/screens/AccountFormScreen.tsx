import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
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
  AccountForm: { id?: number; homeId?: number; provider?: string; label?: string };
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
  const [label, setLabel] = useState(route.params?.label || '');
  const [contractNumber, setContractNumber] = useState('');
  const [placeOfConsumption, setPlaceOfConsumption] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
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
            setLabel(acc.label);
            setContractNumber(acc.contract_number);
            setPlaceOfConsumption(acc.place_of_consumption || '');
            setUsername(acc.username || '');
            setPassword(acc.password || '');
            setFullName(acc.full_name || '');
          }
        } catch {
          /* ignore */
        }
      }
    })();
  }, [isEdit, accountId, fixedHomeId]);

  const selectedProvider = providers.find((p) => p.id === provider);
  const needsFullName = selectedProvider?.fields?.includes('full_name') ?? false;

  const save = async () => {
    if (!label.trim() || !provider.trim() || !contractNumber.trim()) {
      Alert.alert('Atenție', 'Completează eticheta, furnizorul și numărul contractului.');
      return;
    }
    setSaving(true);
    const payload = {
      home_id: homeId ? Number(homeId) : null,
      provider,
      label,
      contract_number: contractNumber,
      place_of_consumption: placeOfConsumption,
      username,
      password,
      full_name: needsFullName ? fullName : undefined,
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
        <Text style={styles.title}>{isEdit ? 'Editează contul' : 'Cont nou'}</Text>

        <Input
          label="Etichetă *"
          value={label}
          onChangeText={setLabel}
          placeholder="ex. Energie Electrică"
        />
        <Input
          label="Furnizor *"
          value={provider}
          onChangeText={setProvider}
          editable={!isEdit}
          placeholder="ex. Premier Energy"
        />
        {needsFullName ? (
          <Input
            label="Nume complet (Nume, Prenume)"
            value={fullName}
            onChangeText={setFullName}
            placeholder={selectedProvider?.full_name_placeholder}
          />
        ) : null}
        <Input
          label="Număr contract *"
          value={contractNumber}
          onChangeText={setContractNumber}
          placeholder={selectedProvider?.placeholder}
        />
        <Input
          label="Loc de consum"
          value={placeOfConsumption}
          onChangeText={setPlaceOfConsumption}
        />
        <Input label="Username (utilizator furnizor)" value={username} onChangeText={setUsername} />
        <Input
          label="Parolă (utilizator furnizor)"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
        />

        {homes.length > 0 ? (
          <View>
            <Text style={styles.section}>Locuință</Text>
            {homes.map((h) => (
              <TouchableChip
                key={h.id}
                label={h.name}
                selected={homeId === String(h.id)}
                onPress={() => setHomeId(String(h.id))}
              />
            ))}
          </View>
        ) : null}

        <Button title="Salvează" onPress={save} loading={saving} />
        {loading ? <Text style={styles.muted}>Se încarcă…</Text> : null}
      </ScrollView>
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
    <TouchableOpacity
      style={[styles.chip, selected && styles.chipSelected]}
      onPress={onPress}
    >
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
  muted: { color: colors.muted, textAlign: 'center', marginTop: spacing.lg },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    marginVertical: spacing.xs,
    alignSelf: 'flex-start',
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text },
  chipTextSelected: { color: '#fff', fontWeight: '600' },
});
