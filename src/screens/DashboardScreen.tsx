import React, { useCallback, useEffect, useState } from 'react';
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
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';
import { loadAdConfig, showInterstitialOnce, showRewardedOnce } from '../utils/ads';

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
  const [menuOpen, setMenuOpen] = useState(false);
  const [supportAds, setSupportAds] = useState(false);
  const [supportBusy, setSupportBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      const cfg = await loadAdConfig();
      if (mounted) {
        setSupportAds(
          !!cfg && cfg.enabled && cfg.interstitial.enabled && cfg.rewarded.enabled,
        );
      }
    })().catch(() => undefined);
    return () => {
      mounted = false;
    };
  }, []);

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

  const onShowSupport = useCallback(async () => {
    if (supportBusy) return;
    setSupportBusy(true);
    try {
      const shown = await showInterstitialOnce();
      if (shown) {
        await showRewardedOnce();
      }
    } finally {
      setSupportBusy(false);
    }
  }, [supportBusy]);

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
          <View>
            <View style={styles.grid}>
              <StatCard label="Sold total neachitat" value={`${stats.unpaidBalance.toFixed(2)} MDL`} accent={colors.danger} />
              <StatCard label="Facturi deschise" value={String(stats.openInvoices)} />
              <StatCard label="Facturi achitate" value={String(stats.paidInvoices)} accent={colors.success} />
              <StatCard label="Restanțe" value={`${stats.arrears.toFixed(2)} MDL`} accent={colors.warning} />
              <StatCard label="Locuințe" value={String(stats.homeCount)} />
            </View>
            {supportAds ? (
              <TouchableOpacity
                style={[styles.supportBtn, supportBusy ? styles.supportBtnBusy : null]}
                onPress={onShowSupport}
                disabled={supportBusy}
              >
                <Ionicons name="heart-outline" size={20} color="#fff" />
                <Text style={styles.supportText}>Susține proiectul nostru</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loading ? 'Se încarcă…' : 'Nu ai nicio locuință încă.'}
          </Text>
        }
        ListFooterComponent={<AdBanner placement="dashboard" />}
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
            <Text style={styles.menuText}>Locuință</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.menuItem}
            onPress={() => {
              setMenuOpen(false);
              navigation.navigate('AccountForm', {});
            }}
          >
            <Ionicons name="flash-outline" size={20} color={colors.primary} />
            <Text style={styles.menuText}>Utilitate</Text>
          </TouchableOpacity>
        </View>
      ) : null}
      <TouchableOpacity style={styles.fab} onPress={() => setMenuOpen((v) => !v)}>
        <Ionicons name={menuOpen ? 'close' : 'add'} size={30} color="#fff" />
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
  supportBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.primary,
    borderRadius: 12,
  },
  supportBtnBusy: { opacity: 0.6 },
  supportText: { color: '#fff', fontSize: 15, fontWeight: '700', marginLeft: spacing.sm },
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
