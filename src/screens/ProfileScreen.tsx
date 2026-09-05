import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import Input from '../components/Input';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError, changePassword, clearDeviceToken, deactivateAccount, ReleaseChannel, sendTestNotification, updateNotificationsEnabled, updateReleaseChannel, updateSelf } from '../api/client';
import { useAuth } from '../api/auth-context';
import { useContent } from '../content/useContent';
import { registerPushTokenResult } from '../utils/notify';
import { checkForUpdate, getLocalVersion, installUpdate } from '../utils/updater';
import AppHeader from '../components/AppHeader';
import Button from '../components/Button';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

const NOTIF_KEY = 'utilitati.notifications';
const CHANNEL_KEY = 'utilitati.release_channel';
const LANGUAGES = [
  { code: 'ro', label: 'Română' },
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
];
const CHANNELS: { id: ReleaseChannel; label: string; desc: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { id: 'beta', label: 'Beta', desc: '', icon: 'flask-outline' },
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
  const { user, signOut, setUser } = useAuth();
  const { t, lang, setLang } = useContent();
  const [langModal, setLangModal] = useState(false);
  const [passModal, setPassModal] = useState(false);
  const [currentPass, setCurrentPass] = useState('');
  const [newPass, setNewPass] = useState('');
  const [confirmPass, setConfirmPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editName, setEditName] = useState(user?.full_name || '');
  const [notifOn, setNotifOn] = useState(false);
  const [channel, setChannel] = useState<ReleaseChannel>('beta');
  const [checking, setChecking] = useState(false);
  const p = (key: string, vars?: Record<string, string | number>) =>
    t('profile', key, vars);

  useEffect(() => {
    (async () => {
      const n = await AsyncStorage.getItem(NOTIF_KEY);
      setNotifOn(n === '1');
      const serverChannel = user?.release_channel as ReleaseChannel | undefined;
      const stored = (await AsyncStorage.getItem(CHANNEL_KEY)) as ReleaseChannel | null;
      const effective: ReleaseChannel = 'beta';
      setChannel(effective);
      if (stored !== effective) {
        await AsyncStorage.setItem(CHANNEL_KEY, effective);
      }
      if (serverChannel !== effective) {
        updateReleaseChannel(effective).catch(() => undefined);
      }
    })();
  }, [user?.release_channel]);

  const toggleNotifications = async (value: boolean) => {
    setNotifOn(value);
    if (value) {
      // Register the device and send a test push so the user can verify it works.
      let activationDetail = '';
      const res = await registerPushTokenResult();
      if (!res.ok) activationDetail = res.detail || '';
      if (res.ok) {
        try {
          await sendTestNotification();
        } catch {
          activationDetail = 'Autentificarea a mers, dar trimiterea notificării de test a eșuat.';
        }
      }
      if (res.ok && !activationDetail) {
        Alert.alert('Gata', p('notif_activated'));
        await AsyncStorage.setItem(NOTIF_KEY, '1');
        await updateNotificationsEnabled(true).catch(() => undefined);
      } else {
        setNotifOn(false);
        const detail = activationDetail ? `\n\n${activationDetail}` : '';
        Alert.alert(
          'Atenție',
          `Nu am putut activa notificările.${detail}\n\nVerifică permisiunea de notificări pentru aplicație și instalează o versiune nouă (rebuild) care conține projectId-ul Expo corect.`,
        );
        await AsyncStorage.setItem(NOTIF_KEY, '0');
      }
    } else {
      await updateNotificationsEnabled(false).catch(() => undefined);
      await clearDeviceToken().catch(() => undefined);
      await AsyncStorage.setItem(NOTIF_KEY, '0');
    }
  };

  const saveLang = async (code: string) => {
    setLangModal(false);
    await setLang(code);
  };

  const submitPassword = async () => {
    setError('');
    if (!currentPass || !newPass) {
      setError(p('password_warn_complete'));
      return;
    }
    if (newPass.length < 6) {
      setError(p('password_warn_length'));
      return;
    }
    if (newPass !== confirmPass) {
      setError(p('password_warn_mismatch'));
      return;
    }
    setBusy(true);
    try {
      await changePassword(currentPass, newPass);
      setPassModal(false);
      setCurrentPass('');
      setNewPass('');
      setConfirmPass('');
      Alert.alert('Gata', p('password_changed'));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Schimbarea parolei a eșuat.');
    } finally {
      setBusy(false);
    }
  };

  const deactivate = () => {
    Alert.alert(p('deactivate_title'), p('deactivate_confirm'), [
      { text: t('common', 'cancel'), style: 'cancel' },
      {
        text: p('deactivate_btn'),
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
    ]);
  };

  const logout = () => {
    Alert.alert('Deconectare', 'Sigur vrei să te deconectezi?', [
      { text: t('common', 'cancel'), style: 'cancel' },
      { text: p('logout_btn'), style: 'destructive', onPress: signOut },
    ]);
  };

  const saveName = async () => {
    setBusy(true);
    setError('');
    try {
      const updated = await updateSelf(editName.trim());
      if (updated) setUser(updated);
      Alert.alert('Gata', p('name_saved'));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Salvarea numelui a eșuat.');
    } finally {
      setBusy(false);
    }
  };

  const selectChannel = async (id: ReleaseChannel) => {
    const previous = channel;
    setChannel(id);
    await AsyncStorage.setItem(CHANNEL_KEY, id);
    try {
      const updated = await updateReleaseChannel(id);
      if (updated) setUser(updated);
    } catch (e) {
      setChannel(previous);
      Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Nu am putut salva canalul.');
    }
  };

  const checkUpdates = async () => {
    setChecking(true);
    const label = CHANNELS.find((c) => c.id === channel)?.label || 'Beta';
    try {
      if (Platform.OS === 'ios') {
        Alert.alert(
          'iOS',
          'Pe iOS actualizarea se face din App Store / TestFlight — aici poți doar verifica canalul Beta.',
        );
        return;
      }
      const info = await checkForUpdate();
      if (!info.apkUrl) {
        Alert.alert(p('up_to_date'), `Canalul ${label} nu are încă un build publicat.`);
        return;
      }
      const localVersion = info.localVersion;
      const parts: string[] = [];
      if (info.remoteSha) parts.push(`Build/deploy: ${info.remoteSha.slice(0, 7)}`);
      if (info.remoteVersion && info.remoteVersion !== localVersion) {
        parts.push(`Versiune: v${info.remoteVersion} (ai v${localVersion})`);
      }
      if (!info.available) {
        Alert.alert(
          p('up_to_date'),
          `Ai instalat ultimul build Beta${parts.length ? ` (${parts.join(', ')})` : ''}.`,
        );
        return;
      }
      Alert.alert(
        'Build nou disponibil',
        `Pe canalul ${label} este un build mai nou${parts.length ? `: ${parts.join(', ')}` : ''}.\n\nDescarc APK-ul și îl deschid pentru instalare?`,
        [
          { text: t('common', 'cancel'), style: 'cancel' },
          {
            text: 'Descarcă și instalează',
            style: 'default',
            onPress: async () => {
              try {
                await installUpdate(info.apkUrl!);
              } catch (err) {
                Alert.alert(
                  'Eroare',
                  err instanceof Error && err.message
                    ? err.message
                    : 'Nu am putut descărca/instala APK-ul. Deschide fișierul apk-ului din GitHub release.',
                );
              }
            },
          },
        ],
      );
    } finally {
      setChecking(false);
    }
  };

  return (
    <View style={styles.container}>
      <AppHeader />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profile}>
          <Ionicons name="person-circle-outline" size={64} color={colors.primary} />
          <View style={styles.nameInput}>
            <Input
              label={p('name_label')}
              value={editName}
              onChangeText={setEditName}
            />
          </View>
          <Button
            title={p('save_name')}
            onPress={saveName}
            loading={busy}
          />
          <Text style={styles.muted}>@{user?.username}</Text>
          <Text style={styles.email}>{user?.email}</Text>
        </View>

        <Text style={styles.section}>{p('settings')}</Text>
        <SettingsRow
          icon="lock-closed-outline"
          title={p('change_password')}
          onPress={() => setPassModal(true)}
        />
        <SettingsRow
          icon="language-outline"
          title={p('language')}
          subtitle={LANGUAGES.find((l) => l.code === lang)?.label}
          onPress={() => setLangModal(true)}
        />
        <View style={styles.row}>
          <Ionicons name="notifications-outline" size={22} color={colors.primary} />
          <View style={styles.rowBody}>
            <Text style={styles.rowTitle}>{p('notifications')}</Text>
            <Text style={styles.muted}>
              {notifOn ? p('notif_on') : p('notif_off')}
            </Text>
          </View>
          <Switch
            value={notifOn}
            onValueChange={toggleNotifications}
            trackColor={{ false: colors.border, true: colors.primary }}
          />
        </View>
        <SettingsRow
          icon="person-remove-outline"
          title={p('deactivate')}
          onPress={deactivate}
        />

        <Text style={styles.section}>{p('section_channel')}</Text>
        {CHANNELS.map((c) => (
          <TouchableOpacity
            key={c.id}
            style={[styles.row, channel === c.id && styles.rowActive]}
            onPress={() => selectChannel(c.id)}
          >
            <Ionicons name={c.icon} size={22} color={colors.primary} />
            <View style={styles.rowBody}>
              <Text style={styles.rowTitle}>{c.label}</Text>
              <Text style={styles.muted}>{c.id === 'beta' ? p('beta_desc') : c.desc}</Text>
            </View>
            {channel === c.id ? (
              <Ionicons name="checkmark-circle" size={22} color={colors.primary} />
            ) : null}
          </TouchableOpacity>
        ))}
        <Text style={[styles.muted, styles.versionText]}>
          {p('version', { value: getLocalVersion() })}
        </Text>
        <Button
          title={p('check_updates')}
          onPress={checkUpdates}
          loading={checking}
          disabled={checking}
          style={styles.updateBtn}
        />

        <Text style={styles.section}>{p('section_account')}</Text>
        <Button title={p('logout')} variant="danger" onPress={logout} style={styles.logout} />
      </ScrollView>

      <Modal visible={langModal} transparent animationType="slide">
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>{p('language_title')}</Text>
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
            <Button title={t('common', 'cancel')} variant="ghost" onPress={() => setLangModal(false)} />
          </View>
        </View>
      </Modal>

      <Modal visible={passModal} transparent animationType="slide">
        <KeyboardAvoidingView
          style={styles.modalWrap}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>{p('password_title')}</Text>
            <TextInput
              style={styles.input}
              value={currentPass}
              onChangeText={setCurrentPass}
              secureTextEntry
              placeholder={p('password_current')}
              placeholderTextColor={colors.muted}
            />
            <TextInput
              style={styles.input}
              value={newPass}
              onChangeText={setNewPass}
              secureTextEntry
              placeholder={p('password_new')}
              placeholderTextColor={colors.muted}
            />
            <TextInput
              style={styles.input}
              value={confirmPass}
              onChangeText={setConfirmPass}
              secureTextEntry
              placeholder={p('password_confirm')}
              placeholderTextColor={colors.muted}
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Button title={t('common', 'save')} onPress={submitPassword} loading={busy} />
            <Button title={t('common', 'cancel')} variant="ghost" onPress={() => setPassModal(false)} />
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
  nameInput: { width: '100%', marginTop: spacing.sm },
  name: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  muted: { color: colors.muted, marginTop: 2 },
  email: { color: colors.muted, marginTop: spacing.xs },
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
  rowActive: {
    borderColor: colors.primary,
    backgroundColor: '#f0fdfa',
  },
  rowBody: { flex: 1, marginLeft: spacing.md },
  rowTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  versionText: { marginTop: spacing.md },
  updateBtn: { marginTop: spacing.sm },
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
