import React, { useEffect, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { RouteProp } from '@react-navigation/native';

import { ApiError, createHome, getHome, updateHome } from '../api/client';
import Button from '../components/Button';
import Input from '../components/Input';
import { colors, spacing } from '../theme';

type ParamList = {
  HomeForm: { id?: number };
};

interface Props {
  navigation: { goBack: () => void; navigate: (name: string, params?: object) => void };
  route: RouteProp<ParamList, 'HomeForm'>;
}

export default function HomeFormScreen({ navigation, route }: Props) {
  const homeId = route.params?.id;
  const isEdit = homeId != null;

  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [floor, setFloor] = useState('');
  const [metroArea, setMetroArea] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isEdit) {
      getHome(homeId)
        .then(({ home }) => {
          setName(home.name || '');
          setAddress(home.address || '');
          setFloor(home.floor || '');
          setMetroArea(home.metro_area || '');
        })
        .catch(() => Alert.alert('Eroare', 'Locuința nu a putut fi încărcată.'));
    }
  }, [isEdit, homeId]);

  const save = async () => {
    if (!name.trim()) {
      Alert.alert('Atenție', 'Numele este obligatoriu.');
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await updateHome(homeId, { name, address, floor, metro_area: metroArea });
      } else {
        await createHome({ name, address, floor, metro_area: metroArea });
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
        {loading ? (
          <Text style={styles.muted}>Se încarcă…</Text>
        ) : (
          <View>
            <Text style={styles.title}>
              {isEdit ? 'Editează locuința' : 'Locuință nouă'}
            </Text>
            <Input label="Nume *" value={name} onChangeText={setName} placeholder="ex. Apartament 12" />
            <Input label="Adresă" value={address} onChangeText={setAddress} />
            <Input label="Etaj" value={floor} onChangeText={setFloor} keyboardType="number-pad" />
            <Input label="Sector" value={metroArea} onChangeText={setMetroArea} />
            <Button title="Salvează" onPress={save} loading={saving} />
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.xl },
  title: { fontSize: 24, fontWeight: '800', color: colors.text, marginBottom: spacing.lg },
  muted: { color: colors.muted, textAlign: 'center', marginTop: spacing.xl },
});
