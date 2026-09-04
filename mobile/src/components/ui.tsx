import type { PropsWithChildren, ReactNode } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const palette = {
  bg: '#05070B',
  bgAlt: '#090C12',
  surface: '#0E131B',
  surface2: '#151C27',
  surface3: '#202A38',
  text: '#F8FAFC',
  muted: '#9CAFC4',
  primary: '#FF7A18',
  primaryDeep: '#EA6708',
  primarySoft: '#FFE2C6',
  accent: '#FF9F50',
  accent2: '#3CC8DC',
  success: '#42D98A',
  warning: '#F8BE54',
  danger: '#FF6B7D',
  violet: '#9A6CFF',
  border: 'rgba(255,255,255,0.085)',
  white08: 'rgba(255,255,255,0.08)',
  white04: 'rgba(255,255,255,0.04)',
};

export function Screen({ children, safeTop = true, safeBottom = false }: PropsWithChildren<{ safeTop?: boolean; safeBottom?: boolean }>) {
  const insets = useSafeAreaInsets();
  const androidBottomFallback = Platform.OS === 'android' ? 28 : 8;
  return (
    <View style={[
      styles.screen,
      safeTop && { paddingTop: Math.max(insets.top, 8) },
      safeBottom && { paddingBottom: Math.max(insets.bottom, androidBottomFallback) },
    ]}>
      {children}
    </View>
  );
}

export function Card({ children, style }: PropsWithChildren<{ style?: any }>) {
  return <View style={[styles.card, style]}><View style={styles.cardTopLine} />{children}</View>;
}

export function AccentCard({ children, style }: PropsWithChildren<{ style?: any }>) {
  return <View style={[styles.card, styles.accentCard, style]}>{children}</View>;
}

export function HeroCard({ children, style }: PropsWithChildren<{ style?: any }>) {
  return (
    <View style={[styles.hero, style]}>
      <View style={styles.heroGlowOne} />
      <View style={styles.heroGlowTwo} />
      <View style={styles.heroContent}>{children}</View>
    </View>
  );
}

export function Heading({ children }: PropsWithChildren) {
  return <Text style={styles.heading}>{children}</Text>;
}

export function Subheading({ children }: PropsWithChildren) {
  return <Text style={styles.subheading}>{children}</Text>;
}

export function SectionTitle({ eyebrow, title, detail }: { eyebrow?: string; title: string; detail?: string }) {
  return (
    <View style={{ gap: 4 }}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text style={styles.sectionTitle}>{title}</Text>
      {detail ? <Text style={styles.muted}>{detail}</Text> : null}
    </View>
  );
}

export function ScreenHeader({ eyebrow, title, detail, action }: { eyebrow: string; title: string; detail?: string; action?: ReactNode }) {
  return (
    <View style={styles.screenHeader} accessibilityRole="header">
      <View style={styles.screenHeaderAccent} />
      <View style={styles.screenHeaderCopy}>
        <Text style={styles.eyebrow}>{eyebrow}</Text>
        <Text style={styles.screenHeaderTitle}>{title}</Text>
        {detail ? <Text style={styles.muted}>{detail}</Text> : null}
      </View>
      {action ? <View style={styles.screenHeaderAction}>{action}</View> : null}
    </View>
  );
}

export function StatePanel({ state, title, detail, actionTitle, onAction }: { state: 'loading' | 'empty' | 'error' | 'offline' | 'success' | 'info'; title: string; detail: string; actionTitle?: string; onAction?: () => void }) {
  const icon = { loading: '↻', empty: '○', error: '!', offline: '⇵', success: '✓', info: 'i' }[state];
  return (
    <View accessibilityRole={state === 'error' ? 'alert' : 'summary'} accessibilityLiveRegion="polite" style={[styles.statePanel, styles[`statePanel_${state}`]]}>
      <View style={[styles.stateIcon, styles[`stateIcon_${state}`]]}>
        {state === 'loading' ? <ActivityIndicator color={palette.primary} size="small" /> : <Text style={styles.stateIconText}>{icon}</Text>}
      </View>
      <View style={styles.stateCopy}>
        <Text style={styles.stateTitle}>{title}</Text>
        <Text style={styles.stateDetail}>{detail}</Text>
      </View>
      {actionTitle && onAction ? <Pressable accessibilityRole="button" onPress={onAction} style={styles.stateAction}><Text style={styles.stateActionText}>{actionTitle}</Text></Pressable> : null}
    </View>
  );
}

