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

Notificările sunt **pornite implicit** și **auto-înregistrate**: la fiecare
pornire / login, aplicația își înregistrează automat token-ul la server
(`GET /api/config` → alegerea modului `fcm`/`expo` → `POST /api/devices/token`,
salvat în DB). Nu mai e nevoie de activare manuală. Doar o dezactivare explicită
împiedică reînregistrarea.

Fiecare utilizator are un flag `notifications_enabled` (implicit pornit):

- Din **aplicația mobilă**: Profil → butonul de notificări (`PUT /api/auth/notifications`).
  Când este oprit, backend-ul **șterge token-urile** dispozitivului și nu mai trimite.
- Din **admin** (`?tab=users` → coloana „Notificări"): adminul poate opri/porni
  notificările oricărui utilizator.
- Când flagul este oprit, `send_push` / `send_push_multi` **sar** peste utilizator
  (nu se trimit push-uri, istoricul de notificări nu se mai scrie).

### Prima configurare iOS (o singură dată, interactivă)

Construcția iOS pentru **dispozitiv fizic / App Store** (profilele `preview` și
`production`) necesită credentiale Apple (certificat de distribuție +
provisioning). Credentialele **nu pot fi create automat** de CI — se rulează
**o singură dată, interactiv** pe o mașină cu `eas-cli` instalat:

```bash
npm install -g eas-cli
npx eas login
npx eas credentials --platform ios
npx eas build --profile preview --platform ios   # verifică build-ul de dispozitiv
```

> **Push pe iOS necesită un APNs Key.** În plus față de certificatul de
> distribuție, `eas credentials --platform ios` te întreabă și despre o **cheie
> APNs** (`.p8` creată din Apple Developer → Certificates, Identifiers & Profiles
> → Keys → „Keys" → Enable „Apple Push Notifications service"). Fără această
> cheie, build-ul Expo înregistrează token-ul Expo push, dar **Apple nu livrează
> notificarea**. Cheia se generează o singură dată și EAS o păstrează pentru
> toate build-urile viitoare.

Credentialele sunt stocate în contul de pe **EAS** (nu se commit-uiesc), așa că
după acest pas, build-urile iOS din GitHub Actions / EAS Workflows merg automat.

> **Simulator iOS (fără Apple Developer)**: `eas.json` conține profilul
> `ios-simulator` cu `ios.simulator: true`, care produce un `.app` pentru
> **Simulator fără niciun cont Apple**. EAS Workflows folosește acest profil
> pentru preview-ul iOS automat:
> ```bash
> npx eas build --profile ios-simulator --platform ios
> ```
> Notă: Simulatorul iOS **nu** primește push-uri reale — pentru a verifica
> livrarea pe iOS e nevoie de build pe dispozitiv fizic (profilul `preview`).

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