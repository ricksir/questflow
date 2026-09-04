import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card, HeroCard, Metric, MicroBars, Muted, Pill, ProgressBar, Screen, ScreenHeader, SectionTitle, StatePanel, StatRing, palette } from '../../src/components/ui';
import { formatDuration } from '../../src/lib/format';
import { useQuestFlow } from '../../src/context/QuestFlowContext';
import { enqueueEvent, getMeta, setMeta } from '../../src/lib/db';
import { createLearningEvent } from '../../src/lib/events';
import type { MobileStudyBacklogItem } from '../../src/lib/types';
import type { AnalyticsSnapshotV2 } from '../../src/lib/types';
import { ProjectionInterval, RangeSelector, RankedSubjectBars, TrendLineChart } from '../../src/components/analytics';

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function masteryLabel(value: string) {
  return ({ strong: 'Forte', consolidating: 'Consolidando', developing: 'Em consolidação', fragile: 'Frágil', insufficient_evidence: 'Pouca evidência' } as Record<string,string>)[value] || value;
}

function reasonLabel(reason: string) {
  return ({
    memory_risk: 'Há conteúdo chegando ao ponto de revisão.',
    recent_performance: 'O desempenho recente está abaixo do desejável.',
    learning_gap: 'Você sinalizou que ainda precisa estudar parte do conteúdo.',
    mastery_gap: 'O domínio estimado ainda precisa de consolidação.',
    insufficient_evidence: 'Esta matéria começou agora; todas as respostas já participam desta leitura.',
  } as Record<string,string>)[reason] || reason;
}

function trendLabel(value: number | null | undefined) {
  if (value == null) return 'Histórico iniciado; cada nova resposta atualiza esta leitura.';
  const pp = Math.round(value * 100);
  if (pp >= 4) return `Evolução de +${pp} p.p.`;
  if (pp <= -4) return `Queda de ${Math.abs(pp)} p.p.`;
  return 'Desempenho recente estável';
}

function localStudyTopicKey(item: MobileStudyBacklogItem) {
  return [item.subject, item.topic, item.lesson].map((value) => String(value || '').trim().toLocaleLowerCase()).join('|');
}

