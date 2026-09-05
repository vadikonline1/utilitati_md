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
import { useContent } from '../content/useContent';
import { colors, spacing } from '../theme';

type Row =
  | { kind: 'notif'; key: string; item: AppNotification }
  | { kind: 'banner'; key: string };

const KNOWN_TYPES = ['invoice', 'unpaid', 'admin', 'general', 'other'];

function buildRows(items: AppNotification[]): Row[] {
  const rows: Row[] = [];
  const pushNotif = (item: AppNotification) =>
    rows.push({ kind: 'notif', key: `n-${item.id}`, item });
  if (items.length > 0 && items.length < 10) {
    items.forEach(pushNotif);
    rows.push({ kind: 'banner', key: `banner-end` });
    return rows;
  }
  items.forEach((item, idx) => {
    pushNotif(item);
    if ((idx + 1) % 10 === 0) rows.push({ kind: 'banner', key: `banner-${idx}` });
  });
  return rows;
}

export default function NotificationsScreen() {
  const { t, content } = useContent();
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const badgeOf = (type: string) => {
    const key = KNOWN_TYPES.includes(type) ? type : 'other';
    const badge = content.notifications?.badge?.[key] || {};
    return {
      color: badge.color || colors.primary,
      label: badge.label || t('notifications', `badge.${key}.label`),
    };
  };

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const data = await getNotifications();
      setItems(data.notifications);
    } catch {
      Alert.alert('Eroare', t('notifications', 'error_load'));
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
        data={buildRows(items)}
        keyExtractor={(row) => row.key}
        contentContainerStyle={styles.content}
        refreshing={refreshing}
        onRefresh={() => load(true)}
        ListHeaderComponent={
          <View style={styles.headRow}>
            <Text style={styles.pageTitle}>{t('notifications', 'title')}</Text>
            {total > 0 ? (
              <View style={styles.countPill}>
                <Text style={styles.countPillText}>{total}</Text>
              </View>
            ) : null}
            {hasUnread ? (
              <TouchableOpacity onPress={markAllRead} style={styles.readAllWrap}>
                <Text style={styles.readAll}>{t('notifications', 'read_all')}</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        }
        ListEmptyComponent={
          loading ? (
            <Text style={styles.empty}>{t('common', 'loading')}</Text>
          ) : (
            <View style={styles.emptyWrap}>
              <Text style={styles.emptyIcon}>🔔</Text>
              <Text style={styles.empty}>{t('notifications', 'empty')}</Text>
            </View>
          )
        }
        renderItem={({ item }) => {
          if (item.kind === 'banner') return <AdBanner placement="notificari" />;
          const notif = item.item;
          const ts = badgeOf(notif.type);
          return (
            <TouchableOpacity activeOpacity={0.7} onPress={() => markRead(notif)}>
              <View
                style={[
                  styles.card,
                  { borderLeftColor: ts.color },
                  notif.read ? null : styles.cardUnread,
                ]}
              >
                <View style={styles.cardHead}>
                  <View style={[styles.badge, { backgroundColor: ts.color }]}>
                    <Text style={styles.badgeText}>{ts.label}</Text>
                  </View>
                  {!notif.read ? <View style={styles.dot} /> : null}
                  <Text style={styles.date} numberOfLines={1}>
                    {notif.created_at}
                  </Text>
                </View>
                <Text
                  style={[styles.cardTitle, notif.read ? styles.cardTitleRead : null]}
                >
                  {notif.title || t('notifications', 'default_title')}
                </Text>
                {notif.body ? <Text style={styles.body}>{notif.body}</Text> : null}
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