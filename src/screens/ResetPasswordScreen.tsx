import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { RouteProp } from '@react-navigation/native';

import { ApiError, resetPassword } from '../api/client';
import Button from '../components/Button';
import Input from '../components/Input';
import { colors, spacing } from '../theme';

type ParamList = {
  ResetPassword: { token?: string } | undefined;
};

interface Props {
  navigation: { goBack: () => void; navigate: (name: string) => void };
  route: RouteProp<ParamList, 'ResetPassword'>;
}

export default function ResetPasswordScreen({ navigation, route }: Props) {
  const [token, setToken] = useState(route.params?.token || '');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError('');
    if (!token.trim()) {
      setError('Lipsește codul/linkul de resetare.');
      return;
    }
    if (password.length < 6) {
      setError('Parola trebuie să aibă minim 6 caractere.');
      return;
    }
    if (password !== confirm) {
      setError('Parolele nu se potrivesc.');
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token.trim(), password);
      setDone(true);
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
        <Text style={styles.title}>Parolă nouă</Text>
        {done ? (
          <Text style={styles.done}>
            Parola a fost schimbată. Te poți autentifica acum.
          </Text>
        ) : (
          <View>
            <Input
              label="Cod/link de resetare"
              value={token}
              onChangeText={setToken}
              autoCapitalize="none"
              autoCorrect={false}
            />
            <Input
              label="Parolă nouă"
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            <Input
              label="Confirmă parola"
              value={confirm}
              onChangeText={setConfirm}
              secureTextEntry
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Button title="Resetează parola" onPress={submit} loading={loading} />
          </View>
        )}
        <Button
          title={done ? 'Autentifică-te' : 'Înapoi'}
          variant="ghost"
          onPress={() => (done ? navigation.navigate('Login') : navigation.goBack())}
        />
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
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  done: { color: colors.success, textAlign: 'center', marginBottom: spacing.lg },
  error: { color: colors.danger, textAlign: 'center', marginVertical: spacing.sm },
});