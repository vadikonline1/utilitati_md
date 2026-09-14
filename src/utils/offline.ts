import AsyncStorage from '@react-native-async-storage/async-storage';

export interface CachedResult<T> {
  data: T | null;
  /** True when the data comes from the on-device cache (no connection). */
  offline: boolean;
}

function key(name: string): string {
  return `utilitati.cache.${name}`;
}

/**
 * Try the network fetcher first and persist the result; on any failure fall
 * back to the last saved payload (offline mode). Never throws.
 */
export async function cached<T>(name: string, fetcher: () => Promise<T>): Promise<CachedResult<T>> {
  try {
    const data = await fetcher();
    try {
      await AsyncStorage.setItem(key(name), JSON.stringify({ ts: Date.now(), data }));
    } catch {
      /* storage failure: still return fresh data */
    }
    return { data, offline: false };
  } catch {
    try {
      const raw = await AsyncStorage.getItem(key(name));
      if (raw) {
        const parsed = JSON.parse(raw) as { data: T };
        if (parsed && parsed.data !== undefined) {
          return { data: parsed.data as T, offline: true };
        }
      }
    } catch {
      /* corrupted cache: report no data */
    }
    return { data: null, offline: true };
  }
}
