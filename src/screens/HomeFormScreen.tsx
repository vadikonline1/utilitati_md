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
import { useContent } from '../content/useContent';
import { colors, spacing } from '../theme';

type ParamList = {
  HomeForm: { id?: number };
};

interface Props {
  navigation: { goBack: () => void; navigate: (name: string, params?: object) => void };
  route: RouteProp<ParamList, 'HomeForm'>;
}

export default function HomeFormScreen({ navigation, route }: Props) {
  const { t } = useContent();
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
        .catch(() => Alert.alert('Eroare', t('home_form', 'error_load')));
    }
  }, [isEdit, homeId, t]);

  const save = async () => {
    if (!name.trim()) {
      Alert.alert('Atenție', t('home_form', 'warn_required_name'));
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
      Alert.alert('Eroare', e instanceof ApiError ? e.message : t('home_form', 'error_save'));
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
          <Text style={styles.muted}>{t('common', 'loading')}</Text>
        ) : (
          <View>
            <Text style={styles.title}>
              {isEdit ? t('home_form', 'title_edit') : t('home_form', 'title_new')}
            </Text>
            <Input
              label={t('home_form', 'label_name')}
              value={name}
              onChangeText={setName}
              placeholder={t('home_form', 'placeholder_name')}
            />
            <Input label={t('home_form', 'label_address')} value={address} onChangeText={setAddress} />
            <Input
              label={t('home_form', 'label_floor')}
              value={floor}
              onChangeText={setFloor}
              keyboardType="number-pad"
            />
            <Input label={t('home_form', 'label_sector')} value={metroArea} onChangeText={setMetroArea} />
            <Button title={t('common', 'save')} onPress={save} loading={saving} />
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
