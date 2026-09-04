# Utilități.MD — Aplicație mobilă (Android + iOS)

Aplicație mobilă realizată cu **React Native + Expo** (un singur cod pentru ambele
platforme), care consumă **API-ul REST JSON** al backend-ului FastAPI existent
(`/api`).

> Repo-ul este un monorepo: backend-ul Python (FastAPI) și aplicația Expo
> locuiesc împreună la **rădăcina repo-ului**. Aplicația mobilă folosește
> `app.json`, `package.json`, `App.tsx` și `src/` de la rădăcină.

## Versiuni

- **Expo SDK 54**, **React Native 0.81**, **React 19.1**.
- Navigare: React Navigation **v7** (native-stack + bottom-tabs).
- Reclame: `react-native-google-mobile-ads` **v16** (Banner/Interstitial/Rewarded).
- Notificări: `expo-notifications` (relay **Expo** sau direct **Google FCM** — vezi
  „Push notifications" mai jos).

## Structură

```
App.tsx                  # intrarea aplicației (auth provider + navigare)
app.json                 # configurare Expo (Android/iOS ids, API URL, projectId)
package.json             # dependențe
eas.json                 # configurare EAS Build (profiles preview/production)
src/
  api/                   # client API + autentificare (token bearer)
    client.ts            # toate apelurile către /api (homes, accounts, invoices...)
    auth-context.tsx     # stare de autentificare (login/register/logout)
  components/            # Button, Card, Input (reutilizabile)
  navigation/            # navigare (stack + tab-uri)
  screens/               # Login, Locuințe, Detalii locuință, Cont, Facturi, Profil
  theme/                 # culori + spațieri
android/                 # folder nativ Android — GENERAT (vezi mai jos)
ios/                     # folder nativ iOS — GENERAT (vezi mai jos)
```

## Cerințe locale

- **Node.js 18+** și **npm** (pentru a rula/build aplicația).
- Aplicația mobilă folosește **Expo**, care permite rulare imediată pe dispozitiv
  cu aplicația „Expo Go", sau build nativ cu EAS / prebuild.

## Instalare

```bash
npm install
```

## Rulare (dev)

```bash
npm start          # Expo dev server (scanezi QR-ul cu Expo Go)
npm run android    # deschide pe emulator Android
npm run ios        # deschide pe simulator iOS
```

## Terminal — folderele `android/` și `ios/`

Proiectul folosește fluxul **Expo managed**. Folderele native `android/` și
`ios/` **nu sunt stocate în git** — sunt **generate automat** cu comanda:

```bash
npx expo prebuild
```

Aceasta creează la rădăcină subfolderele `android/` și `ios/` cu proiectele
native complete (Gradle / Xcode). De reținut:

- Modificările aduse sub `android/` sau `ios/` **se pierd** la următorul
  `expo prebuild` (sunt regenerate). Ajustările native persistente se fac prin
  `app.json` sau fișiere de config de la rădăcină.
- Pentru distribuție (Play Store / App Store) se folosește **EAS Build**:
  ```bash
  npx eas build --platform android
  npx eas build --platform ios
  ```

## Push notifications (FCM vs Expo)

Notificările push sunt **server-driven**: backend-ul publică o setare globală
`push_provider` (`fcm` sau `expo`) prin `GET /api/config`, iar aplicația alege
cum obține token-ul:

- **`expo`** — ambele platforme folosesc `getExpoPushTokenAsync` (relay Expo).
- **`fcm`** (implicit) — Android folosește token-ul FCM brut
  (`getDevicePushTokenAsync`, livrat direct prin FCM HTTP v1 cu service account
  Google); iOS folosește token Expo (relay), fiindcă un token APNs brut nu poate
  fi livrat prin FCM fără setup Firebase pe iOS.

### Setarea globală (admin)

Din `GET /admin` → cardul „Furnizor notificări" alegi:

- **Google Firebase (FCM)** — trimite direct către Google (necesită JSON-ul
  service account în `FCM_SERVICE_ACCOUNT` sau câmpul de admin).
- **Expo Push** — tot traficul prin relay-ul Expo (nu necesită service account).

Schimbarea valorii afectează doar **dispozitivele care se reînregistrează** după
schimbare (token-urile existente rămân pe provider-ul cu care au fost create).

### Oprire notificări per-utilizator („oprire notificări")

Fiecare utilizator are un flag `notifications_enabled` (implicit pornit):

- Din **aplicația mobilă**: Profil → butonul de notificări (`PUT /api/auth/notifications`).
  Când este oprit, backend-ul **șterge token-urile** dispozitivului și nu mai trimite.
- Din **admin** (`?tab=users` → coloana „Notificări"): adminul poate opri/porni
  notificările oricărui utilizator.
- Când flagul este oprit, `send_push` / `send_push_multi` **sar** peste utilizator
  (nu se trimit push-uri, istoricul de notificări nu se mai scrie).

### Prima configurare iOS (o singură dată, interactivă)

Construcția iOS necesită credentiale Apple (certificat de distribuție +
provisioning). Profiles-urile au fost configurate în `eas.json`, dar credentialele
**nu pot fi create automat** de CI — se rulează **o singură dată, interactiv** pe o
mașină cu `eas-cli` instalat:

```bash
npm install -g eas-cli
npx eas login
npx eas credentials --platform ios
npx eas build --profile preview --platform ios   # verifică build-ul
```

Credentialele sunt stocate în contul de pe **EAS** (nu se commit-uiesc), așa că
după acest pas, build-urile iOS din GitHub Actions / EAS Workflows merg automat.

## API URL + projectId

URL-ul de API este setat în `app.json` → `extra.apiUrl`
(`https://utilitati.nistorlazar.md/api`). Pentru testare locală, schimbă-l la
`http://<IP-masina>:<port>/api` (backend-ul rulează cu CORS activat).

ProjectId-ul Expo (folosit pentru push notifications) este în
`app.json` → `extra.expo.projectId`.

## Autentificare

Aplicația se loghează prin `POST /api/auth/login` cu username + parolă,
primește un **token de sesiune**, pe care îl trimite mai departe ca
`Authorization: Bearer <token>` pentru toate celelalte cereri. Token-ul este
păstrat securizat în `expo-secure-store`.

## Resetare parolă (în aplicație)

Din ecranul de autentificare → „Ai uitat parola?":

1. Introdu adresa de email → aplicația apelează `POST /api/auth/forgot-password`
   și primești un link de resetare prin email.
2. Deschide linkul (sau lipește codul în aplicație) → ecranul „Resetare parolă"
   apelează `POST /api/auth/reset-password` cu noul token + parola nouă.

Aplicația suportă și **deep linking**: un link `utilitati://reset-password/<token>`
deschide direct ecranul de resetare din aplicație (`scheme: "utilitati"` în `app.json`).

## Build APK în Docker (alternativ la GitHub Actions)

Există și `Dockerfile.mobile` (Node + Android SDK + Java) care generează proiectul
nativ și produce un APK release:

```bash
docker build -f Dockerfile.mobile -t utilitati-mobile .
mkdir -p dist
docker run --rm -v "$(pwd)/dist:/output" utilitati-mobile \
  sh -c 'cd android && ./gradlew assembleRelease && cp app/build/outputs/apk/release/app-release.apk /output/utilitati-md-release.apk'
```

Rezultatul: `dist/utilitati-md-release.apk`. Pentru iOS, build-ul nativ necesită
Xcode/macOS (EAS Build de la Expo gestionează asta drept alternativă).

> Build-ul CI principal se face prin GitHub Actions (`.github/workflows/build-apk.yml`)
> și EAS Workflows (`.eas/workflows/build-apps.yml`) — vezi mai jos.