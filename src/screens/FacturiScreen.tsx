import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import {
  Account,
  ApiError,
  deleteInvoice,
  Home,
  Invoice,
  listAccounts,
  listHomes,
  listInvoices,
  setInvoiceStatus,
} from '../api/client';
import AdBanner from '../components/AdBanner';
import Button from '../components/Button';
import Card from '../components/Card';
import { useContent } from '../content/useContent';
import { colors, fontFamily, radii, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Section = { title: string; invoices: Invoice[] };

type Row =
  | { kind: 'section'; key: string; title: string }
  | { kind: 'invoice'; key: string; inv: Invoice }
  | { kind: 'banner'; key: string };

type StatusFilter = 'all' | 'unpaid' | 'paid';

interface Filters {
  status: StatusFilter;
  account: number | null;
  home: number | null;
}

const EMPTY_FILTERS: Filters = { status: 'all', account: null, home: null };

function buildRows(sections: Section[]): Row[] {
  const rows: Row[] = [];
  let count = 0;
  const pushBanner = () => rows.push({ kind: 'banner', key: `banner-${rows.length}` });
  for (const s of sections) {
    rows.push({ kind: 'section', key: `sec-${s.title}`, title: s.title });
    for (const inv of s.invoices) {
      rows.push({ kind: 'invoice', key: `inv-${inv.id}`, inv });
      count += 1;
      if (count % 10 === 0) pushBanner();
    }
  }
  if (count > 0 && count < 10) pushBanner();
  return rows;
}

function formatMonth(value?: string | null): string {
  const m = /^(\d{4})-(\d{2})/.exec(value || '');
  return m ? `${m[2]}.${m[1]}` : '—';
}

function isPaidInv(inv: Invoice): boolean {
  return inv.is_paid === 1 || inv.pay_status === 'PAID';
}

export default function FacturiScreen() {
  const { t } = useContent();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [homes, setHomes] = useState<Home[]>([]);
  const [accountInfo, setAccountInfo] = useState<Map<number, { label: string; contract: string }>>(new Map());
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [modal, setModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [invData, accs, hm] = await Promise.all([
        listInvoices(),
        listAccounts().catch(() => [] as Account[]),
        listHomes().catch(() => [] as Home[]),
      ]);
      setInvoices(invData.invoices);
      setAccounts(accs);
      setHomes(hm);
      const infoById = new Map<number, { label: string; contract: string }>();
      for (const a of accs) {
        infoById.set(a.id, { label: a.label || a.provider, contract: a.contract_number || '' });
      }
      setAccountInfo(infoById);
    } catch {
      Alert.alert('Eroare', t('invoices', 'error_load'));
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

  const filtered = useMemo(() => {
    const homeIds = filters.home
      ? new Set(accounts.filter((a) => a.home_id === filters.home).map((a) => a.id))
      : null;
    return invoices.filter((inv) => {
      if (filters.status === 'unpaid' && isPaidInv(inv)) return false;
      if (filters.status === 'paid' && !isPaidInv(inv)) return false;
      if (filters.account && inv.account_id !== filters.account) return false;
      if (homeIds && !homeIds.has(inv.account_id)) return false;
      return true;
    });
  }, [invoices, filters, accounts]);

  const sections = useMemo(() => {
    const labelById = new Map<number, string>();
    for (const a of accounts) labelById.set(a.id, a.label || a.provider);
    const byAccount = new Map<string, Invoice[]>();
    const ungrouped: Invoice[] = [];
    for (const inv of filtered) {
      const label = labelById.get(inv.account_id);
      if (label) {
        if (!byAccount.has(label)) byAccount.set(label, []);
        byAccount.get(label)!.push(inv);
      } else {
        ungrouped.push(inv);
      }
    }
    const grouped: Section[] = [];
    byAccount.forEach((list, title) => grouped.push({ title, invoices: list }));
    if (ungrouped.length > 0) grouped.push({ title: t('invoices', 'group_others'), invoices: ungrouped });
    return grouped;
  }, [filtered, accounts, t]);

  const activeCount =
    (filters.status !== 'all' ? 1 : 0) +
    (filters.account ? 1 : 0) +
    (filters.home ? 1 : 0);

  const markPaid = async (inv: Invoice) => {
    try {
      await setInvoiceStatus(inv.id, 'paid');
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : t('invoices', 'error_save'));
    }
  };

  const setStatus = async (inv: Invoice, status: 'enabled' | 'disabled') => {
    try {
      await setInvoiceStatus(inv.id, status);
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : t('invoices', 'error_save'));
    }
  };

  const remove = async (inv: Invoice) => {
    Alert.alert(t('invoices', 'delete_title'), t('invoices', 'delete_confirm'), [
      { text: t('common', 'cancel'), style: 'cancel' },
      {
        text: t('common', 'delete'),
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteInvoice(inv.id);
            await load();
          } catch (e) {
            Alert.alert('Eroare', e instanceof ApiError ? e.message : t('invoices', 'error_delete'));
          }
        },
      },
    ]);
  };

  const openFilter = () => {
    setDraft({ ...filters });
    setModal(true);
  };

  const renderInvoice = ({ item }: { item: Invoice }) => {
    const paid = isPaidInv(item);
    const cancelled = item.pay_status === 'CANCELLED';
    const disabled = item.status === 'disabled';
    const showDelete = paid || cancelled || disabled;
    const info = accountInfo.get(item.account_id);
    const contractLine = [info?.contract || '', formatMonth(item.issue_date)].filter((x) => x && x !== '—').join(' · ');
    return (
      <Card style={styles.invoice}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.invTitle}>
              {item.invoice_number || item.period || t('invoices', 'default_title')}
            </Text>
            {!paid ? (
              <Text style={styles.muted}>{contractLine || '—'}</Text>
            ) : null}
            {item.period ? (
              <Text style={styles.muted}>{t('invoices', 'period', { value: item.period })}</Text>
            ) : null}
            {item.due_date ? (
              <Text style={styles.muted}>{t('invoices', 'due', { value: item.due_date })}</Text>
            ) : null}
            {item.checked_at ? (
              <Text style={styles.muted}>{t('invoices', 'checked_at', { value: item.checked_at })}</Text>
            ) : null}
          </View>
          <View style={styles.invRight}>
            <Text style={styles.amount}>
              {Number(item.amount_mdl).toFixed(2)} {item.currency}
            </Text>
            <Text style={[styles.status, cancelled ? styles.cancelled : paid ? styles.paid : styles.unpaid]}>
              {cancelled ? t('invoices', 'cancelled') : paid ? t('invoices', 'paid') : t('invoices', 'unpaid')}
            </Text>
            <View style={styles.actions}>
              {!paid && !disabled ? (
                <>
                  <TouchableOpacity
                    style={styles.iconBtn}
                    onPress={() => markPaid(item)}
                    accessibilityLabel={t('invoices', 'mark_paid')}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Ionicons name="checkmark-circle-outline" size={22} color={colors.success} />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={styles.iconBtn}
                    onPress={() => setStatus(item, 'disabled')}
                    accessibilityLabel={t('invoices', 'disable')}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Ionicons name="eye-off-outline" size={22} color={colors.warning} />
                  </TouchableOpacity>
                </>
              ) : null}
              {disabled ? (
                <TouchableOpacity
                  style={styles.iconBtn}
                  onPress={() => setStatus(item, 'enabled')}
                  accessibilityLabel={t('invoices', 'enable')}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Ionicons name="eye-outline" size={22} color={colors.primary} />
                </TouchableOpacity>
              ) : null}
              {showDelete ? (
                <TouchableOpacity
                  style={styles.iconBtn}
                  onPress={() => remove(item)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Ionicons name="trash-outline" size={22} color={colors.danger} />
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        </View>
      </Card>
    );
  };

  const statusOpts: { value: StatusFilter; label: string }[] = [
    { value: 'all', label: t('invoices', 'f_all') },
    { value: 'unpaid', label: t('invoices', 'f_unpaid') },
    { value: 'paid', label: t('invoices', 'f_paid') },
  ];

  return (
    <View style={styles.container}>
      <FlatList
        data={buildRows(sections)}
        keyExtractor={(row) => row.key}
        renderItem={({ item }) => {
          if (item.kind === 'banner') return <AdBanner placement="facturi" />;
          if (item.kind === 'section') {
            return <Text style={styles.sectionTitle}>{item.title}</Text>;
          }
          return renderInvoice({ item: item.inv });
        }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <Pressable
            style={({ pressed }) => [styles.filterBtn, pressed && styles.pressed]}
            android_ripple={{ color: 'rgba(15,118,110,0.12)' }}
            onPress={openFilter}
          >
            <Ionicons name="funnel-outline" size={20} color={colors.primary} />
            <Text style={styles.filterBtnText}>
              {t('invoices', 'filter_title')}
              {activeCount > 0 ? ` (${activeCount})` : ''}
            </Text>
            {activeCount > 0 ? (
              <TouchableOpacity
                onPress={() => setFilters({ ...EMPTY_FILTERS })}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons name="close-circle-outline" size={20} color={colors.muted} />
              </TouchableOpacity>
            ) : null}
          </Pressable>
        }
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loading ? t('common', 'loading') : t('invoices', 'empty')}
          </Text>
        }
      />

      <Modal visible={modal} transparent animationType="slide" onRequestClose={() => setModal(false)}>
        <KeyboardAvoidingView style={styles.modalWrap} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.modal}>
            <ScrollView>
              <Text style={styles.modalTitle}>{t('invoices', 'filter_title')}</Text>
              <Text style={styles.sectionLabel}>{t('invoices', 'f_status')}</Text>
              <View style={styles.chipRow}>
                {statusOpts.map((o) => (
                  <Pressable
                    key={o.value}
                    style={({ pressed }) => [
                      styles.statusChip,
                      draft.status === o.value && styles.statusChipActive,
                      pressed && styles.pressed,
                    ]}
                    onPress={() => setDraft((d) => ({ ...d, status: o.value }))}
                  >
                    <Text style={[styles.statusChipText, draft.status === o.value && styles.statusChipTextActive]}>
                      {o.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
              <Text style={styles.sectionLabel}>{t('invoices', 'f_utility')}</Text>
              {accounts.map((a) => (
                <Pressable
                  key={a.id}
                  style={({ pressed }) => [styles.pickRow, draft.account === a.id && styles.pickRowActive, pressed && styles.pressed]}
                  onPress={() => setDraft((d) => ({ ...d, account: d.account === a.id ? null : a.id }))}
                >
                  <View style={styles.radio}>{draft.account === a.id ? <View style={styles.radioDot} /> : null}</View>
                  <View style={styles.flex}>
                    <Text style={styles.pickLabel}>{a.label || a.provider}</Text>
                    {a.contract_number ? <Text style={styles.muted}>{a.contract_number}</Text> : null}
                  </View>
                </Pressable>
              ))}
              {homes.length > 0 ? (
                <>
                  <Text style={styles.sectionLabel}>{t('invoices', 'f_home')}</Text>
                  {homes.map((h) => (
                    <Pressable
                      key={h.id}
                      style={({ pressed }) => [styles.pickRow, draft.home === h.id && styles.pickRowActive, pressed && styles.pressed]}
                      onPress={() => setDraft((d) => ({ ...d, home: d.home === h.id ? null : h.id }))}
                    >
                      <View style={styles.radio}>{draft.home === h.id ? <View style={styles.radioDot} /> : null}</View>
                      <Text style={styles.pickLabel}>{h.name}</Text>
                    </Pressable>
                  ))}
                </>
              ) : null}
              <Button
                title={t('invoices', 'f_apply')}
                onPress={() => {
                  setFilters({ ...draft });
                  setModal(false);
                }}
              />
              <Button
                title={t('invoices', 'f_reset')}
                variant="danger"
                onPress={() => {
                  setDraft({ ...EMPTY_FILTERS });
                  setFilters({ ...EMPTY_FILTERS });
                  setModal(false);
                }}
              />
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 100 },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  invoice: { backgroundColor: colors.background, borderWidth: 1 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  invTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  invRight: { alignItems: 'flex-end' },
  amount: { fontSize: 18, fontWeight: '700', color: colors.text },
  status: { fontSize: 13, fontWeight: '600', marginTop: 2 },
  paid: { color: colors.success },
  unpaid: { color: colors.danger },
  cancelled: { color: '#7c3aed' },
  actions: { flexDirection: 'row', marginTop: spacing.sm },
  iconBtn: { marginLeft: spacing.md },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
  pressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  filterBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  filterBtnText: { fontSize: 15, fontWeight: '600', color: colors.primary, fontFamily, marginLeft: spacing.sm, flex: 1 },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  modal: { backgroundColor: colors.card, borderTopLeftRadius: radii.dialog, borderTopRightRadius: radii.dialog, padding: spacing.xl, maxHeight: '92%' },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: spacing.md, fontFamily },
  sectionLabel: { fontSize: 14, fontWeight: '600', color: colors.text, fontFamily, marginTop: spacing.md, marginBottom: spacing.sm },
  chipRow: { flexDirection: 'row', gap: spacing.sm },
  statusChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.chip,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.background,
  },
  statusChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  statusChipText: { fontSize: 14, fontWeight: '600', color: colors.text, fontFamily },
  statusChipTextActive: { color: '#fff' },
  pickRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.card,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  pickRowActive: { borderColor: colors.primary, borderWidth: 2 },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary },
  pickLabel: { fontSize: 15, fontWeight: '600', color: colors.text, fontFamily },
});