export default function ProgressScreen() {
  const { bootstrap, refresh, syncing, syncNow, session, api } = useQuestFlow();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [releasing, setReleasing] = useState('');
  const [backlogMessage, setBacklogMessage] = useState('');
  const [range, setRange] = useState<'all' | '4w' | '12w'>('all');
  const [analytics, setAnalytics] = useState<AnalyticsSnapshotV2 | null>(bootstrap?.analytics || null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  useFocusEffect(useCallback(() => { refresh().catch(() => undefined); }, [refresh]));
  const progress = bootstrap?.progress;

  useEffect(() => {
    let cancelled = false;
    if (!api) return () => { cancelled = true; };
    if (range === 'all' && bootstrap?.analytics) setAnalytics(bootstrap.analytics);
    setAnalyticsLoading(true);
    api.analytics(String(bootstrap?.active_project?.id || ''), range, 'attempt')
      .then((value) => { if (!cancelled) setAnalytics(value); })
      .catch(() => { if (!cancelled && range !== 'all') setAnalytics(null); })
      .finally(() => { if (!cancelled) setAnalyticsLoading(false); });
    return () => { cancelled = true; };
  }, [api, bootstrap?.active_project?.id, bootstrap?.analytics, range]);

  const releaseBacklogItem = async (item: MobileStudyBacklogItem) => {
    if (!session) return;
    setReleasing(item.backlog_id);
    setBacklogMessage('');
    try {
      await enqueueEvent(createLearningEvent({
        event_type: 'topic_study_completed',
        device_id: session.deviceId,
        exam_project_id: String(bootstrap?.active_project?.id || item.exam_project_id || ''),
        payload: { backlog_id: item.backlog_id, topic_key: item.topic_key },
      }));
      const raw = await getMeta('study_backlog_topic_keys_v1');
      let values: string[] = [];
      try { values = raw ? JSON.parse(raw) as string[] : []; } catch { values = []; }
      const key = localStudyTopicKey(item);
      await setMeta('study_backlog_topic_keys_v1', JSON.stringify(values.filter((value) => value !== key)));
      const result = await syncNow();
      setBacklogMessage(result?.online && result.reachable && !result.failed
        ? 'Assunto liberado. Ele poderá voltar às próximas sessões de questões.'
        : 'A liberação foi salva no aparelho e será concluída quando a sincronização voltar.');
      await refresh();
    } catch (error) {
      setBacklogMessage((error as Error)?.message || 'Não foi possível atualizar este assunto.');
    } finally {
      setReleasing('');
    }
  };

  const correct = Number(progress?.summary.correct || 0);
  const wrong = Number(progress?.summary.wrong || 0);
  const attempts = Number(progress?.summary.attempts || 0);
  const accuracy = progress?.summary.accuracy || 0;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={syncing} onRefresh={() => syncNow().catch(() => undefined)} tintColor={palette.primary} />}>
        <ScreenHeader eyebrow="EVOLUÇÃO REAL" title="Progresso" detail="Veja onde você está forte, onde está caindo e qual matéria merece a próxima revisão." action={<Pill text={syncing ? 'Atualizando' : 'Evidência ativa'} tone={syncing ? 'warning' : 'info'} />} />

        {!progress ? <StatePanel state="loading" title="Calculando seu diagnóstico" detail="O QuestFlow está reunindo respostas, memória e qualidade do tempo ativo." /> : null}

        {progress ? (
          <HeroCard>
            <View style={styles.heroTop}>
              <StatRing value={progress.summary.accuracy} label="acerto geral" tone="primary" size={104} />
              <View style={{ flex: 1, gap: 7 }}>
                <Pill text="Leitura inteligente" tone="info" />
                <Text style={styles.coachText}>{progress.summary.coach_text}</Text>
              </View>
            </View>
            <View style={styles.splitBar}>
              <View style={[styles.splitCorrect, { flex: Math.max(correct, attempts ? 0.5 : 1) }]} />
              <View style={[styles.splitWrong, { flex: Math.max(wrong, attempts ? 0.5 : 0.001) }]} />
            </View>
            <View style={styles.legendRow}>
              <Text style={styles.legendSuccess}>● {correct} acertos</Text>
              <Text style={styles.legendDanger}>● {wrong} erros</Text>
              <Text style={styles.legendNeutral}>● {progress.summary.today_attempts} hoje</Text>
            </View>
            <View style={styles.trendStrip}>
              <View><Text style={styles.trendStripTitle}>Ritmo entre matérias</Text><Muted>comparação visual das evidências recentes</Muted></View>
              <MicroBars values={(progress.subjects || []).slice(0, 7).map((item) => item.insight?.recent_accuracy ?? item.performance.accuracy ?? 0)} tone="accent" height={48} />
            </View>
          </HeroCard>
        ) : null}

        <View style={styles.metrics}>
          <Metric label="Tentativas" value={attempts || '—'} tone="primary" />
          <Metric label="Hoje" value={progress?.summary.today_attempts ?? '—'} tone="violet" />
          <Metric label="Tempo ativo médio" value={progress?.summary.avg_active_response_seconds == null ? '—' : `${Math.round(progress.summary.avg_active_response_seconds)}s`} tone="success" />
        </View>

        <View style={styles.sectionGap}>
          <View style={styles.analyticsHeader}>
            <SectionTitle eyebrow="Histórico" title="Percurso desde o início" detail="Tudo mostra o histórico completo; os outros filtros apenas aproximam períodos recentes." />
            <RangeSelector value={range} onChange={setRange} />
          </View>
          {analyticsLoading && !analytics ? <StatePanel state="loading" title="Atualizando série" detail="Agrupando tentativas reais no período escolhido." /> : null}
          {analytics ? (
            <>
              <Card style={styles.chartCard}>
                <View style={styles.rowBetween}><Text style={styles.chartTitle}>Resultado por resposta</Text><Pill text={`${analytics.sample_size} respostas`} tone="info" /></View>
                <Muted>Pontos ciano são acertos, pontos laranja são erros e a linha mostra o percentual acumulado.</Muted>
                <TrendLineChart points={analytics.timeline} />
              </Card>
              <ProjectionInterval analytics={analytics} />
              <Card style={styles.chartCard}>
                <SectionTitle eyebrow="Comparação" title="Oportunidade por matéria" detail="Ordenado por menor acerto; barras começam em zero e mostram quantas respostas formam o percentual." />
                <RankedSubjectBars analytics={analytics} />
              </Card>
              {analytics.source_freshness.retention_history !== 'available' ? <StatePanel state="info" title="Retenção histórica ainda não é uma linha" detail={analytics.source_freshness.note} /> : null}
            </>
          ) : !analyticsLoading ? <StatePanel state="empty" title="Sem dados neste período" detail="Escolha um período maior ou responda novas questões." /> : null}
        </View>

        {progress ? (
          <Card style={{ gap: 10 }}>
            <View style={styles.rowBetween}>
              <SectionTitle eyebrow="Qualidade" title="Tempo confiável" detail={progress.summary.timing_note} />
              <Pill text={`${progress.summary.timing_samples} válidas`} tone={progress.summary.timing_samples_excluded ? 'warning' : 'success'} />
            </View>
            <ProgressBar value={progress.summary.timing_samples ? Math.max(0, 1 - (progress.summary.timing_samples_excluded / Math.max(progress.summary.timing_samples + progress.summary.timing_samples_excluded, 1))) : 0} tone={progress.summary.timing_samples_excluded ? 'warning' : 'success'} />
            {progress.summary.timing_samples_excluded ? <Text style={styles.excluded}>{progress.summary.timing_samples_excluded} amostras foram preservadas, mas ficaram fora das métricas de velocidade.</Text> : <Text style={styles.qualityOk}>Nenhuma amostra problemática nesta leitura.</Text>}
          </Card>
        ) : null}

        {(progress?.study_backlog?.pending_count || 0) > 0 ? (
          <View style={styles.sectionGap}>
            <View style={styles.rowBetween}>
              <SectionTitle eyebrow="Fila pedagógica" title="Ainda não estudados" detail="Esses assuntos não contam como erro até você estudá-los." />
              <Pill text={`${progress!.study_backlog.pending_count}`} tone="warning" />
            </View>
            {backlogMessage ? <Text style={styles.backlogMessage}>{backlogMessage}</Text> : null}
            {progress!.study_backlog.items.map((item) => (
              <Card key={item.backlog_id} style={{ gap: 10 }}>
                <View style={styles.rowBetween}>
                  <View style={{ flex: 1, gap: 3 }}>
                    <Text style={styles.subject}>{item.topic || 'Assunto não informado'}</Text>
                    <Muted>{item.subject}{item.lesson ? ` • ${item.lesson}` : ''}</Muted>
                  </View>
                  <Pill text="Estudar" tone="warning" />
                </View>
                <Muted>Marcações: {item.mark_count}. Assim que estudar, libere o assunto para voltar às sessões.</Muted>
                <Button title="Já estudei — liberar para questões" onPress={() => releaseBacklogItem(item)} disabled={Boolean(releasing)} tone="secondary" />
              </Card>
            ))}
          </View>
        ) : null}

        <View style={styles.sectionGap}>
          <SectionTitle eyebrow="Mapa de desempenho" title="Prioridade por matéria" detail="Toque em uma matéria para entender a recomendação do QuestFlow." />
          {(progress?.subjects || []).map((item, idx) => {
            const open = Boolean(expanded[item.subject_id]);
            const gap = item.insight?.learning_gap;
            const recent = item.insight?.recent_accuracy ?? item.performance.accuracy ?? 0;
            const tones = ['primary', 'accent', 'violet', 'warning'] as const;
            return (
              <Pressable key={item.subject_id} onPress={() => setExpanded((current) => ({ ...current, [item.subject_id]: !open }))}>
                <Card style={{ gap: 11 }}>
                  <View style={styles.rowBetween}>
                    <Text style={styles.subject}>{item.label}</Text>
                    <Pill text={item.priority.level === 'high' ? 'Alta' : item.priority.level === 'medium' ? 'Média' : 'Baixa'} tone={item.priority.level === 'high' ? 'warning' : item.priority.level === 'medium' ? 'info' : 'success'} />
                  </View>
                  <View style={styles.rowBetween}>
                    <Muted>Acerto recente</Muted>
                    <Text style={styles.accuracy}>{pct(recent)}</Text>
                  </View>
                  <ProgressBar value={recent} tone={tones[idx % tones.length]} height={10} />
                  <View style={styles.subjectMetaRow}>
                    <Text style={styles.subjectMeta}>Domínio: {masteryLabel(item.mastery.level)}</Text>
                    <Text style={styles.subjectMeta}>{item.performance.attempts} respostas</Text>
                    <Text style={styles.subjectMeta}>{item.memory.due_count} revisões</Text>
                  </View>
                  <Text style={styles.trend}>{trendLabel(item.insight?.trend_delta)}</Text>

                  {open ? (
                    <View style={styles.detailBox}>
                      <Text style={styles.detailTitle}>Por que esta prioridade?</Text>
                      {(item.priority.reasons || []).length ? item.priority.reasons.map((reason) => (
                        <Text key={reason} style={styles.detailText}>• {reasonLabel(reason)}</Text>
                      )) : <Text style={styles.detailText}>• A matéria está em manutenção; não há alerta forte neste momento.</Text>}
                      {gap?.known ? <Text style={styles.detailText}>• Lacuna declarada em {gap.marked} de {gap.known} respostas recentes avaliadas.</Text> : null}
                      {(item.insight?.weak_topics || []).length ? (
                        <View style={{ gap: 5 }}>
                          <Text style={styles.detailTitle}>Revisar primeiro</Text>
                          {item.insight!.weak_topics.map((topic) => <Text key={topic.name} style={styles.detailText}>• {topic.name}: {pct(topic.accuracy)} em {topic.attempts} resposta(s)</Text>)}
                        </View>
                      ) : null}
                      <Text style={styles.tapHint}>Toque novamente para recolher.</Text>
                    </View>
                  ) : <Text style={styles.tapHint}>Toque para ver os motivos e assuntos fracos.</Text>}
                </Card>
              </Pressable>
            );
          })}
          {progress && !(progress.subjects || []).length ? <StatePanel state="empty" title="Sem matérias avaliadas" detail="Responda algumas questões para iniciar o mapa de desempenho." /> : null}
        </View>

        {(progress?.recent_activity || []).length ? (
          <View style={styles.sectionGap}>
            <SectionTitle eyebrow="Histórico" title="Respostas recentes" />
            {progress!.recent_activity.map((item) => (
              <Card key={`${item.attempt_id}-${item.answered_at}`} style={styles.activityRow}>
                <View style={{ flex: 1, gap: 3 }}>
                  <Text style={styles.activityTitle}>{item.code} • {item.subject}</Text>
                  <Muted>{item.active_response_seconds == null ? 'Tempo fora da métrica' : formatDuration(item.active_response_seconds, { suffix: 'ativos' })}</Muted>
                </View>
                <Pill text={item.is_correct ? 'Acerto' : 'Erro'} tone={item.is_correct ? 'success' : 'danger'} />
              </Card>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingVertical: 14, gap: 16, paddingBottom: 34 },
  heroTop: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  coachText: { color: palette.text, fontSize: 15, fontWeight: '700', lineHeight: 21 },
  splitBar: { height: 12, flexDirection: 'row', overflow: 'hidden', borderRadius: 999, backgroundColor: palette.white08 },
  splitCorrect: { backgroundColor: palette.success },
  splitWrong: { backgroundColor: palette.danger },
  legendRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  legendSuccess: { color: palette.success, fontSize: 12, fontWeight: '800' },
  legendDanger: { color: palette.danger, fontSize: 12, fontWeight: '800' },
  legendNeutral: { color: palette.primarySoft, fontSize: 12, fontWeight: '800' },
  trendStrip: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 14, paddingTop: 4 },
  trendStripTitle: { color: palette.text, fontSize: 13, fontWeight: '900', marginBottom: 2 },
  metrics: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  analyticsHeader: { gap: 10 },
  chartCard: { gap: 12 },
  chartTitle: { color: palette.text, fontSize: 17, fontWeight: '900' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  sectionGap: { gap: 10 },
  subject: { color: palette.text, fontSize: 16, fontWeight: '800', flex: 1 },
  accuracy: { color: palette.text, fontWeight: '900' },
  trend: { color: palette.accent2, fontSize: 13, fontWeight: '800' },
  subjectMetaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  subjectMeta: { color: palette.muted, fontSize: 11, fontWeight: '700' },
  excluded: { color: palette.warning, fontSize: 12, fontWeight: '700', lineHeight: 18 },
  qualityOk: { color: palette.success, fontSize: 12, fontWeight: '700' },
  detailBox: { gap: 7, backgroundColor: palette.surface2, borderRadius: 16, padding: 13, borderWidth: 1, borderColor: palette.white04 },
  detailTitle: { color: palette.text, fontSize: 13, fontWeight: '900' },
  detailText: { color: palette.muted, fontSize: 13, lineHeight: 19 },
  tapHint: { color: palette.primarySoft, fontSize: 12, fontWeight: '700' },
  activityRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  activityTitle: { color: palette.text, fontWeight: '800' },
  backlogMessage: { color: palette.accent, fontSize: 13, fontWeight: '700', lineHeight: 19 },
});
