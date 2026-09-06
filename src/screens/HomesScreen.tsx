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
import AppHeader from '../components/AppHeader';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { useContent } from '../content/useContent';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Nav = {
  navigate: (name: string, params?: object) => void;
};

export default function HomesScreen({ navigation }: { navigation: Nav }) {
  const { t } = useContent();
  const [homes, setHomes] = useState<Home[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      setHomes(await listHomes());
    } catch {
      Alert.alert('Eroare', t('homes', 'error_load'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

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
                <Text style={styles.chipText}>
                  {t('homes', 'accounts_chip', { count: item.utilities_count ?? 0 })}
                </Text>
              </View>
              {(item.unpaid_invoices ?? 0) > 0 ? (
                <View style={[styles.chip, styles.chipWarn]}>
                  <Text style={[styles.chipText, styles.chipTextWarn]}>
                    {t('homes', 'unpaid_chip', { count: item.unpaid_invoices })}
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
      <AppHeader />
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
            <Text style={styles.empty}>{t('common', 'loading')}</Text>
          ) : (
            <Text style={styles.empty}>{t('homes', 'empty')}</Text>
          )
        }
        ListFooterComponent={<AdBanner placement="homes" />}
      />
      {menuOpen ? (
        <View style={styles.menu}>
          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => {
              setMenuOpen(false);
              navigation.navigate('HomeForm', {});
            }}
          >
            <Ionicons name="home-outline" size={20} color={colors.primary} />
            <Text style={styles.menuText}>{t('homes', 'fab_home')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => {
              setMenuOpen(false);
              navigation.navigate('AccountForm', {});
            }}
          >
            <Ionicons name="flash-outline" size={20} color={colors.primary} />
            <Text style={styles.menuText}>{t('homes', 'fab_utility')}</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => setMenuOpen((v) => !v)}
      >
        <Ionicons name={menuOpen ? 'close' : 'add'} size={30} color="#fff" />
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
  menu: {
    position: 'absolute',
    right: spacing.xl,
    bottom: 90,
    backgroundColor: colors.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    elevation: 6,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  menuText: { color: colors.text, fontSize: 15, fontWeight: '600', marginLeft: spacing.sm },
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
});
