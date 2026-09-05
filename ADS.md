# AdMob / Google Ads setup

Ads are **server-driven**: everything except the AdMob **App ID** is configured
live from the `/admin` dashboard (`?tab=Ads`). The mobile app fetches
`GET /api/config` at startup and only renders ads for the placements and formats
you enable there — no app reinstall needed for unit-id/config changes.

## Important: build-time App IDs vs runtime unit ids

| Item              | Where                | When it applies                     |
| ----------------- | -------------------- | ----------------------------------- |
| AdMob **App ID**  | `app.json` root key   | Baked into the native build (build-time) |
| Ad **unit IDs**   | `/admin` → Ads        | Runtime, served via `/api/config`    |
| Master switch     | `/admin` → Ads        | Runtime                             |
| Placements        | `/admin` → Ads        | Runtime                             |

The `react-native-google-mobile-ads` SDK requires the AdMob **App ID** at native
init — it **cannot** be set from JS at runtime. So the App ID must live in
`app.json` and be replaced before release. The App ID fields in `/admin` are for
reference only.

## Before release you must replace the sample ids

`app.json` currently ships with Google's **sample** App IDs, and/or `/admin` unit
ids default to empty (the app then falls back to Google test ads when a format is
enabled). For real monetization:

1. In the AdMob console create your app (`md.utilitati.app` / `md.utilitati.app`).
2. Copy both App IDs into the root-level `react-native-google-mobile-ads` key of
   `app.json` (NOT inside the `expo` object — the library's Gradle script reads it
   exactly there):
   ```json
   "react-native-google-mobile-ads": {
     "android_app_id": "ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX",
     "ios_app_id":     "ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX"
   }
   ```
   This key both satisfies the native build (it fails Gradle if `android_app_id`
   is missing) and injects the App ID into the Android manifest +
   `GADApplicationIdentifier` for iOS. The upstream npm config plugin is NOT used
   (it ships uncompiled ESM that crashes `npx expo prebuild` with "Unexpected
   token 'typeof'").
3. Create ad units in AdMob and paste the unit ids into `/admin` → Ads
   (banner / interstitial / rewarded, per platform), set the master switch on,
   check the placements you want, and save. A build with the real App ID is now
   monetized.

Until the App ID in `app.json` is a real one, the app shows **Google test ads**.
To disable ads entirely, leave the master switch off / no placements checked in
`/admin`.

## Placements (screen keys the app understands)

| Key          | Screen           |
| ------------ | ---------------- |
| `dashboard`  | Dashboard tab    |
| `homes`      | Locuințe tab     |
| `facturi`    | Facturi tab      |
| `home_detail`| Home detail view |

Only checked placements render ads. Interstitial frequency is limited by the
`Minimum minutes between interstitials` field in `/admin` (default 5).

## How it works

- Backend: `app/services/settings.py` (`admob_config`, `placement_allows_ads`),
  `GET /api/config` (`app/routers/api.py`), `/admin/ads` POST handler
  (`app/routers/pages.py`), `tab-ads` UI (`app/templates/admin.html`), i18n keys
  (`app/i18n.py`).
- Mobile: `src/utils/ads.ts` (config cache, platform unit resolution, fallback to
  Google test ids, frequency gating), `src/components/AdBanner.tsx`, initialized
  in `App.tsx`, rendered on screens gated by placement.