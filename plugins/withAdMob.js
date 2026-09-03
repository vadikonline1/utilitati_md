/**
 * Local Expo config plugin that injects the Google Mobile Ads (AdMob)
 * Application ID into the native build, so the GMA SDK can initialize.
 *
 * This replaces the upstream `react-native-google-mobile-ads` config plugin,
 * which ships uncompiled ESM and breaks `npx expo prebuild`
 * ("Unexpected token 'typeof'" / does not contain a valid config plugin).
 *
 * Behavior mirrors the upstream plugin:
 *  - Android: adds <meta-data android:name="com.google.android.gms.ads.APPLICATION_ID">
 *    to the application manifest node.
 *  - iOS:     sets GADApplicationIdentifier in Info.plist.
 */

const { withAndroidManifest, withInfoPlist } = require('expo/config-plugins');

module.exports = function withAdMob(config, props = {}) {
  const androidAppId = props.androidAppId;
  const iosAppId = props.iosAppId;

  if (androidAppId) {
    config = withAndroidManifest(config, (c) => {
      const app = c.modResults.manifest.application && c.modResults.manifest.application[0];
      if (app) {
        app['meta-data'] = app['meta-data'] || [];
        const exists = app['meta-data'].some(
          (m) => m.$ && m.$['android:name'] === 'com.google.android.gms.ads.APPLICATION_ID',
        );
        if (!exists) {
          app['meta-data'].push({
            $: {
              'android:name': 'com.google.android.gms.ads.APPLICATION_ID',
              'android:value': androidAppId,
            },
          });
        }
      }
      return c;
    });
  }

  if (iosAppId) {
    config = withInfoPlist(config, (c) => {
      c.modResults.GADApplicationIdentifier = iosAppId;
      return c;
    });
  }

  return config;
};