# Utilități.MD — Aplicație mobilă (Android + iOS)

Aplicație mobilă realizată cu **React Native + Expo** (un singur cod pentru ambele
platforme), care consumă **API-ul REST JSON** al backend-ului FastAPI existent
(`/api`).

## Structură

```
mobile/
  App.tsx                  # intrarea aplicației (auth provider + navigare)
  app.json                 # configurare Expo (Android/iOS ids, API URL)
  package.json             # dependențe
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
  cu aplicația „Expo Go”, sau build nativ cu EAS / prebuild.

## Instalare

```bash
cd mobile
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

Aceasta creează în folderul `mobile/` subfolderele `android/` și `ios/` cu
proiectele native complete (Gradle / Xcode). De reținut:

- Modificările aduse sub `mobile/android/` sau `mobile/ios/` **se pierd** la
  următorul `expo prebuild` (sunt regenerate). Ajustările native persistente se
  fac prin `app.json` sau fișiere de config din `mobile/`.
- Pentru distribuție (Play Store / App Store) se folosește **EAS Build**:
  ```bash
  npx eas build --platform android
  npx eas build --platform ios
  ```

## API URL

URL-ul de API este setat în `app.json` → `extra.apiUrl`
(`https://utilitati.nistorlazar.md/api`). Pentru testare locală, schimbă-l la
`http://<IP-masina>:<port>/api` (backend-ul rulează cu CORS activat).

## Autentificare

Aplicația se loghează prin `POST /api/auth/login` cu username + parolă,
primește un **token de sesiune**, pe care îl trimite mai departe ca
`Authorization: Bearer <token>` pentru toate celelalte cereri. Token-ul este
păstrat securizat în `expo-secure-store`.

## Resetare parolă (în aplicație)

Din ecranul de autentificare → „Ai uitat parola?”:

1. Introdu adresa de email → aplicația apelează `POST /api/auth/forgot-password`
   și primești un link de resetare prin email.
2. Deschide linkul (sau lipește codul în aplicație) → ecranul „Resetare parolă”
   apelează `POST /api/auth/reset-password` cu noul token + parola nouă.

Aplicația suportă și **deep linking**: un link `utilitati://reset-password/<token>`
deschide direct ecranul de resetare din aplicație (`scheme: "utilitati"` în `app.json`).

## Build Android în Docker (APK)

Imaginea `Dockerfile` instalează Node + Android SDK + Java, generează proiectul
nativ (`expo prebuild --platform android`) și poate produce un APK release:

```bash
cd mobile
docker build -t utilitati-mobile .
mkdir -p dist
docker run --rm -v "$(pwd)/dist:/output" utilitati-mobile \
  sh -c 'cd android && ./gradlew assembleRelease && cp app/build/outputs/apk/release/app-release.apk /output/utilitati-md-release.apk'
# sau doar:
docker run --rm -v "$(pwd)/dist:/output" utilitati-mobile
```

Rezultatul: `dist/utilitati-md-release.apk`. Pentru iOS, build-ul nativ necesită
Xcode/macOS (EAS Build de la Expo gestionează asta drept alternativă).
