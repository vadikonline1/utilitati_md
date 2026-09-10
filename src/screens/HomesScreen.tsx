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

import { Account, Home, Invoice, listAccounts, listHomes, listInvoices } from '../api/client';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { useContent } from '../content/useContent';
import { colors, radii, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Nav = {
  navigate: (name: string, params?: object) => void;
};

export default function HomesScreen({ navigation }: { navigation: Nav }) {
  const { t } = useContent();
  const [homes, setHomes] = useState<Home[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const [h, accs, inv] = await Promise.all([
        listHomes(),
        listAccounts().catch(() => [] as Account[]),
        listInvoices().catch(() => ({ invoices: [] as Invoice[] })),
      ]);
      setHomes(h);
      setAccounts(accs);
      setInvoices(inv.invoices);
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

  const homeStats = useCallback(
    (homeId: number) => {
      const accs = accounts.filter((a) => a.home_id === homeId);
      const ids = new Set(accs.map((a) => a.id));
      let unpaidCount = 0;
      let unpaidSum = 0;
      for (const inv of invoices) {
        if (!ids.has(inv.account_id)) continue;
        const paid = inv.is_paid === 1 || inv.pay_status === 'PAID';
        if (!paid) {
          unpaidCount += 1;
          unpaidSum += Number(inv.amount_mdl) || 0;
        }
      }
      return { accounts: accs.length, unpaidCount, unpaidSum };
    },
    [accounts, invoices],
  );

  const renderHome = ({ item }: { item: Home }) => {
    const st = homeStats(item.id);
    return (
      <TouchableOpacity
        onPress={() => navigation.navigate('HomeDetail', { id: item.id, name: item.name })}
        activeOpacity={0.7}
      >
        <Card>
          <View style={styles.row}>
            <View style={styles.homeIcon}>
              <Ionicons name="home" size={24} color={colors.primary} />
            </View>
            <View style={styles.flex}>
              <Text style={styles.name}>{item.name}</Text>
              {item.address ? <Text style={styles.muted} numberOfLines={1}>{item.address}</Text> : null}
              <Text style={styles.stats}>
                {t('homes', 'accounts_chip', { count: st.accounts })} ·{' '}
                {st.unpaidCount > 0
                  ? `${st.unpaidCount} neachitate · ${st.unpaidSum.toFixed(2)} MDL`
                  : 'totul achitat'}
              </Text>
              <View style={styles.chips}>
                {(item.unpaid_invoices ?? 0) > 0 ? (
                  <View style={[styles.chip, styles.chipWarn]}>
                    <Text style={[styles.chipText, styles.chipTextWarn]}>
                      {t('homes', 'unpaid_chip', { count: item.unpaid_invoices ?? 0 })}
                    </Text>
                  </View>
                ) : (
                  <View style={[styles.chip, styles.chipOk]}>
                    <Text style={[styles.chipText, styles.chipTextOk]}>la zi</Text>
                  </View>
                )}
              </View>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.muted} />
          </View>
        </Card>
      </TouchableOpacity>
    );
  };

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
            <Text style={styles.empty}>{t('common', 'loading')}</Text>
          ) : (
            <Text style={styles.empty}>{t('homes', 'empty')}</Text>
          )
        }
        ListFooterComponent={<AdBanner placement="homes" />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 100 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  homeIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  name: { fontSize: 18, fontWeight: '700', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  stats: { fontSize: 14, fontWeight: '600', color: colors.text, marginTop: spacing.xs },
  chips: { flexDirection: 'row', marginTop: spacing.sm, flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    backgroundColor: colors.primary,
    borderRadius: radii.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipWarn: { backgroundColor: '#fef3c7' },
  chipOk: { backgroundColor: '#dcfce7' },
  chipText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  chipTextWarn: { color: colors.warning },
  chipTextOk: { color: colors.success },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
});
