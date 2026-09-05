import { Platform } from 'react-native';
import {
  BannerAd,
  BannerAdSize,
  InterstitialAd,
  MobileAds,
  RewardedAd,
  RewardedAdEventType,
  TestIds,
  AdEventType,
} from 'react-native-google-mobile-ads';

import { AdmobConfig, getConfig } from '../api/client';

let cached: AdmobConfig | null = null;
let loadPromise: Promise<AdmobConfig | null> | null = null;
let initPromise: Promise<void> | null = null;

function platformUnit(androidId: string, iosId: string): string | null {
  if (Platform.OS === 'ios') return iosId || null;
  if (Platform.OS === 'android') return androidId || null;
  return null;
}

function realUnitId(value: string | null): boolean {
  return !!value && /^ca-app-pub-\d+\/\d+$/.test(value);
}

/**
 * Resolve the effective ad unit id. Uses the real id when a valid
 * `ca-app-pub-...` id is configured (from /admin); otherwise falls back to
 * Google's official test unit id so the build works before creds are set.
 */
function resolveUnitId(type: 'banner' | 'interstitial' | 'rewarded', realId: string | null): string | null {
  if (realUnitId(realId)) return realId!;
  if (type === 'banner') return TestIds.BANNER;
  if (type === 'interstitial') return TestIds.INTERSTITIAL;
  return TestIds.REWARDED;
}

export function bannerSize(): BannerAdSize {
  return BannerAdSize.ANCHORED_ADAPTIVE_BANNER;
}

function ensureInit(): Promise<void> {
  if (!initPromise) {
    initPromise = MobileAds()
      .initialize()
      .catch(() => undefined)
      .then(() => undefined);
  }
  return initPromise;
}

/**
 * Load (once) and cache the server-driven AdMob config. Non-fatal on error.
 */
export async function loadAdConfig(): Promise<AdmobConfig | null> {
  if (cached) return cached;
  if (!loadPromise) {
    loadPromise = getConfig()
      .then((cfg) => {
        cached = cfg.admob;
        return cached;
      })
      .catch(() => null);
  }
  return loadPromise;
}

export async function ensureAdmobInitialized(): Promise<void> {
  await loadAdConfig();
  await ensureInit();
}

/**
 * Whether ads may show on the given placement (server config only).
 */
export async function adsAllowed(placement: string): Promise<boolean> {
  const cfg = await loadAdConfig();
  return !!cfg && cfg.enabled && cfg.placements.includes(placement);
}

/**
 * Banner unit id for this platform, or null when banners are disabled/off.
 */
export async function bannerUnitFor(): Promise<string | null> {
  const cfg = await loadAdConfig();
  if (!cfg || !cfg.enabled || !cfg.banner.enabled) return null;
  const real = platformUnit(cfg.banner.unit_android, cfg.banner.unit_ios);
  return resolveUnitId('banner', real);
}

let lastInterstitialAt = 0;

/**
 * Show an interstitial (frequency-limited to the /admin interval).
 * Returns true when an interstitial was actually shown.
 */
export async function showInterstitialOnce(): Promise<boolean> {
  const cfg = await loadAdConfig();
  if (!cfg || !cfg.enabled || !cfg.interstitial.enabled) return false;
  const real = platformUnit(cfg.interstitial.unit_android, cfg.interstitial.unit_ios);
  const unitId = resolveUnitId('interstitial', real);
  if (!unitId) return false;

  const now = Date.now();
  const minMs = Math.max(1, cfg.interstitial.interval_minutes) * 60 * 1000;
  if (now - lastInterstitialAt < minMs) return false;
  lastInterstitialAt = now;

  const ad = InterstitialAd.createForAdRequest(unitId);
  const shown = await new Promise<boolean>((resolve) => {
    const loaded = ad.addAdEventListener(AdEventType.LOADED, () => ad.show());
    const closed = ad.addAdEventListener(AdEventType.CLOSED, () => {
      loaded(); // remove listeners
      closed();
      resolve(true);
    });
    const failed = ad.addAdEventListener(AdEventType.ERROR, () => {
      loaded();
      failed();
      resolve(false);
    });
    ad.load();
  });
  return shown;
}

let lastRewardedAt = 0;

/**
 * Show a rewarded ad. Returns true when the ad was shown.
 * Rewarded ads are only presented via the "Sustine proiectul" button and are
 * NOT gated by the placement list (they are always active when enabled).
 */
export async function showRewardedOnce(): Promise<boolean> {
  const cfg = await loadAdConfig();
  if (!cfg || !cfg.enabled || !cfg.rewarded.enabled) return false;
  const real = platformUnit(cfg.rewarded.unit_android, cfg.rewarded.unit_ios);
  const unitId = resolveUnitId('rewarded', real);
  if (!unitId) return false;

  const now = Date.now();
  if (now - lastRewardedAt < 60 * 1000) return false;
  lastRewardedAt = now;

  const ad = RewardedAd.createForAdRequest(unitId);
  const shown = await new Promise<boolean>((resolve) => {
    const loaded = ad.addAdEventListener(RewardedAdEventType.LOADED, () => ad.show());
    const closed = ad.addAdEventListener(AdEventType.CLOSED, () => {
      loaded(); // remove listeners
      closed();
      resolve(true);
    });
    const failed = ad.addAdEventListener(AdEventType.ERROR, () => {
      loaded();
      failed();
      resolve(false);
    });
    ad.load();
  });
  return shown;
}

export { BannerAd, RewardedAd, TestIds };
export type { InterstitialAd };