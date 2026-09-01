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
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError('');
    if (!username || !password) {
      setError('Completează username-ul și parola.');
      return;
    }
    setLoading(true);
    try {
      if (mode === 'login') {
        await signIn(username, password);
      } else {
        if (!email) {
          setError('Completează email-ul.');
          return;
        }
        await signUp(username, password, email, fullName);
      }
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
            : 'Creează un cont nou'}
        </Text>

        <View style={styles.form}>
          <Input
            label="Username"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Input
            label="Parolă"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />
          {mode === 'register' ? (
            <>
              <Input
                label="Nume complet (opțional)"
                value={fullName}
                onChangeText={setFullName}
              />
              <Input
                label="Email"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </>
          ) : null}

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Button
            title={mode === 'login' ? 'Autentificare' : 'Creare cont'}
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
});
