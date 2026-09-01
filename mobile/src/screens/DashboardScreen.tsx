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

import { Home, Invoice, listHomes, listInvoices } from '../api/client';
import AppHeader from '../components/AppHeader';
import Card from '../components/Card';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Nav = {
  navigate: (name: string, params?: object) => void;
};

interface Stats {
  unpaidBalance: number;
  openInvoices: number;
  paidInvoices: number;
  arrears: number;
  homeCount: number;
}

function todayISO(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function computeStats(invoices: Invoice[]): Omit<Stats, 'homeCount'> {
  const today = todayISO();
  let unpaidBalance = 0;
  let openInvoices = 0;
  let paidInvoices = 0;
  let arrears = 0;
  for (const inv of invoices) {
    const paid = inv.is_paid === 1 || inv.pay_status === 'PAID';
    const amount = Number(inv.amount_mdl) || 0;
    if (!paid) {
      unpaidBalance += amount;
      openInvoices += 1;
      if (inv.due_date && inv.due_date < today) arrears += amount;
    } else {
      paidInvoices += 1;
    }
  }
  return { unpaidBalance, openInvoices, paidInvoices, arrears };
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <Card style={styles.statCard}>
      <Text style={[styles.statValue, accent ? { color: accent } : null]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </Card>
  );
}

export default function DashboardScreen({ navigation }: { navigation: Nav }) {
  const [homes, setHomes] = useState<Home[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const h = await listHomes();
      const inv = await listInvoices();
      setHomes(h);
      setInvoices(inv.invoices);
    } catch {
      Alert.alert('Eroare', 'Nu s-au putut încărca datele.');
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

  const stats: Stats = { homeCount: homes.length, ...computeStats(invoices) };
  const grid: (keyof Stats)[] = ['unpaidBalance', 'openInvoices', 'paidInvoices', 'arrears'];

  return (
    <View style={styles.container}>
      <AppHeader />
      <FlatList
        data={homes}
        keyExtractor={(h) => String(h.id)}
        renderItem={({ item }) => (
          <TouchableOpacity
            onPress={() => navigation.navigate('HomeDetail', { id: item.id, name: item.name })}
          >
            <Card>
              <View style={styles.row}>
                <View style={styles.flex}>
                  <Text style={styles.homeName}>{item.name}</Text>
                  {item.address ? <Text style={styles.muted}>{item.address}</Text> : null}
                </View>
                <Text style={styles.vezi}>vezi</Text>
              </View>
            </Card>
          </TouchableOpacity>
        )}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.grid}>
            <StatCard label="Sold total neachitat" value={`${stats.unpaidBalance.toFixed(2)} MDL`} accent={colors.danger} />
            <StatCard label="Facturi deschise" value={String(stats.openInvoices)} />
            <StatCard label="Facturi achitate" value={String(stats.paidInvoices)} accent={colors.success} />
            <StatCard label="Restanțe" value={`${stats.arrears.toFixed(2)} MDL`} accent={colors.warning} />
            <StatCard label="Locuințe" value={String(stats.homeCount)} />
          </View>
        }
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loading ? 'Se încarcă…' : 'Nu ai nicio locuință încă.'}
          </Text>
        }
      />
      <TouchableOpacity style={styles.fab} onPress={() => navigation.navigate('HomeForm', {})}>
        <Ionicons name="add" size={30} color="#fff" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 100 },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  statCard: { width: '48%' },
  statValue: { fontSize: 20, fontWeight: '800', color: colors.text },
  statLabel: { fontSize: 13, color: colors.muted, marginTop: spacing.xs },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  homeName: { fontSize: 18, fontWeight: '700', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  vezi: { color: colors.primary, fontWeight: '700' },
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
});
