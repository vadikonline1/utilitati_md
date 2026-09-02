import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError } from '../api/client';
import { useAuth } from '../api/auth-context';
import Button from '../components/Button';
import Input from '../components/Input';
import { colors, spacing } from '../theme';

export default function LoginScreen({ navigation }: { navigation?: { navigate: (name: string, params?: object) => void } }) {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [info, setInfo] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError('');
    setInfo('');
    if (mode === 'login') {
      if (!username || !password) {
        setError('Completează username-ul și parola.');
        return;
      }
      setLoading(true);
      try {
        await signIn(username, password);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'A apărut o eroare.');
      } finally {
        setLoading(false);
      }
      return;
    }
    // register (email invitation, same as web — no password)
    if (!firstName.trim() || !lastName.trim()) {
      setError('Completează prenumele și numele.');
      return;
    }
    if (!email.trim()) {
      setError('Completează email-ul.');
      return;
    }
    if (email.indexOf('@') < 1 || !email.split('@')[1]?.includes('.')) {
      setError('Adresa de email nu este validă.');
      return;
    }
    if (!username.trim()) {
      setError('Completează username-ul.');
      return;
    }
    setLoading(true);
    try {
      await signUp(username, firstName.trim(), lastName.trim(), email.trim());
      setInfo('Contul a fost creat. Verifică-ți emailul pentru link-ul de confirmare și parola.');
      setPassword('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'A apărut o eroare.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.logo}>Utilități.MD</Text>
        <Text style={styles.subtitle}>
          {mode === 'login'
            ? 'Autentifică-te pentru a vedea facturile tale'
            : 'Creare cont (confirmare pe email)'}
        </Text>

        <View style={styles.form}>
          <Input
            label="Username"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {mode === 'register' ? (
            <>
              <Input
                label="Prenume"
                value={firstName}
                onChangeText={setFirstName}
              />
              <Input
                label="Nume"
                value={lastName}
                onChangeText={setLastName}
              />
              <Input
                label="Email"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </>
          ) : (
            <Input
              label="Parolă"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
          )}

          {info ? <Text style={styles.info}>{info}</Text> : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Button
            title={mode === 'login' ? 'Autentificare' : 'Trimite confirmare'}
            onPress={submit}
            loading={loading}
          />
          <Button
            title={
              mode === 'login'
                ? 'Nu ai cont? Înregistrează-te'
                : 'Ai deja cont? Autentifică-te'
            }
            variant="ghost"
            onPress={() => {
              setError('');
              setInfo('');
              setMode(mode === 'login' ? 'register' : 'login');
            }}
          />
          {mode === 'login' ? (
            <Button
              title="Ai uitat parola?"
              variant="ghost"
              onPress={() => navigation?.navigate('ForgotPassword')}
            />
          ) : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: spacing.xl,
  },
  logo: {
    fontSize: 32,
    fontWeight: '800',
    color: colors.primary,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    color: colors.muted,
    textAlign: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
  form: { width: '100%' },
  error: {
    color: colors.danger,
    textAlign: 'center',
    marginVertical: spacing.sm,
  },
  info: {
    color: colors.success,
    textAlign: 'center',
    marginVertical: spacing.sm,
  },
});
