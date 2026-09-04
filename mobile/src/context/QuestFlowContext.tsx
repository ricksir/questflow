import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';
import * as Device from 'expo-device';
import * as Network from 'expo-network';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react';
import { createApi, exchangePairing, health } from '../lib/api';
import { getDb, outboxCount, resetLocalStudyData } from '../lib/db';
import { apiBasesOnDeviceSubnet, developmentServerApiBase, ipv4SubnetCandidates, uniqueApiBases } from '../lib/networkDiscovery';
import { normalizeApiBase } from '../lib/pairing';
import { clearSession, loadDeviceId, loadSession, saveDeviceId, saveSession, type StoredSession } from '../lib/session';
import { runSync, type SyncResult } from '../lib/sync';
import type { BootstrapProjection } from '../lib/types';
import { MOBILE_APP_VERSION } from '../lib/config';

export type QuestFlowContextValue = {
  loading: boolean;
  session: StoredSession | null;
  bootstrap: BootstrapProjection | null;
  error: string;
  pendingEvents: number;
  syncing: boolean;
  lastSync: SyncResult | null;
  pair: (apiBaseUrl: string, pairingToken: string, alternateApiBaseUrls?: string[], cloudBaseUrl?: string) => Promise<void>;
  refresh: () => Promise<void>;
  syncNow: () => Promise<SyncResult | null>;
  logout: (revokeRemote?: boolean) => Promise<void>;
  api: ReturnType<typeof createApi> | null;
};

const Context = createContext<QuestFlowContextValue | null>(null);

async function getOrCreateDeviceId(): Promise<string> {
  const persistent = await loadDeviceId();
  if (persistent) return persistent;
  const current = await loadSession();
  if (current?.deviceId) {
    await saveDeviceId(current.deviceId);
    return current.deviceId;
  }
  const created = Crypto.randomUUID();
  await saveDeviceId(created);
  return created;
}

function currentDevServerApiBase(): string {
  const expoConfigHost = String(Constants.expoConfig?.hostUri || '');
  const expoGoHost = String((Constants as any).expoGoConfig?.debuggerHost || '');
  return developmentServerApiBase(expoConfigHost || expoGoHost, 53155);
}

async function currentLanPlan(known: string[]): Promise<{ quick: string[]; scan: string[]; fallback: string[] }> {
  try {
    const ip = await Network.getIpAddressAsync();
    const devBase = currentDevServerApiBase();
    const sameSubnet = apiBasesOnDeviceSubnet(ip, known);
    const quick = uniqueApiBases([devBase, ...sameSubnet]);
    const allCurrentSubnet = ipv4SubnetCandidates(ip, 53155, quick);
    const quickSet = new Set(quick);
    const scan = allCurrentSubnet.filter((base) => !quickSet.has(base));
    const currentSet = new Set(allCurrentSubnet);
    const fallback = known.filter((base) => !currentSet.has(base));
    return { quick, scan, fallback };
  } catch {
    return { quick: uniqueApiBases([currentDevServerApiBase()]), scan: [], fallback: uniqueApiBases(known) };
  }
}

async function probeAuthenticatedBase(base: string, accessToken: string, expectedFingerprint = '', healthTimeoutMs = 500): Promise<BootstrapProjection | null> {
  try {
    const status = await health(base, healthTimeoutMs);
    if (expectedFingerprint && status.server_fingerprint && status.server_fingerprint !== expectedFingerprint) return null;
    return await createApi(base, accessToken).bootstrap();
  } catch {
    return null;
  }
}

async function discoverAuthenticatedServer(stored: StoredSession): Promise<{ base: string; bootstrap: BootstrapProjection } | null> {
  const known = uniqueApiBases([stored.apiBaseUrl, stored.cloudBaseUrl || '', ...(stored.knownApiBaseUrls || [])]);
  const plan = await currentLanPlan(known);

  // Em desenvolvimento, o host do Metro normalmente é o mesmo computador
  // que publica a API local. Tente a rede atual antes de IPs lembrados de outra rede.
  for (const base of plan.quick) {
    const bootstrap = await probeAuthenticatedBase(base, stored.accessToken, stored.serverFingerprint || '', 450);
    if (bootstrap) return { base, bootstrap };
  }

  // Varredura da sub-rede atual em lotes curtos. Assim uma troca de Wi-Fi não
  // fica aguardando timeouts longos do endereço antigo salvo no SecureStore.
  const width = 32;
  for (let index = 0; index < plan.scan.length; index += width) {
    const batch = plan.scan.slice(index, index + width);
    const results = await Promise.all(batch.map(async (base) => {
      const bootstrap = await probeAuthenticatedBase(base, stored.accessToken, stored.serverFingerprint || '', 400);
      return bootstrap ? { base, bootstrap } : null;
    }));
    const found = results.find(Boolean);
    if (found) return found;
  }

  // Endereços lembrados de outras redes ficam por último e com timeout curto.
  for (const base of plan.fallback) {
    const bootstrap = await probeAuthenticatedBase(base, stored.accessToken, stored.serverFingerprint || '', 350);
    if (bootstrap) return { base, bootstrap };
  }
  return null;
}

