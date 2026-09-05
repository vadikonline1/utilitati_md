import React, { useCallback, useState } from 'react';
import {
  Alert,
  FlatList,
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
import { colors, spacing } from '../theme';

const TYPE_STYLE: Record<string, { color: string; label: string }> = {
  invoice: { color: colors.success, label: 'Factură' },
  unpaid: { color: colors.warning, label: 'Neachitat' },
  admin: { color: colors.danger, label: 'Administrație' },
  general: { color: colors.primary, label: 'General' },
};

function typeStyle(type: string) {
  return TYPE_STYLE[type] || { color: colors.primary, label: 'Altele' };
}

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
  const total = items.length;

  return (
    <View style={styles.screen}>
      <AppHeader />
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.content}
        refreshing={refreshing}
        onRefresh={() => load(true)}
        ListHeaderComponent={
          <View style={styles.headRow}>
            <Text style={styles.pageTitle}>Notificări</Text>
            {total > 0 ? (
              <View style={styles.countPill}>
                <Text style={styles.countPillText}>{total}</Text>
              </View>
            ) : null}
            {hasUnread ? (
              <TouchableOpacity onPress={markAllRead} style={styles.readAllWrap}>
                <Text style={styles.readAll}>Marchează toate ca citite</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          loading ? (
            <Text style={styles.empty}>Se încarcă…</Text>
          ) : (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyIcon}>🔔</Text>
              <Text style={styles.empty}>Nicio notificare încă.</Text>
            </View>
          )
        }
        ListFooterComponent={<AdBanner placement="dashboard" />}
        renderItem={({ item }) => {
          const ts = typeStyle(item.type);
          return (
            <TouchableOpacity activeOpacity={0.7} onPress={() => markRead(item)}>
              <View
                style={[
                  styles.card,
                  { borderLeftColor: ts.color },
                  item.read ? null : styles.cardUnread,
                ]}
              >
                <View style={styles.cardHead}>
                  <View style={[styles.badge, { backgroundColor: ts.color }]}>
                    <Text style={styles.badgeText}>{ts.label}</Text>
                  </View>
                  {!item.read ? <View style={styles.dot} /> : null}
                  <Text style={styles.date} numberOfLines={1}>
                    {item.created_at}
                  </Text>
                </View>
                <Text
                  style={[styles.cardTitle, item.read ? styles.cardTitleRead : null]}
                >
                  {item.title || 'Notificare'}
                </Text>
                {item.body ? <Text style={styles.body}>{item.body}</Text> : null}
              </View>
            </TouchableOpacity>
          );
        }}
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
    marginBottom: spacing.lg,
  },
  pageTitle: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
    marginRight: spacing.sm,
  },
  countPill: {
    backgroundColor: colors.primary,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 2,
    marginRight: spacing.md,
  },
  countPillText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  readAllWrap: { marginLeft: 'auto' },
  readAll: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  emptyWrap: { alignItems: 'center', marginTop: spacing.xl },
  emptyIcon: { fontSize: 40, marginBottom: spacing.md },
  empty: { color: colors.muted, textAlign: 'center', marginTop: spacing.sm },
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderLeftWidth: 4,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardUnread: { backgroundColor: '#f0fdfa' },
  cardHead: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  badge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
    marginRight: spacing.sm,
  },
  badgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.danger,
    marginRight: spacing.sm,
  },
  date: { color: colors.muted, fontSize: 12, marginLeft: 'auto', flexShrink: 1 },
  cardTitle: { fontWeight: '800', color: colors.text, fontSize: 15, marginBottom: 2 },
  cardTitleRead: { fontWeight: '600', color: colors.text },
  body: { color: colors.text, lineHeight: 20, marginTop: 2 },
});