import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const SESSION_KEY = 'questflow.mobile.session.v1';
const DEVICE_ID_KEY = 'questflow.mobile.device-id.v1';

export type StoredSession = {
  accessToken: string;
  apiBaseUrl: string;
  knownApiBaseUrls?: string[];
  cloudBaseUrl?: string;
  serverFingerprint?: string;
  deviceId: string;
  expiresAt: string;
  identity?: { account_id: string; tenant_id: string; learner_id: string };
};

async function readSecureValue(key: string): Promise<string | null> {
  if (Platform.OS === 'web') return globalThis.localStorage?.getItem(key) || null;
  return SecureStore.getItemAsync(key);
}

async function writeSecureValue(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value, { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK });
}

async function removeSecureValue(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}


export async function loadDeviceId(): Promise<string | null> {
  const value = (await readSecureValue(DEVICE_ID_KEY))?.trim();
  return value || null;
}

export async function saveDeviceId(deviceId: string): Promise<void> {
  const value = String(deviceId || '').trim();
  if (!value) return;
  await writeSecureValue(DEVICE_ID_KEY, value);
}

export async function loadSession(): Promise<StoredSession | null> {
  const raw = await readSecureValue(SESSION_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredSession;
    if (!parsed.accessToken || !parsed.apiBaseUrl || !parsed.deviceId) return null;
    if (parsed.expiresAt && Date.parse(parsed.expiresAt) <= Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function saveSession(session: StoredSession): Promise<void> {
  await saveDeviceId(session.deviceId);
  await writeSecureValue(SESSION_KEY, JSON.stringify(session));
}

export async function clearSession(): Promise<void> {
  await removeSecureValue(SESSION_KEY);
}
