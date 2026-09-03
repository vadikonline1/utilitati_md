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

import {
  ApiError,
  deleteInvoice,
  Invoice,
  listAccounts,
  listInvoices,
  setInvoiceStatus,
} from '../api/client';
import AppHeader from '../components/AppHeader';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { colors, spacing } from '../theme';
import { Ionicons } from '@expo/vector-icons';

type Section = { title: string; invoices: Invoice[] };

export default function FacturiScreen() {
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const invData = await listInvoices();
      const invoices = invData.invoices;
      const accounts = await listAccounts();
      const labelById = new Map<number, string>();
      for (const a of accounts) labelById.set(a.id, a.label || a.provider);

      const byAccount = new Map<string, Invoice[]>();
      const ungrouped: Invoice[] = [];
      for (const inv of invoices) {
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
      if (ungrouped.length > 0) grouped.push({ title: 'Altele', invoices: ungrouped });
      setSections(grouped);
    } catch {
      Alert.alert('Eroare', 'Nu s-au putut încărca facturile.');
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

  const markPaid = async (inv: Invoice) => {
    try {
      await setInvoiceStatus(inv.id, 'paid');
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Operațiunea a eșuat.');
    }
  };

  const remove = async (inv: Invoice) => {
    Alert.alert('Șterge factura', 'Sigur vrei să ștergi această factură?', [
      { text: 'Anulează', style: 'cancel' },
      {
        text: 'Șterge',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteInvoice(inv.id);
            await load();
          } catch (e) {
            Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Ștergerea a eșuat.');
          }
        },
      },
    ]);
  };

  const renderInvoice = ({ item }: { item: Invoice }) => {
    const paid = item.is_paid === 1 || item.pay_status === 'PAID';
    return (
      <Card style={styles.invoice}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.invTitle}>
              {item.invoice_number || item.period || 'Factură'}
            </Text>
            {item.period ? <Text style={styles.muted}>Perioada {item.period}</Text> : null}
            {item.due_date ? <Text style={styles.muted}>Scadență {item.due_date}</Text> : null}
          </View>
          <View style={styles.invRight}>
            <Text style={styles.amount}>
              {Number(item.amount_mdl).toFixed(2)} {item.currency}
            </Text>
            <Text style={[styles.status, paid ? styles.paid : styles.unpaid]}>
              {paid ? 'Plătită' : 'Neplătită'}
            </Text>
            <View style={styles.actions}>
              {!paid ? (
                <TouchableOpacity
                  style={styles.iconBtn}
                  onPress={() => markPaid(item)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                >
                  <Ionicons name="checkmark-circle-outline" size={22} color={colors.success} />
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity
                style={styles.iconBtn}
                onPress={() => remove(item)}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons name="trash-outline" size={22} color={colors.danger} />
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Card>
    );
  };

  return (
    <View style={styles.container}>
      <AppHeader />
      <FlatList
        data={sections}
        keyExtractor={(s) => `${s.title}-${s.invoices[0]?.id}`}
        renderItem={({ item }) => (
          <View>
            <Text style={styles.sectionTitle}>{item.title}</Text>
            {item.invoices.map((inv) => renderInvoice({ item: inv }))}
          </View>
        )}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {loading ? 'Se încarcă…' : 'Nicio factură disponibilă.'}
          </Text>
        }
      />
      <AdBanner placement="facturi" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.lg, paddingBottom: 40 },
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
  actions: { flexDirection: 'row', marginTop: spacing.sm },
  iconBtn: { marginLeft: spacing.md },
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
});