export function Muted({ children, style }: PropsWithChildren<{ style?: any }>) {
  return <Text style={[styles.muted, style]}>{children}</Text>;
}

export function LabelValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <View style={styles.labelRow}>
      <Text style={styles.labelRowLabel}>{label}</Text>
      <Text style={styles.labelRowValue}>{value}</Text>
    </View>
  );
}

export function Metric({ label, value, tone = 'neutral' }: { label: string; value: ReactNode; tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'violet' }) {
  return (
    <View style={[styles.metric, styles[`metric_${tone}`]]}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

export function ProgressBar({ value, tone = 'primary', height = 9 }: { value: number; tone?: 'primary' | 'success' | 'warning' | 'danger' | 'accent' | 'violet'; height?: number }) {
  const safe = Math.max(0, Math.min(1, Number(value) || 0));
  return (
    <View style={[styles.progressTrack, { height }]}>
      <View style={[styles.progressFill, styles[`progress_${tone}`], { width: `${Math.max(safe > 0 ? 3 : 0, safe * 100)}%`, height }]} />
    </View>
  );
}

export function StatRing({ value, label, tone = 'primary', size = 108 }: { value: number | null | undefined; label: string; tone?: 'primary' | 'success' | 'warning' | 'danger' | 'accent' | 'violet'; size?: number }) {
  const safe = Math.max(0, Math.min(1, Number(value) || 0));
  const toneColor = {
    primary: palette.primary,
    success: palette.success,
    warning: palette.warning,
    danger: palette.danger,
    accent: palette.accent2,
    violet: palette.violet,
  }[tone];
  return (
    <View
      accessibilityRole="progressbar"
      accessibilityLabel={`${label}: ${Math.round(safe * 100)}%`}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(safe * 100) }}
      style={[styles.statRing, { width: size, height: size, borderRadius: size / 2, borderColor: toneColor }]}
    >
      <View style={[styles.statRingInner, { width: size - 20, height: size - 20, borderRadius: (size - 20) / 2 }]}>
        <Text style={styles.statRingValue}>{value == null ? '—' : `${Math.round(safe * 100)}%`}</Text>
        <Text style={styles.statRingLabel}>{label}</Text>
      </View>
    </View>
  );
}

export function MicroBars({ values, tone = 'primary', height = 44 }: { values: number[]; tone?: 'primary' | 'success' | 'warning' | 'danger' | 'accent' | 'violet'; height?: number }) {
  const safeValues = (values.length ? values : [0]).map((value) => Math.max(0.08, Math.min(1, Number(value) || 0)));
  return (
    <View accessibilityLabel="Tendência visual de desempenho" style={[styles.microBars, { height }]}>
      {safeValues.map((value, index) => <View key={`${index}-${value}`} style={[styles.microBar, styles[`progress_${tone}`], { height: Math.max(4, value * height) }]} />)}
    </View>
  );
}

export function Button({ title, onPress, disabled, tone = 'primary' }: { title: string; onPress: () => void; disabled?: boolean; tone?: 'primary' | 'secondary' | 'danger' | 'success' }) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.button, styles[`button_${tone}`], pressed && styles.pressed, disabled && styles.disabled]}
    >
      <Text style={[styles.buttonText, tone === 'secondary' && styles.buttonTextSecondary]}>{title}</Text>
    </Pressable>
  );
}

