import fs from "node:fs";

const GRAPHQL_URL = "https://api.expo.dev/graphql";
const TOKEN = process.env.EXPO_TOKEN;
const FCM_JSON = process.env.FCM_SERVICE_ACCOUNT_JSON;

const PLATFORM = process.argv.includes("--ios")
  ? "ios"
  : process.argv.includes("--all")
    ? "all"
    : "android";

if (!TOKEN) {
  console.error("EXPO_TOKEN lipsa: seteaza-l ca GitHub Secret (EXPO_TOKEN).");
  process.exit(2);
}

const appJson = JSON.parse(fs.readFileSync("app.json", "utf8")).expo;
const projectId = appJson?.extra?.eas?.projectId;
const androidPackage = appJson?.android?.package;
const iosBundle = appJson?.ios?.bundleIdentifier;

if (!projectId || !androidPackage) {
  console.error(
    "app.json invalid: lipsesc expo.extra.eas.projectId / exo.android.package."
  );
  process.exit(2);
}

async function gql(query, variables) {
  const res = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) {
    const msgs = json.errors.map((e) => e.message).join(" | ");
    throw new Error(`GraphQL: ${msgs}`);
  }
  return json.data;
}

async function fetchCredentials() {
  const q = `query AppCredentials($appId: String!) {
    app { byId(appId: $appId) {
      id
      androidAppCredentials {
        id
        applicationIdentifier
        googleServiceAccountKeyForFcmV1 { id }
      }
      iosAppCredentials {
        id
        appleAppIdentifier { id bundleIdentifier }
        pushKey { id }
      }
    } }
  }`;
  return gql(q, { appId: projectId });
}

async function ensureAndroid(creds) {
  let cred = creds.find((c) => c.applicationIdentifier === androidPackage);

  if (!cred) {
    console.log(`+ Creez Android app credentials pentru ${androidPackage}...`);
    const q = `mutation CreateAndroid($appId: ID!, $applicationIdentifier: String!) {
      androidAppCredentials { createAndroidAppCredentials(
        androidAppCredentialsInput: {}, appId: $appId, applicationIdentifier: $applicationIdentifier
      ) { id applicationIdentifier } }
    }`;
    cred = (await gql(q, { appId: projectId, applicationIdentifier: androidPackage }))
      .androidAppCredentials.createAndroidAppCredentials;
    console.log(`  -> id=${cred.id}`);
  }

  if (cred.googleServiceAccountKeyForFcmV1) {
    console.log(`OK Android: FCM V1 service account atasat la ${cred.applicationIdentifier}`);
    return;
  }

  if (!FCM_JSON) {
    console.error(
      `FCM V1 service account lipseste pe ${cred.applicationIdentifier} si ` +
        `secretul FCM_SERVICE_ACCOUNT_JSON nu a fost furnizat. Adauga in repo: Settings -> Secrets -> actions \n` +
        `  FCM_SERVICE_ACCOUNT_JSON = continutul JSON-ului generat in Firebase Console\n` +
        `  (proiect utilitati-md -> Project settings -> Service accounts -> Generate new private key).`
    );
    process.exit(1);
  }

  console.log(`+ Creez FCM V1 service account key pentru ${cred.applicationIdentifier}...`);
  const q = `mutation LinkFcmV1($androidAppCredentialsId: String!, $credential: String!) {
    androidAppCredentials { createFcmV1Credential(
      androidAppCredentialsId: $androidAppCredentialsId, credential: $credential
    ) { id } }
  }`;
  await gql(q, { androidAppCredentialsId: cred.id, credential: FCM_JSON });
  console.log("OK Android: FCM V1 service account atasat.");
}

async function ensureIos(creds) {
  if (!iosBundle) return;
  const cred = creds.find((c) => c.appleAppIdentifier?.bundleIdentifier === iosBundle);
  if (!cred) {
    console.error(
      `iOS: nu exista Apple App Identifier pentru ${iosBundle}. ` +
        `Conecteaza un APNs key (.p8) in expo.dev -> Credentials sau prin eas credentials (necesita Apple Developer membership). ` +
        "Build-urile de Simulator nu au nevoie de push credentials."
    );
    process.exit(1);
  }
  if (!cred.pushKey) {
    console.error(
      `iOS: exista appleAppIdentifier ${iosBundle} dar lipseste pushKey (APNs). ` +
        "Adauga APNs .p8 in expo.dev -> Credentials."
    );
    process.exit(1);
  }
  console.log(`OK iOS: push credentials gata pentru ${cred.appleAppIdentifier.bundleIdentifier}`);
}

const data = await fetchCredentials();
const app = data.app.byId;
console.log(`Proiect: ${app.id}`);

await ensureAndroid(app.androidAppCredentials || []);
if ((PLATFORM === "ios" || PLATFORM === "all") && iosBundle) {
  await ensureIos(app.iosAppCredentials || []);
}

console.log("Credentialele Expo push sunt corecte si complete.");
process.exit(0);