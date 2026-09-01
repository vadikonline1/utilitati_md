import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError, changePassword, deactivateAccount } from '../api/client';
import { useAuth } from '../api/auth-context';
import AppHeader from '../components/AppHeader';
import Button from '../components/Button';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

const LANG_KEY = 'utilitati.language';
const LANGUAGES = [
  { code: 'ro', label: 'Română' },
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
];

function SettingsRow({
  icon,
  title,
  subtitle,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity style={styles.row} onPress={onPress}>
      <Ionicons name={icon} size={22} color={colors.primary} />
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.muted}>{subtitle}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.muted} />
    </TouchableOpacity>
  );
}

export default function ProfileScreen() {
  const { user, signOut } = useAuth();
  const [lang, setLang] = useState('ro');
  const [langModal, setLangModal] = useState(false);
  const [passModal, setPassModal] = useState(false);
  const [currentPass, setCurrentPass] = useState('');
  const [newPass, setNewPass] = useState('');
  const [confirmPass, setConfirmPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      const saved = await AsyncStorage.getItem(LANG_KEY);
      if (saved) setLang(saved);
    })();
  }, []);

  const saveLang = async (code: string) => {
    setLang(code);
    setLangModal(false);
    await AsyncStorage.setItem(LANG_KEY, code);
  };

  const submitPassword = async () => {
    setError('');
    if (!currentPass || !newPass) {
      setError('Completează parola curentă și cea nouă.');
      return;
    }
    if (newPass.length < 6) {
      setError('Parola nouă trebuie să aibă minim 6 caractere.');
      return;
    }
    if (newPass !== confirmPass) {
      setError('Parolele nu coincid.');
      return;
    }
    setBusy(true);
    try {
      await changePassword(currentPass, newPass);
      setPassModal(false);
      setCurrentPass('');
      setNewPass('');
      setConfirmPass('');
      Alert.alert('Gata', 'Parola a fost schimbată.');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Schimbarea parolei a eșuat.');
    } finally {
      setBusy(false);
    }
  };

  const deactivate = () => {
    Alert.alert(
      'Dezactivare cont',
      'Sigur vrei să dezactivezi contul? Vei fi deconectat.',
      [
        { text: 'Anulează', style: 'cancel' },
        {
          text: 'Dezactivează',
          style: 'destructive',
          onPress: async () => {
            try {
              await deactivateAccount();
              await signOut();
            } catch (e) {
              Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Dezactivarea a eșuat.');
            }
          },
        },
      ],
    );
  };

  const logout = () => {
    Alert.alert('Deconectare', 'Sigur vrei să te deconectezi?', [
      { text: 'Anulează', style: 'cancel' },
      { text: 'Deconectează-te', style: 'destructive', onPress: signOut },
    ]);
  };

  return (
    <View style={styles.container}>
      <AppHeader />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profile}>
          <Ionicons name="person-circle-outline" size={64} color={colors.primary} />
          <Text style={styles.name}>{user?.full_name || user?.username}</Text>
          <Text style={styles.muted}>@{user?.username}</Text>
          {user?.email ? <Text style={styles.muted}>{user.email}</Text> : null}
        </View>

        <Text style={styles.section}>Setări</Text>
        <SettingsRow
          icon="lock-closed-outline"
          title="Schimbă parola"
          onPress={() => setPassModal(true)}
        />
        <SettingsRow
          icon="language-outline"
          title="Limba"
          subtitle={LANGUAGES.find((l) => l.code === lang)?.label}
          onPress={() => setLangModal(true)}
        />
        <SettingsRow
          icon="notifications-outline"
          title="Notificări"
          subtitle="Primești notificări pentru facturile scadente"
          onPress={() =>
            Alert.alert(
              'Notificări',
              'Primești notificări pentru facturile scadente și actualizările conturilor tale.',
            )
          }
        />
        <SettingsRow
          icon="person-remove-outline"
          title="Dezactivare cont"
          onPress={deactivate}
        />

        <Text style={styles.section}>Cont</Text>
        <Button title="Deconectare" variant="danger" onPress={logout} style={styles.logout} />
      </ScrollView>

      <Modal visible={langModal} transparent animationType="slide">
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Limba</Text>
            {LANGUAGES.map((l) => (
              <TouchableOpacity
                key={l.code}
                style={styles.langRow}
                onPress={() => saveLang(l.code)}
              >
                <Text style={styles.langLabel}>{l.label}</Text>
                {lang === l.code ? (
                  <Ionicons name="checkmark" size={20} color={colors.primary} />
                ) : null}
              </TouchableOpacity>
            ))}
            <Button title="Anulează" variant="ghost" onPress={() => setLangModal(false)} />
          </View>
        </View>
      </Modal>

      <Modal visible={passModal} transparent animationType="slide">
        <KeyboardAvoidingView
          style={styles.modalWrap}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Schimbă parola</Text>
            <TextInput
              style={styles.input}
              value={currentPass}
              onChangeText={setCurrentPass}
              secureTextEntry
              placeholder="Parola curentă"
              placeholderTextColor={colors.muted}
            />
            <TextInput
              style={styles.input}
              value={newPass}
              onChangeText={setNewPass}
              secureTextEntry
              placeholder="Parola nouă (min 6 caractere)"
              placeholderTextColor={colors.muted}
            />
            <TextInput
              style={styles.input}
              value={confirmPass}
              onChangeText={setConfirmPass}
              secureTextEntry
              placeholder="Confirmă parola"
              placeholderTextColor={colors.muted}
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Button title="Salvează" onPress={submitPassword} loading={busy} />
            <Button title="Anulează" variant="ghost" onPress={() => setPassModal(false)} />
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.xl },
  profile: { alignItems: 'center', marginTop: spacing.md },
  name: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  muted: { color: colors.muted, marginTop: 2 },
  section: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.muted,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginVertical: spacing.xs,
  },
  rowBody: { flex: 1, marginLeft: spacing.md },
  rowTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  logout: { marginTop: spacing.md },
  modalWrap: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  modal: { backgroundColor: colors.card, borderRadius: 16, padding: spacing.xl },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: spacing.md },
  langRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  langLabel: { fontSize: 16, color: colors.text },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    fontSize: 16,
    color: colors.text,
    backgroundColor: colors.card,
    minHeight: 48,
    marginVertical: spacing.xs,
  },
  error: { color: colors.danger, textAlign: 'center', marginVertical: spacing.sm },
});
