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

Provider-ul poate fi setat și din **variabila de mediu `PUSH_PROVIDER=expo|fcm`**
(are prioritate față de /admin; în admin select-ul apare dezactivat când env-ul
e setat). Când provider-ul se schimbă din /admin, toate token-urile se șterg și
fiecare dispozitiv se reînregistrează automat la următoarea deschidere.

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
  (nu se trimit push-uri). Excepție: **facturile noi** (la conectare/refresh/sync
  programată) apar întotdeauna în lista/clopotelul de notificări, chiar și când
  push-urile sunt oprite sau nu există niciun dispozitiv înregistrat.

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

URL-ul de API nu mai este „cimentat" în build. La fiecare pornire aplicația își
**rezolvă dinamic DNS-ul** din sursa versionată
[`hosts_app_dns`](https://raw.githubusercontent.com/vadikonline1/pi.hole/refs/heads/main/hosts_app_dns):
caută linia `md.utilitati.app=<host>` și folosește `https://<host>/api` ca bază
pentru toate cererile. Astfel, când DNS-ul curent expiră, e suficient să
actualizezi **fișierul din repo** (nu trebuie un build nou).

Ordinea de precedență:
`fișierul DNS live` > `valoarea cache-uită local` > `app.json → extra.apiUrl` >
`constantă default`.

- `src/api/dns.ts` — preluarea + parsarea sursei (`resolveApiBase`), cu timeout
  de 5s și fallback la cache; `src/api/client.ts` folosește rezultatul în
  `request()`.

Pentru testare locală, schimbă fallback-ul la
`http://<IP-masina>:<port>/api` (backend-ul rulează cu CORS activat).

ProjectId-ul Expo (folosit pentru push notifications) este în
`app.json` → `extra.expo.projectId`.

## Actualizări in-app (canale beta / stable / Play)

În **Profil → Canal de actualizare** fiecare utilizator alege canalul:

- **Beta** — build-uri din ramura `deploy` (release-uri GitHub `apk-deploy-*`).
- **Stable** — build-uri din ramura `main` (release-uri GitHub `apk-main-*`).
- **Play Market** — deschide pagina Google Play în magazin.

Canalul ales se salvează local (AsyncStorage) și se raportează la server
(`PUT /api/auth/me { release_channel }`) — în admin, tabul **Users**, coloana
**Beta** afișează **Da/Nu** în funcție de canalul utilizatorului.

Butonul **„Verifică actualizări"**:

1. Citește versiunea aplicației instalate (`app.json → expo.version`).
2. Compară cu versiunea din `app.json` de pe ramura corespunzătoare
   (branch deploy/main pe GitHub) — „ultima versiune din git".
3. Dacă există una mai nouă, descarcă APK-ul (cel mai recent release
   `apk-<branch>-<sha>` din GitHub) în cache și îl deschide cu installer-ul
   Android (`expo-file-system` + `expo-intent-launcher`, content URI).

Detalii de implementare în `src/utils/updater.ts`. Dependențele noi:
`expo-file-system` (~19, pe API-ul legacy pentru `getContentUriAsync`) și
`expo-intent-launcher` (~13).

> **iOS**: instalarea nativă in-app nu există — actualizările vin din App
> Store / TestFlight. Utilizatorul poate totuși alege canalul (pentru raportare
> în admin), dar butonul de actualizare afișează explicația.

## Reclame (AdMob)

Configurația reclamelor este **server-driven**: citită la pornire din
`GET /api/config` (modificată din `GET /admin` → tabul **Ads**), fără să fie
nevoie de build nou. Formatările:

- **Banner** — momentan controlat de lista **Poziții (placements)** din admin
  (`dashboard`, `homes`, `facturi`, `home_detail`, `notificari`). Apare **doar
  în partea de jos** a ecranelor bifate:
  - Dashboard → după lista de locuințe.
  - Locuințe (`homes`) → după listă.
  - Detalii locuință (`home_detail`) → doar la final (în lista de utilități).
  - Facturi (`facturi`) → după fiecare 10 facturi; dacă sunt sub 10, un singur
    banner la finalul listei.
  - Notificări (`notificari`) → după fiecare 10 notificări; dacă sunt sub 10,
    un singur banner la finalul listei.
- **Interstițial + Recompensată** — **nu depind** de lista Poziții; sunt
  mereu active când sunt activate. Se declanșează doar din butonul
  **„Susține proiectul nostru"** de pe Dashboard (după diagrame/stats):
  `Interstițial` (limitat la intervalul din admin) → dacă se afișează, urmează
  și `Recompensată`. Butonul este vizibil doar când ambele sunt activate.

Unitățile (`ca-app-pub-...`) se setează în admin pe platformă (Android/iOS);
dacă lipsesc, aplicația folosește id-urile de test oferite de Google.

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