export function QuestFlowProvider({ children }: PropsWithChildren) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<StoredSession | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapProjection | null>(null);
  const [error, setError] = useState('');
  const [pendingEvents, setPendingEvents] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState<SyncResult | null>(null);
  const syncLock = useRef(false);
  const recoveryLock = useRef(false);

  const api = useMemo(() => session ? createApi(session.apiBaseUrl, session.accessToken) : null, [session]);
  const updatePending = useCallback(async () => setPendingEvents(await outboxCount()), []);

  const recoverServer = useCallback(async (): Promise<boolean> => {
    if (!session || recoveryLock.current) return false;
    recoveryLock.current = true;
    try {
      const found = await discoverAuthenticatedServer(session);
      if (!found) return false;
      const projectedCloud = normalizeApiBase(found.bootstrap?.sync?.cloud_bridge?.base_url || session.cloudBaseUrl || '');
      const knownApiBaseUrls = uniqueApiBases([found.base, projectedCloud, session.apiBaseUrl, ...(session.knownApiBaseUrls || [])]).slice(0, 12);
      const updated: StoredSession = { ...session, apiBaseUrl: found.base, cloudBaseUrl: projectedCloud || undefined, knownApiBaseUrls };
      if (found.base !== session.apiBaseUrl || projectedCloud !== (session.cloudBaseUrl || '') || JSON.stringify(knownApiBaseUrls) !== JSON.stringify(session.knownApiBaseUrls || [])) {
        await saveSession(updated);
        setSession(updated);
      }
      setBootstrap(found.bootstrap);
      setError('');
      return true;
    } finally {
      recoveryLock.current = false;
    }
  }, [session]);

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      const data = await api.bootstrap();
      setBootstrap(data);
      if (session) {
        const projectedCloud = normalizeApiBase(data?.sync?.cloud_bridge?.base_url || session.cloudBaseUrl || '');
        if (projectedCloud && projectedCloud !== (session.cloudBaseUrl || '')) {
          const knownApiBaseUrls = uniqueApiBases([session.apiBaseUrl, projectedCloud, ...(session.knownApiBaseUrls || [])]).slice(0, 12);
          const updated: StoredSession = { ...session, cloudBaseUrl: projectedCloud, knownApiBaseUrls };
          await saveSession(updated);
          setSession(updated);
        }
      }
      setError('');
    } catch (e) {
      const recovered = await recoverServer();
      if (!recovered) {
        setError((e as Error)?.message || 'Não foi possível atualizar o QuestFlow.');
        throw e;
      }
    } finally {
      await updatePending();
    }
  }, [api, recoverServer, session, updatePending]);

  const syncNow = useCallback(async () => {
    if (!api || syncLock.current) return null;
    syncLock.current = true;
    setSyncing(true);
    try {
      let result = await runSync(api, session?.apiBaseUrl || 'default', String(bootstrap?.active_project?.id || ''));
      if (!result.reachable && await recoverServer()) {
        // A mudança do endereço atualiza a sessão; o novo objeto api dispara outra
        // passagem de sync usando Studio local ou Cloud Bridge. A outbox permanece intacta.
        result = { ...result, online: true, message: 'Rota alternativa encontrada. Retomando a sincronização pelo melhor caminho disponível.' };
      }
      setLastSync(result);
      await updatePending();
      if (result.online && result.failed === 0) {
        try { setBootstrap(await api.bootstrap()); } catch { /* keep local UI */ }
      }
      return result;
    } finally {
      syncLock.current = false;
      setSyncing(false);
    }
  }, [api, bootstrap?.active_project?.id, recoverServer, session?.apiBaseUrl, updatePending]);

  const pair = useCallback(async (apiBaseUrl: string, pairingToken: string, alternateApiBaseUrls: string[] = [], cloudBaseUrl = '') => {
    const base = normalizeApiBase(apiBaseUrl);
    if (!base) throw new Error('Informe o endereço do QuestFlow Studio.');
    if (!pairingToken.trim()) throw new Error('Token de pareamento ausente.');

    const preferred = uniqueApiBases([base, ...alternateApiBaseUrls.map(normalizeApiBase)]);
    const lanPlan = await currentLanPlan(preferred);
    // No pareamento, tente primeiro exatamente o endereço entregue pelo QR/manual.
    // Depois tente a rede atual e, por último, endereços lembrados de outras redes.
    const candidates = uniqueApiBases([
      ...preferred,
      ...lanPlan.quick,
      ...lanPlan.scan,
      ...lanPlan.fallback,
    ]);
    const deviceId = await getOrCreateDeviceId();
    const device = {
      device_id: deviceId,
      platform: Device.osName?.toLowerCase().includes('ios') ? 'ios' : Device.osName?.toLowerCase().includes('android') ? 'android' : 'unknown',
      name: Device.deviceName || Device.modelName || 'QuestFlow Mobile',
      app_version: MOBILE_APP_VERSION,
      native_app_version: String((Constants as any).nativeAppVersion || ''),
    };

    let lastError: Error | null = null;
    const width = 24;
    for (let index = 0; index < candidates.length; index += width) {
      const batch = candidates.slice(index, index + width);
      const reachable = (await Promise.all(batch.map(async (candidate) => {
        try { await health(candidate, 850); return candidate; } catch { return ''; }
      }))).filter(Boolean);
      for (const candidate of reachable) {
        try {
          const result = await exchangePairing(candidate, pairingToken.trim(), device);
          const cloud = normalizeApiBase(result.cloud_bridge?.base_url || cloudBaseUrl || '');
          const stored: StoredSession = {
            accessToken: result.access_token,
            apiBaseUrl: candidate,
            knownApiBaseUrls: uniqueApiBases([candidate, cloud, ...preferred]).slice(0, 12),
            cloudBaseUrl: cloud || undefined,
            serverFingerprint: result.server_fingerprint || '',
            deviceId: result.device_id,
            expiresAt: result.expires_at,
            identity: result.identity,
          };
          await saveSession(stored);
          setSession(stored);
          setError('');
          return;
        } catch (e) {
          lastError = e as Error;
        }
      }
    }
    throw lastError || new Error('Não encontrei o QuestFlow no computador para o primeiro pareamento. Conecte o celular à mesma rede e tente novamente; depois do primeiro pareamento, o estudo pode continuar fora da rede local quando essa opção estiver configurada no programa.');
  }, []);


  const logout = useCallback(async (revokeRemote = true) => {
    try {
      if (revokeRemote && api && session) await api.disconnectSelf(session.deviceId);
    } catch { /* local logout must still work */ }
    await clearSession();
    await resetLocalStudyData();
    setSession(null);
    setBootstrap(null);
    setPendingEvents(0);
    setLastSync(null);
  }, [api, session]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        await getDb();
        const stored = await loadSession();
        if (stored?.deviceId) await saveDeviceId(stored.deviceId);
        if (mounted) setSession(stored);
      } finally {
        if (mounted) {
          setPendingEvents(await outboxCount());
          setLoading(false);
        }
      }
    })();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!api) return;
    refresh().catch(() => undefined);
    syncNow().catch(() => undefined);
  }, [api, refresh, syncNow]);

  useEffect(() => {
    if (!session) return;
    const subscription = Network.addNetworkStateListener((state) => {
      if (state.isConnected) {
        recoverServer().then(() => syncNow()).catch(() => undefined);
      }
    });
    return () => subscription.remove();
  }, [session, recoverServer, syncNow]);

  return (
    <Context.Provider value={{ loading, session, bootstrap, error, pendingEvents, syncing, lastSync, pair, refresh, syncNow, logout, api }}>
      {children}
    </Context.Provider>
  );
}

export function useQuestFlow() {
  const value = useContext(Context);
  if (!value) throw new Error('useQuestFlow precisa estar dentro de QuestFlowProvider.');
  return value;
}
