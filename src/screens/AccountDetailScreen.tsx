import React, { useCallback, useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { RouteProp, useFocusEffect } from '@react-navigation/native';

import {
  Account,
  ApiError,
  accountInvoices,
  deleteInvoice,
  invoiceHistory,
  Invoice,
  InvoiceHistoryEntry,
  listAccounts,
  refreshAccount,
  setInvoiceStatus,
} from '../api/client';
import Button from '../components/Button';
import Card from '../components/Card';
import { useContent } from '../content/useContent';
import { colors, spacing } from '../theme';
import { notifyNewInvoice } from '../utils/notify';

type ParamList = {
  AccountDetail: { id: number; label: string };
};

interface Props {
  navigation: {
    navigate: (name: string, params?: object) => void;
    setOptions: (opts: object) => void;
  };
  route: RouteProp<ParamList, 'AccountDetail'>;
}

function InvoiceDetail({
  inv,
  onPaid,
  onDisable,
  onEnable,
  onDelete,
}: {
  inv: Invoice;
  onPaid: () => void;
  onDisable: () => void;
  onEnable: () => void;
  onDelete: () => void;
}) {
  const { t } = useContent();
  const paid = inv.is_paid === 1 || inv.pay_status === 'PAID';
  const disabled = (inv as { status?: string }).status === 'disabled';
  return (
    <View style={styles.detailBox}>
      <Text style={styles.detailAmount}>
        {Number(inv.amount_mdl).toFixed(2)} {inv.currency || 'MDL'}
      </Text>
      <Text style={[styles.detailStatus, paid ? styles.paid : styles.unpaid]}>
        {paid ? t('invoices', 'paid') : t('invoices', 'unpaid')}
        {disabled ? ' · dezactivată' : ''}
      </Text>
      {inv.period ? (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Perioada</Text>
          <Text style={styles.detailValue}>{inv.period}</Text>
        </View>
      ) : null}
      {inv.issue_date ? (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Emisă</Text>
          <Text style={styles.detailValue}>{inv.issue_date}</Text>
        </View>
      ) : null}
      {inv.due_date ? (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Scadență</Text>
          <Text style={styles.detailValue}>{inv.due_date}</Text>
        </View>
      ) : null}
      <View style={styles.detailRow}>
        <Text style={styles.detailLabel}>Ultima verificare</Text>
        <Text style={styles.detailValue}>{inv.checked_at || '—'}</Text>
      </View>
      {inv.external_invoice_id ? (
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>ID extern</Text>
          <Text style={styles.detailValue}>{inv.external_invoice_id}</Text>
        </View>
      ) : null}
      <View style={styles.detailActions}>
        {!paid && !disabled ? (
          <>
            <Button title={t('invoices', 'mark_paid')} onPress={onPaid} style={styles.detailBtn} />
            <Button title={t('invoices', 'disable')} variant="ghost" onPress={onDisable} style={styles.detailBtn} />
          </>
        ) : null}
        {disabled ? (
          <Button title={t('invoices', 'enable')} variant="ghost" onPress={onEnable} style={styles.detailBtn} />
        ) : null}
        {paid || disabled ? (
          <Button title={t('invoices', 'delete_title')} variant="danger" onPress={onDelete} style={styles.detailBtn} />
        ) : null}
      </View>
    </View>
  );
}

export default function AccountDetailScreen({ navigation, route }: Props) {
  const { t, content } = useContent();
  const accountId = route.params.id;
  const [account, setAccount] = useState<Account | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [historyInv, setHistoryInv] = useState<Invoice | null>(null);
  const [history, setHistory] = useState<InvoiceHistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      try {
        // fetch account via accounts list to keep single source
        const accounts = await listAccounts();
        const acc = accounts.find((a) => a.id === accountId);
        setAccount(acc ?? null);
        const data = await accountInvoices(accountId);
        setInvoices(data.invoices);
      } catch {
        Alert.alert('Eroare', t('account_detail', 'error_load'));
      } finally {
        setRefreshing(false);
      }
    },
    [accountId, t],
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const doRefresh = async () => {
    setBusy(true);
    try {
      const res = await refreshAccount(accountId);
      if (!res.is_connected) {
        Alert.alert(
          t('account_detail', 'connect_error_title'),
          res.error_message || t('account_detail', 'connect_error_body'),
        );
      } else {
        Alert.alert(
          'Gata',
          t('account_detail', 'refresh_done', { unpaid: res.unpaid_balance_mdl }),
        );
        const hasNew = (res.created_count ?? 0) > 0 || (res.changed_count ?? 0) > 0 || Boolean(res.balance_increased);
        if (hasNew) {
          notifyNewInvoice(
            content.notifications?.new_invoice_title || 'Factură nouă 🔔',
            t('account_detail', 'refresh_done', { unpaid: res.unpaid_balance_mdl }),
          );
        }
      }
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : t('account_detail', 'error_save'));
    } finally {
      setBusy(false);
    }
  };

  const openHistory = async (inv: Invoice) => {
    setHistoryInv(inv);
    setHistory([]);
    setHistoryError('');
    setHistoryLoading(true);
    try {
      const res = await invoiceHistory(inv.id);
      setHistory(res.history || []);
    } catch {
      setHistoryError(t('account_detail', 'error_history'));
    } finally {
      setHistoryLoading(false);
    }
  };

  const invoiceAction = async (inv: Invoice, kind: 'paid' | 'disabled' | 'enabled' | 'delete') => {
    try {
      if (kind === 'delete') {
        await deleteInvoice(inv.id);
      } else {
        await setInvoiceStatus(inv.id, kind);
      }
      setHistoryInv(null);
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : t('account_detail', 'error_save'));
    }
  };

  const confirmDelete = (inv: Invoice) => {
    Alert.alert(t('invoices', 'delete_title'), t('invoices', 'delete_confirm'), [
      { text: t('common', 'cancel'), style: 'cancel' },
      { text: t('common', 'delete'), style: 'destructive', onPress: () => invoiceAction(inv, 'delete') },
    ]);
  };

  const historyLabel = (status: string) => {
    const s = status || '';
    if (s === 'PAID' || s === 'OVERPAID' || s === 'PARTIALLY_PAID') {
      return t('account_detail', 'history_paid');
    }
    if (s === 'UNKNOWN') return t('account_detail', 'history_unknown');
    return t('account_detail', 'history_unpaid');
  };

  const renderInvoice = ({ item }: { item: Invoice }) => (
    <TouchableOpacity onPress={() => openHistory(item)}>
      <Card style={styles.invoice}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.invTitle}>
              {item.invoice_number || item.period || t('invoices', 'default_title')}
            </Text>
            {item.period ? (
              <Text style={styles.muted}>{t('invoices', 'period', { value: item.period })}</Text>
            ) : null}
            {item.due_date ? (
              <Text style={styles.muted}>{t('invoices', 'due', { value: item.due_date })}</Text>
            ) : null}
            {item.checked_at ? (
              <Text style={styles.muted}>
                {t('account_detail', 'checked_at', { date: item.checked_at })}
              </Text>
            ) : null}
          </View>
          <View style={styles.invRight}>
            <Text style={styles.amount}>
              {Number(item.amount_mdl).toFixed(2)} {item.currency}
            </Text>
            <Text style={[styles.status, item.is_paid ? styles.paid : styles.unpaid]}>
              {item.is_paid
                ? t('account_detail', 'status_paid')
                : item.pay_status === 'UNKNOWN'
                ? t('account_detail', 'status_unknown')
                : t('account_detail', 'status_unpaid')}
            </Text>
          </View>
        </View>
      </Card>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={invoices}
        keyExtractor={(i) => String(i.id)}
        renderItem={renderInvoice}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <>
            {account ? (
              <Card>
                <Text style={styles.title}>{account.label}</Text>
                <Text style={styles.muted}>{account.provider}</Text>
                <Text style={styles.muted}>
                  {t('account_detail', 'contract', { value: account.contract_number })}
                </Text>
                {account.place_of_consumption ? (
                  <Text style={styles.muted}>
                    {t('account_detail', 'location', { value: account.place_of_consumption })}
                  </Text>
                ) : null}
                <View style={styles.actions}>
                  <Button
                    title={t('account_detail', 'refresh')}
                    onPress={doRefresh}
                    loading={busy}
                    style={styles.smallBtn}
                  />
                  <Button
                    title={t('account_detail', 'edit')}
                    variant="ghost"
                    onPress={() => navigation.navigate('AccountForm', { id: accountId })}
                    style={styles.smallBtn}
                  />
                </View>
              </Card>
            ) : null}
            <Text style={styles.listTitle}>{t('account_detail', 'invoices_title')}</Text>
          </>
        }
        ListEmptyComponent={
          <Text style={styles.empty}>{t('account_detail', 'empty')}</Text>
        }
      />

      <Modal visible={historyInv != null} transparent animationType="slide">
        <View style={styles.modalWrap}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>
              {historyInv?.invoice_number || t('invoices', 'default_title')}
            </Text>
            {historyInv ? (
              <InvoiceDetail
                inv={historyInv}
                onPaid={() => invoiceAction(historyInv, 'paid')}
                onDisable={() => invoiceAction(historyInv, 'disabled')}
                onEnable={() => invoiceAction(historyInv, 'enabled')}
                onDelete={() => confirmDelete(historyInv)}
              />
            ) : null}
            <Text style={[styles.modalTitle, styles.historyTitle]}>{t('account_detail', 'history_title')}</Text>
            <ScrollView>
              {historyLoading ? (
                <Text style={styles.empty}>{t('common', 'loading')}</Text>
              ) : historyError ? (
                <Text style={styles.error}>{historyError}</Text>
              ) : history.length === 0 ? (
                <Text style={styles.empty}>{t('account_detail', 'history_empty')}</Text>
              ) : (
                history.map((h) => (
                  <View key={String(h.id)} style={styles.historyRow}>
                    <Text style={styles.historyStatus}>{historyLabel(h.pay_status)}</Text>
                    <Text style={styles.historyAmount}>
                      {Number(h.amount_mdl).toFixed(2)} MDL
                    </Text>
                    <Text style={styles.historyDate}>{h.checked_at}</Text>
                  </View>
                ))
              )}
            </ScrollView>
            <Button
              title={t('common', 'cancel')}
              variant="ghost"
              onPress={() => setHistoryInv(null)}
              style={styles.historyClose}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg },
  title: { fontSize: 22, fontWeight: '800', color: colors.text },
  muted: { color: colors.muted, marginTop: 2 },
  listTitle: { fontSize: 16, fontWeight: '700', color: colors.text, marginTop: spacing.md },
  actions: { marginTop: spacing.md },
  smallBtn: { minHeight: 40, paddingVertical: spacing.sm },
  invoice: { backgroundColor: colors.background, borderWidth: 1 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  invTitle: { fontSize: 16, fontWeight: '600', color: colors.text },
  invRight: { alignItems: 'flex-end' },
  amount: { fontSize: 18, fontWeight: '700', color: colors.text },
  status: { fontSize: 13, fontWeight: '600', marginTop: 2 },
  paid: { color: colors.success },
  unpaid: { color: colors.danger },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
  modalWrap: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  modal: { backgroundColor: colors.card, borderRadius: 16, padding: spacing.xl, maxHeight: '80%' },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, marginBottom: spacing.md },
  historyTitle: { fontSize: 16, marginTop: spacing.md },
  detailBox: {
    backgroundColor: colors.background,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  detailAmount: { fontSize: 24, fontWeight: '800', color: colors.text, textAlign: 'center' },
  detailStatus: { fontSize: 14, fontWeight: '700', textAlign: 'center', marginTop: spacing.xs },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: spacing.sm },
  detailLabel: { fontSize: 14, color: colors.muted },
  detailValue: { fontSize: 14, fontWeight: '600', color: colors.text, marginLeft: spacing.md, textAlign: 'right', flexShrink: 1 },
  detailActions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  detailBtn: { flex: 1, minWidth: '45%' },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingVertical: spacing.sm,
  },
  historyStatus: { flex: 1, fontSize: 14, fontWeight: '600', color: colors.text },
  historyAmount: { fontSize: 14, color: colors.text, marginRight: spacing.md },
  historyDate: { fontSize: 13, color: colors.muted },
  historyClose: { marginTop: spacing.md },
  error: { color: colors.danger, textAlign: 'center', marginVertical: spacing.sm },
});
