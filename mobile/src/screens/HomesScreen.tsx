import React, { useCallback, useState } from 'react';
import {
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import { Home, listHomes } from '../api/client';
import Card from '../components/Card';
import { colors, spacing } from '../theme';

type Nav = {
  navigate: (name: string, params?: object) => void;
};

export default function HomesScreen({ navigation }: { navigation: Nav }) {
  const [homes, setHomes] = useState<Home[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      setHomes(await listHomes());
    } catch {
      Alert.alert('Eroare', 'Nu s-au putut încărca locuințele.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const renderHome = ({ item }: { item: Home }) => (
    <TouchableOpacity
      onPress={() => navigation.navigate('HomeDetail', { id: item.id, name: item.name })}
    >
      <Card>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.name}>{item.name}</Text>
            {item.address ? <Text style={styles.muted}>{item.address}</Text> : null}
            <View style={styles.chips}>
              <View style={styles.chip}>
                <Text style={styles.chipText}>{item.utilities_count ?? 0} conturi</Text>
              </View>
              {(item.unpaid_invoices ?? 0) > 0 ? (
                <View style={[styles.chip, styles.chipWarn]}>
                  <Text style={[styles.chipText, styles.chipTextWarn]}>
                    {item.unpaid_invoices} neplătite
                  </Text>
                </View>
              ) : null}
            </View>
          </View>
        </View>
      </Card>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={homes}
        keyExtractor={(h) => String(h.id)}
        renderItem={renderHome}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        ListEmptyComponent={
          loading ? (
            <Text style={styles.empty}>Se încarcă…</Text>
          ) : (
            <Text style={styles.empty}>Nu ai nicio locuință încă.</Text>
          )
        }
      />
      <TouchableOpacity
        style={styles.fab}
        onPress={() => navigation.navigate('HomeForm', {})}
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 100 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  name: { fontSize: 18, fontWeight: '700', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  chips: { flexDirection: 'row', marginTop: spacing.sm, flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipWarn: { backgroundColor: '#fef3c7' },
  chipText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  chipTextWarn: { color: colors.warning },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
  fab: {
    position: 'absolute',
    right: spacing.xl,
    bottom: spacing.xl,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
  },
  fabText: { color: '#fff', fontSize: 28, lineHeight: 30 },
});
