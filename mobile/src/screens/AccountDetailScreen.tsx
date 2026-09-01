import React, { useCallback, useState } from 'react';
import {
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { RouteProp, useFocusEffect } from '@react-navigation/native';

import {
  Account,
  ApiError,
  accountInvoices,
  listAccounts,
  refreshAccount,
  Invoice,
} from '../api/client';
import Button from '../components/Button';
import Card from '../components/Card';
import { colors, spacing } from '../theme';

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

export default function AccountDetailScreen({ navigation, route }: Props) {
  const accountId = route.params.id;
  const [account, setAccount] = useState<Account | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

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
        Alert.alert('Eroare', 'Nu s-au putut încărca datele contului.');
      } finally {
        setRefreshing(false);
      }
    },
    [accountId],
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
        Alert.alert('Nu s-a putut conecta', res.error_message || 'Conectare eșuată la furnizor.');
      } else {
        Alert.alert('Gata', `Facturile au fost actualizate. Sold neplătit: ${res.unpaid_balance_mdl} MDL.`);
      }
      await load();
    } catch (e) {
      Alert.alert('Eroare', e instanceof ApiError ? e.message : 'Actualizarea a eșuat.');
    } finally {
      setBusy(false);
    }
  };

  const renderInvoice = ({ item }: { item: Invoice }) => (
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
          <Text style={[styles.status, item.is_paid ? styles.paid : styles.unpaid]}>
            {item.is_paid ? 'Plătită' : item.pay_status === 'UNKNOWN' ? 'Necunoscută' : 'Neplătită'}
          </Text>
        </View>
      </View>
    </Card>
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
                <Text style={styles.muted}>Contract: {account.contract_number}</Text>
                {account.place_of_consumption ? (
                  <Text style={styles.muted}>Loc: {account.place_of_consumption}</Text>
                ) : null}
                <View style={styles.actions}>
                  <Button
                    title="Actualizează facturi"
                    onPress={doRefresh}
                    loading={busy}
                    style={styles.smallBtn}
                  />
                  <Button
                    title="Editează"
                    variant="ghost"
                    onPress={() => navigation.navigate('AccountForm', { id: accountId })}
                    style={styles.smallBtn}
                  />
                </View>
              </Card>
            ) : null}
            <Text style={styles.listTitle}>Facturi</Text>
          </>
        }
        ListEmptyComponent={<Text style={styles.empty}>Nicio factură. Apasă „Actualizează facturi”.</Text>}
      />
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
});