export function Pill({ text, tone = 'neutral' }: { text: string; tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'violet' }) {
  return <View style={[styles.pill, styles[`pill_${tone}`]]}><Text style={styles.pillText}>{text}</Text></View>;
}

const shadow = {
  shadowColor: '#020714',
  shadowOpacity: 0.34,
  shadowRadius: 22,
  shadowOffset: { width: 0, height: 12 },
  elevation: 7,
};

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.bg, paddingHorizontal: 14 },
  card: {
    backgroundColor: palette.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: palette.border,
    padding: 15,
    overflow: 'hidden',
    ...shadow,
  },
  cardTopLine: { position: 'absolute', left: 15, right: '58%', top: 0, height: 2, borderRadius: 2, backgroundColor: palette.accent2, opacity: .74 },
  accentCard: { backgroundColor: palette.bgAlt, borderColor: 'rgba(255,122,24,0.44)' },
  hero: { overflow: 'hidden', backgroundColor: '#111721', borderRadius: 18, borderWidth: 1, borderColor: 'rgba(255,122,24,0.42)', ...shadow },
  heroGlowOne: { position: 'absolute', width: 215, height: 215, borderRadius: 999, backgroundColor: 'rgba(255,122,24,0.19)', right: -84, top: -105 },
  heroGlowTwo: { position: 'absolute', width: 170, height: 170, borderRadius: 999, backgroundColor: 'rgba(60,200,220,0.13)', left: -70, bottom: -104 },
  heroContent: { padding: 18, gap: 12 },
  heading: { color: palette.text, fontSize: 32, fontWeight: '900', letterSpacing: -0.8 },
  subheading: { color: palette.text, fontSize: 18, fontWeight: '800' },
  eyebrow: { color: palette.accent, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1.1 },
  sectionTitle: { color: palette.text, fontSize: 20, fontWeight: '900', letterSpacing: -0.3 },
  muted: { color: palette.muted, fontSize: 14, lineHeight: 21 },
  screenHeader: { position: 'relative', overflow: 'hidden', flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 16, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: palette.border, backgroundColor: 'transparent' },
  screenHeaderAccent: { position: 'absolute', left: 4, top: 7, width: 34, height: 3, borderRadius: 999, backgroundColor: palette.primary },
  screenHeaderCopy: { flex: 1, gap: 3, paddingLeft: 4 },
  screenHeaderTitle: { color: palette.text, fontSize: 34, lineHeight: 38, fontWeight: '900', letterSpacing: -1.2 },
  screenHeaderAction: { alignSelf: 'center' },
  statePanel: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 18, borderWidth: 1, backgroundColor: palette.surface },
  statePanel_loading: { borderColor: 'rgba(255,138,42,0.34)' },
  statePanel_empty: { borderColor: palette.border },
  statePanel_error: { borderColor: 'rgba(255,107,125,0.54)', backgroundColor: 'rgba(255,107,125,0.08)' },
  statePanel_offline: { borderColor: 'rgba(248,190,84,0.48)', backgroundColor: 'rgba(248,190,84,0.07)' },
  statePanel_success: { borderColor: 'rgba(66,217,138,0.44)', backgroundColor: 'rgba(66,217,138,0.07)' },
  statePanel_info: { borderColor: 'rgba(37,199,217,0.42)', backgroundColor: 'rgba(37,199,217,0.07)' },
  stateIcon: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surface2 },
  stateIcon_loading: { backgroundColor: 'rgba(255,138,42,0.10)' },
  stateIcon_empty: { backgroundColor: palette.surface2 },
  stateIcon_error: { backgroundColor: 'rgba(255,107,125,0.14)' },
  stateIcon_offline: { backgroundColor: 'rgba(248,190,84,0.14)' },
  stateIcon_success: { backgroundColor: 'rgba(66,217,138,0.14)' },
  stateIcon_info: { backgroundColor: 'rgba(37,199,217,0.14)' },
  stateIconText: { color: palette.text, fontSize: 18, fontWeight: '900' },
  stateCopy: { flex: 1, gap: 2 },
  stateTitle: { color: palette.text, fontSize: 14, fontWeight: '900' },
  stateDetail: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  stateAction: { minHeight: 38, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: palette.surface2, borderWidth: 1, borderColor: palette.border },
  stateActionText: { color: palette.text, fontSize: 12, fontWeight: '900' },
  labelRow: { gap: 4, borderRadius: 14, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: palette.white04, borderWidth: 1, borderColor: palette.white04 },
  labelRowLabel: { color: palette.muted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.55 },
  labelRowValue: { color: palette.text, fontSize: 14, fontWeight: '700' },
  metric: { flex: 1, minWidth: 92, backgroundColor: palette.surface, borderRadius: 14, padding: 13, borderWidth: 1, borderTopWidth: 2, borderColor: palette.border },
  metric_neutral: { borderColor: 'rgba(255,255,255,0.10)' },
  metric_primary: { borderTopColor: palette.primary },
  metric_success: { borderTopColor: palette.success },
  metric_warning: { borderTopColor: palette.warning },
  metric_danger: { borderTopColor: palette.danger },
  metric_violet: { borderTopColor: palette.violet },
  metricValue: { color: palette.text, fontSize: 24, fontWeight: '900' },
  metricLabel: { color: palette.muted, marginTop: 4, fontSize: 12 },
  progressTrack: { width: '100%', borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.08)', overflow: 'hidden' },
  progressFill: { borderRadius: 999 },
  progress_primary: { backgroundColor: palette.primary },
  progress_success: { backgroundColor: palette.success },
  progress_warning: { backgroundColor: palette.warning },
  progress_danger: { backgroundColor: palette.danger },
  progress_accent: { backgroundColor: palette.accent },
  progress_violet: { backgroundColor: palette.violet },
  statRing: { alignItems: 'center', justifyContent: 'center', borderWidth: 8, backgroundColor: 'rgba(255,255,255,0.05)' },
  statRingInner: { alignItems: 'center', justifyContent: 'center', backgroundColor: palette.surface },
  statRingValue: { color: palette.text, fontSize: 27, fontWeight: '900', letterSpacing: -0.8 },
  statRingLabel: { color: palette.muted, fontSize: 10, fontWeight: '800', marginTop: 1 },
  microBars: { flexDirection: 'row', alignItems: 'flex-end', gap: 5, paddingHorizontal: 2 },
  microBar: { flex: 1, minWidth: 5, borderRadius: 999, opacity: 0.94 },
  button: { borderRadius: 16, minHeight: 50, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, paddingVertical: 12 },
  button_primary: { backgroundColor: palette.primaryDeep },
  button_secondary: { backgroundColor: palette.surface2, borderWidth: 1, borderColor: 'rgba(255,138,42,0.36)' },
  button_danger: { backgroundColor: '#7B2B3C' },
  button_success: { backgroundColor: '#0F725E' },
  buttonText: { color: '#FFFFFF', fontSize: 15, fontWeight: '900' },
  buttonTextSecondary: { color: palette.text },
  pressed: { opacity: 0.86, transform: [{ scale: 0.995 }] },
  disabled: { opacity: 0.45 },
  pill: { alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: palette.surface2 },
  pill_neutral: { backgroundColor: palette.surface2 },
  pill_success: { backgroundColor: 'rgba(66,217,138,0.17)' },
  pill_warning: { backgroundColor: 'rgba(248,190,84,0.18)' },
  pill_danger: { backgroundColor: 'rgba(255,107,125,0.18)' },
  pill_info: { backgroundColor: 'rgba(37,199,217,0.16)' },
  pill_violet: { backgroundColor: 'rgba(176,124,255,0.18)' },
  pillText: { color: palette.text, fontSize: 12, fontWeight: '800' },
});
