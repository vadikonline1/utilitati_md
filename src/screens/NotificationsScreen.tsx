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
  AppNotification,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
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

  const markRead = useCallback((item: AppNotification) => {
    if (item.read) return;
    setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, read: 1 } : i)));
    markNotificationRead(item.id).catch(() => undefined);
  }, []);

  const markAllRead = useCallback(() => {
    setItems((prev) => prev.map((i) => ({ ...i, read: 1 })));
    markAllNotificationsRead().catch(() => undefined);
  }, []);

  const hasUnread = items.some((i) => !i.read);

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
          <View style={styles.headRow}>
            <Text style={styles.title}>Notificări</Text>
            {hasUnread ? (
              <TouchableOpacity onPress={markAllRead}>
                <Text style={styles.readAll}>Mark all as read</Text>
              </TouchableOpacity>
            ) : null}
          </View>
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
            <TouchableOpacity activeOpacity={0.7} onPress={() => markRead(item)}>
              <View style={styles.cardHead}>
                {!item.read ? <View style={styles.dot} /> : null}
                <Text style={[styles.cardTitle, item.read ? styles.cardTitleRead : null]}>
                  {item.title || 'Notificare'}
                </Text>
                <Text style={styles.date}>{item.created_at}</Text>
              </View>
              {item.body ? <Text style={styles.body}>{item.body}</Text> : null}
            </TouchableOpacity>
          </Card>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: 40 },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
  },
  readAll: { color: colors.primary, fontWeight: '700', fontSize: 14 },
  empty: { color: colors.muted, textAlign: 'center', marginTop: spacing.xl },
  card: { marginBottom: spacing.md },
  cardHead: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.danger,
    marginRight: 6,
  },
  cardTitle: { fontWeight: '800', color: colors.text, flex: 1, marginRight: 8 },
  cardTitleRead: { fontWeight: '600', color: colors.muted },
  date: { color: colors.muted, fontSize: 12 },
  body: { color: colors.text, lineHeight: 20, marginTop: 2 },
});