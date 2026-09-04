import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button, Card, HeroCard, Muted, Screen, SectionTitle, StatePanel, palette } from '../src/components/ui';
import { useQuestFlow } from '../src/context/QuestFlowContext';
import { parsePairingValue } from '../src/lib/pairing';
import { MOBILE_APP_VERSION } from '../src/lib/config';

export default function PairScreen() {
  const { pair } = useQuestFlow();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [server, setServer] = useState('');
  const [serverCandidates, setServerCandidates] = useState<string[]>([]);
  const [cloudServer, setCloudServer] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [showManual, setShowManual] = useState(false);
  const scanConsumed = useRef(false);
  const canSubmit = useMemo(() => Boolean(server.trim() && token.trim() && !busy), [server, token, busy]);

  const absorb = (value: string) => {
    const parsed = parsePairingValue(value);
    if (parsed.server) setServer(parsed.server);
    if (parsed.servers.length) setServerCandidates(parsed.servers);
    if (parsed.cloud) setCloudServer(parsed.cloud);
    if (parsed.token) setToken(parsed.token);
    if (parsed.server && parsed.token) setScanning(false);
    return parsed;
  };

  const pairingErrorMessage = (failure: unknown) => {
    const detail = String((failure as Error)?.message || failure || '').toLowerCase();
    if (detail.includes('expired') || detail.includes('expir') || detail.includes('used') || detail.includes('usado') || detail.includes('invalid token')) {
      return 'Este QR expirou ou já foi usado. Gere um novo código no QuestFlow Studio e leia novamente.';
    }
    if (detail.includes('network') || detail.includes('fetch') || detail.includes('timeout') || detail.includes('connect')) {
      return 'O QR foi lido, mas o celular não alcançou o Studio. Confirme que ambos estão na mesma rede Wi-Fi e permita o QuestFlow no Firewall do Windows.';
    }
    return 'O QR foi lido, mas não foi possível concluir o pareamento. Gere um novo código ou use a alternativa manual.';
  };

  const connectPayload = async (nextServer: string, nextToken: string, nextCandidates: string[] = [], nextCloud = '') => {
    setBusy(true);
    setError('');
    setScanning(false);
    try {
      await pair(nextServer, nextToken, nextCandidates, nextCloud);
      router.replace('/(tabs)/today');
    } catch (e) {
      setShowManual(true);
      setError(pairingErrorMessage(e));
    } finally {
      setBusy(false);
      scanConsumed.current = false;
    }
  };

  const connect = async () => connectPayload(server, token, serverCandidates, cloudServer);

  const handleBarcodeScanned = ({ data }: { data: string }) => {
    if (scanConsumed.current || busy) return;
    scanConsumed.current = true;
    const parsed = absorb(data);
    if (!parsed.server || !parsed.token) {
      setScanning(false);
      setShowManual(true);
      setError('Este QR não contém um endereço e um token válidos do QuestFlow Studio. Gere um novo código e tente novamente.');
      scanConsumed.current = false;
      return;
    }
    void connectPayload(parsed.server, parsed.token, parsed.servers, parsed.cloud);
  };

  const openScanner = async () => {
    setError('');
    scanConsumed.current = false;
    if (!permission?.granted) {
      const result = await requestPermission();
      if (!result.granted) {
        setError('Permissão de câmera negada. Você ainda pode informar o endereço e o token manualmente.');
        return;
      }
    }
    setScanning(true);
  };

  if (scanning) {
    return (
      <View style={styles.cameraScreen}>
        <CameraView
          style={StyleSheet.absoluteFill}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          onBarcodeScanned={handleBarcodeScanned}
        />
        <View style={styles.cameraOverlay}>
          <View style={styles.scanFrame} />
          <Text style={styles.cameraText}>Aponte para o QR exibido na aba QuestFlow Mobile do Studio.</Text>
          <Pressable onPress={() => setScanning(false)} style={styles.closeScan}><Text style={styles.closeScanText}>Cancelar</Text></Pressable>
        </View>
      </View>
    );
  }

  return (
    <Screen safeTop={false} safeBottom>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <HeroCard>
            <Text style={styles.heroKicker}>QUESTFLOW MOBILE {MOBILE_APP_VERSION}</Text>
            <Text style={styles.heroTitle}>Conecte pelo QR</Text>
            <Muted>Abra QuestFlow Mobile no Studio e leia o código exibido. A conexão é segura e de uso único.</Muted>
            <Button title="Ler QR do QuestFlow Studio" onPress={openScanner} tone="success" />
          </HeroCard>

          <Pressable accessibilityRole="button" accessibilityState={{ expanded: showManual }} onPress={() => setShowManual((value) => !value)} style={({ pressed }) => [styles.manualToggle, pressed && styles.pressed]}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.manualToggleTitle}>Não consegue ler o QR?</Text>
              <Text style={styles.manualToggleDetail}>{showManual ? 'Ocultar conexão manual' : 'Usar endereço e código manualmente'}</Text>
            </View>
            <Text style={styles.manualToggleIcon}>{showManual ? '−' : '+'}</Text>
          </Pressable>

          {showManual ? <Card style={{ gap: 12 }}>
              <SectionTitle eyebrow="Alternativa manual" title="Informar código" detail="Use o endereço e o token exibidos pelo Studio." />
              <Text style={styles.label}>Endereço do Studio</Text>
              <TextInput autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="http://192.168.1.20:53155" placeholderTextColor={palette.muted} value={server} onChangeText={setServer} style={styles.input} />
              <Text style={styles.label}>Token de pareamento</Text>
              <TextInput autoCapitalize="none" autoCorrect={false} placeholder="Cole o token ou o link questflow://pair..." placeholderTextColor={palette.muted} value={token} onChangeText={(value) => { if (value.startsWith('questflow://')) absorb(value); else setToken(value); }} style={styles.input} />
              {error ? <StatePanel state="error" title="Não foi possível conectar" detail={error} actionTitle="Ler QR" onAction={openScanner} /> : null}
              {busy ? <StatePanel state="loading" title="QR lido — conectando" detail="Validando o endereço e criando uma sessão segura." /> : <Button title="Conectar este aparelho" onPress={connect} disabled={!canSubmit} />}
            </Card> : error ? <StatePanel state="error" title="Não foi possível conectar" detail="Tente ler o QR novamente ou abra a alternativa manual." actionTitle="Ler QR" onAction={openScanner} /> : null}

          <Card style={{ gap: 5 }}>
            <Text style={styles.tipTitle}>No computador</Text>
            <Muted><Text style={{ color: palette.text, fontWeight: '800' }}>QuestFlow Mobile</Text> → <Text style={{ color: palette.text, fontWeight: '800' }}>Conectar novo aparelho</Text>.</Muted>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingVertical: 14, gap: 12, paddingBottom: 36 },
  heroKicker: { color: palette.accent, fontSize: 11, fontWeight: '900', letterSpacing: 1.1 },
  heroTitle: { color: palette.text, fontSize: 27, fontWeight: '900', lineHeight: 32 },
  label: { color: palette.text, fontSize: 13, fontWeight: '800' },
  input: { minHeight: 52, borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.surface2, color: palette.text, paddingHorizontal: 14 },
  manualToggle: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 16, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.surface },
  manualToggleTitle: { color: palette.text, fontSize: 15, fontWeight: '900' },
  manualToggleDetail: { color: palette.muted, fontSize: 12, lineHeight: 17 },
  manualToggleIcon: { color: palette.accent2, fontSize: 24, fontWeight: '700' },
  pressed: { opacity: 0.84 },
  tipTitle: { color: palette.text, fontWeight: '900', fontSize: 16 },
  cameraScreen: { flex: 1, backgroundColor: '#000' },
  cameraOverlay: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28, backgroundColor: 'rgba(0,0,0,0.30)' },
  scanFrame: { width: 250, height: 250, borderWidth: 3, borderColor: palette.primary, borderRadius: 28, marginBottom: 24, backgroundColor: 'rgba(255,138,42,0.04)' },
  cameraText: { color: '#FFFFFF', textAlign: 'center', fontSize: 16, fontWeight: '700' },
  closeScan: { marginTop: 24, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.64)' },
  closeScanText: { color: '#FFFFFF', fontWeight: '800' },
});
