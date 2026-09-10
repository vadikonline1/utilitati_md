import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { Home, Invoice, listAccounts, listHomes, listInvoices } from '../api/client';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { useContent } from '../content/useContent';
import { colors, fontFamily, radii, spacing } from '../theme';
import { showInterstitialOnce, showRewardedOnce } from '../utils/ads';

type Nav = {
  navigate: (name: string, params?: object) => void;
};

interface Stats {
  unpaidBalance: number;
  openInvoices: number;
  paidInvoices: number;
  paidAmount: number;
  arrears: number;
  arrearsCount: number;
  homeCount: number;
}

function todayISO(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function isPaid(inv: Invoice): boolean {
  return inv.is_paid === 1 || inv.pay_status === 'PAID';
}

function computeStats(invoices: Invoice[], homeCount: number): Stats {
  const today = todayISO();
  let unpaidBalance = 0;
  let openInvoices = 0;
  let paidInvoices = 0;
  let paidAmount = 0;
  let arrears = 0;
  let arrearsCount = 0;
  for (const inv of invoices) {
    const amount = Number(inv.amount_mdl) || 0;
    if (!isPaid(inv)) {
      unpaidBalance += amount;
      openInvoices += 1;
      if (inv.due_date && inv.due_date < today) {
        arrears += amount;
        arrearsCount += 1;
      }
    } else {
      paidInvoices += 1;
      paidAmount += amount;
    }
  }
  return { unpaidBalance, openInvoices, paidInvoices, paidAmount, arrears, arrearsCount, homeCount };
}

function StatCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <Card style={styles.statCard}>
      <Text style={[styles.statValue, accent ? { color: accent } : null]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </Card>
  );
}

