import { Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Line, Path, Text as SvgText } from 'react-native-svg';
import type { AnalyticsSnapshotV2, AnalyticsTimelinePoint } from '../lib/types';
import { Card, Pill, ProgressBar, StatePanel, palette } from './ui';

function clamp01(value: number | null | undefined) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

function dateLabel(value: string) {
  const parsed = new Date(value.includes('T') ? value : `${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: 'UTC' });
}

export function RangeSelector({ value, onChange }: { value: string; onChange: (value: 'all' | '4w' | '12w') => void }) {
  const labels = { all: 'Tudo', '4w': '28 dias', '12w': '84 dias' } as const;
  return (
    <View accessibilityLabel="Período da análise" style={styles.rangeSelector}>
      {(['all', '4w', '12w'] as const).map((item) => (
        <Pressable
          key={item}
          accessibilityRole="tab"
          accessibilityState={{ selected: value === item }}
          onPress={() => onChange(item)}
          style={[styles.rangeOption, value === item && styles.rangeOptionActive]}
        >
          <Text style={[styles.rangeText, value === item && styles.rangeTextActive]}>{labels[item]}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function TrendLineChart({ points, title = 'Histórico de respostas' }: { points: AnalyticsTimelinePoint[]; title?: string }) {
  const usable = points.filter((point) => point.accuracy != null);
  if (!usable.length) {
    return <StatePanel state="info" title="Histórico ainda vazio" detail="Sua primeira resposta aparecerá aqui imediatamente como acerto ou erro." />;
  }
  const width = 336;
  const height = 176;
  const pad = { left: 34, right: 12, top: 16, bottom: 28 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (index: number) => pad.left + (index / Math.max(1, usable.length - 1)) * innerW;
  const y = (value: number) => pad.top + (1 - clamp01(value)) * innerH;
  const observed = points.filter((point) => point.accuracy != null);
  const cumulative = usable.map((point) => Number(point.cumulative_accuracy ?? point.accuracy));
  const segments = cumulative.map((value, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(1)} ${y(value).toFixed(1)}`);
  const latest = [...usable].reverse()[0];
  const firstValue = Number(cumulative[0] || 0);
  const latestValue = Number(cumulative[cumulative.length - 1] || 0);
  const delta = usable.length > 1 ? Math.round((latestValue - firstValue) * 100) : null;
  const summary = `${title}. ${usable.length} ${usable.length === 1 ? 'resposta registrada' : 'respostas registradas'} desde o início. Acerto acumulado atual de ${Math.round(clamp01(latestValue) * 100)} por cento.`;
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={summary}>
      <View style={styles.sampleBanner}>
        <View style={styles.sampleCopy}>
          <Text style={styles.sampleMaturity}>Desde a primeira resposta</Text>
          <Text style={styles.metaText}>{usable.length} {usable.length === 1 ? 'resposta real' : 'respostas reais'}</Text>
        </View>
        <View style={styles.sampleValueBox}>
          <Text style={styles.sampleValue}>{Math.round(latestValue * 100)}% acumulado</Text>
          {delta == null ? null : (
            <Text style={styles.sampleDelta}>{delta >= 0 ? '+' : '−'}{Math.abs(delta)} p.p. desde o início</Text>
          )}
        </View>
      </View>
      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.5, 1].map((value) => (
          <Line key={value} x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} stroke="rgba(156,175,196,0.20)" strokeWidth="1" />
        ))}
        <SvgText x={2} y={y(1) + 4} fill={palette.muted} fontSize="10">100%</SvgText>
        <SvgText x={8} y={y(0.5) + 4} fill={palette.muted} fontSize="10">50%</SvgText>
        <SvgText x={15} y={y(0) + 4} fill={palette.muted} fontSize="10">0%</SvgText>
        {observed.length === 1 ? <Line x1={pad.left} x2={width-pad.right} y1={y(latestValue)} y2={y(latestValue)} stroke={palette.accent2} strokeWidth="2" strokeDasharray="7 6" /> : <Path d={segments.join(' ')} fill="none" stroke={palette.accent2} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />}
        {usable.map((point, index) => (
          <Circle key={`${point.period_start}-${index}`} cx={x(index)} cy={y(Number(point.accuracy))} r={index === usable.length - 1 ? 4.2 : 2.8} fill={palette.bg} stroke={Number(point.accuracy) >= 0.5 ? palette.accent2 : palette.primary} strokeWidth="2" />
        ))}
        <SvgText x={pad.left} y={height - 6} fill={palette.muted} fontSize="10">{dateLabel(usable[0]?.period_start || '')}</SvgText>
        <SvgText x={width - pad.right} y={height - 6} fill={palette.muted} fontSize="10" textAnchor="end">{dateLabel(latest?.period_start || '')}</SvgText>
      </Svg>
      <Text style={styles.chartSummary}>{summary}</Text>
    </View>
  );
}

