import { router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card, HeroCard, Metric, MicroBars, Muted, Pill, ProgressBar, Screen, ScreenHeader, SectionTitle, StatePanel, StatRing, palette } from '../../src/components/ui';
import { formatDuration } from '../../src/lib/format';
import { useQuestFlow } from '../../src/context/QuestFlowContext';
import { ReviewQueuePreview, TrendLineChart } from '../../src/components/analytics';

function reasonLabel(reason: string) {
  return ({
    memory_risk: 'há revisões vencidas ou próximas',
    recent_performance: 'o desempenho recente pede atenção',
    learning_gap: 'você marcou que ainda precisa estudar parte do conteúdo',
    mastery_gap: 'o domínio ainda está em consolidação',
    insufficient_evidence: 'o histórico desta matéria começou agora e já entra no cálculo',
  } as Record<string,string>)[reason] || reason;
}

function pct(value: number | null | undefined) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function timeLabel(value: number | null) {
  if (value == null) return 'tempo fora da métrica';
  return formatDuration(value, { suffix: 'ativos' });
}

export default function TodayScreen() {
  const { bootstrap, refresh, syncing, syncNow, pendingEvents, error } = useQuestFlow();
  useFocusEffect(useCallback(() => { refresh().catch(() => undefined); }, [refresh]));

  const today = bootstrap?.today;
  const progress = bootstrap?.progress;
  const analytics = bootstrap?.analytics;
  const top = today?.top_priority;
  const coach = today?.coach;
  const projectName = bootstrap?.active_project?.name || 'Projeto de prova ativo';
  const accuracy = progress?.summary.accuracy;
  const correct = Number(progress?.summary.correct || 0);
  const wrong = Number(progress?.summary.wrong || 0);
  const attempts = Number(progress?.summary.attempts || 0);
  const chartSubjects = (progress?.subjects || []).slice(0, 4);

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={syncing} onRefresh={() => syncNow().catch(() => undefined)} tintColor={palette.primary} />}
      >
        <ScreenHeader eyebrow="SEU ESTUDO HOJE" title="Hoje" detail={projectName} action={<Pill text={syncing ? 'Atualizando' : pendingEvents ? `${pendingEvents} pendentes` : 'Em dia'} tone={syncing || pendingEvents ? 'warning' : 'success'} />} />

        {!bootstrap ? <StatePanel state="loading" title="Montando seu plano" detail="Combinando revisões, domínio e prioridade para preparar a próxima sessão." /> : null}
        {error ? <StatePanel state="offline" title="Usando dados preservados" detail={`${error} Suas respostas registradas continuam seguras no aparelho.`} actionTitle="Tentar novamente" onAction={() => refresh().catch(() => undefined)} /> : null}

        {coach ? (
          <HeroCard>
            <View style={styles.rowBetween}>
              <Pill text="Plano inteligente" tone="info" />
              {top ? <Pill text={top.priority.level === 'high' ? 'Prioridade alta' : top.priority.level === 'medium' ? 'Prioridade média' : 'Manutenção'} tone={top.priority.level === 'high' ? 'warning' : 'violet'} /> : null}
            </View>
            <Text style={styles.heroHeadline}>{coach.headline}</Text>
            <Text style={styles.heroBody}>{coach.next_action}</Text>
            <View style={styles.heroMetaRow}>
              <View style={styles.heroMeta}><Text style={styles.heroMetaValue}>{coach.question_count}</Text><Text style={styles.heroMetaLabel}>questões agora</Text></View>
              <View style={styles.heroMeta}><Text style={styles.heroMetaValue}>{today?.today.reviews_due ?? 0}</Text><Text style={styles.heroMetaLabel}>revisões devidas</Text></View>
              <View style={styles.heroMeta}><Text style={styles.heroMetaValue}>{today?.today.not_studied_topics ?? 0}</Text><Text style={styles.heroMetaLabel}>a estudar</Text></View>
            </View>
            <Button title={`Começar sessão de ${coach.question_count} questões`} onPress={() => router.push('/(tabs)/questions')} tone="success" />
          </HeroCard>
        ) : null}

        {bootstrap ? (
          <Card style={styles.routeCard}>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={styles.routeEyebrow}>ROTEIRO DA SESSÃO</Text>
                <Text style={styles.routeTitle}>Do reforço à consolidação</Text>
              </View>
              <Pill text="3 etapas" tone="violet" />
            </View>
            <View style={styles.routeSteps}>
              <View style={styles.routeStep}>
                <View style={[styles.routeIndex, styles.routeIndexOrange]}><Text style={styles.routeIndexText}>1</Text></View>
                <View style={styles.routeCopy}><Text style={styles.routeLabel}>Recuperar</Text><Muted>{today?.today.reviews_due ? `${today.today.reviews_due} revisões no ponto ideal` : 'Memória em dia agora'}</Muted></View>
              </View>
              <View style={styles.routeConnector} />
              <View style={styles.routeStep}>
                <View style={[styles.routeIndex, styles.routeIndexCyan]}><Text style={styles.routeIndexText}>2</Text></View>
                <View style={styles.routeCopy}><Text style={styles.routeLabel}>Intercalar</Text><Muted>{coach?.question_count || today?.today.recommended_questions || 0} questões entre prioridades</Muted></View>
              </View>
              <View style={styles.routeConnector} />
              <View style={styles.routeStep}>
                <View style={[styles.routeIndex, styles.routeIndexViolet]}><Text style={styles.routeIndexText}>3</Text></View>
                <View style={styles.routeCopy}><Text style={styles.routeLabel}>Consolidar</Text><Muted>{pendingEvents ? `${pendingEvents} registros seguros aguardando envio` : 'Progresso sincronizado'}</Muted></View>
              </View>
            </View>
          </Card>
        ) : null}

        <View style={styles.sectionGap}>
          <SectionTitle eyebrow="Performance" title="Seu desempenho" detail="Uma leitura rápida do que as questões estão mostrando agora." />
          <Card style={styles.performanceCard}>
            <View style={styles.performanceTop}>
              <StatRing value={accuracy} label="acerto geral" />
              <View style={styles.performanceSummary}>
                <Text style={styles.performanceLead}>{attempts ? `${attempts} respostas analisadas` : 'Comece respondendo uma questão'}</Text>
                <Muted>{attempts ? `${correct} acertos e ${wrong} erros desde o início.` : 'A primeira resposta já aparecerá no histórico.'}</Muted>
              </View>
            </View>

            <View style={styles.splitBar}>
              <View style={[styles.splitCorrect, { flex: Math.max(correct, attempts ? 0.5 : 1) }]} />
              <View style={[styles.splitWrong, { flex: Math.max(wrong, attempts ? 0.5 : 0.001) }]} />
            </View>
            <View style={styles.legendRow}>
              <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: palette.success }]} /><Text style={styles.legendText}>Acertos {correct}</Text></View>
              <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: palette.danger }]} /><Text style={styles.legendText}>Erros {wrong}</Text></View>
              <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: palette.violet }]} /><Text style={styles.legendText}>Hoje {progress?.summary.today_attempts ?? 0}</Text></View>
            </View>

            {chartSubjects.length ? (
              <View style={styles.subjectChart}>
                <View style={styles.chartHeader}>
                  <View><Text style={styles.chartTitle}>Acerto por matéria</Text><Text style={styles.chartHint}>todo o histórico registrado</Text></View>
                  <MicroBars values={chartSubjects.map((item) => item.insight?.recent_accuracy ?? item.performance.accuracy ?? 0)} tone="accent" />
                </View>
                {chartSubjects.map((item, idx) => {
                  const value = item.insight?.recent_accuracy ?? item.performance.accuracy ?? 0;
                  const tones = ['primary', 'accent', 'violet', 'warning'] as const;
                  return (
                    <View key={item.subject_id} style={styles.subjectBarRow}>
                      <View style={styles.subjectBarHeader}><Text style={styles.subjectBarLabel} numberOfLines={1}>{item.label}</Text><Text style={styles.subjectBarPct}>{pct(value)}</Text></View>
                      <ProgressBar value={value} tone={tones[idx % tones.length]} height={8} />
                    </View>
                  );
                })}
              </View>
            ) : null}
          </Card>
        </View>

        <View style={styles.metrics}>
          <Metric label="Revisões devidas" value={today?.today.reviews_due ?? '—'} tone="warning" />
          <Metric label="Questões sugeridas" value={today?.today.recommended_questions ?? '—'} tone="primary" />
          <Metric label="Ainda não estudados" value={today?.today.not_studied_topics ?? 0} tone="violet" />
          <Metric label="Fila offline" value={pendingEvents} tone={pendingEvents ? 'warning' : 'success'} />
        </View>

        {analytics ? (
          <View style={styles.analyticsGrid}>
            <Card style={styles.analyticsCard}>
              <SectionTitle eyebrow="Percurso" title="Da primeira à última resposta" detail={`${analytics.sample_size} respostas reais • atualizado ${new Date(analytics.generated_at).toLocaleDateString('pt-BR')}`} />
              <TrendLineChart points={analytics.timeline} />
            </Card>
            <Card style={styles.analyticsCard}>
              <SectionTitle eyebrow="Memória" title="Revisões que pedem ação" detail="Barras mostram o volume vencido; não são uma nota de domínio." />
              <ReviewQueuePreview analytics={analytics} />
            </Card>
          </View>
        ) : null}

        <View style={styles.sectionGap}>
          <SectionTitle eyebrow="Foco" title="Onde concentrar esforço" detail="As matérias abaixo combinam desempenho recente, memória e lacunas de estudo." />
          {(today?.focus || []).slice(0, 5).map((item) => (
            <Card key={item.subject_id} style={styles.focusCard}>
              <View style={styles.rowBetween}>
                <Text style={styles.subjectSmall}>{item.label}</Text>
                <Pill text={item.status === 'needs_attention' ? 'Atenção' : item.status === 'monitor' ? 'Monitorar' : 'Estável'} tone={item.status === 'needs_attention' ? 'warning' : item.status === 'stable' ? 'success' : 'info'} />
              </View>
              <ProgressBar value={item.insight?.recent_accuracy ?? item.performance.accuracy ?? 0} tone={item.status === 'needs_attention' ? 'warning' : 'accent'} />
              <View style={styles.focusMetrics}>
                <Text style={styles.focusMetric}>Recente <Text style={styles.focusStrong}>{pct(item.insight?.recent_accuracy)}</Text></Text>
                <Text style={styles.focusMetric}>{item.performance.attempts} respostas</Text>
                <Text style={styles.focusMetric}>{item.memory.due_count} revisões</Text>
              </View>
              {(item.priority.reasons || []).slice(0, 2).map((reason) => <Text key={reason} style={styles.reason}>• {reasonLabel(reason)}</Text>)}
            </Card>
          ))}
          {bootstrap && !(today?.focus || []).length ? <StatePanel state="empty" title="Nenhum foco crítico agora" detail="Continue estudando; cada nova resposta atualiza imediatamente as prioridades." /> : null}
        </View>

        {(today?.recent_activity || []).length ? (
          <View style={styles.sectionGap}>
            <SectionTitle eyebrow="Histórico" title="Últimas respostas" detail="Todas as respostas registradas fazem parte do mesmo histórico de aprendizagem." />
            {today!.recent_activity.map((item) => (
              <Card key={`${item.attempt_id}-${item.answered_at}`} style={styles.activityRow}>
                <View style={{ flex: 1, gap: 3 }}>
                  <Text style={styles.activityTitle}>{item.code} • {item.subject}</Text>
                  <Muted>{timeLabel(item.active_response_seconds)}</Muted>
                </View>
                <Pill text={item.is_correct ? 'Acertou' : 'Errou'} tone={item.is_correct ? 'success' : 'danger'} />
              </Card>
            ))}
          </View>
        ) : null}

        <Button title={syncing ? 'Sincronizando…' : 'Sincronizar agora'} onPress={() => syncNow().catch(() => undefined)} disabled={syncing} tone="secondary" />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingVertical: 14, gap: 18, paddingBottom: 34 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  heroHeadline: { color: palette.text, fontSize: 27, fontWeight: '900', lineHeight: 32, letterSpacing: -0.6 },
  heroBody: { color: palette.primarySoft, fontSize: 15, lineHeight: 22, fontWeight: '600' },
  heroMetaRow: { flexDirection: 'row', gap: 8 },
  heroMeta: { flex: 1, backgroundColor: 'rgba(7,16,31,0.32)', borderRadius: 16, padding: 11, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  heroMetaValue: { color: palette.text, fontSize: 20, fontWeight: '900' },
  heroMetaLabel: { color: palette.primarySoft, fontSize: 10, marginTop: 2 },
  routeCard: { gap: 14, borderColor: 'rgba(167,121,255,0.28)' },
  routeEyebrow: { color: palette.violet, fontSize: 10, fontWeight: '900', letterSpacing: 1.1 },
  routeTitle: { color: palette.text, fontSize: 18, fontWeight: '900' },
  routeSteps: { gap: 0 },
  routeStep: { flexDirection: 'row', alignItems: 'center', gap: 11, minHeight: 48 },
  routeConnector: { width: 2, height: 12, marginLeft: 17, backgroundColor: palette.white08 },
  routeIndex: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  routeIndexOrange: { backgroundColor: 'rgba(255,122,24,0.14)', borderColor: 'rgba(255,122,24,0.35)' },
  routeIndexCyan: { backgroundColor: 'rgba(37,199,217,0.12)', borderColor: 'rgba(37,199,217,0.32)' },
  routeIndexViolet: { backgroundColor: 'rgba(167,121,255,0.12)', borderColor: 'rgba(167,121,255,0.32)' },
  routeIndexText: { color: palette.text, fontSize: 13, fontWeight: '900' },
  routeCopy: { flex: 1, gap: 2 },
  routeLabel: { color: palette.text, fontSize: 14, fontWeight: '900' },
  sectionGap: { gap: 10 },
  performanceCard: { gap: 15 },
  performanceTop: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  performanceSummary: { flex: 1, gap: 4 },
  performanceLead: { color: palette.text, fontSize: 16, fontWeight: '800', lineHeight: 22 },
  splitBar: { height: 13, flexDirection: 'row', overflow: 'hidden', borderRadius: 999, backgroundColor: palette.white08 },
  splitCorrect: { backgroundColor: palette.success },
  splitWrong: { backgroundColor: palette.danger },
  legendRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 8 },
  legendText: { color: palette.muted, fontSize: 12, fontWeight: '700' },
  subjectChart: { gap: 11, paddingTop: 4 },
  chartHeader: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 14 },
  chartTitle: { color: palette.text, fontSize: 14, fontWeight: '900' },
  chartHint: { color: palette.muted, fontSize: 10, fontWeight: '700', marginTop: 2 },
  subjectBarRow: { gap: 5 },
  subjectBarHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  subjectBarLabel: { color: palette.muted, fontSize: 12, fontWeight: '700', flex: 1 },
  subjectBarPct: { color: palette.text, fontSize: 12, fontWeight: '900' },
  metrics: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  analyticsGrid: { gap: 12 },
  analyticsCard: { gap: 12 },
  focusCard: { gap: 10 },
  subjectSmall: { color: palette.text, fontSize: 16, fontWeight: '800', flex: 1 },
  focusMetrics: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  focusMetric: { color: palette.muted, fontSize: 12 },
  focusStrong: { color: palette.text, fontWeight: '900' },
  reason: { color: palette.muted, lineHeight: 19, fontSize: 13 },
  activityRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  activityTitle: { color: palette.text, fontWeight: '800' },
});
