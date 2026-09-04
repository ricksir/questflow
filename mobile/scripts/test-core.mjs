import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const timing = require('../.core-test-build/timing.js');
const format = require('../.core-test-build/format.js');
const pairing = require('../.core-test-build/pairing.js');
const discovery = require('../.core-test-build/networkDiscovery.js');
const studySession = require('../.core-test-build/studySession.js');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

let state = timing.createTimer(0);
for (let t = 1000; t <= 42000; t += 1000) state = timing.tickTimer(state, t);
const idle = timing.snapshotTimer(state, 3600000);
assert(idle.wall_response_seconds === 3600, 'wall-clock deveria ser 3600 s');
assert(Math.abs(idle.active_response_seconds - 42) <= 0.1, '1h aberta/42s ativos deve registrar 42s ativos');
assert(idle.idle_seconds >= 3557.9, 'ociosidade deveria ser preservada separadamente');

let background = timing.createTimer(0);
for (let t = 1000; t <= 10000; t += 1000) background = timing.tickTimer(background, t);
background = timing.setForeground(background, false, 10000);
const bg = timing.snapshotTimer(background, 3600000);
assert(Math.abs(bg.active_response_seconds - 10) <= 0.1, 'background não pode aumentar tempo ativo');

let tabFocus = timing.createTimer(0);
for (let t = 1000; t <= 10000; t += 1000) tabFocus = timing.tickTimer(tabFocus, t);
tabFocus = timing.setQuestionScreenActive(tabFocus, false, 10000);
const outsideQuestions = timing.snapshotTimer(tabFocus, 120000);
assert(Math.abs(outsideQuestions.active_response_seconds - 10) <= 0.1, 'fora da aba Questões o tempo deve ficar pausado');
tabFocus = timing.setQuestionScreenActive(tabFocus, true, 120000);
for (let t = 121000; t <= 125000; t += 1000) tabFocus = timing.tickTimer(tabFocus, t);
const backToQuestions = timing.snapshotTimer(tabFocus, 125000);
assert(Math.abs(backToQuestions.active_response_seconds - 15) <= 0.1, 'ao voltar à aba Questões o tempo deve retomar sem contar o intervalo fora dela');

assert(format.formatDuration(120) === '2 minutos', '120 segundos deve aparecer como 2 minutos');
assert(format.formatDuration(125) === '2 minutos e 5 segundos', '125 segundos deve aparecer como 2 minutos e 5 segundos');

assert(studySession.sessionModeLabel('review') === 'Revisões', 'modo de revisão deve ter rótulo amigável');
assert(studySession.normalizeSessionCount(99) === 50, 'sessão deve limitar lote a 50 questões');
const parsedSession = studySession.parsePersistedStudySession(JSON.stringify({
  version: 1,
  session_id: 'session-1',
  config: { mode: 'errors', count: 10, subject: '' },
  question_refs: [{ id: 'q1', revision: 1 }, { id: 'q2', revision: 1 }],
  index: 1,
  stats: { answered: 1, correct: 0, wrong: 1, skipped: 0, active_seconds: 42 },
  counted_attempt_ids: ['a1'],
  attempt_id: 'a2', phase: 'answer', selected: null, confidence: null, difficulty: null,
  submitted_active_seconds: 0, started_at: '2026-08-19T00:00:00Z', updated_at: '2026-08-19T00:01:00Z'
}));
assert(parsedSession?.index === 1 && parsedSession?.stats.wrong === 1, 'sessão interrompida deve ser restaurável');
assert(Math.abs(studySession.sessionAccuracy({ answered: 4, correct: 3, wrong: 1, skipped: 0, active_seconds: 80 }) - 0.75) < 0.001, 'acurácia da sessão deve usar acertos e erros');

const parsed = pairing.parsePairingValue('questflow://pair?api=v1&token=abc123&server=http%3A%2F%2F192.168.1.20%3A53155');
assert(parsed.token === 'abc123', 'token do QR inválido');
assert(parsed.server === 'http://192.168.1.20:53155', 'servidor do QR inválido');
assert(parsed.servers.length === 1, 'lista de servidores do QR inválida');

const multi = pairing.parsePairingValue('questflow://pair?api=v1&token=abc&server=http%3A%2F%2F192.168.15.131%3A53155&server=http%3A%2F%2F192.168.128.84%3A53155');
assert(multi.server === 'http://192.168.15.131:53155', 'servidor preferencial deve vir primeiro');
assert(multi.servers.length === 2, 'QR deve preservar candidatos alternativos');

const hybrid = pairing.parsePairingValue('questflow://pair?api=v1&token=abc&server=http%3A%2F%2F192.168.15.131%3A53155&cloud=https%3A%2F%2Fmobile.example.org');
assert(hybrid.cloud === 'https://mobile.example.org', 'QR híbrido deve preservar URL do Cloud Bridge');

const scan = discovery.ipv4SubnetCandidates('192.168.15.77', 53155, ['http://192.168.15.131:53155']);
assert(scan[0] === 'http://192.168.15.131:53155', 'endereço preferencial deve ser testado antes da varredura');
assert(scan.includes('http://192.168.15.1:53155'), 'varredura /24 deve conter hosts da rede atual');
assert(!scan.includes('http://192.168.15.77:53155'), 'varredura não deve testar o próprio celular');

console.log('QuestFlow Mobile core tests: OK');
console.log(JSON.stringify({ one_hour_open: idle, background_after_10s: bg, outside_questions_tab: outsideQuestions, returned_to_questions: backToQuestions }, null, 2));
