import { router } from 'expo-router';
import { Alert, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useMemo, useState } from 'react';
import { Button, Card, HeroCard, LabelValue, Metric, Muted, Pill, Screen, ScreenHeader, SectionTitle, StatePanel, palette } from '../../src/components/ui';
import { useQuestFlow } from '../../src/context/QuestFlowContext';
import { registerNativePush, type ReminderRegistration } from '../../src/lib/push';
import * as Application from 'expo-application';
import { MOBILE_APP_VERSION } from '../../src/lib/config';

export default function ProfileScreen() {
  const { bootstrap, pendingEvents, lastSync, syncing, syncNow, logout } = useQuestFlow();
  const [reminderState, setReminderState] = useState<ReminderRegistration | null>(null);
  const [pushBusy, setPushBusy] = useState(false);
  const [reminderModalOpen, setReminderModalOpen] = useState(false);
  const [reminderHour, setReminderHour] = useState(19);
  const [reminderMinute, setReminderMinute] = useState(0);
  const [disconnectBusy, setDisconnectBusy] = useState(false);
  const project = bootstrap?.active_project;
  const reviewsDue = bootstrap?.today?.today?.reviews_due ?? 0;
  const recommendedQuestions = bootstrap?.today?.today?.recommended_questions ?? 0;

  const saveSummary = useMemo<{ title: string; tone: 'success' | 'warning' | 'info' }>(() => {
    if (syncing) return { title: 'Salvando…', tone: 'info' as const };
    if (pendingEvents > 0) return { title: `${pendingEvents} para salvar`, tone: 'warning' as const };
    if (lastSync?.online === false || lastSync?.reachable === false) return { title: 'Salvo no aparelho', tone: 'info' as const };
    return { title: 'Progresso salvo', tone: 'success' as const };
  }, [lastSync, pendingEvents, syncing]);

  const disconnect = () => {
    Alert.alert(
      'Desconectar este aparelho?',
      'Sua sessão será encerrada. O histórico de estudo já registrado no QuestFlow não será apagado.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Desconectar',
          style: 'destructive',
          onPress: async () => {
            setDisconnectBusy(true);
            try {
              await logout(true);
              router.replace('/pair');
            } finally {
              setDisconnectBusy(false);
            }
          },
        },
      ],
    );
  };

  const reminderTimeLabel = `${String(reminderHour).padStart(2, '0')}:${String(reminderMinute).padStart(2, '0')}`;

  const scheduleReminder = async () => {
    setPushBusy(true);
    try {
      const nextState = await registerNativePush(reminderHour, reminderMinute);
      setReminderState(nextState);
      if (nextState.ok) {
        setReminderModalOpen(false);
        Alert.alert('Lembrete reprogramado', nextState.message);
      } else {
        Alert.alert('Permissão necessária', nextState.message);
      }
    } catch {
      const unavailableState: ReminderRegistration = {
        ok: false,
        state: 'unavailable',
        message: 'Não foi possível programar o lembrete neste aparelho. Seu estudo e sua sincronização continuam funcionando normalmente.',
      };
      setReminderState(unavailableState);
      Alert.alert('Lembrete não programado', unavailableState.message);
    } finally {
      setPushBusy(false);
    }
  };


  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <ScreenHeader eyebrow="MEU ESTUDO" title="Perfil" detail="Projeto, revisões, lembretes e preferências que ajudam você a manter o ritmo de estudo." action={<Pill text={saveSummary.title} tone={saveSummary.tone} />} />

        <HeroCard>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.heroEyebrow}>QUESTFLOW MOBILE</Text>
              <Text style={styles.heroTitle}>Pronto para estudar</Text>
              <Text style={styles.heroBody}>Seu progresso é preservado no aparelho e enviado ao QuestFlow quando a conexão estiver disponível.</Text>
            </View>
            <Pill text={saveSummary.title} tone={saveSummary.tone} />
          </View>
        </HeroCard>

        <View style={styles.metrics}>
          <Metric label="Revisões hoje" value={reviewsDue} tone={reviewsDue ? 'warning' : 'success'} />
          <Metric label="Questões sugeridas" value={recommendedQuestions} tone="primary" />
          <Metric label="Respostas para salvar" value={pendingEvents} tone={pendingEvents ? 'warning' : 'success'} />
        </View>

        <View style={styles.sectionGap}>
          <SectionTitle eyebrow="Projeto" title={project?.name || 'Projeto ativo'} detail="O contexto usado para organizar questões, revisões e recomendações." />
          <Card style={{ gap: 9 }}>
            {project?.agency ? <LabelValue label="Órgão" value={project.agency} /> : null}
            {project?.role ? <LabelValue label="Cargo" value={project.role} /> : null}
            {project?.board ? <LabelValue label="Banca" value={project.board} /> : null}
            {project?.exam_date ? <LabelValue label="Prova" value={project.exam_date} /> : null}
            {!project ? <StatePanel state="empty" title="Nenhum projeto ativo" detail="Ative um projeto no Studio para receber recomendações contextualizadas pela prova." /> : null}
          </Card>
        </View>

        <Card style={{ gap: 11 }}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.cardTitle}>Salvar progresso</Text>
              <Muted>Respostas feitas sem conexão permanecem no aparelho até serem confirmadas pelo QuestFlow.</Muted>
            </View>
            <Pill text={saveSummary.title} tone={saveSummary.tone} />
          </View>
          <Button title={syncing ? 'Salvando…' : 'Salvar progresso agora'} onPress={() => syncNow().catch(() => undefined)} disabled={syncing} />
        </Card>

        <Card style={{ gap: 10 }}>
          <Text style={styles.cardTitle}>Lembretes de estudo</Text>
          <Muted>Ative um lembrete local diário. Ele funciona mesmo quando o Studio estiver fechado ou fora da rede.</Muted>
          {reminderState ? <StatePanel state={reminderState.ok ? 'success' : 'info'} title={reminderState.ok ? 'Lembrete ativado' : 'Permissão necessária'} detail={reminderState.message} /> : null}
          <Button
            title={reminderState?.ok ? 'Reprogramar lembrete' : 'Ativar lembrete diário'}
            disabled={pushBusy}
            onPress={() => {
              if (reminderState?.hour !== undefined) setReminderHour(reminderState.hour);
              if (reminderState?.minute !== undefined) setReminderMinute(reminderState.minute);
              setReminderModalOpen(true);
            }}
            tone="secondary"
          />
        </Card>

        <Card style={{ gap: 10 }}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.cardTitle}>Acessibilidade e versão</Text>
              <Muted>A interface respeita o tamanho de fonte do sistema, não depende apenas de cor e mantém alvos de toque ampliados.</Muted>
            </View>
            <Pill text={`v${MOBILE_APP_VERSION}`} tone="violet" />
          </View>
          <LabelValue label="Aplicativo" value={`QuestFlow Mobile ${MOBILE_APP_VERSION}`} />
          <LabelValue label="Build instalado" value={Application.nativeBuildVersion || 'preview'} />
        </Card>


        <Card style={{ gap: 8 }}>
          <Text style={styles.cardTitle}>Conta neste aparelho</Text>
          <Muted>Desconectar encerra a sessão neste celular, mas não apaga o histórico de estudo já salvo.</Muted>
          <Button title={disconnectBusy ? 'Desconectando…' : 'Desconectar deste QuestFlow'} onPress={disconnect} disabled={disconnectBusy} tone="danger" />
        </Card>
      </ScrollView>

      <Modal
        visible={reminderModalOpen}
        transparent
        animationType="slide"
        onRequestClose={() => !pushBusy && setReminderModalOpen(false)}
        statusBarTranslucent
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.reminderSheet} accessibilityViewIsModal>
            <Text style={styles.modalEyebrow}>LEMBRETE LOCAL</Text>
            <Text style={styles.modalTitle}>{reminderState?.ok ? 'Reprogramar lembrete' : 'Escolher horário'}</Text>
            <Muted>Escolha quando o QuestFlow deve lembrar você de iniciar uma sessão de estudo.</Muted>

            <View style={styles.timeSelector}>
              <Pressable accessibilityRole="button" accessibilityLabel="Diminuir uma hora" style={styles.timeControl} onPress={() => setReminderHour((value) => (value + 23) % 24)}>
                <Text style={styles.timeControlText}>−</Text>
              </Pressable>
              <Text style={styles.timeValue} accessibilityLabel={`Horário selecionado ${reminderTimeLabel}`}>{reminderTimeLabel}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Aumentar uma hora" style={styles.timeControl} onPress={() => setReminderHour((value) => (value + 1) % 24)}>
                <Text style={styles.timeControlText}>+</Text>
              </Pressable>
            </View>

            <View style={styles.presetRow}>
              {[7, 12, 19, 21].map((hour) => (
                <Pressable
                  key={hour}
                  accessibilityRole="button"
                  accessibilityState={{ selected: reminderHour === hour && reminderMinute === 0 }}
                  style={[styles.presetButton, reminderHour === hour && reminderMinute === 0 ? styles.presetButtonActive : null]}
                  onPress={() => { setReminderHour(hour); setReminderMinute(0); }}
                >
                  <Text style={styles.presetText}>{String(hour).padStart(2, '0')}:00</Text>
                </Pressable>
              ))}
            </View>

            <Pressable accessibilityRole="button" style={styles.minuteButton} onPress={() => setReminderMinute((value) => (value + 15) % 60)}>
              <Text style={styles.minuteButtonText}>Minutos: {String(reminderMinute).padStart(2, '0')} · tocar para alterar</Text>
            </Pressable>

            <Button title={pushBusy ? 'Programando…' : `Confirmar para ${reminderTimeLabel}`} onPress={scheduleReminder} disabled={pushBusy} />
            <Button title="Cancelar" onPress={() => setReminderModalOpen(false)} disabled={pushBusy} tone="secondary" />
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingVertical: 14, gap: 16, paddingBottom: 34 },
  rowBetween: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  heroEyebrow: { color: palette.accent, fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  heroTitle: { color: palette.text, fontSize: 25, fontWeight: '900', letterSpacing: -0.5 },
  heroBody: { color: palette.primarySoft, lineHeight: 21, fontWeight: '600' },
  metrics: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  sectionGap: { gap: 9 },
  cardTitle: { color: palette.text, fontSize: 17, fontWeight: '900' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(2, 7, 16, 0.78)', justifyContent: 'flex-end' },
  reminderSheet: { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1, borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 22, paddingBottom: 30, gap: 15 },
  modalEyebrow: { color: palette.accent2, fontSize: 11, fontWeight: '900', letterSpacing: 1.2 },
  modalTitle: { color: palette.text, fontSize: 25, fontWeight: '900', letterSpacing: -0.4 },
  timeSelector: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, backgroundColor: palette.surface2, borderColor: palette.border, borderWidth: 1, borderRadius: 18, padding: 10 },
  timeControl: { width: 56, height: 56, alignItems: 'center', justifyContent: 'center', borderRadius: 16, backgroundColor: palette.surface3 },
  timeControlText: { color: palette.text, fontSize: 34, fontWeight: '800', lineHeight: 38 },
  timeValue: { flex: 1, color: palette.text, fontSize: 35, fontWeight: '900', textAlign: 'center', fontVariant: ['tabular-nums'] },
  presetRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  presetButton: { flexGrow: 1, minWidth: 66, alignItems: 'center', borderWidth: 1, borderColor: palette.border, borderRadius: 14, paddingVertical: 11, paddingHorizontal: 10 },
  presetButtonActive: { borderColor: palette.accent, backgroundColor: 'rgba(255, 122, 24, 0.16)' },
  presetText: { color: palette.text, fontWeight: '800' },
  minuteButton: { alignItems: 'center', borderRadius: 14, paddingVertical: 12, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border },
  minuteButtonText: { color: palette.primarySoft, fontWeight: '800' },
});