export default function DashboardScreen({ navigation }: { navigation: Nav }) {
  const { t } = useContent();
  const [homes, setHomes] = useState<Home[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [accountLabel, setAccountLabel] = useState<Map<number, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [supportBusy, setSupportBusy] = useState(false);

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      try {
        const [h, inv, accs] = await Promise.all([listHomes(), listInvoices(), listAccounts().catch(() => [])]);
        setHomes(h);
        setInvoices(inv.invoices);
        const map = new Map<number, string>();
        for (const a of accs) map.set(a.id, a.label || a.provider);
        setAccountLabel(map);
      } catch {
        Alert.alert('Eroare', t('dashboard', 'error_load'));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [t],
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const stats = useMemo(() => computeStats(invoices, homes.length), [invoices, homes]);

  const byProvider = useMemo(() => {
    const map = new Map<string, { unpaid: number; open: number }>();
    for (const inv of invoices) {
      if (isPaid(inv)) continue;
      const label = accountLabel.get(inv.account_id) || t('invoices', 'group_others');
      const cur = map.get(label) || { unpaid: 0, open: 0 };
      cur.unpaid += Number(inv.amount_mdl) || 0;
      cur.open += 1;
      map.set(label, cur);
    }
    return [...map.entries()].sort((a, b) => b[1].unpaid - a[1].unpaid).slice(0, 5);
  }, [invoices, accountLabel, t]);

  const recent = useMemo(() => {
    const sorted = [...invoices].sort((a, b) =>
      String(b.created_at || b.issue_date || '').localeCompare(String(a.created_at || a.issue_date || '')),
    );
    return sorted.slice(0, 5);
  }, [invoices]);

  const unpaidTable = useMemo(() => {
    return invoices
      .filter((inv) => !isPaid(inv))
      .sort((a, b) =>
        String(a.due_date || a.issue_date || '').localeCompare(String(b.due_date || b.issue_date || '')),
      );
  }, [invoices]);

  const paidTable = useMemo(() => {
    return invoices
      .filter(isPaid)
      .sort((a, b) =>
        String(b.checked_at || b.created_at || '').localeCompare(String(a.checked_at || a.created_at || '')),
      );
  }, [invoices]);

  const supportEnabled = t('dashboard', 'support_enabled') === '1';

  const onShowSupport = useCallback(async () => {
    if (supportBusy) return;
    setSupportBusy(true);
    try {
      const shown = await showInterstitialOnce();
      if (shown) await showRewardedOnce();
    } finally {
      setSupportBusy(false);
    }
  }, [supportBusy]);

  const parentNav = (name: string, params?: object) => navigation.navigate(name, params);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.list}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />}
    >
      <View style={styles.grid}>
        <StatCard label={t('dashboard', 'stat_unpaid_balance')} value={`${stats.unpaidBalance.toFixed(2)} MDL`} accent={colors.danger} />
        <StatCard label={t('dashboard', 'stat_open_invoices')} value={String(stats.openInvoices)} />
        <StatCard label={t('dashboard', 'stat_paid_invoices')} value={String(stats.paidInvoices)} accent={colors.success} />
        <StatCard label={t('dashboard', 'stat_arrears')} value={`${stats.arrears.toFixed(2)} MDL`} accent={colors.warning} />
        <StatCard label={t('dashboard', 'stat_homes')} value={String(stats.homeCount)} />
        <StatCard label="Achitat total (MDL)" value={`${stats.paidAmount.toFixed(2)}`} accent={colors.success} />
      </View>

      {supportEnabled ? (
        <Pressable
          style={({ pressed }) => [styles.supportBtn, supportBusy && styles.supportBtnBusy, pressed && styles.pressed]}
          android_ripple={{ color: 'rgba(255,255,255,0.25)' }}
          onPress={onShowSupport}
          disabled={supportBusy}
        >
          <View style={styles.supportTitleRow}>
            <Ionicons name="heart-outline" size={20} color="#fff" />
            <Text style={styles.supportTitle}>{t('dashboard', 'support_title')}</Text>
          </View>
          <Text style={styles.supportText}>{t('dashboard', 'support_text')}</Text>
        </Pressable>
      ) : null}

      <Card title={`Restanțe: ${stats.arrearsCount} facturi`}>
        {stats.arrearsCount === 0 ? (
          <Text style={styles.muted}>Nicio restanță. Toate facturile deschise sunt în termen.</Text>
        ) : (
          <Text style={styles.muted}>
            {stats.arrearsCount} facturi depășite totalizează {stats.arrears.toFixed(2)} MDL. Verifică tab-ul Facturi.
          </Text>
        )}
      </Card>

      <Card title="Top utilități neachitate">
        {byProvider.length === 0 ? (
          <Text style={styles.muted}>{loading ? t('common', 'loading') : 'Nicio datorie deschisă.'}</Text>
        ) : (
          byProvider.map(([label, v]) => (
            <View key={label} style={styles.kvRow}>
              <Text style={styles.kvLabel} numberOfLines={1}>{label}</Text>
              <View style={styles.chip}>
                <Text style={styles.chipText}>{v.open} deschise</Text>
              </View>
              <Text style={styles.kvValue}>{v.unpaid.toFixed(2)} MDL</Text>
            </View>
          ))
        )}
      </Card>

      <Card title={`Facturi neachitate (${unpaidTable.length})`}>
        {unpaidTable.length === 0 ? (
          <Text style={styles.muted}>{loading ? t('common', 'loading') : 'Nicio factură neachitată. Totul e la zi!'}</Text>
        ) : (
          unpaidTable.map((inv) => (
            <Pressable
              key={inv.id}
              style={({ pressed }) => [styles.recentRow, pressed && styles.pressed]}
              android_ripple={{ color: 'rgba(15,118,110,0.12)' }}
              onPress={() => parentNav('AccountDetail', { id: inv.account_id, label: accountLabel.get(inv.account_id) || '' })}
            >
              <View style={styles.flex}>
                <Text style={styles.recentTitle}>{inv.invoice_number || inv.period || t('invoices', 'default_title')}</Text>
                <Text style={styles.muted}>{accountLabel.get(inv.account_id) || ''}</Text>
              </View>
              <View style={styles.invRight}>
                <Text style={styles.amount}>{Number(inv.amount_mdl).toFixed(2)} {inv.currency}</Text>
                <Text style={[styles.status, styles.unpaid]}>{t('invoices', 'unpaid')}</Text>
              </View>
            </Pressable>
          ))
        )}
      </Card>

      <Card title={`Facturi achitate (${paidTable.length})`}>
        {paidTable.length === 0 ? (
          <Text style={styles.muted}>{loading ? t('common', 'loading') : 'Nicio factură achitată încă.'}</Text>
        ) : (
          paidTable.slice(0, 10).map((inv) => (
            <Pressable
              key={inv.id}
              style={({ pressed }) => [styles.recentRow, pressed && styles.pressed]}
              android_ripple={{ color: 'rgba(15,118,110,0.12)' }}
              onPress={() => parentNav('AccountDetail', { id: inv.account_id, label: accountLabel.get(inv.account_id) || '' })}
            >
              <View style={styles.flex}>
                <Text style={styles.recentTitle}>{inv.invoice_number || inv.period || t('invoices', 'default_title')}</Text>
                <Text style={styles.muted}>{accountLabel.get(inv.account_id) || ''}</Text>
              </View>
              <View style={styles.invRight}>
                <Text style={styles.amount}>{Number(inv.amount_mdl).toFixed(2)} {inv.currency}</Text>
                <Text style={[styles.status, styles.paid]}>{t('invoices', 'paid')}</Text>
              </View>
            </Pressable>
          ))
        )}
        {paidTable.length > 10 ? (
          <Text style={styles.muted}>+ alte {paidTable.length - 10} în tab-ul Facturi.</Text>
        ) : null}
      </Card>

      <Card title="Facturi recente">
        {recent.length === 0 ? (
          <Text style={styles.muted}>{loading ? t('common', 'loading') : t('invoices', 'empty')}</Text>
        ) : (
          recent.map((inv) => {
            const paid = isPaid(inv);
            return (
              <Pressable
                key={inv.id}
                style={({ pressed }) => [styles.recentRow, pressed && styles.pressed]}
                android_ripple={{ color: 'rgba(15,118,110,0.12)' }}
                onPress={() => parentNav('AccountDetail', { id: inv.account_id, label: accountLabel.get(inv.account_id) || '' })}
              >
                <View style={styles.flex}>
                  <Text style={styles.recentTitle}>{inv.invoice_number || inv.period || t('invoices', 'default_title')}</Text>
                  <Text style={styles.muted}>{accountLabel.get(inv.account_id) || ''}</Text>
                </View>
                <View style={styles.invRight}>
                  <Text style={styles.amount}>{Number(inv.amount_mdl).toFixed(2)} {inv.currency}</Text>
                  <Text style={[styles.status, paid ? styles.paid : styles.unpaid]}>
                    {paid ? t('invoices', 'paid') : t('invoices', 'unpaid')}
                  </Text>
                </View>
              </Pressable>
            );
          })
        )}
      </Card>

      <Card title="Locuințele mele">
        {homes.length === 0 ? (
          <Text style={styles.muted}>{loading ? t('common', 'loading') : t('dashboard', 'empty')}</Text>
        ) : (
          homes.map((item) => (
            <Pressable
              key={item.id}
              style={({ pressed }) => [styles.homeRow, pressed && styles.pressed]}
              android_ripple={{ color: 'rgba(15,118,110,0.12)' }}
              onPress={() => parentNav('HomeDetail', { id: item.id, name: item.name })}
            >
              <View style={styles.flex}>
                <Text style={styles.homeName}>{item.name}</Text>
                {item.address ? <Text style={styles.muted}>{item.address}</Text> : null}
              </View>
              <Text style={styles.vezi}>{t('dashboard', 'vezi')}</Text>
            </Pressable>
          ))
        )}
      </Card>

      <AdBanner placement="dashboard" />
      <View style={{ height: 90 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  statCard: { width: '48%' },
  statValue: { fontSize: 18, fontWeight: '800', color: colors.text, fontFamily },
  statLabel: { fontSize: 13, color: colors.muted, marginTop: spacing.xs, fontFamily },
  muted: { color: colors.muted, marginTop: 2, fontFamily },
  flex: { flex: 1 },
  homeRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.sm },
  homeName: { fontSize: 17, fontWeight: '700', color: colors.text, fontFamily },
  vezi: { color: colors.primary, fontWeight: '700', fontFamily },
  kvRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.sm },
  kvLabel: { flex: 1, fontSize: 15, color: colors.text, fontFamily },
  kvValue: { fontSize: 15, fontWeight: '700', color: colors.text, fontFamily, marginLeft: spacing.sm },
  chip: { backgroundColor: colors.primary, borderRadius: radii.chip, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, marginLeft: spacing.sm },
  chipText: { color: '#fff', fontSize: 12, fontWeight: '600', fontFamily },
  recentRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.sm },
  recentTitle: { fontSize: 15, fontWeight: '600', color: colors.text, fontFamily },
  invRight: { alignItems: 'flex-end' },
  amount: { fontSize: 16, fontWeight: '700', color: colors.text, fontFamily },
  status: { fontSize: 13, fontWeight: '600', marginTop: 2, fontFamily },
  paid: { color: colors.success },
  unpaid: { color: colors.danger },
  pressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  supportBtn: {
    marginTop: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.primary,
    borderRadius: radii.pill,
    alignItems: 'center',
  },
  supportBtnBusy: { opacity: 0.6 },
  supportTitleRow: { flexDirection: 'row', alignItems: 'center' },
  supportTitle: { color: '#fff', fontSize: 15, fontWeight: '700', marginLeft: spacing.sm, fontFamily },
  supportText: { color: 'rgba(255,255,255,0.85)', fontSize: 13, fontWeight: '500', marginTop: spacing.xs, textAlign: 'center', fontFamily },
});
