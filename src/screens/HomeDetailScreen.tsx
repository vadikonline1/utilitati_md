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
import { RouteProp, useFocusEffect } from '@react-navigation/native';

import { Account, getHome, Home as HomeType } from '../api/client';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { colors, spacing } from '../theme';

type ParamList = {
  HomeDetail: { id: number; name: string };
};

interface Props {
  navigation: {
    navigate: (name: string, params?: object) => void;
    setOptions: (opts: object) => void;
  };
  route: RouteProp<ParamList, 'HomeDetail'>;
}

export default function HomeDetailScreen({ navigation, route }: Props) {
  const homeId = route.params.id;
  const [home, setHome] = useState<HomeType | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) setRefreshing(true);
      try {
        const data = await getHome(homeId);
        setHome(data.home);
        setAccounts(data.accounts);
      } catch {
        Alert.alert('Eroare', 'Nu s-au putut încărca datele.');
      } finally {
        setRefreshing(false);
      }
    },
    [homeId],
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const renderAccount = ({ item }: { item: Account }) => (
    <TouchableOpacity
      onPress={() =>
        navigation.navigate('AccountDetail', { id: item.id, label: item.label })
      }
    >
      <Card>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.name}>{item.label}</Text>
            <Text style={styles.muted}>{item.provider}</Text>
            <Text style={styles.muted}>Contract: {item.contract_number}</Text>
          </View>
          <View style={[styles.badge, item.status === 'disabled' ? styles.badgeOff : styles.badgeOn]}>
            <Text style={styles.badgeText}>
              {item.status === 'disabled' ? 'Dezactivat' : 'Activ'}
            </Text>
          </View>
        </View>
      </Card>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={accounts}
        keyExtractor={(a) => String(a.id)}
        renderItem={renderAccount}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          home ? (
            <Card>
              <Text style={styles.name}>{home.name}</Text>
              {home.address ? <Text style={styles.muted}>{home.address}</Text> : null}
              {home.floor ? <Text style={styles.muted}>Etaj {home.floor}</Text> : null}
              {home.metro_area ? <Text style={styles.muted}>{home.metro_area}</Text> : null}
            </Card>
          ) : null
        }
        ListEmptyComponent={
          <Text style={styles.empty}>Niciun cont de utilități adăugat.</Text>
        }
        ListFooterComponent={<AdBanner placement="home_detail" />}
      />
      <TouchableOpacity
        style={styles.fab}
        onPress={() =>
          navigation.navigate('AccountForm', { homeId, provider: '', label: '' })
        }
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
  empty: { textAlign: 'center', color: colors.muted, marginTop: spacing.xl },
  badge: { borderRadius: 999, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  badgeOn: { backgroundColor: '#dcfce7' },
  badgeOff: { backgroundColor: '#f1f5f9' },
  badgeText: { color: colors.text, fontSize: 12, fontWeight: '600' },
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