export function RankedSubjectBars({ analytics, limit = 6 }: { analytics: AnalyticsSnapshotV2; limit?: number }) {
  const rows = [...(analytics.subjects || [])]
    .sort((a, b) => (a.accuracy ?? 2) - (b.accuracy ?? 2) || b.due_reviews - a.due_reviews)
    .slice(0, limit);
  if (!rows.length) return <StatePanel state="empty" title="Sem matérias avaliadas" detail="Responda algumas questões para formar comparações por matéria." />;
  return (
    <View style={styles.rankList} accessibilityLabel="Matérias ordenadas por oportunidade de melhoria">
      {rows.map((item, index) => (
        <View key={item.subject_id} style={styles.rankRow}>
          <View style={styles.rankHeader}>
            <Text style={styles.rankIndex}>{index + 1}</Text>
            <Text style={styles.rankLabel} numberOfLines={1}>{item.label}</Text>
            <Text style={styles.rankValue}>{item.accuracy == null ? '—' : `${Math.round(item.accuracy * 100)}%`}</Text>
          </View>
          <ProgressBar value={item.accuracy || 0} tone={item.accuracy != null && item.accuracy < 0.6 ? 'warning' : 'accent'} height={8} />
          <View style={styles.rankMeta}>
            <Text style={styles.metaText}>{item.attempts} {item.attempts === 1 ? 'resposta' : 'respostas'}</Text>
            <Text style={styles.metaText}>{item.due_reviews} revisões</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

export function ProjectionInterval({ analytics }: { analytics: AnalyticsSnapshotV2 }) {
  const band = analytics.projection_band;
  if (band.estimate == null || band.low == null || band.high == null) {
    return <StatePanel state="info" title="Intervalo ainda indisponível" detail="O intervalo aparecerá depois das primeiras respostas confirmadas." />;
  }
  return (
    <Card style={styles.intervalCard}>
      <View style={styles.intervalHeader}>
        <View><Text style={styles.intervalValue}>{Math.round(band.estimate * 100)}%</Text><Text style={styles.metaText}>desempenho observado</Text></View>
        <Pill text={`${band.sample_size} ${band.sample_size === 1 ? 'resposta' : 'respostas'}`} tone="info" />
      </View>
      <View accessibilityRole="progressbar" accessibilityLabel={`Intervalo de 95 por cento entre ${Math.round(band.low * 100)} e ${Math.round(band.high * 100)} por cento`} style={styles.intervalTrack}>
        <View style={[styles.intervalBand, { left: `${band.low * 100}%`, width: `${Math.max(2, (band.high - band.low) * 100)}%` }]} />
        <View style={[styles.intervalMarker, { left: `${band.estimate * 100}%` }]} />
      </View>
      <View style={styles.intervalLabels}><Text style={styles.metaText}>{Math.round(band.low * 100)}%</Text><Text style={styles.metaText}>{Math.round(band.high * 100)}%</Text></View>
      <Text style={styles.chartSummary}>{band.label}</Text>
    </Card>
  );
}

export function ReviewQueuePreview({ analytics }: { analytics: AnalyticsSnapshotV2 }) {
  const rows = (analytics.review_queue || []).slice(0, 5);
  if (!rows.length) return <StatePanel state="success" title="Memória em dia" detail="Nenhuma matéria possui revisão vencida neste recorte." />;
  const max = Math.max(...rows.map((row) => row.due_count), 1);
  return (
    <View style={styles.reviewList}>
      {rows.map((row) => (
        <View key={row.subject_id} style={styles.reviewRow}>
          <View style={styles.rankHeader}><Text style={styles.rankLabel} numberOfLines={1}>{row.label}</Text><Text style={styles.rankValue}>{row.due_count}</Text></View>
          <ProgressBar value={row.due_count / max} tone="warning" height={7} />
          <Text style={styles.metaText}>Sessão sugerida: {row.question_count} questões</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  rangeSelector: { flexDirection: 'row', alignSelf: 'flex-start', padding: 4, borderRadius: 14, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border },
  rangeOption: { minHeight: 36, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 10 },
  rangeOptionActive: { backgroundColor: palette.primaryDeep },
  rangeText: { color: palette.muted, fontSize: 12, fontWeight: '800' },
  rangeTextActive: { color: palette.text },
  chartSummary: { color: palette.muted, fontSize: 11, lineHeight: 16, marginTop: 2 },
  sampleBanner: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, paddingVertical: 9, paddingHorizontal: 11, borderRadius: 12, backgroundColor: 'rgba(33,184,154,0.07)', borderWidth: 1, borderColor: 'rgba(33,184,154,0.20)' },
  sampleCopy: { flexGrow: 1, flexShrink: 1, flexBasis: 142, minWidth: 126 },
  sampleValueBox: { flexGrow: 1, flexShrink: 1, flexBasis: 142, minWidth: 126, alignItems: 'flex-end' },
  sampleMaturity: { color: palette.text, fontSize: 12, fontWeight: '900' },
  sampleValue: { color: palette.accent2, fontSize: 14, lineHeight: 19, fontWeight: '900', textAlign: 'right' },
  sampleDelta: { color: palette.muted, fontSize: 10, lineHeight: 15, fontWeight: '800', textAlign: 'right' },
  rankList: { gap: 14 },
  rankRow: { gap: 7 },
  rankHeader: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  rankIndex: { width: 24, color: palette.primary, fontSize: 12, fontWeight: '900' },
  rankLabel: { flex: 1, color: palette.text, fontSize: 13, fontWeight: '800' },
  rankValue: { color: palette.text, fontSize: 13, fontWeight: '900' },
  rankMeta: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  metaText: { color: palette.muted, fontSize: 11, fontWeight: '700' },
  intervalCard: { gap: 12 },
  intervalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  intervalValue: { color: palette.text, fontSize: 28, fontWeight: '900' },
  intervalTrack: { position: 'relative', height: 14, borderRadius: 999, backgroundColor: palette.white08, overflow: 'hidden' },
  intervalBand: { position: 'absolute', top: 2, bottom: 2, borderRadius: 999, backgroundColor: 'rgba(33,184,154,0.45)' },
  intervalMarker: { position: 'absolute', top: 0, bottom: 0, width: 3, marginLeft: -1, borderRadius: 3, backgroundColor: palette.primary },
  intervalLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  reviewList: { gap: 13 },
  reviewRow: { gap: 6 },
});
