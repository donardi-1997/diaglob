import * as SecureStore from "expo-secure-store";

const KEYS = {
  accessToken: "diaglob.accessToken",
  idToken: "diaglob.idToken",
  refreshToken: "diaglob.refreshToken",
  organizationId: "diaglob.organizationId",
  storeId: "diaglob.storeId",
} as const;

export interface StoredTokens {
  accessToken: string | null;
  idToken: string | null;
  refreshToken: string | null;
}

export async function getTokens(): Promise<StoredTokens> {
  const [accessToken, idToken, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(KEYS.accessToken),
    SecureStore.getItemAsync(KEYS.idToken),
    SecureStore.getItemAsync(KEYS.refreshToken),
  ]);

  return { accessToken, idToken, refreshToken };
}

export async function saveTokens(
  accessToken: string,
  idToken: string,
  refreshToken?: string,
) {
  const tasks = [
    SecureStore.setItemAsync(KEYS.accessToken, accessToken),
    SecureStore.setItemAsync(KEYS.idToken, idToken),
  ];

  if (refreshToken) {
    tasks.push(
      SecureStore.setItemAsync(KEYS.refreshToken, refreshToken),
    );
  }

  await Promise.all(tasks);
}

export async function getOrganizationId() {
  return SecureStore.getItemAsync(KEYS.organizationId);
}

export async function setOrganizationId(value: string | null) {
  if (!value) {
    await SecureStore.deleteItemAsync(KEYS.organizationId);
    return;
  }
  await SecureStore.setItemAsync(KEYS.organizationId, value);
}

export async function getStoreId() {
  return SecureStore.getItemAsync(KEYS.storeId);
}

export async function setStoreId(value: string | null) {
  if (!value) {
    await SecureStore.deleteItemAsync(KEYS.storeId);
    return;
  }
  await SecureStore.setItemAsync(KEYS.storeId, value);
}

export async function clearSession() {
  await Promise.all(
    Object.values(KEYS).map((key) =>
      SecureStore.deleteItemAsync(key),
    ),
  );
}
