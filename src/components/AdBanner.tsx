import React, { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { BannerAd } from 'react-native-google-mobile-ads';

import {
  adsAllowed,
  bannerSize,
  bannerUnitFor,
  ensureAdmobInitialized,
} from '../utils/ads';

interface Props {
  placement: string;
}

/**
 * Renders a bottom banner ad on the given placement, only when the server
 * config (from /admin) enables ads for that placement. Renders null otherwise.
 */
export default function AdBanner({ placement }: Props) {
  const [unitId, setUnitId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await ensureAdmobInitialized();
      } catch {
        /* ignore */
      }
      const allowed = await adsAllowed(placement);
      if (!allowed) {
        if (active) setUnitId(null);
        return;
      }
      const unit = await bannerUnitFor();
      if (active) setUnitId(unit);
    })();
    return () => {
      active = false;
    };
  }, [placement]);

  if (!unitId) return null;

  return (
    <View style={styles.wrap}>
      <BannerAd
        unitId={unitId}
        size={bannerSize()}
        requestOptions={{ requestNonPersonalizedAdsOnly: true }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', width: '100%', paddingVertical: 6, minHeight: 50 },
});