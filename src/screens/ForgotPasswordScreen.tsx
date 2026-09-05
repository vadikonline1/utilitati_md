import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError, forgotPassword } from '../api/client';
import Button from '../components/Button';
import Input from '../components/Input';
import { colors, spacing } from '../theme';

interface Props {
  navigation: { goBack: () => void; navigate: (name: string, params?: object) => void };
}

export default function ForgotPasswordScreen({ navigation }: Props) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError('');
    if (!/@.+\..+/.test(email)) {
      setError('Introdu o adresă de email validă.');
      return;
    }
    setLoading(true);
    try {
      await forgotPassword(email);
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
        <Text style={styles.title}>Resetare parolă</Text>
        {done ? (
          <Text style={styles.done}>
            Dacă adresa de email este asociată unui cont, ți-am trimis un link de
            resetare. Verifică inbox-ul (și folderul spam).
          </Text>
        ) : (
          <View>
            <Text style={styles.muted}>
              Introdu adresa de email asociată contului tău. Vei primi un link pentru
              a-ți reseta parola.
            </Text>
            <Input
              label="Email"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Button title="Trimite link" onPress={submit} loading={loading} />
          </View>
        )}
        <Button title="Înapoi" variant="ghost" onPress={() => navigation.goBack()} />
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
  muted: { color: colors.muted, marginBottom: spacing.md, textAlign: 'center' },
  done: { color: colors.success, textAlign: 'center', marginBottom: spacing.lg },
  error: { color: colors.danger, textAlign: 'center', marginVertical: spacing.sm },
});