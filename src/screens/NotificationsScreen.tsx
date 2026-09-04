import React, { useCallback, useState } from 'react';
import {
  Alert,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import {
  AppNotification,
  getNotifications,
} from '../api/client';
import AppHeader from '../components/AppHeader';
import AdBanner from '../components/AdBanner';
import Card from '../components/Card';
import { colors, spacing } from '../theme';

export default function NotificationsScreen() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await getNotifications();
      setItems(data.notifications);
    } catch {
      Alert.alert('Eroare', 'Nu s-au putut încărca notificările.');
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

  return (
    <View style={styles.screen}>
      <AppHeader />
      <AdBanner placement="dashboard" />
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.content}
        refreshing={refreshing}
        onRefresh={() => load(true)}
        ListHeaderComponent={
          <Text style={styles.title}>Notificări</Text>
        }
        ListEmptyComponent={
          loading ? (
            <Text style={styles.empty}>Se încarcă…</Text>
          ) : (
            <Text style={styles.empty}>Nicio notificare încă.</Text>
          )
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHead}>
              <Text style={styles.cardTitle}>{item.title || 'Notificare'}</Text>
              <Text style={styles.date}>{item.created_at}</Text>
            </View>
            {item.body ? <Text style={styles.body}>{item.body}</Text> : null}
          </Card>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: 40 },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
    marginBottom: spacing.md,
  },
  empty: { color: colors.muted, textAlign: 'center', marginTop: spacing.xl },
  card: { marginBottom: spacing.md },
  cardHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  cardTitle: { fontWeight: '800', color: colors.text, flex: 1, marginRight: 8 },
  date: { color: colors.muted, fontSize: 12 },
  body: { color: colors.text, lineHeight: 20, marginTop: 2 },
});
