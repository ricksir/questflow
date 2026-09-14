'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const formatNumber = (value) => new Intl.NumberFormat('pt-BR').format(Number(value || 0));
const formatDate = (value) => {
  if (!value) return 'Não informado';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
};
const debounce = (fn, wait = 250) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
};
const textOrMissing = (value, fallback = 'Não encontrado') => {
  const text = String(value ?? '').trim();
  return text || fallback;
};
const numberOrZero = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
};
const currentMobileRelease = () => document.querySelector('[data-mobile-source-version]')?.textContent?.trim()
  || document.querySelector('.mobile-studio-kicker')?.textContent?.match(/\d+\.\d+\.\d+/)?.[0]
  || 'atual';
const QUESTFLOW_ART = {
  light: {
    heroSvg: 'assets/questflow_exam_light.svg',
    heroPng: 'assets/questflow_exam_light_256.png',
    logo128: 'assets/questflow_logo_light_128.png',
    logo256: 'assets/questflow_logo_light_256.png',
    favicon: 'assets/questflow_logo_light_32.png',
  },
  dark: {
    heroSvg: 'assets/questflow_exam_dark.svg',
    heroPng: 'assets/questflow_exam_dark_256.png',
    logo128: 'assets/questflow_logo_dark_128.png',
    logo256: 'assets/questflow_logo_dark_256.png',
    favicon: 'assets/questflow_logo_dark_32.png',
  },
};
const identityPicture = (className = 'empty-state-art', eager = false) => `
  <span class="theme-picture ${escapeHtml(className)}" aria-hidden="true">
    <img class="theme-art theme-art--light" src="${QUESTFLOW_ART.light.heroSvg}" alt="" width="144" height="144" loading="${eager ? 'eager' : 'lazy'}" decoding="async">
    <img class="theme-art theme-art--dark" src="${QUESTFLOW_ART.dark.heroSvg}" alt="" width="144" height="144" loading="${eager ? 'eager' : 'lazy'}" decoding="async">
  </span>`;
const emptyStateHtml = ({ title = '', text = '', compact = false, button = '' } = {}) => `
  <div class="empty-state${compact ? ' empty-state--compact' : ''}">
    ${identityPicture('empty-state-art')}
    ${title ? `<h3>${escapeHtml(title)}</h3>` : ''}
    ${text ? `<p>${escapeHtml(text)}</p>` : ''}
    ${button || ''}
  </div>`;
const readJsonPreference = (key, fallback) => {
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null');
    return value ?? fallback;
  } catch (_) { return fallback; }
};

const qfUiDiagnostics = {
  startedAt: performance.now(),
  lastVisibility: document.visibilityState,
  modalOpenedAt: 0,
};
window.addEventListener('pageshow', (event) => {
  const navigation = performance.getEntriesByType('navigation')[0];
  console.info('[QF UI 6.21.1] pageshow', { persisted: Boolean(event.persisted), navigation: navigation?.type || 'unknown', at: new Date().toISOString() });
});
document.addEventListener('visibilitychange', () => {
  qfUiDiagnostics.lastVisibility = document.visibilityState;
  console.info('[QF UI 6.21.1] visibility', { state: document.visibilityState, at: new Date().toISOString() });
});
try {
  if ('PerformanceObserver' in window && PerformanceObserver.supportedEntryTypes?.includes('longtask')) {
    new PerformanceObserver((list) => list.getEntries().forEach((entry) => {
      if (entry.duration >= 80) console.info('[QF UI 6.21.1] longtask', { duration_ms: Math.round(entry.duration), at_ms: Math.round(entry.startTime) });
    })).observe({ entryTypes: ['longtask'] });
  }
} catch (_) {}

const state = {
  route: 'dashboard',
  routeRequestId: 0,
  routeScroll: Object.create(null),
  routeStates: Object.create(null),
  bootstrap: null,
  config: {},
  taxonomy: { materias: [] },
  questions: [],
  questionTotal: 0,
  currentUid: null,
  currentQuestion: null,
  originalQuestion: null,
  currentImage: null,
  questionIntelligence: null,
  tutorSelectedUid: null,
  tutorCandidates: [],
  tutorInteractionId: null,
  pendingEditorialAiInteractionId: null,
  tutorScaffoldSessionId: null,
  tutorScaffoldLevel: null,
  adaptiveSimulationId: null,
  adaptiveSimulationQuestionUid: null,
  adaptiveSimulationStartedAt: 0,
  stage5SelectedUid: null,
  stage5DraftId: null,
  stage5LastWorkspace: null,
  examProjectId: null,
  examProjectDashboard: null,
  todayDashboard: null,
  multipleChoiceDraft: null,
  questionListCollapsed: false,
  questionHeaderCollapsed: localStorage.getItem('qf-question-header-collapsed') === '1',
  selectedImportFiles: [],
  importContext: null,
  importTask: null,
  eventCursor: 0,
  zoom: Number(localStorage.getItem('qf-ui-zoom') || 1),
  theme: localStorage.getItem('qf-theme') || 'system',
  dirty: false,
  curationReviewContext: false,
  coverage: [],
  coverageSummary: {},
  coverageSource: {},
  coverageGeneratedAt: '',
  coverageSyncedSession: false,
  guideStatus: {},
  guideWatchPromise: null,
  lastGuideWarningSignature: '',
  lastGuideWatchAt: 0,
  corrections: [],
  correctionsSummary: { editorial: 0, not_studied: 0, total: 0 },
  bankFixQuestions: [],
  bankFixTotal: 0,
  bankFixOptions: { subjects: [], lessons: [], tasks: [] },
  bankFixOptionsSubject: null,
  bankFixRequestId: 0,
  dashboardTask: null,
  dashboardPreview: null,
  databaseHealthPromise: null,
  startupReady: false,
  questionRequestId: 0,
  sidebarCollapsed: false,
  taxonomyLoading: null,
  questionColumnOrder: readJsonPreference('qf-question-column-order', ['codigo', 'materia', 'aula', 'assunto', 'ano', 'status']),
  questionColumnWidths: readJsonPreference('qf-question-column-widths', {}),
  questionSort: readJsonPreference('qf-question-sort', { key: 'codigo', direction: 'asc' }),
  updateMonitorStatus: null,
  courseCatalogSettings: null,
  updateMonitorPromptCycle: '',
};

const questionColumnDefinitions = {
  codigo: { label: 'Código', className: 'cell-code', min: 92, width: 118, type: 'text' },
  materia: { label: 'Matéria', className: 'cell-subject', min: 150, width: 210, type: 'text' },
  aula: { label: 'Aula', className: 'cell-lesson', min: 80, width: 100, type: 'text' },
  assunto: { label: 'Assunto', className: 'cell-topic', min: 190, width: 330, type: 'text' },
  ano: { label: 'Ano', className: 'cell-year', min: 68, width: 78, type: 'number' },
  status: { label: 'Status', className: 'cell-status', min: 105, width: 125, type: 'text' },
  origem: { label: 'Origem', className: 'cell-origin', min: 120, width: 145, type: 'text' },
  qualidade: { label: 'Qualidade', className: 'cell-quality', min: 92, width: 110, type: 'number' },
  dificuldade: { label: 'Dificuldade', className: 'cell-difficulty', min: 100, width: 120, type: 'text' },
};

function normalizedQuestionColumnOrder() {
  const keys = Object.keys(questionColumnDefinitions);
  const stored = Array.isArray(state.questionColumnOrder) ? state.questionColumnOrder : [];
  return [...stored.filter((key) => keys.includes(key)), ...keys.filter((key) => !stored.includes(key))];
}

function questionColumnWidth(key) {
  const column = questionColumnDefinitions[key];
  return Math.max(column.min, Number(state.questionColumnWidths[key] || column.width));
}

function questionGridTemplate() {
  return normalizedQuestionColumnOrder().map((key) => `${questionColumnWidth(key)}px`).join(' ');
}

function questionGridWidth() {
  const gap = 10;
  const order = normalizedQuestionColumnOrder();
  return order.reduce((total, key) => total + questionColumnWidth(key), 0) + Math.max(0, order.length - 1) * gap + 24;
}

let questionScrollSyncing = false;

function syncQuestionHorizontalGeometry() {
  const width = questionGridWidth();
  const head = $('#questionTableHead');
  const track = $('#questionHorizontalScrollTrack');
  const spacer = $('#questionSpacer');
  const viewport = $('#questionViewport');
  const scroller = $('#questionHorizontalScroll');
  if (head) head.style.width = `${width}px`;
  if (track) track.style.width = `${width}px`;
  if (spacer) spacer.style.width = `${width}px`;
  if (scroller && viewport) {
    const hasOverflow = width > viewport.clientWidth + 2;
    scroller.classList.toggle('is-inactive', !hasOverflow);
    $('#questionScrollHint')?.classList.toggle('is-hidden', !hasOverflow);
  }
}

function syncQuestionHorizontalPosition(scrollLeft, source = '') {
  if (questionScrollSyncing) return;
  questionScrollSyncing = true;
  const viewport = $('#questionViewport');
  const scroller = $('#questionHorizontalScroll');
  const head = $('#questionTableHead');
  const position = Math.max(0, Number(scrollLeft || 0));
  if (source !== 'viewport' && viewport) viewport.scrollLeft = position;
  if (source !== 'scroller' && scroller) scroller.scrollLeft = position;
  if (head) head.style.transform = `translateX(-${position}px)`;
  requestAnimationFrame(() => { questionScrollSyncing = false; });
}

function questionSortValue(item, key) {
  const values = {
    codigo: item.codigo, materia: item.materia, aula: item.aula, assunto: item.assunto || item.enunciado,
    ano: item.ano, status: formatStatus(item.status),
  };
  return values[key] ?? '';
}

function sortQuestionItems(items) {
  const { key = 'codigo', direction = 'asc' } = state.questionSort || {};
  const column = questionColumnDefinitions[key] || questionColumnDefinitions.codigo;
  const factor = direction === 'desc' ? -1 : 1;
  return [...(items || [])].sort((left, right) => {
    const a = questionSortValue(left, key);
    const b = questionSortValue(right, key);
    if (column.type === 'number') return (numberOrZero(a) - numberOrZero(b)) * factor;
    return String(a || '').localeCompare(String(b || ''), 'pt-BR', { numeric: true, sensitivity: 'base' }) * factor;
  });
}

class Bridge {
  constructor() {
    this.ready = false;
    this.mock = null;
    const params = new URLSearchParams(location.search);
    const sessionToken = sessionStorage.getItem('qf-http-token') || '';
    this.httpToken = params.get('qf_token') || sessionToken;
    this.httpMode = Boolean(this.httpToken && ['127.0.0.1', 'localhost'].includes(location.hostname));
    if (this.httpMode) {
      // Mantém a sessão após F5 sem deixar o token visível na barra de endereço.
      sessionStorage.setItem('qf-http-token', this.httpToken);
      history.replaceState(null, '', `${location.pathname}${location.hash}`);
    }
  }

  hasNativeMethod(method) {
    try {
      return typeof window.pywebview?.api?.[method] === 'function';
    } catch (_) {
      return false;
    }
  }

  async waitForNativeMethod(method, timeoutMs = 9000) {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      if (this.hasNativeMethod(method)) return window.pywebview.api;
      await sleep(60);
    }
    return null;
  }

  isStandalonePreview() {
    return !this.httpMode && !window.pywebview && (/^https?:$/.test(location.protocol) || navigator.webdriver === true);
  }

  async httpRequest(path, options = {}, timeoutMs = 600000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(path, {
        ...options,
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          'X-QuestFlow-Token': this.httpToken,
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
          ...(options.headers || {}),
        },
      });
      let payload;
      try {
        payload = await response.json();
      } catch (_) {
        throw new Error(`O motor local retornou uma resposta inválida (${response.status}).`);
      }
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.error || `Falha no motor local (${response.status}).`);
      }
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('O motor local excedeu o tempo de resposta.');
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async waitForHttp(timeoutMs = 15000) {
    const deadline = performance.now() + timeoutMs;
    let lastError = null;
    while (performance.now() < deadline) {
      try {
        await this.httpRequest('/api/health', { method: 'GET' }, 2500);
        return true;
      } catch (error) {
        lastError = error;
        await sleep(100);
      }
    }
    throw lastError || new Error('O motor local do QuestFlow não respondeu.');
  }

  async init(requiredMethod = 'bootstrap_shell') {
    if (this.ready) return;
    if (this.httpMode) {
      await this.waitForHttp();
      this.ready = true;
      return;
    }
    if (this.isStandalonePreview()) {
      this.mock = createMockApi();
      this.ready = true;
      return;
    }

    const nativeApi = await this.waitForNativeMethod(requiredMethod, 9000);
    if (nativeApi) {
      this.ready = true;
      return;
    }

    if (window.pywebview) {
      throw new Error('A ponte interna do QuestFlow não terminou de carregar. Execute a versão 5.2 ou o diagnóstico.');
    }
    this.mock = createMockApi();
    this.ready = true;
  }

  async call(method, ...args) {
    if (!this.ready) await this.init(method);
    if (this.httpMode) {
      const response = await this.httpRequest('/api/call', {
        method: 'POST',
        body: JSON.stringify({ method, args }),
      });
      return response.result;
    }

    let target = window.pywebview?.api || this.mock;
    if (typeof target?.[method] !== 'function' && window.pywebview) {
      target = await this.waitForNativeMethod(method, 5000);
    }
    if (typeof target?.[method] !== 'function') {
      throw new Error(`O recurso interno “${method}” ainda não está disponível.`);
    }
    return target[method](...args);
  }

  async studioGet(path, fallbackMethod = '', fallbackArgs = []) {
    if (!this.ready) await this.init(fallbackMethod || 'bootstrap_shell');
    if (!this.httpMode) {
      if (!fallbackMethod) throw new Error('O contrato Studio v1 requer o transporte HTTP local.');
      const fallback = await this.call(fallbackMethod, ...fallbackArgs);
      if (fallback?.ok === false) throw new Error(fallback.error || 'Falha no recurso legado.');
      return fallback?.data ?? fallback;
    }
    const response = await this.httpRequest(`/api/v1/studio/${String(path || '').replace(/^\//, '')}`, {
      method: 'GET',
    });
    return response.data ?? response;
  }

  async studioPost(path, payload = {}, fallbackMethod = '', fallbackArgs = []) {
    if (!this.ready) await this.init(fallbackMethod || 'bootstrap_shell');
    if (!this.httpMode) {
      if (!fallbackMethod) throw new Error('O contrato Studio v1 requer o transporte HTTP local.');
      const fallback = await this.call(fallbackMethod, ...fallbackArgs);
      if (fallback?.ok === false) throw new Error(fallback.error || 'Falha no recurso legado.');
      return fallback?.data ?? fallback;
    }
    const response = await this.httpRequest(`/api/v1/studio/${String(path || '').replace(/^\//, '')}`, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
    return response.data ?? response;
  }

  startHeartbeat() {
    if (!this.httpMode) return;
    const beat = async () => {
      try {
        await this.httpRequest('/api/heartbeat', { method: 'POST' }, 2500);
      } catch (_) { /* encerramento do programa ou suspensão do computador */ }
      finally {
        window.setTimeout(beat, document.hidden ? 7000 : 3000);
      }
    };
    beat();
  }
}
const bridge = new Bridge();

function createMockApi() {
  const sample = {
    database_uid: 'demo-1', codigo_origem: 'Q2534553', materia: 'CONTABILIDADE PÚBLICA', aula_planilha: 'Aula 01',
    assunto: 'PRINCÍPIOS ORÇAMENTÁRIOS', assuntos: ['PRINCÍPIOS ORÇAMENTÁRIOS'], banca: 'FGV', ano: 2024,
    orgao: 'MF', prova: 'FGV - 2024 - Auditor Federal', cargo: 'Auditor', area: '', especialidade: '', turno: 'Manhã',
    tipo: 'multipla_escolha', gabarito: 'E',
    enunciado: 'Determinado município aprovou uma lei para passar a cobrar um tributo dos moradores dos bairros próximos às novas estações de metrô, para custear as obras e considerando a valorização dos imóveis neles situados.\n\nAssinale a opção que o indica.',
    alternativas: [
      { chave: 'A', texto: 'Contribuição Social.' }, { chave: 'B', texto: 'CIDE.' }, { chave: 'C', texto: 'Imposto sobre Grandes Fortunas.' },
      { chave: 'D', texto: 'Empréstimo Compulsório.' }, { chave: 'E', texto: 'Contribuição de Melhoria.' },
    ],
    explicacao: 'A contribuição de melhoria pode ser instituída para custear obra pública da qual decorra valorização imobiliária.',
    revisao: { status: 'pendente', alertas: [] },
  };
  const mockTasks = new Map();
  const makeMockTask = (result) => {
    const id = `mock-${Date.now()}-${Math.random()}`;
    mockTasks.set(id, { status: 'done', progress: 1, message: 'Concluído', result });
    return { ok: true, task_id: id };
  };
  const dashboardMock = { question_stats: { total: 668, pending: 139, approved: 421 }, study_stats: { answers: 322, correct: 241, accuracy: 74.8 }, adaptive: { retention: 0.86, overdue: 28 }, learner_model: { version: 'qf-learner-2', events: 322, concepts: 48, reliable_concepts: 31, strong_concepts: 12, gap_concepts: 7, modeled_questions: 144, avg_mastery: 0.73, avg_confidence: 0.62, avg_information: 0.31, avg_fusion_priority: 41.2, weakest_concepts: [{concept_type:'assunto',subject:'DIREITO TRIBUTÁRIO',label:'Suspensão da exigibilidade',mastery:0.39,confidence:0.71,exposure_count:9,mastery_label:'Lacuna provável'}], abilities:[{subject:'DIREITO TRIBUTÁRIO',theta:-0.35,theta_scale:43.6,standard_error:0.74,attempt_count:60,accuracy:48.3}], informative_questions:[], caveat:'A IRT é uma calibração pessoal regularizada.' }, subjects: [
    { subject: 'CONTABILIDADE GERAL E AVANÇADA', questions: 142, sent: 54, correct: 31, wrong: 17, attempts: 48, accuracy: 64.6, has_answers: true, performance_label: 'Em evolução', performance_tone: 'warning' },
    { subject: 'FLUÊNCIA EM DADOS', questions: 78, sent: 12, correct: 10, wrong: 2, attempts: 12, accuracy: 83.3, has_answers: true, performance_label: 'Bom domínio', performance_tone: 'success' },
    { subject: 'DIREITO TRIBUTÁRIO', questions: 185, sent: 66, correct: 29, wrong: 31, attempts: 60, accuracy: 48.3, has_answers: true, performance_label: 'Prioridade alta', performance_tone: 'danger' },
    { subject: 'AUDITORIA', questions: 96, sent: 0, correct: 0, wrong: 0, attempts: 0, accuracy: 0, has_answers: false, performance_label: 'Sem respostas', performance_tone: 'neutral' },
  ], recent: [], flow: {}, pending_reviews: 3, elapsed_seconds: 0.02 };
  const bootstrapMock = { app: { name: 'QuestFlow Studio', version: '6.24.0' }, stats: { total: 668, pending: 139, approved: 421 }, config: {}, taxonomy: { loaded: true, materias: ['CONTABILIDADE PÚBLICA', 'DIREITO TRIBUTÁRIO'], task_count: 473 }, flow: {}, pending_reviews: 3 };
  return {
    bootstrap_shell: async () => ({ ...bootstrapMock, stats: {}, pending_reviews: 0, deferred: true }),
    bootstrap: async () => bootstrapMock,
    start_bootstrap_load: async () => makeMockTask(bootstrapMock),
    start_dashboard_load: async () => makeMockTask(dashboardMock),
    get_dashboard: async () => dashboardMock,
    list_questions: async () => ({ total: 1, items: [{ uid: 'demo-1', codigo: sample.codigo_origem, materia: sample.materia, aula: sample.aula_planilha, assunto: sample.assunto, ano: sample.ano, banca: sample.banca, status: 'pendente', enunciado: sample.enunciado }] }),
    get_bank_classification_options: async (subject = '', lesson = '') => ({ ok: true, subjects: ['AUDITORIA', 'DIREITO TRIBUTÁRIO'], lessons: subject === 'AUDITORIA' ? ['Aula 00', 'Aula 01', 'Aula 02'] : ['Aula 00', 'Aula 01'], tasks: [{ task_id: 'TRILHA 02:85', trilha: 'Trilha 02', tarefa: '85', materia: subject || 'AUDITORIA', aula: lesson || 'Aula 02', conteudo: 'Teoria da Aula 02 – Auditoria Interna.', descricao: 'Teoria da Aula 02 – Parte 1 de 1 – Auditoria Interna.', estudado: true }] }),
      update_question_classification: async (_uid, payload) => ({ ok: true, question: { ...sample, materia: payload.materia || sample.materia, aula_planilha: payload.aula || sample.aula_planilha }, coverage_assignment: { materia: payload.materia, aula: payload.aula } }),
      organize_bank_lesson_group: async (payload) => ({ ok: true, group: { updated: 1, subject: payload.materia, lesson: bankFixCanonicalLesson(payload.aula), lesson_title: payload.titulo_aula } }),
    get_question: async () => ({ ok: true, question: sample, image: null }),
    save_question: async (_uid, payload, approve) => ({ ok: true, question: { ...sample, ...payload, revisao: { status: approve ? 'aprovado' : 'pendente' } }, stats: { total: 668, pending: approve ? 138 : 139 } }),
    create_manual_question: async () => ({ ok: true, uid: 'demo-new', question: { ...sample, database_uid: 'demo-new', codigo_origem: 'MANUAL-DEMO', enunciado: '', alternativas: [], gabarito: '' } }),
    delete_question: async () => ({ ok: true }), annul_question: async () => ({ ok: true }), attach_image: async () => ({ ok: false, cancelled: true }), remove_image: async () => ({ ok: true }),
    choose_import_files: async () => ({ paths: [] }), start_import: async () => ({ ok: false, error: 'Modo de demonstração.' }), poll_task: async (taskId) => mockTasks.get(taskId) || ({ status: 'missing' }), start_reread: async () => ({ ok: false, error: 'Modo de demonstração.' }),
    get_flow: async () => ({ status: { running: true, listening: true, paused: false, next_run: new Date(Date.now() + 3600000).toISOString() }, settings: { flow_enabled: true, flow_daily_time: '10:00', flow_questions_per_cycle: 10, flow_target_retention: 0.88, flow_approved_only: true, flow_unanswered_resend_enabled: true, flow_unanswered_resend_hours: 24, flow_delay_seconds: 5, flow_question_card_enabled: true, flow_explanation_mode: 'automatico' }, stats: {}, recent: [], failed: [] }), save_flow_settings: async () => ({ ok: true }), flow_action: async () => ({ ok: true }),
    get_ai_privacy_settings: async () => ({ ok:true, settings:{mode:'balanced',share_taxonomy:true,share_statement:true,share_alternatives:true,share_official_answer:true,share_rag:true,share_binary_media:false,share_learner_summary:false,share_user_prompt:true,share_personal_notes:false,confirm_before_external:true} }),
    save_ai_privacy_settings: async (payload) => ({ ok:true, settings:{...payload} }),
    get_ai_privacy_preview: async () => ({ ok:true, provider:'local', preview:{mode:'balanced',shared_count:5,fields:[{field:'Enunciado',shared:true},{field:'Alternativas',shared:true},{field:'Gabarito oficial',shared:true},{field:'Evidências RAG',shared:true},{field:'Resumo do Learner Model',shared:false},{field:'Pergunta digitada',shared:true},{field:'Anotações pessoais',shared:false}]}, security:{sources_with_signals:0} }),
    start_tutor_scaffolding: async (_uid,_prompt,representation,_mediaNotes) => makeMockTask({ok:true,session:{id:'mock-scaffold',question_uid:'demo-1',current_level:0,status:'em_andamento',representation:representation||'texto',independence_score:1},step:{level:0,level_label:'Tentativa independente',level_description:'Sem pista de conteúdo.',representation:representation||'texto',content:{hint:'Organize o comando e formule sua hipótese sem consultar o gabarito.',question_to_student:'Qual regra controla o item?',warnings:[]}}}),
    advance_tutor_scaffolding: async (_sid,action) => makeMockTask(action==='solved'?{ok:true,completed:true,session:{id:'mock-scaffold',current_level:0,solved_level:0,status:'resolvido'},signal:{independence_score:1,signal:'boa_independencia'}}:{ok:true,completed:false,session:{id:'mock-scaffold',current_level:1,status:'em_andamento'},step:{level:1,level_label:'Pista metacognitiva',level_description:'Identifique o comando.',representation:'texto',content:{hint:'Identifique o que o comando realmente pede.',question_to_student:'Regra ou exceção?',warnings:[]}}}),
    get_tutor_scaffolding: async () => ({ok:true,session:{id:'mock-scaffold',current_level:0,status:'em_andamento'}}),
    get_ai_telemetry: async () => ({ ok:true, telemetry:{days:30,calls:3,input_tokens:4200,output_tokens:1100,estimated_cost_usd:0,avg_latency_ms:1820,prompt_injection_flags:0,items:[{provider:'openai',model:'demo',calls:3,success_rate:100,avg_latency_ms:1820,input_tokens:4200,output_tokens:1100,prompt_injection_flags:0,structured_calls:3}],cost_note:'Modo demonstração.'} }),
    get_update_monitor_status: async () => ({ ok: true, enabled: true, days: [1, 15], due: false, cycle: 'demo', source_count: 9, history: [], privacy: 'Modo demonstração.' }),
    save_update_monitor_settings: async (_payload) => ({ ok: true, enabled: true, days: [1, 15], due: false }),
    defer_update_monitor: async () => ({ ok: true, due: false }),
    start_update_monitor_check: async () => makeMockTask({ ok: true, summary: { successes: 9, failures: 0, changed: 0, baseline: 9 }, items: [], changed_items: [], message: 'Linha de base criada.' }),
    list_corrections: async () => ({ items: [] }), correction_action: async () => ({ ok: true }), get_coverage: async () => ({
      items: [
        { materia: 'DIREITO TRIBUTÁRIO', aula: 'Aula 00', conteudo: 'Espécies tributárias', questoes_planilha: 20, questoes_banco: 12, faltam_adicionar: 8, faltam_display: '8', acertos_planilha: 18, desempenho_planilha: 90, ch_efetiva: '1h30', status_code: 'cobertura_parcial', situacao: 'Cobertura parcial', needs_attention: true },
        { materia: 'AUDITORIA', aula: 'Aula 00', conteudo: 'Princípios éticos', questoes_planilha: 15, questoes_banco: 15, faltam_adicionar: 0, faltam_display: '0', acertos_planilha: 12, desempenho_planilha: 80, ch_efetiva: '1h30', status_code: 'coberto', situacao: 'Coberto', needs_attention: false },
        { materia: 'FLUÊNCIA EM DADOS', aula: 'Aula 01', conteudo: 'Conceitos Básicos até Tipos de Operadores', questoes_planilha: 20, questoes_banco: 0, faltam_adicionar: 20, faltam_display: '20', acertos_planilha: 14, desempenho_planilha: 70, ch_efetiva: '1h30', status_code: 'faltam_questoes', situacao: 'Sem cobertura: adicionar questões', needs_attention: true },
      ],
      summary: { studied_contents: 3, studied_subjects: 3, contents_needing_questions: 2, contents_without_questions: 0, partial_contents: 1, covered_contents: 1, known_missing_questions: 28 },
      source: { title: 'Trilhas00a18_AFRFB_Planilha de Controle' },
      generated_at: new Date().toISOString(),
      guide_status: { available_trails: [0,1,2,3,4,5], available_label: 'Trilhas 00 a 05', documented_through: 5, documented_through_label: 'Trilha 05', next_expected_trail: 6, next_expected_label: 'Trilha 06', studied_trails: [0,1], missing_studied_trails: [], missing_count: 0, needs_attention: false, knowledge: { sheet_roles: { ciclo: { fill_fields: ['DATA','CH EFETIVA','TOT QUEST FEITAS','TOT ACERTOS'], study_evidence: ['DATA','CH EFETIVA','TOT QUEST FEITAS','TOT ACERTOS'] }, mapa: { fill_fields: ['T+R = SIM','QTD EXE','ACERTOS'] } }, workflow: ['Registrar as tarefas realizadas no CICLO.'] } },
    }), sync_study_coverage: async () => ({ ok: true, synced: true, message: 'Planilha sincronizada.', items: [
      { materia: 'DIREITO TRIBUTÁRIO', aula: 'Aula 00', conteudo: 'Espécies tributárias', questoes_planilha: 20, questoes_banco: 12, faltam_adicionar: 8, faltam_display: '8', acertos_planilha: 18, desempenho_planilha: 90, ch_efetiva: '1h30', status_code: 'cobertura_parcial', situacao: 'Cobertura parcial', needs_attention: true },
      { materia: 'FLUÊNCIA EM DADOS', aula: 'Aula 01', conteudo: 'Conceitos Básicos até Tipos de Operadores', questoes_planilha: 20, questoes_banco: 0, faltam_adicionar: 20, faltam_display: '20', acertos_planilha: 14, desempenho_planilha: 70, ch_efetiva: '1h30', status_code: 'faltam_questoes', situacao: 'Sem cobertura: adicionar questões', needs_attention: true },
    ], summary: { studied_contents: 3, studied_subjects: 3, contents_needing_questions: 2, contents_without_questions: 0, partial_contents: 1, covered_contents: 1, known_missing_questions: 28 }, source: { title: 'Trilhas00a18_AFRFB_Planilha de Controle' }, generated_at: new Date().toISOString(), guide_status: { available_trails: [0,1,2,3,4,5], available_label: 'Trilhas 00 a 05', documented_through: 5, documented_through_label: 'Trilha 05', next_expected_trail: 6, next_expected_label: 'Trilha 06', studied_trails: [0,1], missing_studied_trails: [], missing_count: 0, needs_attention: false, knowledge: { sheet_roles: { ciclo: { fill_fields: ['DATA','CH EFETIVA','TOT QUEST FEITAS','TOT ACERTOS'], study_evidence: ['DATA','CH EFETIVA','TOT QUEST FEITAS','TOT ACERTOS'] }, mapa: { fill_fields: ['T+R = SIM','QTD EXE','ACERTOS'] } }, workflow: ['Registrar as tarefas realizadas no CICLO.'] } } }), get_course_catalog_settings: async () => ({ok:true,url:'https://docs.google.com/spreadsheets/d/demo/edit',source_title:'Trilhas00a18_AFRFB_Planilha de Controle',trail_range:'Trilhas 00 a 18',trail_count:19,lesson_count:184,last_sync:new Date().toISOString(),catalog_version:'demo',merge_strategy:'incremental-preserve-progress-v1',sheets:['MAPA_AF','CICLO_REG']}), preflight_course_catalog: async () => ({ok:true,ready:true,preflight:{ok:true,catalog_version:'demo-new',sheets:['MAPA_AF','CICLO_REG'],counts:{equal:184,updated:4,new:73,archived:1,uncertain:0},diffs:[],personal_fields_blank_overwrite:0,message:'Pronta para mesclar com preservação de progresso.'}}), apply_course_catalog: async () => ({ok:true,catalog_version:'demo-new',import_id:'demo-import',quick_check:'ok',foreign_key_violations:0,summary:{equal:184,updated:4,new:73,archived:1,uncertain:0,progress_preserved:184,personal_fields_overwritten_by_blank:0,fsrs_rows_preserved:120,knowledge_tracing_rows_preserved:90},backup:{path:'backup.sqlite',sha256:'demo'}}), choose_trail_guide_files: async () => ({ paths: [] }), import_trail_guides: async () => ({ ok: false, error: 'Modo de demonstração.' }), save_settings: async () => ({ ok: true }),
    get_network_settings: async () => ({ ok: true, settings: { network_mode: 'auto', network_proxy_host: '', network_proxy_port: '', network_pac_url: '', network_proxy_bypass: 'localhost;127.0.0.1;::1;<local>', network_proxy_auth: 'none', network_proxy_username: '', network_proxy_password_configured: false, network_system_detected: { source: 'direct', https_proxy: '', http_proxy: '', pac_url: '', auto_detect: false, bypass: 'localhost;127.0.0.1' } } }),
    detect_network_proxy: async () => ({ ok: true, detected: { source: 'direct', https_proxy: '', http_proxy: '', pac_url: '', auto_detect: false, bypass: 'localhost;127.0.0.1' }, effective: { enabled: false, source: 'direct', detail: 'Nenhum proxy detectado.' } }),
    save_network_settings: async (payload) => ({ ok: true, settings: { ...payload, network_proxy_password_configured: Boolean(payload.network_proxy_password) }, config: payload }),
    test_network_connection: async () => ({ ok: true, proxy: { enabled: false, source: 'direct', detail: 'Conexão direta.' }, tests: [{ name: 'Motor local', ok: true, detail: '127.0.0.1 fora do proxy.' }, { name: 'DNS', ok: true, detail: 'Resolvido.' }, { name: 'Google', ok: true, detail: 'HTTP 204' }, { name: 'Google Sheets', ok: true, detail: 'HTTP 200' }, { name: 'Telegram', ok: true, detail: 'HTTP 200' }] }),
    get_cloud_sync_settings: async () => ({ ok: true, settings: { cloud_sync_enabled: false, cloud_turso_url: '', cloud_device_name: 'Este computador', cloud_sync_interval_seconds: 30, cloud_sync_on_start: true, cloud_sync_on_shutdown: true, cloud_turso_token_configured: false, mobile_lan_enabled: false }, status: { state: 'ready', pending: 0, conflicts: 0, generation: 1 } }),
    save_cloud_sync_settings: async (payload) => ({ ok: true, settings: { ...payload, cloud_turso_token_configured: Boolean(payload.cloud_turso_token) }, status: { state: payload.cloud_sync_enabled ? 'ready' : 'disabled', pending: 0 } }),
    test_cloud_sync_connection: async () => ({ ok: true, result: { generation: 1, elapsed_ms: 25 } }),
    get_cloud_sync_activation_preview: async () => ({ ok: true, preview: { ok:true, read_only:true, local_healthy:true, quick_check:'ok', foreign_key_violations:0, configuration:{url_configured:true,token_configured:true,complete:true}, remote:{reachable:true,generation:1,elapsed_ms:25,event_count:0}, questions:{local_count:668,remote_count:0,same_count:0,different_count:0,local_only_count:668,remote_only_count:0,counts_equal:false,hashes_equal:false}, dry_run:{pending:4,predicted_conflict_count:0,unseen_remote_events:0,event_ids_unique:true,groups:[{namespace:'learner',kind:'canonical',table_name:'telegram_attempts',label:'Tentativas / respostas',count:4}]}, recommended_source:'this_device',requires_difference_confirmation:false,blocking_conflicts:false,activation:{required:true,completed:false,state:'validated'} } }),
    activate_cloud_sync_safely: async (source='this_device') => ({ ok:true,completed:true,in_progress:false,source,backup:{path:'data/cloud_sync_backups/QuestFlow-pre-cloud-sync.sqlite',quick_check:'ok'},seeded:668,sync:{ok:true,pushed:668,pulled:0,pending:0},activation:{completed:true,state:'active',completed_at:new Date().toISOString()},status:{enabled:true,state:'synced',pending:0,conflicts:0,last_sync_at:new Date().toISOString()} }),
    prepare_cloud_sync: async () => ({ ok: true, result: { seeded: 1, sync: { ok: true, pushed: 1, pulled: 0 } } }),
    sync_cloud_now: async () => ({ ok: true, pushed: 0, pulled: 0, status: { state: 'synced', pending: 0, last_sync_at: new Date().toISOString() } }),
    get_cloud_sync_status: async () => ({ ok: true, status: { state: 'synced', pending: 0, conflicts: 0, generation: 1, last_sync_at: new Date().toISOString() } }),
    get_cloud_sync_pending: async () => ({ ok: true, queue: { total: 0, with_error: 0, deadletter: 0, groups: [], items: [] } }),
    get_database_health: async () => ({ ok: true, health: { local_healthy: true, local_question_count: 668, remote_question_count: 668, counts_equal: true, synchronized: true, cloud_reachable: true, quick_check: 'ok', foreign_key_violations: 0, status: { pending: 0, conflicts: 0, last_sync_at: new Date().toISOString() }, message: 'Banco saudável, atualizado e sincronizado com o Turso.' } }),
    get_runtime_watchdog_status: async () => ({ ok:true, watchdog:{overall:'healthy',score:100,enabled:true,auto_recover:true,interval_seconds:5,uptime_seconds:120,supervisor_thread_alive:true,services:[{name:'local_http',label:'Servidor local e interface',status:'healthy',recoverable:false,detail:{heartbeat_age_seconds:1.2}},{name:'sqlite',label:'SQLite local',status:'healthy',recoverable:false,detail:{latency_ms:2.4,quick_check:'ok'}},{name:'async_runtime',label:'Runtime assíncrono',status:'healthy',recoverable:true,detail:{active:1,max_concurrency:4}},{name:'cloud_sync',label:'Cloud Sync / Turso',status:'offline',recoverable:true,detail:{pending:0,last_error:'Sem internet'}},{name:'telegram',label:'Telegram e agendador',status:'healthy',recoverable:true,detail:{}},{name:'domain_modules',label:'Módulos de domínio QuestFlow',status:'healthy',recoverable:false,detail:{engine_count:6,extensible:true}},{name:'task_runtime',label:'Fila de tarefas',status:'healthy',recoverable:false,detail:{active:0}}],history:[]},compatibility:{ok:true,status:'compatível',app_version:'6.15.2',python:{version:'3.13.5',validated_range:'3.11–3.13',validated:true},sqlite:{version:'3.46.1',minimum:'3.24.0',supported:true},platform:{system:'Windows',release:'11',machine:'AMD64',bits:64},warnings:[]},rate_limits:[] }),
    run_runtime_watchdog_check: async () => ({ok:true,watchdog:{overall:'healthy',score:100,services:[]}}),
    restart_runtime_service: async (name) => ({ok:true,service:name}),
    save_runtime_watchdog_settings: async (payload) => ({ok:true,watchdog:{overall:'healthy',score:100,services:[]},compatibility:{ok:true,status:'compatível'},rate_limits:[],settings:payload}),
    get_bank_intelligence: async () => ({ ok: true, summary: { total: 668, average_quality: 84.3, ready: 510, needs_review: 158, with_commentary: 522, official: 610, unverified_origin: 20, open_duplicate_candidates: 4, origins: { oficial: 610, inedita_propria: 18, manual: 20, nao_informada: 20 }, curation: { pronta: 510, revisar: 104, incompleta: 40, bloqueada: 14 }, difficulty: { facil: 120, media: 180, dificil: 90, sem_dados: 278 }, comments: { manual_nao_classificado: 390, ia_assistida: 132, sem_comentario: 146 }, quality_bands: { A: 390, B: 170, C: 82, D: 26 }, semantic: { version: 'qf-semantic-1', indexed_questions: 668, coverage: 100, rag_chunks: 1180, knowledge_nodes: 245, knowledge_edges: 410, offline_ready: true } } }),
    refresh_bank_intelligence: async () => ({ ok: true, updated: 3, status_changes: 1, comment_changes: 1, difficulty_changes: 1, summary: { total: 668, average_quality: 84.5, ready: 511, needs_review: 157, with_commentary: 523, official: 610, unverified_origin: 20, open_duplicate_candidates: 4, origins: { oficial: 610, inedita_propria: 18, manual: 20, nao_informada: 20 }, curation: { pronta: 511, revisar: 103, incompleta: 40, bloqueada: 14 }, difficulty: { facil: 121, media: 180, dificil: 90, sem_dados: 277 }, comments: { manual_nao_classificado: 391, ia_assistida: 132, sem_comentario: 145 }, quality_bands: { A: 391, B: 169, C: 82, D: 26 } } }),
    get_curation_attention: async (kind='curation') => ({ ok: true, kind, total: 2, items: [{ uid:'demo-1', code:'Q2534553', subject:'CONTABILIDADE PÚBLICA', topic:'PRINCÍPIOS ORÇAMENTÁRIOS', score:84, grade:'B', can_complete_review: kind==='curation', human_approved:false, missing: kind==='difficulty' ? ['Responder a questão para gerar dificuldade empírica'] : ['Comentário disponível','Curadoria aprovada'] }] }),
    complete_curation_review: async () => ({ ok:true, summary:{total:668,ready:511,needs_review:157,awaiting_review_completion:0,objective_curation_gaps:157,average_quality:84.5,with_commentary:523,open_duplicate_candidates:4,origins:{oficial:610},curation:{pronta:511,revisar:103,incompleta:40,bloqueada:14},difficulty:{sem_dados:277},comments:{manual_nao_classificado:391,sem_comentario:145},quality_bands:{A:391,B:169,C:82,D:26}} }),
    get_semantic_index_summary: async () => ({ ok: true, summary: { version: 'qf-semantic-1', indexed_questions: 668, total_questions: 668, coverage: 100, rag_chunks: 1180, knowledge_nodes: 245, knowledge_edges: 410, concept_links: 2400, engine: 'hybrid_local_hashing', offline_ready: true } }),
    get_question_knowledge_graph: async () => ({ ok: true, graph: { version: 'qf-semantic-1', nodes: [{ id: '1', node_type: 'materia', label: 'DIREITO TRIBUTÁRIO' }, { id: '2', node_type: 'assunto', label: 'Crédito tributário' }, { id: '3', node_type: 'referencia_legal', label: 'CTN, art. 151' }], edges: [{ source_node_id: '1', target_node_id: '2', relation: 'contem', weight: 1 }, { source_node_id: '2', target_node_id: '3', relation: 'relaciona', weight: 1 }] } }),
    get_rag_context: async () => ({ ok: true, retrieval: { version: 'qf-semantic-1', engine: 'hybrid lexical + semantic hashing + metadata rerank', items: [{ title: 'Q123 · Comentário', subject: 'DIREITO TRIBUTÁRIO', topic: 'Crédito tributário', content: 'A suspensão da exigibilidade está disciplinada pelo art. 151 do CTN.', scores: { score: 0.84, lexical: 0.66, semantic: 0.87, metadata: 0.5 } }] } }),
    start_semantic_rebuild: async () => makeMockTask({ version: 'qf-semantic-1', indexed_questions: 668, total_questions: 668, coverage: 100, rag_chunks: 1180, knowledge_nodes: 245, knowledge_edges: 410, concept_links: 2400, engine: 'hybrid_local_hashing', offline_ready: true }),
    get_question_intelligence: async () => ({ ok: true, intelligence: { origin_type: 'oficial', curation_status: 'pronta', quality: { score: 92, grade: 'A', status: 'pronta', missing: [] }, difficulty: { score: 52, label: 'media', accuracy: 66.7, confidence: 'moderada' }, attempts: { attempts: 12, correct: 8, hard_count: 3 }, commentary_source: 'manual_nao_classificado', rights_status: 'origem_oficial_identificada', learning_model: { mastery: .72, mastery_confidence: .66, mastery_label: 'Domínio bom', theta_scale: 56, item_difficulty_label: 'Média', item_information: .31 }, duplicate_candidates: [] } }),
    resolve_duplicate_candidate: async () => ({ ok: true }),
    get_ai_commentary_brief: async () => ({ ok: true, brief: { schema: 'questflow.ai-commentary.v1', instruction: 'Explique a questão com evidências.', publication_policy: 'rascunho_requer_aprovacao_humana', context: {}, recommended_evidence: ['PDF/aula vinculada', 'legislação oficial'], hybrid_retrieval: { items: [{ title: 'Q123 · Comentário', content: 'Fundamentação recuperada localmente.', scores: { score: 0.84 } }] } } }),
    start_ai_commentary_assist: async () => ({ ok: true, task_id: 'demo-ai' }),
    start_google_commentary_research: async () => makeMockTask({ ok:true, provider:'Google Modo IA', interaction_id:'demo-google-commentary', explanation:'Gabarito: C.\n\nExplicação pesquisada no Google para revisão humana.', suggested_answer:'C', official_answer:'C', verified_match:true, sources:[{provider:'Google Modo IA',title:'Resposta exibida no Modo IA do Google'}], warnings:[], evaluation:{overall_score:92}, commentary_source:'ia_assistida' }),
    get_learning_model: async () => ({ ok: true, model: dashboardMock.learner_model }),
    get_evidence_collection_plan: async (conceptKey) => ({ok:true,plan:{concept_key:conceptKey,concept_type:'assunto',subject:'DIREITO TRIBUTÁRIO',label:'Suspensão da exigibilidade',mastery:.45,confidence:.24,exposures:2,correct:1,wrong:1,evidence:{abstain:true,label:'Evidência insuficiente',reasons:['apenas 2 evidências']},is_problem:false,explanation:'Não é um problema no programa. O modelo está se abstendo porque ainda há pouca evidência.',minimum_evidence:3,missing_minimum:1,recommended_questions:2,can_start:true,candidates:[{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',lesson:'Aula 03',topic:'Suspensão da exigibilidade',board:'CEBRASPE',attempts:0,diagnostic_score:91.2}]}}),
    start_evidence_collection: async () => ({ok:true,simulation:{session:{id:'mock-evidence-1',mode:'diagnostico',target_count:2,answered_count:0,correct_count:0,status:'em_andamento',progress:0,accuracy:null},current:{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',topic:'Suspensão da exigibilidade',board:'CEBRASPE',statement:sample.enunciado,alternatives:sample.alternativas.map((x,i)=>({index:i,key:x.chave,text:x.texto})),recommendation:{score:91,bucket:2,scheduler_reason:'Coleta diagnóstica',reasons:['evidência insuficiente']}},items:[]}}),
    get_scaffolding_benchmark: async () => ({ok:true,benchmark:{sessions:8,observations:11,delayed_observations:7,delayed_accuracy:.71,by_support:[{key:'independente',samples:4,delayed_samples:3,delayed_accuracy:.8},{key:'apoio_moderado',samples:4,delayed_samples:3,delayed_accuracy:.67},{key:'apoio_alto',samples:3,delayed_samples:1,delayed_accuracy:1}],by_representation:[{key:'texto',samples:7,delayed_samples:5,delayed_accuracy:.8},{key:'passo',samples:4,delayed_samples:2,delayed_accuracy:.5}],recommendations:['A amostra ainda é observacional.'],caveat:'Associação observacional, não prova causal.',version:'qf-scaffold-benchmark-1'}}),
    run_multimodal_grounding_benchmark: async () => ({ok:true,benchmark:{version:'qf-grounding-benchmark-1',cases:8,visual_cases:3,sample_status:'suficiente',quality_label:'Grounding adequado',hybrid_gain:6.4,backends:[{backend:'text',cases:8,score:72.1,grounding_rate:100,commentary_support:68,precision:76,recall:70,path_safety:100},{backend:'visual',cases:8,score:58.2,grounding_rate:100,commentary_support:42,precision:null,recall:null,visual_coverage:100,path_safety:100},{backend:'hybrid',cases:8,score:78.5,grounding_rate:100,commentary_support:75,precision:79,recall:78,visual_coverage:100,path_safety:100}],recommendations:['Continue ampliando a amostra ouro.'],caveat:'Benchmark determinístico sobre Questões Ouro locais.'}}),
    run_retrieval_calibration: async () => ({ok:true,calibration:{version:'qf-retrieval-calibration-1',cases:8,sample_status:'suficiente',objective:'70% composite + 20% recall + 10% grounding',current:{profile:{id:'balanced-v1',label:'Balanceado 6.8.2',weights:{original_score:.45,query_overlap:.25,grounding:.20,visual_context:.10}},objective:78.1,score:77.2,recall:75,grounding_rate:100},recommended:{profile:{id:'grounding-first-v1',label:'Grounding prioritário',weights:{original_score:.36,query_overlap:.22,grounding:.32,visual_context:.10}},objective:80.4,score:79.5,recall:78,grounding_rate:100},recommended_change:true,objective_gain:2.3,auto_apply:false,caveat:'Aplicação exige confirmação humana.'}}),
    apply_retrieval_calibration: async (id) => ({ok:true,result:{active:{id,label:id}}}),
    rollback_retrieval_calibration: async () => ({ok:true,result:{active:{id:'balanced-v1',label:'Balanceado 6.8.2'}}}),
    save_retrieval_regression_baseline: async () => ({ok:true,baseline:{release:'6.8.2',cases:8,saved_at:new Date().toISOString()}}),
    get_retrieval_regression_status: async () => ({ok:true,status:{profile:{id:'balanced-v1',label:'Balanceado 6.8.2'},baseline:null,comparison:{status:'sem_baseline',alerts:[],deltas:{},message:'Salve um baseline para habilitar regressão contínua.'}}}),
    get_retrieval_health_service: async () => ({ok:true,service:{version:'qf-retrieval-health-service-1',status:'idle',execution_mode:'dedicated_serial_evaluator_worker',query_mode:'metrics_snapshot_store_only'}}),
    get_retrieval_health_snapshot: async () => ({ok:true,snapshot:{release:'6.15.2',service:{status:'idle'}}}),
    start_retrieval_evaluation: async (_limit=30,source='manual') => ({ok:true,job:{id:'mock-retrieval-job',release:'6.15.2',source,status:'completed',progress:1,message:'Avaliação concluída e snapshot publicado.',result:{gate_status:'pass'}}}),
    get_retrieval_evaluation_job: async () => ({ok:true,job:{id:'mock-retrieval-job',status:'completed',progress:1,message:'Avaliação concluída e snapshot publicado.',result:{gate_status:'pass'}}}),
    get_retrieval_observability: async () => ({ok:true,observability:{version:'qf-retrieval-observability-2',release:'6.15.2',engine:{id:'knowledge_engine',name:'Knowledge Engine',version:'qf-knowledge-engine-3.4'},profile:{id:'balanced-v1',label:'Balanceado'},retrieval:{cases:8,sample_status:'suficiente',hybrid:{score:79.2,recall:78,grounding_rate:100},subjects:{AUDITORIA:{cases:3,score:81,recall:80,grounding_rate:100}}},index:{coverage:100,rag_chunks:1180,source_count:670,by_subject:{AUDITORIA:112}},drift:{status:'stable',added_chunks:0,removed_chunks:0,changed_chunks:0,added_sources:0,removed_sources:0,changed_sources:0,coverage_delta:0,message:'Índice estável.'},history:[{at:new Date().toISOString(),release:'6.10.3',profile_id:'balanced-v1',cases:8,score:79.2,recall:78,grounding_rate:100,index_coverage:100,rag_chunks:1180,sources:670,drift:{status:'stable'}}],snapshot_release:'6.10.3',snapshot_at:new Date().toISOString(),snapshot_current:true,release_comparison:{available:true,deltas:{score:1.2,recall:2,grounding_rate:0,index_coverage:0}},caveat:'Observabilidade local.'}}),
    record_retrieval_observability: async () => ({ok:true,job:{id:'mock-retrieval-job',status:'completed',progress:1}}),
    suggest_gold_question_expansion: async () => ({ok:true,suggestions:{active_gold_questions:8,auto_apply:false,message:'Sugestões apenas.',suggestions:[{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',topic:'Crédito tributário',quality_score:92,score:102,reasons:['qualidade editorial alta','matéria sub-representada'],requires_human_approval:true,auto_approved:false}]}}),
    export_retrieval_observability_report: async (format) => ({ok:true,report:{filename:`QuestFlow_Retrieval_Observability_6.15.2.${format==='csv'?'csv':'json'}`,mime:format==='csv'?'text/csv;charset=utf-8':'application/json;charset=utf-8',content:format==='csv'?'timestamp,release,score\n2026-08-19,6.15.2,79.2':'{\n  "release": "6.15.2"\n}'}}),
    get_retrieval_quality_gate: async () => ({ok:true,gate:{version:'qf-retrieval-quality-gates-2',release:'6.15.2',engine:{id:'knowledge_engine',name:'Knowledge Engine',version:'qf-knowledge-engine-3.4'},status:'pass',evaluated_at:new Date().toISOString(),current:{cases:8,hybrid:{score:80.2,recall:79,grounding_rate:100},index_coverage:100},approved_baseline:{release:'6.10.2',hybrid:{score:79.2,recall:78,grounding_rate:100},index_coverage:100},baseline_source:'approved_release',profile:{id:'balanced-v1',label:'Balanceado'},comparison:{deltas:{score:1,recall:1,grounding_rate:0,index_coverage:0}},policy:{score_drop_warn:4,recall_drop_warn:5,grounding_drop_warn:3,coverage_drop_warn:3,min_cases:3},blockers:[],warnings:[],sample_ok:true,can_promote:true,can_override:false,can_rollback:true,requires_human_action:true,auto_promote:false,message:'Quality gates aprovados; promoção humana está disponível.'}}),
    reevaluate_retrieval_quality_gate: async () => ({ok:true,job:{id:'mock-retrieval-job',status:'completed',progress:1}}),
    promote_retrieval_release: async () => ({ok:true,result:{approved:{release:'6.15.2',approval_action:'promote',approved_at:new Date().toISOString()}}}),
    override_retrieval_quality_gate: async (reason) => ({ok:true,result:{approved:{release:'6.15.2',approval_action:'override',approval_reason:reason,override:true}}}),
    rollback_retrieval_release_gate: async () => ({ok:true,result:{restored:{release:'6.8.3'}}}),
    export_retrieval_quality_gate_report: async (format) => ({ok:true,report:{filename:`QuestFlow_Retrieval_Quality_Gate_6.15.2.${format==='csv'?'csv':'json'}`,mime:format==='csv'?'text/csv;charset=utf-8':'application/json;charset=utf-8',content:format==='csv'?'release,status,metric\n6.15.2,pass,all':'{\n  "release": "6.15.2", "status": "pass"\n}'}}),
    start_learner_model_rebuild: async () => makeMockTask(dashboardMock.learner_model),
    get_engine_architecture: async () => ({ ok: true, architecture: { architecture: 'modular_monolith_hexagonal', engine_count: 6, extensible: true, all_ready: true, principles: ['offline_first','human_in_the_loop','auditable_ai','rag_grounding','hexagonal_boundaries','vertical_modules'], engines: [
      { id:'editorial_bank', name:'Banco Editorial', version:'qf-editorial-engine-1', status:'ready', metrics:{questions:668,ready:510} },
      { id:'learner_model', name:'Learner Model', version:'qf-learner-engine-1', status:'ready', metrics:{concepts:48,events:322} },
      { id:'learning_engine', name:'Learning Engine', version:'qf-learning-engine-2', status:'ready', metrics:{attempts:322,scheduler:'FSRS'} },
      { id:'knowledge_engine', name:'Knowledge Engine', version:'qf-knowledge-engine-3.4', status:'ready', metrics:{coverage:100,rag_chunks:1180} },
      { id:'ai_engine', name:'AI Engine', version:'qf-ai-engine-4', status:'ready', metrics:{modes:4,offline_fallback:true} },
      { id:'evaluation_governance', name:'Evaluation & Governance Engine', version:'qf-ai-governance-4', status:'ready', metrics:{policy:'human_in_the_loop'} },
    ] } }),
    get_tutor_workspace: async () => ({ ok: true, workspace: { selected: { uid:'demo-1', code:'Q2534553', subject:'CONTABILIDADE PÚBLICA', topic:'PRINCÍPIOS ORÇAMENTÁRIOS', statement:sample.enunciado, diagnosis:{label:'Confusão conceitual',confidence:.81,signals:['KT indica domínio intermediário.'],intervention:'Compare os conceitos confundidos antes de refazer a questão.'}, learner:{mastery:.62,mastery_confidence:.7,mastery_label:'Em consolidação',retrievability:.58,theta_scale:54,item_difficulty_label:'Média'} }, recent_errors:[{question_uid:'demo-1',source_code:'Q2534553',subject:'CONTABILIDADE PÚBLICA',primary_topic:'PRINCÍPIOS ORÇAMENTÁRIOS',answered_at:new Date().toISOString(),confidence:'duvida'}], governance:{interactions:3,drafts:1,approved:2,rejected:0,diagnoses:4,average_evaluation:88.2,policy:'human_in_the_loop'} } }),
    diagnose_question_error: async () => ({ ok:true, diagnosis:{label:'Confusão conceitual',error_type:'confusao_conceitual',confidence:.81,signals:['KT indica domínio intermediário.'],intervention:'Compare os conceitos confundidos antes de refazer a questão.',explanation:'Hipótese baseada em sinais de aprendizagem.'} }),
    start_tutor_assist: async () => makeMockTask({ ok:true, interaction_id:'demo-tutor-1', mode:'professor', provider:'QuestFlow Grounded Composer', model:'qf-tutor-grounded-1', response:'**Modo professor**\n\nGabarito: E.\n\n**Fundamentação:** A contribuição de melhoria decorre de obra pública que gere valorização imobiliária.\n\n**Intervenção recomendada:** diferencie contribuição de melhoria das demais espécies.', diagnosis:{label:'Confusão conceitual',confidence:.81,intervention:'Compare os conceitos.'}, learner:{mastery:.62,mastery_confidence:.7}, sources:[{title:'Comentário existente no QuestFlow',provider:'Banco Editorial',content:sample.explicacao,score:1}], evaluation:{overall_score:91,groundedness:94,answer_alignment:96,source_coverage:78,pedagogical_quality:92,flags:[],status:'apto_para_revisao_humana'}, warnings:[], publication_policy:'rascunho_requer_aprovacao_humana' }),
    get_ai_audit: async () => ({ ok:true, summary:{interactions:3,drafts:1,approved:2,rejected:0,diagnoses:4,average_evaluation:88.2,policy:'human_in_the_loop'}, items:[{id:'demo-tutor-1',source_code:'Q2534553',subject:'CONTABILIDADE PÚBLICA',tutor_mode:'professor',provider:'QuestFlow Grounded Composer',model:'qf-tutor-grounded-1',status:'rascunho',overall_score:91,groundedness:94,created_at:new Date().toISOString(),flags:[]}] }),
    get_ai_interaction: async () => ({ok:true, interaction:{id:'demo-tutor-1',interaction_type:'tutor',status:'rascunho',response_text:'Texto original da IA.',display_response_text:'Texto original da IA.',question_changed:false}}),
    save_ai_interaction_text: async (_id, text) => ({ok:true, interaction:{id:'demo-tutor-1',interaction_type:'tutor',status:'rascunho',response_text:'Texto original da IA.',edited_response_text:text,display_response_text:text,has_human_edit:true,question_changed:false,evaluation:{overall_score:88,groundedness:90,answer_alignment:92,source_coverage:80,pedagogical_quality:86}}}),
    review_ai_interaction: async (_id, decision) => ({ok:true, review:{id:'demo-tutor-1',status:decision==='aprovar'?'aprovado':'rejeitado'}}),
    get_recommendation_dashboard: async (mode='equilibrado') => ({ok:true,dashboard:{schema:'questflow.recommender.v1',version:'qf-multiobjective-2',mode,recommendations:[{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',lesson:'Aula 03',topic:'Suspensão da exigibilidade',board:'CEBRASPE',bucket:2,scheduler_reason:'Revisão FSRS vencida',score:78.4,reasons:['risco de esquecimento FSRS (+21)','lacuna de domínio KT (+18)','cobertura do conteúdo (+12)'],components:{forgetting_risk:21,mastery_gap:18,coverage_gap:12,board_incidence:8,irt_information:7,exam_urgency:5,uncertainty:4,recency:3},retrievability:.42,mastery:.53,mastery_confidence:.71,irt_information:.45}],projections:[{subject:'DIREITO TRIBUTÁRIO',question_count:185,attempts:60,correct:29,mastery:.58,mastery_confidence:.72,theta_scale:44,projection:{estimate:.54,low:.41,high:.67,confidence:'boa'}},{subject:'AUDITORIA',question_count:96,attempts:18,correct:13,mastery:.71,mastery_confidence:.5,theta_scale:57,projection:{estimate:.68,low:.50,high:.84,confidence:'moderada'}}],overall_projection:{estimate:.59,low:.44,high:.73,label:'projeção de acerto no conteúdo disponível — não é probabilidade de aprovação'},board_incidence:[{board:'CEBRASPE',questions:310,share:.46},{board:'FGV',questions:205,share:.30},{board:'FCC',questions:91,share:.14}],active_simulation:null,caveats:['Incidência calculada no banco local.']}}),
    start_adaptive_simulation: async (payload={}) => ({ok:true,simulation:{session:{id:'mock-sim-1',mode:payload.mode||'equilibrado',target_count:Number(payload.target_count||10),answered_count:0,correct_count:0,status:'em_andamento',progress:0,accuracy:null},current:{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',topic:'Suspensão da exigibilidade',board:'CEBRASPE',statement:sample.enunciado,alternatives:sample.alternativas.map((x,i)=>({index:i,key:x.chave,text:x.texto})),recommendation:{score:78.4,bucket:2,scheduler_reason:'Revisão FSRS vencida',reasons:['risco de esquecimento FSRS (+21)']}},items:[]}}),
    get_adaptive_simulation: async () => ({ok:false,error:'Sessão de demonstração não persistida.'}),
    submit_adaptive_simulation_answer: async (_id,selected) => ({ok:true,simulation:{session:{id:'mock-sim-1',mode:'equilibrado',target_count:10,answered_count:1,correct_count:selected===4?1:0,status:'em_andamento',progress:.1,accuracy:selected===4?1:0},current:null,items:[],feedback:{is_correct:selected===4,selected_index:selected,correct_index:4,answer:'E',explanation:sample.explicacao},projection:{estimate:.6,low:.45,high:.74}}}),
    abandon_adaptive_simulation: async () => ({ok:true,simulation:{session:{id:'mock-sim-1',status:'abandonado',target_count:10,answered_count:1,correct_count:1,progress:.1},current:null,items:[]}}),
    get_stage5_workspace: async () => ({ok:true,workspace:{selected:{uid:'demo-1',code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',topic:'Suspensão da exigibilidade',board:'CEBRASPE',statement:sample.enunciado},candidates:[{uid:'demo-1',source_code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',primary_topic:'Suspensão da exigibilidade',board:'CEBRASPE'}],source_pool:[{id:'chunk-demo-1',source_kind:'question',source_ref:'demo-1',title:'Q2534553 · Comentário',subject:'DIREITO TRIBUTÁRIO',topic:'Suspensão da exigibilidade',content:sample.explicacao,metadata:{section:'explicacao'},scores:{score:.92}},{id:'chunk-leg-1',source_kind:'legislation',source_ref:'leg-demo',title:'CTN · art. 151',subject:'DIREITO TRIBUTÁRIO',topic:'CTN_ART_151',content:'Suspendem a exigibilidade do crédito tributário a moratória e as demais hipóteses previstas em lei.',metadata:{canonical_key:'CTN_ART_151',effective_from:'1966-10-25',effective_to:'',temporal_source:true},scores:{score:.88}}],legislation:[{id:'leg-demo',canonical_key:'CTN_ART_151',title:'CTN · art. 151',subject:'DIREITO TRIBUTÁRIO',effective_from:'1966-10-25',effective_to:'',source_label:'Fonte oficial'}],legislation_summary:{versions:1,canonical_norms:1,rag_chunks:1,temporal_resolution:true},drafts:[],gold:{active_gold_questions:1,last_run:null,evaluator:'qf-gold-regression-2'},policies:{selected_sources_only:true,second_model_validation:true,human_approval_required:true}}}),
    create_legislation_version: async (payload={}) => ({ok:true,version:{id:'leg-new',...payload},summary:{versions:2,canonical_norms:1,rag_chunks:2}}),
    resolve_legislation_version: async (_key,date) => ({ok:true,version:{id:'leg-demo',canonical_key:'CTN_ART_151',title:'CTN · art. 151',effective_from:'1966-10-25',effective_to:'',text_content:'Texto vigente de demonstração.',reference_date:date}}),
    generate_controlled_question: async () => ({ok:true,draft:{id:'draft-demo-1',status:'validado',validation_score:91,subject:'DIREITO TRIBUTÁRIO',topic:'Suspensão da exigibilidade',source_snapshot:[{id:'chunk-demo-1',title:'Q2534553 · Comentário',source_kind:'question'}],draft:{codigo_origem:'QFLOW-IA-DEMO',materia:'DIREITO TRIBUTÁRIO',assunto:'Suspensão da exigibilidade',tipo:'Múltipla escolha',enunciado:'A respeito da suspensão da exigibilidade, assinale a alternativa correta.',alternativas:[{chave:'A',texto:'A moratória suspende a exigibilidade do crédito tributário.'},{chave:'B',texto:'A moratória sempre extingue o crédito tributário.'},{chave:'C',texto:'A suspensão dispensa os requisitos legais.'},{chave:'D',texto:'A regra produz o efeito oposto ao texto legal.'},{chave:'E',texto:'A nomenclatura basta para definir a resposta.'}],gabarito:'A',explicacao:'Rascunho fundamentado nas fontes selecionadas.'},validation:{version:'qf-generation-critic-1',overall_score:91,groundedness:96,source_score:78,wording:92,distractor_quality:90,flags:[],critical_flags:[],status:'apto_para_revisao_humana'}},validation:{overall_score:91,status:'apto_para_revisao_humana',flags:[],critical_flags:[]}}),
    get_generation_draft: async () => ({ok:false,error:'Rascunho de demonstração não persistido.'}),
    review_generation_draft: async (_id,decision) => ({ok:true,draft:{id:'draft-demo-1',status:decision==='aprovar'?'aprovado':decision==='rejeitar'?'rejeitado':'rascunho',validation_score:91,draft:{codigo_origem:'QFLOW-IA-DEMO'}}}),
    publish_generation_draft: async () => ({ok:true,draft:{id:'draft-demo-1',status:'publicado'},published:{uid:'demo-published',question:{codigo_origem:'QFLOW-IA-DEMO'}}}),
    add_gold_question: async () => ({ok:true,gold:{id:'gold-demo',label:'Q2534553',expected_answer:'E'},summary:{active_gold_questions:2,last_run:null}}),
    run_gold_regression: async () => ({ok:true,result:{run_id:'run-demo',model:'qf-gold-grounded-baseline-2',cases:2,average_score:100,correct:2,items:[{source_code:'Q2534553',expected_answer:'E',predicted_answer:'E',score:100,flags:[]}]},summary:{active_gold_questions:2,last_run:{run_id:'run-demo',cases:2,average_score:100,correct:2}}}),
    get_gold_dashboard: async () => ({ok:true,summary:{active_gold_questions:1,last_run:null,evaluator:'qf-gold-regression-2'},items:[{id:'gold-demo',question_uid:'demo-1',label:'Q2534553',expected_answer:'E',source_code:'Q2534553',subject:'DIREITO TRIBUTÁRIO'}]}),
    get_today_dashboard: async () => ({ok:true,today:{schema:'questflow.today.v1',project:{id:'project-demo',name:'RFB · Auditor-Fiscal',agency:'Receita Federal',role:'Auditor-Fiscal',board:'CEBRASPE',exam_date:'2026-12-06'},days_to_exam:115,coverage:{items:42,covered:31,studied:22,mastered:12,coverage_rate:.738,mastery_rate:.286,weighted_coverage:.76},due_reviews:18,new_questions:121,critical_gaps:[{subject:'DIREITO TRIBUTÁRIO',topic:'Crédito Tributário',priority:82},{subject:'AUDITORIA',topic:'Risco de detecção',priority:74}],recommendations:[],tasks:[{kind:'fsrs',title:'18 revisões vencidas',detail:'Comece pelas revisões FSRS vencidas.',minutes:25,route:'recommend',priority:100},{kind:'gaps',title:'2 lacunas prioritárias do edital',detail:'Itens com baixa cobertura ou domínio incerto.',minutes:12,route:'examproject',priority:85},{kind:'questions',title:'8 questões de alto valor',detail:'FSRS + KT + IRT + edital.',minutes:16,route:'recommend',priority:75}],estimated_minutes:53,message:'Faltam 115 dias para a prova.'}}),
    get_exam_project_dashboard: async () => ({ok:true,dashboard:{schema:'questflow.exam-project.v1',project:{id:'project-demo',name:'RFB · Auditor-Fiscal',agency:'Receita Federal',role:'Auditor-Fiscal',board:'CEBRASPE',exam_date:'2026-12-06',status:'edital_publicado',active:1,notes:''},projects:[{id:'project-demo',name:'RFB · Auditor-Fiscal',active:1,version_count:2}],version:{id:'v2',version_no:2,label:'Retificação 1',published_at:'2026-08-01'},versions:[{id:'v2',version_no:2,label:'Retificação 1',published_at:'2026-08-01',change_summary_json:'{"counts":{"added":2,"removed":1,"changed":1}}'},{id:'v1',version_no:1,label:'Edital inicial',published_at:'2026-07-01',change_summary_json:'{}'}],days_to_exam:115,coverage:{items:42,covered:31,studied:22,mastered:12,coverage_rate:.738,study_rate:.524,mastery_rate:.286,weighted_coverage:.76,weighted_mastery:.31},items:[{id:'i1',subject:'DIREITO TRIBUTÁRIO',topic:'Crédito Tributário',weight:1.5,linked_questions:38,attempts:22,accuracy:.64,mastery:.58,mastery_confidence:.72,priority:82,covered:true,studied:true,mastered:false,restricted_questions:1},{id:'i2',subject:'AUDITORIA',topic:'Risco de detecção',weight:1,linked_questions:16,attempts:8,accuracy:.75,mastery:.66,mastery_confidence:.49,priority:63,covered:true,studied:true,mastered:false,restricted_questions:0}],diff:{counts:{added:2,removed:1,changed:1},added:['contabilidade|demonstrações'],removed:['ti|legado'],changed:[]},currency:{counts:{vigente:1268,potencialmente_desatualizada:14,desatualizada:2,anulada:1,controversa:1,historica:7},attention:18,items:[{question_uid:'demo-1',source_code:'Q2534553',subject:'DIREITO TRIBUTÁRIO',primary_topic:'Crédito Tributário',exam_year:2021,status:'potencialmente_desatualizada',reason:'Norma relacionada possui versão posterior.'}]}}}),
    save_exam_project: async (payload={}) => ({ok:true,project:{id:payload.id||'project-demo',...payload,active:1},dashboard:(await createMockBridge().get_exam_project_dashboard()).dashboard}),
    set_active_exam_project: async () => ({ok:true,dashboard:(await createMockBridge().get_exam_project_dashboard()).dashboard,today:(await createMockBridge().get_today_dashboard()).today}),
    parse_edital_text: async (text='') => ({ok:true,count:Math.max(1,String(text).split(/\n+/).filter(Boolean).length),items:String(text).split(/\n+/).filter(Boolean).slice(0,20).map((line,i)=>({ordinal:i+1,subject:line.includes(':')?line.split(':')[0]:'Conteúdo geral',topic:line.includes(':')?line.split(':').slice(1).join(':'):line,weight:1,expected_questions:0}))}),
    add_edital_version: async () => ({ok:true,dashboard:(await createMockBridge().get_exam_project_dashboard()).dashboard,today:(await createMockBridge().get_today_dashboard()).today}),
    relink_exam_project: async () => ({ok:true,result:{linked:612,items:42,questions:668},dashboard:(await createMockBridge().get_exam_project_dashboard()).dashboard}),
    scan_question_currency: async () => ({ok:true,result:{scanned:668,flagged:14,reference_date:'2026-12-06',attention:18}}),
    set_question_currency: async (uid,status,reason='',referenceDate='') => ({ok:true,currency:{question_uid:uid,status,reason,reference_date:referenceDate}}),
    request_close: async () => ({ ok: true, message: 'Fechamento seguro solicitado.' }),
    get_mobile_access: async () => ({ ok: true, enabled: false, urls: [] }),
    get_mobile_foundation_status: async () => ({ ok:true,api:'questflow.mobile.v1',schema_version:1,identity_ready:true,account_id:'account-demo',tenant_id:'tenant-demo',learner_id:'learner-demo',database_per_tenant_control_plane:true,active_devices:0,devices:[],learning_events:0,applied_event_effects:0,open_pairings:0,event_idempotency:true,question_revisions:true,offline_sync_cursor:true,active_timing_quality_gate:true }),
    create_mobile_pairing: async () => ({ok:true,pairing:{pairing_token:'DEMO-PAIRING-TOKEN',pairing_uri:'questflow://pair?api=v1&token=DEMO-PAIRING-TOKEN',qr_data_uri:'',expires_at:new Date(Date.now()+300000).toISOString(),expires_in_seconds:300,single_use:true}}),
    revoke_mobile_device: async (deviceId) => ({ok:true,device_id:deviceId,revoked_at:new Date().toISOString()}),
    export_data: async () => ({ ok: false, cancelled: true }), import_database: async () => ({ ok: false, cancelled: true }), launch_classic: async () => ({ ok: true }), poll_events: async () => ({ items: [], cursor: 0 }),
  };
}

const routes = {
  dashboard: 'Visão geral', visualanalytics: 'Painel visual', examproject: 'Projeto de concurso e edital', import: 'Importar arquivos', curation: 'Curadoria inteligente', tutor: 'Tutor IA adaptativo', recommend: 'Recomendador e simulados adaptativos', stage5: 'Geração controlada e legislação temporal', review: 'Revisar banco', bankfix: 'Corrigir banco', flow: 'Fluxo Telegram',
  corrections: 'Correções e Matérias não Estudadas', coverage: 'Cobertura dos estudos', mobile: 'QuestFlow Mobile', settings: 'Configurações',
};

function resolvedThemeIsDark(theme = state.theme) {
  if (theme === 'dark') return true;
  if (theme === 'light') return false;
  return Boolean(window.matchMedia?.('(prefers-color-scheme: dark)').matches);
}

function updateThemeIdentity() {
  const dark = resolvedThemeIsDark();
  const art = dark ? QUESTFLOW_ART.dark : QUESTFLOW_ART.light;
  const favicon = $('#appFavicon');
  const touch = $('#appTouchIcon');
  const meta = $('#themeColorMeta');
  if (favicon) favicon.href = art.favicon;
  if (touch) touch.href = art.logo256;
  if (meta) meta.content = dark ? '#071525' : '#f3f7fb';
  document.body?.classList.toggle('is-dark-resolved', dark);
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('qf-theme', theme);
  const dark = resolvedThemeIsDark(theme);
  const label = dark ? 'Ativar tema claro' : 'Ativar tema escuro';
  $('#themeToggle')?.setAttribute('aria-label', label);
  updateThemeIdentity();
}

function applyZoom(value) {
  state.zoom = Math.max(0.8, Math.min(1.45, Number(value.toFixed(2))));
  document.documentElement.style.fontSize = `${state.zoom * 100}%`;
  $('#zoomValue').textContent = `${Math.round(state.zoom * 100)}%`;
  localStorage.setItem('qf-ui-zoom', String(state.zoom));
  if (virtualList) virtualList.measure();
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
    else await document.exitFullscreen();
  } catch (error) {
    toast(`Não foi possível alternar a tela cheia: ${error.message}`, 'warning');
  }
}

function updateFullscreenButton() {
  const button = $('#fullscreenToggle');
  if (!button) return;
  const active = Boolean(document.fullscreenElement);
  button.setAttribute('aria-label', active ? 'Sair da tela cheia' : 'Ativar tela cheia');
  button.title = active ? 'Sair da tela cheia' : 'Tela cheia';
  const icon = $('span', button);
  if (icon) icon.textContent = active ? '⛶' : '⛶';
  button.classList.toggle('is-active', active);
}

function setSidebarCollapsed(collapsed, persist = true) {
  state.sidebarCollapsed = Boolean(collapsed);
  const shell = $('#appShell');
  shell.classList.toggle('is-sidebar-collapsed', state.sidebarCollapsed);
  $('#sidebarToggle').setAttribute('aria-expanded', String(!state.sidebarCollapsed));
  $('#sidebarToggle').setAttribute('aria-label', state.sidebarCollapsed ? 'Expandir menu' : 'Recolher menu');
  $$('.nav-item[data-route]').forEach((button) => {
    const label = button.querySelector(':scope > span:not(.nav-icon):not(.nav-badge)')?.textContent?.trim() || '';
    button.title = state.sidebarCollapsed ? label : '';
  });
  if (persist) localStorage.setItem('qf-sidebar-collapsed', state.sidebarCollapsed ? '1' : '0');
}

function setSystemStatus(text, type = 'ok') {
  const chip = $('#systemChip');
  chip.innerHTML = `<span class="status-dot status-dot--${type}"></span><span>${escapeHtml(text)}</span>`;
}

function toast(message, type = 'info', timeout = 4200) {
  const region = $('#toastRegion');
  const node = document.createElement('div');
  node.className = `toast toast--${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '!' : type === 'warning' ? '⚠' : 'i';
  node.innerHTML = `<strong aria-hidden="true">${icon}</strong><div>${escapeHtml(message)}</div><button type="button" aria-label="Fechar aviso">×</button>`;
  node.querySelector('button').addEventListener('click', () => node.remove());
  region.append(node);
  if (timeout) setTimeout(() => node.remove(), timeout);
}


const CURATION_ISSUE_TARGETS = Object.freeze({
  'Enunciado íntegro': ['#statementInput'],
  'Gabarito consistente': ['#field-gabarito', '#alternativesSection'],
  'Alternativas estruturadas': ['#alternativesSection', '#alternativesList'],
  'Matéria informada': ['#field-materia'],
  'Assunto informado': ['#field-assunto'],
  'Banca identificada': ['#field-banca'],
  'Ano identificado': ['#field-ano'],
  'Prova/órgão identificados': ['#field-prova', '#field-orgao'],
  'Proveniência classificada': ['#field-origem_questao'],
  'Fonte rastreável': ['#field-fonte_primaria'],
  'Comentário disponível': ['#explanationInput'],
  'Curadoria aprovada': ['#approveQuestion'],
});

const CURATION_ISSUE_GUIDANCE = Object.freeze({
  'Enunciado íntegro': 'Confira o enunciado no campo destacado. Enunciados curtos são válidos quando formam um conjunto coerente com alternativas e gabarito; o bloqueio ocorre apenas se o texto estiver ausente ou apresentar sinais objetivos de truncamento.',
  'Gabarito consistente': 'Escolha um gabarito que corresponda a uma das alternativas existentes.',
  'Alternativas estruturadas': 'Mantenha pelo menos duas alternativas preenchidas e separadas.',
  'Matéria informada': 'Selecione a matéria correta da questão.',
  'Assunto informado': 'Preencha o assunto principal da questão.',
  'Banca identificada': 'Informe a banca organizadora quando esse dado estiver disponível.',
  'Ano identificado': 'Informe o ano da prova quando esse dado estiver disponível.',
  'Prova/órgão identificados': 'Preencha a prova completa ou o órgão de origem.',
  'Proveniência classificada': 'Selecione a origem editorial da questão.',
  'Fonte rastreável': 'Informe a fonte primária, referência, arquivo ou documento de origem.',
  'Comentário disponível': 'Escreva a explicação pós-resposta neste campo.',
  'Curadoria aprovada': 'Use o botão de conclusão humana depois de conferir os campos críticos.',
});

function curationIssueIsNavigable(label = '') {
  return Boolean(CURATION_ISSUE_TARGETS[String(label || '').trim()]);
}

function resolveCurationIssueElement(label = '') {
  const selectors = CURATION_ISSUE_TARGETS[String(label || '').trim()] || [];
  for (const selector of selectors) {
    const element = $(selector);
    if (!element) continue;
    // Para prova/órgão, prefira um campo vazio; se ambos tiverem valor, use o primeiro.
    if (String(label).trim() === 'Prova/órgão identificados') {
      const empty = selectors.map((item) => $(item)).find((node) => node && !String(node.value || '').trim());
      if (empty) return empty;
    }
    return element;
  }
  return null;
}

function clearCurationFieldHighlights() {
  $$('.curation-field-highlight').forEach((node) => node.classList.remove('curation-field-highlight'));
  $$('.curation-section-highlight').forEach((node) => node.classList.remove('curation-section-highlight'));
}

function focusCurationIssue(label = '', { announce = true } = {}) {
  const issue = String(label || '').trim();
  const target = resolveCurationIssueElement(issue);
  if (!target) {
    if (announce) toast(`Não encontrei automaticamente o campo de “${issue}”. Abra a seção Inteligência e curadoria para ver o requisito.`, 'warning', 6500);
    return false;
  }
  clearCurationFieldHighlights();
  const section = target.closest?.('.editor-section') || target.closest?.('.form-field') || target;
  target.classList.add('curation-field-highlight');
  if (section && section !== target) section.classList.add('curation-section-highlight');
  target.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
  window.setTimeout(() => {
    if (typeof target.focus === 'function' && !target.disabled) {
      try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
      if (['INPUT', 'TEXTAREA'].includes(target.tagName) && typeof target.setSelectionRange === 'function') {
        try { const end = String(target.value || '').length; target.setSelectionRange(end, end); } catch (_) { /* noop */ }
      }
    }
  }, 420);
  const validation = $('#editorValidation');
  if (validation) {
    validation.className = 'validation-message is-warning curation-guidance-message';
    validation.innerHTML = `<strong>Corrigir: ${escapeHtml(issue)}</strong><span>${escapeHtml(CURATION_ISSUE_GUIDANCE[issue] || 'Edite o campo destacado e salve novamente.')}</span>`;
  }
  if (announce) toast(`Campo localizado: ${issue}.`, 'info', 3200);
  window.setTimeout(clearCurationFieldHighlights, 9000);
  return true;
}

function curationIssueButtonHtml(label, { compact = false } = {}) {
  const issue = String(label || '').trim();
  if (!curationIssueIsNavigable(issue)) return escapeHtml(issue);
  return `<button type="button" class="curation-issue-jump${compact ? ' is-compact' : ''}" data-curation-jump="${escapeHtml(issue)}"><span>${escapeHtml(issue)}</span><b>Ir ao campo →</b></button>`;
}

function bindCurationIssueJumps(root = document) {
  $$('[data-curation-jump]', root).forEach((button) => {
    if (button.dataset.curationJumpBound === '1') return;
    button.dataset.curationJumpBound = '1';
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      focusCurationIssue(button.dataset.curationJump || '', { announce: true });
    });
  });
}

function showEditorCurationBlockers(blockers = []) {
  const issues = Array.isArray(blockers) ? blockers.filter(Boolean) : [];
  const validation = $('#editorValidation');
  if (!validation || !issues.length) return;
  validation.className = 'validation-message is-error curation-blocker-message';
  validation.innerHTML = `<strong>A revisão ainda não pode ser concluída.</strong><span>Clique no requisito para ir exatamente ao campo que precisa ser corrigido.</span><div class="curation-blocker-links">${issues.map((issue) => curationIssueButtonHtml(issue, { compact: true })).join('')}</div>`;
  bindCurationIssueJumps(validation);
  validation.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function openCurationIssueForQuestion(uid, issue) {
  if (!uid) return;
  state.curationReviewContext = true;
  if (state.route !== 'review') await navigate('review');
  if (state.currentUid !== uid) await selectQuestion(uid);
  applyCurationReviewActionState();
  window.setTimeout(() => focusCurationIssue(issue, { announce: false }), 100);
}

function setBusy(button, busy, label = '') {
  if (!button) return;
  if (busy) {
    button.dataset.previousText = button.textContent;
    button.classList.add('is-loading');
    button.disabled = true;
    if (label) button.setAttribute('aria-label', label);
  } else {
    button.classList.remove('is-loading');
    button.disabled = false;
    if (button.dataset.previousText) button.textContent = button.dataset.previousText;
  }
}

function openModal({ title, eyebrow = '', body = '', footer = '', onOpen = null }) {
  const layer = $('#modalLayer');
  $('#modalTitle').textContent = title;
  $('#modalEyebrow').textContent = eyebrow;
  $('#modalBody').innerHTML = body;
  $('#modalFooter').innerHTML = footer;
  layer.hidden = false;
  document.body.style.overflow = 'hidden';
  document.body.classList.add('qf-modal-open');
  qfUiDiagnostics.modalOpenedAt = performance.now();
  console.info('[QF UI 6.21.1] modal-open', { title, at: new Date().toISOString() });
  const close = () => closeModal();
  $$('[data-modal-close]', layer).forEach((element) => element.addEventListener('click', close, { once: true }));
  layer.addEventListener('keydown', trapModalFocus);
  requestAnimationFrame(() => $('.modal [button], .modal button, .modal input, .modal textarea, .modal select')?.focus());
  onOpen?.(layer);
}

function closeModal() {
  const layer = $('#modalLayer');
  layer.hidden = true;
  document.body.style.overflow = '';
  document.body.classList.remove('qf-modal-open');
  console.info('[QF UI 6.21.1] modal-close', { duration_ms: Math.round(Math.max(0, performance.now() - qfUiDiagnostics.modalOpenedAt)), at: new Date().toISOString() });
  layer.removeEventListener('keydown', trapModalFocus);
}

function trapModalFocus(event) {
  if (event.key === 'Escape') return closeModal();
  if (event.key !== 'Tab') return;
  const focusables = $$('button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])', $('#modalLayer'));
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function measurePageLayout(page) {
  if (!page?.classList?.contains('page') || !page.classList.contains('is-active')) return;
  const width = page.getBoundingClientRect().width;
  const layout = width < 780 ? 'compact' : width < 1180 ? 'standard' : 'wide';
  if (page.dataset.layout !== layout) {
    page.dataset.layout = layout;
    page.dispatchEvent(new CustomEvent('questflow:layoutchange', { bubbles: true, detail: { layout, width } }));
  }
}

function enhanceDynamicDom(root = document) {
  const scope = root?.querySelectorAll ? root : document;
  const includeRoot = (selector) => root instanceof Element && root.matches(selector) ? [root] : [];
  [...includeRoot('.skeleton'), ...scope.querySelectorAll('.skeleton')].forEach((node) => {
    node.setAttribute('aria-hidden', 'true');
    node.closest('.panel, [aria-live]')?.setAttribute('aria-busy', 'true');
  });
  [...includeRoot('.empty-state'), ...scope.querySelectorAll('.empty-state')].forEach((node) => {
    if (!node.hasAttribute('role')) node.setAttribute('role', 'status');
    node.setAttribute('aria-live', 'polite');
  });
  [...includeRoot('.panel'), ...scope.querySelectorAll('.panel')].forEach((panel) => {
    if (!panel.querySelector('.skeleton')) panel.removeAttribute('aria-busy');
  });
  [...includeRoot('button'), ...scope.querySelectorAll('button')].forEach((button) => {
    if (!button.hasAttribute('type')) button.type = 'button';
  });
}

function installDomRuntime() {
  const pages = $$('.page');
  const resizeObserver = 'ResizeObserver' in window ? new ResizeObserver((entries) => {
    entries.forEach((entry) => measurePageLayout(entry.target));
  }) : null;
  pages.forEach((page) => {
    resizeObserver?.observe(page);
    page.setAttribute('aria-hidden', page.classList.contains('is-active') ? 'false' : 'true');
    page.inert = !page.classList.contains('is-active');
  });
  let mutationFrame = 0;
  const observer = new MutationObserver((mutations) => {
    if (mutationFrame) return;
    mutationFrame = requestAnimationFrame(() => {
      mutationFrame = 0;
      mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) enhanceDynamicDom(node);
      }));
      measurePageLayout($('.page.is-active'));
    });
  });
  observer.observe($('#workspace'), { childList: true, subtree: true });
  enhanceDynamicDom($('#workspace'));
  window.addEventListener('resize', debounce(() => measurePageLayout($('.page.is-active')), 90));
}

function setPageState(route, status, message = '') {
  const page = $(`.page[data-page="${route}"]`);
  if (!page) return;
  const isLoading = status === 'loading';
  page.dataset.state = status;
  page.toggleAttribute('aria-busy', isLoading);
  state.routeStates[route] = { status, message, at: Date.now() };
  const progress = $('#routeProgress');
  progress?.classList.toggle('is-active', isLoading && state.route === route);
  document.documentElement.dataset.pageState = status;
  const announcer = $('#pageStateAnnouncer');
  if (announcer && state.route === route) {
    announcer.textContent = isLoading ? `Carregando ${routes[route]}.` : status === 'error' ? `Falha ao atualizar ${routes[route]}. ${message}` : status === 'degraded' ? `${routes[route]} atualizada parcialmente. ${message}` : `${routes[route]} atualizada.`;
  }
  let feedback = $('.page-feedback', page);
  if (status === 'error' || status === 'degraded') {
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.className = 'page-feedback';
      feedback.setAttribute('role', 'alert');
      page.querySelector('.page-header')?.after(feedback);
    }
    feedback.classList.toggle('is-warning', status === 'degraded');
    feedback.innerHTML = `<div><strong>${status === 'degraded' ? 'Parte desta área está temporariamente indisponível.' : 'Não foi possível atualizar esta área.'}</strong><span>${escapeHtml(message || 'Tente novamente em instantes.')}</span></div><button class="button button--secondary button--compact" type="button">Tentar novamente</button>`;
    $('button', feedback)?.addEventListener('click', () => navigate(route, { refresh: true }));
    feedback.hidden = false;
  } else if (feedback) feedback.hidden = true;
}

async function settleRouteTasks(tasks = []) {
  const results = await Promise.allSettled(tasks);
  const failures = results.filter((item) => item.status === 'rejected');
  if (failures.length === results.length && failures.length) throw failures[0].reason;
  return failures.map((item) => item.reason?.message || 'Serviço indisponível.');
}

async function navigate(route, { refresh = false } = {}) {
  if (!routes[route]) return;
  if (state.dirty && route !== 'review') {
    const leave = window.confirm('Há alterações não salvas. Deseja sair desta tela?');
    if (!leave) return;
    state.dirty = false;
  }
  const workspace = $('#workspace');
  const previousRoute = state.route;
  if (previousRoute) state.routeScroll[previousRoute] = workspace?.scrollTop || 0;
  state.route = route;
  const requestId = ++state.routeRequestId;
  $$('.page').forEach((page) => {
    const active = page.dataset.page === route;
    page.classList.toggle('is-active', active);
    page.setAttribute('aria-hidden', active ? 'false' : 'true');
    page.inert = !active;
  });
  $$('.nav-item[data-route]').forEach((button) => {
    const active = button.dataset.route === route;
    button.classList.toggle('is-active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('#breadcrumbs').textContent = routes[route];
  document.title = `${routes[route]} · QuestFlow Studio`;
  document.documentElement.dataset.currentRoute = route;
  history.replaceState(null, '', `#${route}`);
  workspace.scrollTop = refresh || previousRoute === route ? workspace.scrollTop : (state.routeScroll[route] || 0);
  requestAnimationFrame(() => measurePageLayout($(`.page[data-page="${route}"]`)));
  setPageState(route, 'loading');
  document.dispatchEvent(new CustomEvent('questflow:route-will-change', { detail: { route, previousRoute, requestId } }));
  try {
    let routeWarnings = [];
    if (route === 'dashboard') await Promise.all([loadDashboard(), loadTodayDashboard()]);
    if (route === 'visualanalytics') await loadDashboard();
    if (route === 'examproject') await loadExamProjectPage(state.examProjectId || '');
    if (route === 'import') { renderImportContext(); renderImportFiles(); await loadRecentImports(); }
    if (route === 'curation') await Promise.all([loadBankIntelligence(), loadSemanticIndex()]);
    if (route === 'tutor') await loadTutorPage(state.tutorSelectedUid || '');
    if (route === 'recommend') await loadRecommendationPage();
    if (route === 'stage5') await loadStage5Page(state.stage5SelectedUid || '');
    if (route === 'review') await loadQuestions();
    if (route === 'bankfix') await loadBankFix();
    if (route === 'flow') await loadFlow();
    if (route === 'corrections') await loadCorrections();
    if (route === 'coverage') await loadCoverage();
    if (route === 'mobile') routeWarnings = await settleRouteTasks([loadCloudSyncSettings(), loadMobileFoundation(), loadMobileCloudBridgeSettings()]);
    if (route === 'settings') { renderSettings(); routeWarnings = await settleRouteTasks([loadCourseCatalogSettings(), loadAiProviderSettings(), loadAiPrivacySettings(), loadAiTelemetry(), loadUpdateMonitorStatus(), loadRuntimeWatchdogStatus()]); }
    if (requestId === state.routeRequestId) {
      setPageState(route, routeWarnings.length ? 'degraded' : 'ready', routeWarnings.join(' '));
      enhanceDynamicDom($(`.page[data-page="${route}"]`));
      document.dispatchEvent(new CustomEvent('questflow:route-ready', { detail: { route, requestId } }));
    }
  } catch (error) {
    if (requestId === state.routeRequestId) setPageState(route, 'error', error?.message || 'Erro inesperado.');
    console.error(`[QuestFlow] falha ao carregar ${route}`, error);
  }
}

function renderSkeletonCards(container, count = 4) {
  container.innerHTML = Array.from({ length: count }, () => '<div class="metric-card"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>').join('');
}

function renderDashboardData(data, { cached = false } = {}) {
  const q = data.question_stats || {};
  const s = data.study_stats || {};
  const adaptive = data.adaptive || {};
  const analytics = analyticsBuildContext(data);
  const accuracy = s.accuracy ?? (s.total_answers ? (s.correct_answers / s.total_answers) * 100 : 0);
  const activity = data.activity_summary || {};
  const avgActive = activity.avg_active_seconds == null ? '—' : `${Number(activity.avg_active_seconds).toFixed(1)} s`;
  const metrics = [
    { label: 'Questões respondidas', value: formatNumber(activity.attempts ?? s.attempts ?? 0), detail: 'Evidências reais que já alimentaram seu modelo', icon: '↗', tone: 'blue', progress: Math.min(100, Number(activity.attempts ?? s.attempts ?? 0) / 5) },
    { label: 'Acerto geral', value: activity.attempts ? `${Number(activity.accuracy || accuracy || 0).toFixed(1)}%` : '—', detail: `${formatNumber(activity.correct ?? s.correct ?? 0)} acertos · ${formatNumber(activity.wrong ?? s.wrong ?? 0)} erros`, icon: '✓', tone: 'green', progress: Number(activity.accuracy || accuracy || 0) },
    { label: 'Tempo médio ativo', value: avgActive, detail: `${formatNumber(activity.speed_samples||0)} amostras confiáveis; ociosidade excluída`, icon: '◷', tone: 'cyan', progress: Math.min(100, Number(activity.speed_samples || 0) * 4) },
    { label: 'Revisões para priorizar', value: formatNumber(adaptive.overdue ?? adaptive.reviews_due ?? analytics.dueTotal ?? 0), detail: 'Memória FSRS no ponto certo de recuperação', icon: '⟳', tone: 'orange', progress: Math.min(100, Number(adaptive.overdue ?? adaptive.reviews_due ?? analytics.dueTotal ?? 0) * 4) },
  ];
  $('#metricGrid').innerHTML = metrics.map((item) => `<article class="metric-card metric-card--explained metric-card--${item.tone}">
    <div class="metric-card__top"><span>${escapeHtml(item.label)}</span><i aria-hidden="true">${escapeHtml(item.icon)}</i></div>
    <strong>${escapeHtml(String(item.value))}</strong>
    <div class="metric-card__signal" aria-hidden="true"><b style="width:${Math.max(3, Math.min(100, Number(item.progress) || 0))}%"></b></div>
    <small>${escapeHtml(item.detail)}</small>
  </article>`).join('');
  renderLearningPulsePanel(data);
  renderQuestAiInsightPanel(data);
  renderStudyCommandPanel(data);
  loadAdaptiveDecisionPanel().catch(()=>undefined);
  renderAdaptivePanel(data);
  renderVisualAnalyticsPanel(data);
  renderFlowHealth(data.flow || {});
  renderRecentActivity(data.activity_summary?.recent_attempts || data.recent || []);
  const pending = q.pending ?? q.pendente ?? 0;
  $('#pendingBadge').hidden = !pending;
  $('#pendingBadge').textContent = pending;
  $('#correctionsBadge').hidden = !data.pending_reviews;
  $('#correctionsBadge').textContent = data.pending_reviews || 0;
  if (cached) setSystemStatus('Painel exibido do cache local • atualizando dados…', 'loading');
}

function renderLearningPulsePanel(data) {
  const panel = $('#learningPulsePanel');
  if (!panel) return;
  const context = analyticsBuildContext(data);
  const activity = data.activity_summary || {};
  // The headline and the rows must describe the same collection.  Previously
  // this list was truncated to three rows while the headline counted every
  // high/medium-priority subject, which could report "4 em foco" and render
  // only three subjects.
  const priorityFocus = context.prioritized.filter((item) => ['danger', 'warning'].includes(String(item.priority_tone)));
  const focusSubjects = (priorityFocus.length
    ? priorityFocus
    : context.prioritized.filter((item) => item.studied || item.has_answers)
  );
  const visibleFocus = focusSubjects.slice(0, 6);
  const hiddenFocusCount = Math.max(0, focusSubjects.length - visibleFocus.length);
  const retention = context.retentionWeighted;
  const recent = context.recentWeighted;
  const coverage = context.studiedCoverage;
  const retentionValue = retention == null ? 0 : Math.max(0, Math.min(100, Number(retention)));
  const ringStyle = `--pulse-value:${retentionValue.toFixed(1)}`;
  const top = visibleFocus[0] || null;
  const sessionCount = Math.max(5, Math.min(20, Number(data?.today?.recommended_questions || data?.recommended_questions || (context.dueTotal > 10 ? 15 : 10))));
  const focusRows = visibleFocus.length ? visibleFocus.map((item, index) => {
    const value = item.recent_accuracy == null ? 0 : Math.max(0, Math.min(100, Number(item.recent_accuracy)));
    const label = textOrMissing(item.subject || item.materia, 'Matéria');
    const tone = ['orange', 'cyan', 'violet', 'green'][index % 4];
    const sourceIndex = context.subjects.indexOf(item);
    const attempts = numberOrZero(item.attempts);
    return `<button class="learning-focus-row learning-focus-row--${tone}" type="button" data-pulse-subject-key="${sourceIndex}" aria-label="Abrir diagnóstico de ${escapeHtml(label)}"><span class="learning-focus-rank">${String(index + 1).padStart(2, '0')}</span><div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(textOrMissing(item.priority_label, 'Em acompanhamento'))} · ${formatNumber(attempts)} ${attempts === 1 ? 'resposta' : 'respostas'}</span></div><b>${analyticsPct(item.recent_accuracy)}</b><i aria-hidden="true"><span style="width:${value}%"></span></i></button>`;
  }).join('') : '';
  const focusMore = hiddenFocusCount
    ? `<div class="learning-focus-more"><span><strong>+${formatNumber(hiddenFocusCount)}</strong> ${hiddenFocusCount === 1 ? 'outra prioridade' : 'outras prioridades'}</span><button class="button button--secondary" type="button" data-pulse-all>Ver todas</button></div>`
    : '';
  panel.innerHTML = `<div class="learning-pulse-grid">
    <section class="learning-pulse-action">
      <span class="learning-pulse-kicker">Próxima melhor ação</span>
      <h3>${top ? `Reforce ${escapeHtml(textOrMissing(top.subject || top.materia, 'a matéria prioritária'))}` : 'Inicie uma sessão diagnóstica'}</h3>
      <p>${top ? escapeHtml((top.priority_reasons || [])[0] || 'É a maior prioridade calculada a partir de memória, desempenho e cobertura.') : 'O QuestFlow precisa de uma amostra curta para personalizar a rotação.'}</p>
      <div class="learning-session-plan"><strong>${sessionCount}</strong><span>questões · prática intercalada · feedback imediato</span></div>
      <button class="button button--primary" type="button" data-pulse-action>Abrir sessão recomendada</button>
    </section>
    <section class="learning-pulse-chart">
      <div class="learning-pulse-section-head"><div><span>Evolução recente</span><strong>${analyticsPct(recent)}</strong></div><small>${context.aggregateTrend.length >= 2 ? 'tendência por janelas de estudo' : 'coletando novas janelas'}</small></div>
      ${analyticsLineChart(context.aggregateTrend, 'Evolução recente do desempenho')}
      <div class="learning-pulse-legend"><span><i class="is-orange"></i>Acerto recente</span><span><i class="is-cyan"></i>Retenção ${analyticsPct(retention)}</span><span><i class="is-violet"></i>Cobertura ${analyticsPct(coverage)}</span></div>
    </section>
    <section class="learning-pulse-retention">
      <div class="learning-retention-ring" style="${ringStyle}" role="img" aria-label="Retenção estimada ${analyticsPct(retention)}"><div><strong>${analyticsPct(retention)}</strong><span>retenção hoje</span></div></div>
      <div class="learning-retention-copy"><strong>${context.dueTotal ? `${formatNumber(context.dueTotal)} revisões no ponto ideal` : 'Memória em dia'}</strong><span>${context.due7Total ? `${formatNumber(context.due7Total)} entram na janela de 7 dias.` : 'Nenhuma revisão próxima exige atenção.'}</span></div>
    </section>
    <section class="learning-pulse-focus"><div class="learning-pulse-section-head"><div><span>Prioridade por matéria</span><strong>${formatNumber(focusSubjects.length)} ${focusSubjects.length === 1 ? 'matéria em foco' : 'matérias em foco'}</strong></div><small>clique para abrir o diagnóstico</small></div>${focusRows ? `<div class="learning-focus-grid">${focusRows}</div>` : '<div class="learning-pulse-empty">Responda algumas questões para formar o primeiro mapa de prioridades.</div>'}${focusMore}</section>
  </div>`;
  panel.querySelector('[data-pulse-action]')?.addEventListener('click', () => navigate('recommend'));
  panel.querySelector('[data-pulse-all]')?.addEventListener('click', () => openFocusSubjectsModal(context));
  panel.querySelectorAll('[data-pulse-subject-key]').forEach((row) => row.addEventListener('click', () => openSubjectAnalyticsModal(context, row.dataset.pulseSubjectKey)));
}

async function openQuestAiInsightInTutor({ headline = '', explanation = '', topName = '' } = {}) {
  const prompt = [
    'Quero aprofundar este diagnóstico do meu painel de estudos:',
    String(headline || '').trim(),
    String(explanation || '').trim(),
    topName ? 'Foco atual: ' + String(topName).trim() + '.' : '',
    '',
    'Use a questão que eu selecionar como contexto. Explique de forma clara qual regra, conceito ou padrão de erro merece atenção e proponha uma recuperação ativa curta. Não invente métricas ou fatos que não estejam no contexto.',
  ].filter(Boolean).join('\n');
  await navigate('tutor');
  if (state.route !== 'tutor') return;
  const field = $('#tutorUserPrompt');
  if (!field) return;
  field.value = prompt;
  field.focus();
  field.dispatchEvent(new Event('change', { bubbles: true }));
  toast(state.tutorSelectedUid
    ? 'Insight levado ao Tutor. Revise o pedido e gere a orientação quando quiser.'
    : 'Insight levado ao Tutor. Selecione uma questão para usar como contexto antes de gerar a orientação.', 'info', 6500);
}

function renderQuestAiInsightPanel(data) {
  const panel = $('#questAiInsightPanel');
  if (!panel) return;
  const context = analyticsBuildContext(data);
  const activity = data.activity_summary || {};
  const candidates = context.prioritized.filter((item) => item.studied || item.has_answers);
  const top = candidates[0] || context.prioritized[0] || null;
  const topName = top ? textOrMissing(top.subject || top.materia, 'matéria prioritária') : '';
  const attempts = numberOrZero(activity.attempts);
  const due = numberOrZero(context.dueTotal);
  const recent = context.recentWeighted;
  const retention = context.retentionWeighted;
  const coverage = context.studiedCoverage;

  let headline = 'Forme a primeira evidência para personalizar o seu estudo';
  let explanation = 'O QuestFlow ainda precisa de respostas suficientes para comparar memória, desempenho e cobertura com segurança.';
  let action = 'Iniciar sessão diagnóstica';

  if (attempts && top) {
    const reason = (Array.isArray(top.priority_reasons) ? top.priority_reasons[0] : '') || 'é a prioridade mais alta calculada neste momento';
    if (due > 0) {
      headline = 'Recupere ' + topName + ' antes de avançar';
      explanation = formatNumber(due) + ' revisão(ões) estão no ponto de recuperação e ' + reason + '.';
      action = 'Começar revisão recomendada';
    } else if (recent != null && Number(recent) < 65) {
      headline = 'Consolide ' + topName + ' antes de aumentar o ritmo';
      explanation = 'O desempenho recente consolidado está em ' + analyticsPct(recent) + ' e ' + reason + '.';
      action = 'Abrir sessão de consolidação';
    } else if (coverage != null && Number(coverage) < 60) {
      headline = 'Amplie a cobertura sem perder ' + topName + ' de vista';
      explanation = 'A cobertura estudada está em ' + analyticsPct(coverage) + '. O melhor próximo passo é avançar o escopo mantendo a matéria prioritária na rotação.';
      action = 'Continuar plano adaptativo';
    } else {
      headline = 'Mantenha ' + topName + ' na rotação inteligente';
      explanation = 'Seu histórico já permite uma recomendação confiável. Continue o ciclo de questões e revisões para preservar retenção e estabilidade.';
      action = 'Continuar estudo';
    }
  }

  panel.innerHTML = '<div class="quest-ai-insight-grid">'
    + '<section class="quest-ai-message">'
    + '<div class="quest-ai-avatar" aria-hidden="true">Q</div>'
    + '<div class="quest-ai-copy">'
    + '<span>Síntese do Learning Engine</span>'
    + '<h3>' + escapeHtml(headline) + '</h3>'
    + '<p>' + escapeHtml(explanation) + '</p>'
    + '<div class="quest-ai-actions">'
    + '<button class="button button--primary" type="button" data-quest-ai-study>' + escapeHtml(action) + '</button>'
    + '<button class="button button--secondary" type="button" data-quest-ai-tutor>Levar insight ao Tutor</button>'
    + '<button class="button button--ghost" type="button" data-quest-ai-analytics>Ver diagnóstico</button>'
    + '</div></div></section>'
    + '<section class="quest-ai-signals" aria-label="Sinais usados no insight">'
    + '<div><span>Desempenho recente</span><strong>' + analyticsPct(recent) + '</strong><small>' + (attempts ? formatNumber(attempts) + ' resposta(s) no histórico' : 'aguardando respostas') + '</small></div>'
    + '<div><span>Retenção estimada</span><strong>' + analyticsPct(retention) + '</strong><small>' + (due ? formatNumber(due) + ' revisão(ões) vencidas' : 'memória sem pendência crítica') + '</small></div>'
    + '<div><span>Cobertura estudada</span><strong>' + analyticsPct(coverage) + '</strong><small>' + (top ? 'foco atual: ' + escapeHtml(topName) : 'aguardando escopo estudado') + '</small></div>'
    + '</section></div>';

  panel.querySelector('[data-quest-ai-study]')?.addEventListener('click', () => navigate('recommend'));
  panel.querySelector('[data-quest-ai-tutor]')?.addEventListener('click', () => {
    openQuestAiInsightInTutor({ headline, explanation, topName }).catch((error) => toast(error?.message || 'Não foi possível abrir o Tutor.', 'error'));
  });
  panel.querySelector('[data-quest-ai-analytics]')?.addEventListener('click', () => navigate('visualanalytics'));
}

function renderStudyCommandPanel(data) {
  const panel = $('#studyCommandPanel'); if(!panel) return;
  const a=data.activity_summary||{}; const subjects=Array.isArray(data.subjects)?data.subjects:[];
  const top=subjects[0]||null; const flow=data.flow||{}; const total=Number(a.attempts||0);
  const accuracy=a.accuracy==null?null:Number(a.accuracy);
  const verdict = !total ? 'Ainda faltam respostas para personalizar seu estudo.' : accuracy >= 80 ? 'Seu desempenho está bom, mas o QuestFlow ainda verifica memória, cobertura e quantidade de evidência.' : accuracy >= 65 ? 'Seu desempenho está em consolidação: mantenha as revisões e ataque a prioridade indicada.' : 'Seu desempenho pede reforço: priorize os conteúdos destacados antes de aumentar velocidade.';
  const next = top ? `Comece por ${escapeHtml(top.subject||top.materia||'a matéria prioritária')}: ${escapeHtml((top.priority_reasons||[])[0]||'é a maior prioridade calculada agora')}.` : 'Responda algumas questões para o QuestFlow formar uma prioridade confiável.';
  const telegramPaused=Boolean(flow.telegram_questions_paused);
  panel.innerHTML=`<div class="study-command-grid">
    <section class="study-command-primary"><span class="study-command-kicker">Leitura atual</span><h3>${escapeHtml(verdict)}</h3><p><strong>Próxima ação:</strong> ${next}</p><div class="study-command-actions">${top?'<button class="button button--primary" type="button" data-go-questions>Ver prioridade e estudar</button>':''}<button class="button button--secondary" type="button" data-go-progress>Entender meu progresso</button></div></section>
    <section class="study-channel-card"><h3>De onde vêm suas respostas?</h3><div class="channel-stat"><span>Aplicativo</span><strong>${formatNumber(a.mobile_attempts||0)}</strong><small>respostas sincronizadas</small></div><div class="channel-stat"><span>Telegram</span><strong>${formatNumber(a.telegram_attempts||0)}</strong><small>respostas registradas</small></div><p>${telegramPaused?'Envio de novas questões pelo Telegram está pausado. Suas respostas antigas continuam no histórico.':'Telegram ainda pode enviar questões e misturar o fluxo com o aplicativo.'}</p><button class="button ${telegramPaused?'button--success':'button--warning'}" type="button" id="dashboardTelegramToggle">${telegramPaused?'Retomar questões no Telegram':'Pausar questões no Telegram'}</button></section>
    <section class="study-timing-card"><h3>Como o tempo é interpretado</h3><strong>${a.avg_active_seconds==null?'Sem média confiável':`${Number(a.avg_active_seconds).toFixed(1)} s por resposta`}</strong><p>O QuestFlow usa somente tempo ativo aprovado. Tela aberta, inatividade e segundo plano não contam como lentidão.</p><small>${formatNumber(a.speed_samples||0)} amostra(s) válidas · ${formatNumber(a.excluded_timing||0)} tempo(s) excluídos por baixa confiabilidade</small></section>
  </div>`;
  panel.querySelector('[data-go-questions]')?.addEventListener('click',()=>navigate('visualanalytics'));
  panel.querySelector('[data-go-progress]')?.addEventListener('click',()=>navigate('visualanalytics'));
  $('#dashboardTelegramToggle')?.addEventListener('click',async(e)=>{await flowAction(telegramPaused?'resume_questions':'pause_questions',e.currentTarget); await loadDashboard({force:true});});
}

async function loadDashboard({ force = false } = {}) {
  const preview = !force ? state.dashboardPreview : null;
  if (preview && Object.keys(preview).length) {
    renderDashboardData(preview, { cached: true });
  } else {
    renderSkeletonCards($('#metricGrid'));
    if ($('#learningPulsePanel')) $('#learningPulsePanel').innerHTML = '<div class="skeleton" style="height:15rem"></div>';
    if ($('#questAiInsightPanel')) $('#questAiInsightPanel').innerHTML = '<div class="skeleton" style="height:9rem"></div>';
    $('#adaptivePanel').innerHTML = '<div class="skeleton" style="height:7rem"></div>';
    if ($('#visualAnalyticsPanel')) $('#visualAnalyticsPanel').innerHTML = '<div class="skeleton" style="height:18rem"></div>';
    $('#flowHealthPanel').innerHTML = '<div class="skeleton" style="height:7rem"></div>';
    $('#recentActivity').innerHTML = '<div class="skeleton" style="height:7rem"></div>';
  }
  setSystemStatus('Carregando painel em segundo plano…', 'loading');
  try {
    const started = await bridge.call('start_dashboard_load');
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar o painel.');
    state.dashboardTask = started.task_id;
    const data = await monitorTask(started.task_id, (task) => {
      const percent = Math.round(Number(task.progress || 0) * 100);
      setSystemStatus(`${task.message || 'Carregando painel'} ${percent}%`, 'loading');
    }, { timeoutMs: 120000, intervalMs: 350 });
    state.dashboardTask = null;
    state.dashboardPreview = data;
    renderDashboardData(data);
    const elapsed = Number(data.elapsed_seconds || 0);
    setSystemStatus(elapsed > 0 ? `Banco conectado • painel em ${elapsed.toFixed(1)}s` : 'Banco local conectado', 'ok');
    state.startupReady = true;
    loadDatabaseHealth({ quiet: false }).catch(() => {});
  } catch (error) {
    state.dashboardTask = null;
    setSystemStatus('Painel indisponível; interface continua ativa', 'warning');
    $('#metricGrid').innerHTML = emptyStateHtml({ title: 'O painel demorou mais que o esperado', text: error.message, button: '<button class="button button--secondary" id="retryDashboardInline">Tentar novamente</button>' });
    if ($('#learningPulsePanel')) $('#learningPulsePanel').innerHTML = emptyStateHtml({ text: 'O pulso de aprendizagem será recalculado na próxima tentativa.' });
    if ($('#questAiInsightPanel')) $('#questAiInsightPanel').innerHTML = emptyStateHtml({ text: 'O insight contextual será reconstruído assim que os dados do painel voltarem a carregar.' });
    $('#retryDashboardInline')?.addEventListener('click', loadDashboard, { once: true });
    $('#adaptivePanel').innerHTML = emptyStateHtml({ text: 'Os dados adaptativos serão carregados na próxima tentativa.' });
    if ($('#visualAnalyticsPanel')) $('#visualAnalyticsPanel').innerHTML = emptyStateHtml({ text: 'O painel visual será carregado na próxima tentativa.' });
    $('#flowHealthPanel').innerHTML = emptyStateHtml({ text: 'O Telegram continua separado do carregamento do painel.' });
    $('#recentActivity').innerHTML = emptyStateHtml({ text: 'Nenhuma atividade carregada.' });
  }
}

async function loadAdaptiveDecisionPanel() {
  const panel=$('#adaptiveDecisionPanel'); if(!panel) return;
  try {
    const result=await bridge.call('get_adaptive_session_observability', 8);
    if(!result?.ok) throw new Error(result?.error||'Observabilidade adaptativa indisponível.');
    const rows=Array.isArray(result.recent_decisions)?result.recent_decisions:[];
    const evaluation=result.evaluation||{};
    const readiness=String(evaluation.status||'')==='ready'
      ? `${formatNumber(evaluation.delayed_retention_samples||0)} amostras de retenção tardia disponíveis.`
      : `Ainda sem amostra suficiente para comparar retenção futura (${formatNumber(evaluation.delayed_retention_samples||0)}/${formatNumber(evaluation.minimum_delayed_samples||30)}).`;
    if(!rows.length){ panel.innerHTML=emptyStateHtml({text:'Ainda não há decisões de micro-lotes adaptativos registradas. Elas aparecerão após sessões no Mobile atual.'}); return; }
    panel.innerHTML=`<div class="adaptive-explain-summary"><p><strong>Objetivo do algoritmo:</strong> retenção e domínio futuro, não maximizar acertos dentro da sessão.</p><small>${escapeHtml(readiness)}</small></div><div class="adaptive-explain-list">${rows.map(row=>`<button class="adaptive-explain-row" type="button" data-adaptive-explain="${escapeHtml(row.question_uid||'')}" data-adaptive-session="${escapeHtml(row.session_id||'')}"><span><b>${escapeHtml(row.code||'Questão')}</b><small>${escapeHtml([row.subject,row.topic].filter(Boolean).join(' · ')||'Sem classificação')}</small></span><span><strong>${escapeHtml(row.reason||'Prioridade adaptativa')}</strong><small>${escapeHtml(row.strategy_profile||'balanced')} · plano ${formatNumber(row.plan_revision||0)}</small></span><i>Por quê? →</i></button>`).join('')}</div>`;
    $$('[data-adaptive-explain]',panel).forEach(button=>button.addEventListener('click',()=>showAdaptiveQuestionExplanation(button.dataset.adaptiveExplain||'',button.dataset.adaptiveSession||'')));
  } catch(error) {
    panel.innerHTML=emptyStateHtml({text:error?.message||'Não foi possível carregar as decisões adaptativas.'});
  }
}

async function showAdaptiveQuestionExplanation(questionUid, sessionId='') {
  openModal({title:'Por que esta questão?',eyebrow:'Adaptive Session Orchestrator · Studio',body:'<div class="skeleton" style="height:12rem"></div>',footer:'<button class="button button--secondary" data-modal-close>Fechar</button>'});
  try {
    const result=await bridge.call('explain_adaptive_question',questionUid,sessionId);
    if(!result?.ok) throw new Error(result?.error||'Explicação indisponível.');
    const x=result.explanation||{}, q=x.question||{}, state=x.learning_state||{}, decision=x.decision||{}, selection=decision.selection||{};
    const body=`<div class="detail-stack"><section class="detail-card"><span class="eyebrow">Questão</span><h3>${escapeHtml(q.code||q.uid||'Questão')}</h3><p>${escapeHtml([q.subject,q.topic,q.lesson].filter(Boolean).join(' · ')||'Sem classificação')}</p></section><section class="detail-card"><span class="eyebrow">Decisão</span><h3>${escapeHtml(x.reason||'Prioridade adaptativa')}</h3><p>Estratégia: <strong>${escapeHtml(x.strategy_profile||'balanced')}</strong> · revisão do plano ${formatNumber(x.plan_revision||0)}</p><p>${selection.topic_transfer?'A questão também foi usada para testar transferência do conceito em outra formulação.':'A questão foi escolhida pela prioridade calculada e pela composição intercalada da sessão.'}</p></section><section class="detail-card"><span class="eyebrow">Sinais considerados</span><div class="detail-grid"><div><small>Acertos / erros</small><strong>${formatNumber(state.correct_count||0)} / ${formatNumber(state.wrong_count||0)}</strong></div><div><small>KT mastery</small><strong>${state.kt_mastery==null?'—':`${(Number(state.kt_mastery)*100).toFixed(0)}%`}</strong></div><div><small>Retrievability</small><strong>${state.memory_retrievability==null?'—':`${(Number(state.memory_retrievability)*100).toFixed(0)}%`}</strong></div><div><small>Tempo esperado</small><strong>${selection.expected_active_seconds?`${Number(selection.expected_active_seconds).toFixed(0)} s`:'—'}</strong></div></div></section><section class="detail-card"><p><strong>Princípio:</strong> ${escapeHtml(x.principle||'A seleção busca retenção e domínio futuro.')}</p></section></div>`;
    const modalBody=$('#modalBody'); if(modalBody) modalBody.innerHTML=body;
  } catch(error) {
    const modalBody=$('#modalBody'); if(modalBody) modalBody.innerHTML=emptyStateHtml({text:error?.message||'Não foi possível explicar esta decisão.'});
  }
}

function intelligenceLabel(value, kind = '') {
  const key = String(value || '').trim();
  const maps = {
    origin: { oficial: 'Prova oficial', inedita_propria: 'Inédita própria', adaptada: 'Adaptada', literal_norma: 'Literal de norma', manual: 'Manual', nao_informada: 'Não informada' },
    curation: { pronta: 'Pronta', revisar: 'Revisar', incompleta: 'Incompleta', bloqueada: 'Bloqueada' },
    difficulty: { facil: 'Fácil', media: 'Média', dificil: 'Difícil', sem_dados: 'Sem dados' },
    commentary: { sem_comentario: 'Sem comentário', manual_nao_classificado: 'Humano/manual', ia_assistida: 'IA assistida', professor: 'Professor/especialista', fonte_oficial: 'Fonte oficial' },
  };
  return maps[kind]?.[key] || key.replaceAll('_', ' ') || 'Não informado';
}

function distributionBars(items, kind = '') {
  const entries = Object.entries(items || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0) || 1;
  if (!entries.length) return '<p class="muted">Sem dados.</p>';
  return `<div class="distribution-bars">${entries.map(([key, value]) => {
    const pct = Math.max(2, Number(value || 0) / total * 100);
    return `<div class="distribution-row"><span>${escapeHtml(intelligenceLabel(key, kind))}</span><div class="distribution-track"><i style="width:${pct.toFixed(1)}%"></i></div><strong>${formatNumber(value)}</strong></div>`;
  }).join('')}</div>`;
}

function renderBankIntelligence(summary = {}) {
  const total = Number(summary.total || 0);
  const awaitingReview = Number(summary.awaiting_review_completion || 0);
  const objectiveGaps = Number(summary.objective_curation_gaps || 0);
  const curationDetail = Number(summary.needs_review || 0)
    ? [awaitingReview ? `${formatNumber(awaitingReview)} aguardam conclusão humana` : '', objectiveGaps ? `${formatNumber(objectiveGaps)} com lacunas críticas` : ''].filter(Boolean).join(' · ')
    : 'nenhuma revisão pendente';
  const metrics = [
    ['Qualidade média', `${Number(summary.average_quality || 0).toFixed(1)}/100`, `${formatNumber(summary.ready || 0)} prontas`],
    ['Curadoria pendente', formatNumber(summary.needs_review || 0), curationDetail],
    ['Comentários', formatNumber(summary.with_commentary || 0), total ? `${Math.round(Number(summary.with_commentary || 0) / total * 100)}% do banco` : 'sem banco'],
    ['Duplicidade', formatNumber(summary.open_duplicate_candidates || 0), 'candidatos — não removidos automaticamente'],
  ];
  $('#curationMetrics').innerHTML = metrics.map(([label, value, detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
  const badge = $('#curationBadge');
  const pending = Number(summary.needs_review || 0) + Number(summary.open_duplicate_candidates || 0);
  if (badge) { badge.hidden = !pending; badge.textContent = pending > 999 ? '999+' : String(pending); }
  const insights = $('#curationInsights');
  if (insights) {
    const commentaryGap = Math.max(0, total - Number(summary.with_commentary || 0));
    const difficultyGap = Number((summary.difficulty || {}).sem_dados || 0);
    const readyPct = total ? Math.round(Number(summary.ready || 0) / total * 100) : 0;
    const actions = [
      {value: summary.needs_review || 0, label:'Revisar curadoria', detail: awaitingReview ? `${formatNumber(awaitingReview)} já podem ser concluídas com sua aprovação` : 'abra a fila e veja exatamente quais itens faltam em cada questão', kind:'curation'},
      {value: commentaryGap, label:'Adicionar comentários', detail:'o número cai assim que uma explicação é salva; a origem é normalizada automaticamente', kind:'comments'},
      {value: difficultyGap, label:'Coletar dificuldade real', detail:'este indicador depende de respostas reais; editar a questão não altera a dificuldade empírica', kind:'difficulty'},
      {value: summary.open_duplicate_candidates || 0, label:'Conferir duplicidades', detail:'candidatos aguardando uma decisão humana', kind:'duplicates'},
    ].filter(item => Number(item.value)>0).sort((a,b)=>Number(b.value)-Number(a.value));
    insights.innerHTML = `<div class="curation-insight-summary"><div><span>Banco pronto</span><strong>${readyPct}%</strong><small>${formatNumber(summary.ready || 0)} de ${formatNumber(total)} questões</small></div><p>${actions.length ? 'Os números abaixo são filas reais. Clique para ver os registros e o motivo de cada pendência.' : 'Nenhuma pendência editorial relevante detectada.'}</p></div>${actions.length ? `<div class="curation-insight-list">${actions.slice(0,4).map((item,index)=>`<button type="button" data-curation-kind="${escapeHtml(item.kind)}" data-curation-label="${escapeHtml(item.label)}"><b>${index+1}</b><span><strong>${formatNumber(item.value)} · ${escapeHtml(item.label)}</strong><small>${escapeHtml(item.detail)}</small></span><i>→</i></button>`).join('')}</div>` : ''}`;
    $$('[data-curation-kind]', insights).forEach(btn=>btn.addEventListener('click',()=>showCurationAttention(btn.dataset.curationKind, btn.dataset.curationLabel)));
  }
  const overview = $('#curationOverview');
  overview.innerHTML = `<div class="curation-distributions">
    <section><h3>Origem das questões</h3>${distributionBars(summary.origins, 'origin')}</section>
    <section><h3>Qualidade editorial</h3><p class="curation-chart-note">A nota A–D mede enriquecimento. Uma questão B pode estar Pronta após revisão humana.</p>${distributionBars(summary.quality_bands, '')}</section>
    <section><h3>Status de curadoria</h3><p class="curation-chart-note">Este é o indicador que mostra se sua revisão foi concluída.</p>${distributionBars(summary.curation, 'curation')}</section>
    <section><h3>Dificuldade empírica</h3>${distributionBars(summary.difficulty, 'difficulty')}</section>
    <section><h3>Origem dos comentários</h3>${distributionBars(summary.comments, 'commentary')}</section>
  </div>`;
}

async function refreshBankIntelligenceDerived() {
  const button = $('#refreshCuration');
  setBusy(button, true, 'Recalculando curadoria');
  try {
    const result = await bridge.call('refresh_bank_intelligence');
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível recalcular a curadoria.');
    renderBankIntelligence(result.summary || {});
    const changed = Number(result.updated || 0);
    const details = [
      Number(result.status_changes || 0) ? `${formatNumber(result.status_changes)} status` : '',
      Number(result.comment_changes || 0) ? `${formatNumber(result.comment_changes)} comentários` : '',
      Number(result.difficulty_changes || 0) ? `${formatNumber(result.difficulty_changes)} dificuldades` : '',
    ].filter(Boolean).join(' · ');
    toast(changed ? `Curadoria recalculada: ${formatNumber(changed)} questão(ões) atualizada(s)${details ? ` (${details})` : ''}.` : 'Curadoria conferida. Os indicadores já estavam atualizados.', 'success', 6500);
  } catch (error) {
    toast(error.message, 'error', 7000);
  } finally {
    setBusy(button, false);
    button.disabled = !state.selectedImportFiles.length;
  }
}

async function showCurationAttention(kind = 'curation', label = 'Fila de atenção') {
  const panel = $('#curationQueuePanel');
  const body = $('#curationQueueBody');
  const title = $('#curationQueueTitle');
  if (!panel || !body) return;
  panel.hidden = false;
  title.textContent = label || 'Fila de atenção';
  body.innerHTML = '<div class="skeleton" style="height:8rem"></div>';
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  try {
    const refreshed = await bridge.call('refresh_bank_intelligence');
    if (refreshed?.ok && refreshed.summary) renderBankIntelligence(refreshed.summary);
    const result = await bridge.call('get_curation_attention', kind, 150);
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível abrir a fila de atenção.');
    const items = Array.isArray(result.items) ? result.items : [];
    const total = Number(result.total || items.length);
    const note = kind === 'difficulty'
      ? 'Dificuldade empírica é calculada a partir das suas respostas. Ela não diminui ao editar metadados; use o estudo/simulado para gerar evidência real.'
      : kind === 'comments'
        ? 'Uma questão sai desta fila ao salvar uma explicação não vazia. Se a origem do comentário estiver como “Sem comentário”, o QuestFlow agora corrige automaticamente essa inconsistência.'
        : kind === 'curation'
          ? 'Qualidade e revisão humana agora são separadas: uma questão B com campos críticos íntegros pode sair da fila após sua aprovação explícita. Use “Concluir revisão” quando o botão aparecer.'
          : 'Duplicidades só saem da fila após sua decisão explícita.';
    body.innerHTML = `<div class="curation-queue-note"><strong>${formatNumber(total)} item(ns) na fila</strong><span>${escapeHtml(note)}</span></div>${items.length ? `<div class="curation-queue-list">${items.map(item=>{
      const canComplete = kind === 'curation' && item.can_complete_review && !item.human_approved;
      const statusHint = canComplete ? '<div class="curation-ready-review">✓ Campos críticos íntegros · falta apenas concluir a revisão humana</div>' : '';
      const issueList = (item.missing||[]).slice(0,6).map(text=>{
        const issue = String(text || '').trim();
        return curationIssueIsNavigable(issue)
          ? `<li><button type="button" class="curation-queue-issue-link" data-open-curation-issue="${escapeHtml(item.uid)}" data-curation-issue="${escapeHtml(issue)}"><span>${escapeHtml(issue)}</span><b>Ir ao campo →</b></button></li>`
          : `<li>${escapeHtml(issue)}</li>`;
      }).join('');
      return `<article><div><strong>${escapeHtml(item.code || 'Sem código')}</strong><span>${escapeHtml([item.subject,item.topic].filter(Boolean).join(' · ') || 'Classificação não informada')}</span></div><div class="curation-queue-score"><b>${Number(item.score || 0).toFixed(kind==='duplicates'?1:0)}${kind==='duplicates'?'%':'/100'}</b>${item.grade?`<small>Nota ${escapeHtml(item.grade)}</small>`:''}</div>${statusHint}<ul>${issueList}</ul><div class="curation-queue-actions">${canComplete ? `<button type="button" class="button button--small button--success" data-complete-curation-review="${escapeHtml(item.uid)}">Concluir revisão</button>` : ''}<button type="button" class="button button--small button--secondary" data-open-curation-question="${escapeHtml(item.uid)}">Abrir questão</button></div></article>`;
    }).join('')}</div>` : '<p class="curation-ok">Nenhum item permanece nesta fila.</p>'}`;
    $$('[data-complete-curation-review]', body).forEach(btn=>btn.addEventListener('click', async()=>{
      const uid=btn.dataset.completeCurationReview;
      if (!window.confirm('Concluir sua revisão desta questão e retirá-la da fila de Curadoria? A nota editorial continuará mostrando eventuais enriquecimentos opcionais.')) return;
      setBusy(btn, true, 'Concluindo revisão');
      try {
        const completed = await bridge.call('complete_curation_review', uid, 'Revisão humana pela Curadoria');
        if (!completed?.ok) throw new Error(completed?.error || 'Não foi possível concluir a revisão.');
        toast('Revisão concluída. A questão saiu da fila de Curadoria.', 'success');
        if (completed.summary) renderBankIntelligence(completed.summary);
        await showCurationAttention(kind, label);
      } catch (error) { toast(error.message, 'error', 7000); }
      finally { setBusy(btn, false); }
    }));
    $$('[data-open-curation-issue]', body).forEach(btn=>btn.addEventListener('click', async()=>{
      await openCurationIssueForQuestion(btn.dataset.openCurationIssue, btn.dataset.curationIssue || '');
    }));
    $$('[data-open-curation-question]', body).forEach(btn=>btn.addEventListener('click', async()=>{
      const uid=btn.dataset.openCurationQuestion;
      state.curationReviewContext = true;
      await navigate('review');
      await selectQuestion(uid);
      applyCurationReviewActionState();
    }));
  } catch (error) {
    body.innerHTML = emptyStateHtml({title:'Fila indisponível',text:error.message});
  }
}

async function loadBankIntelligence() {
  const metrics = $('#curationMetrics');
  const overview = $('#curationOverview');
  if (metrics) renderSkeletonCards(metrics);
  if (overview) overview.innerHTML = '<div class="skeleton" style="height:16rem"></div>';
  try {
    const result = await bridge.call('get_bank_intelligence');
    if (!result.ok) throw new Error(result.error || 'Não foi possível ler a curadoria do banco.');
    renderBankIntelligence(result.summary || {});
  } catch (error) {
    if (overview) overview.innerHTML = emptyStateHtml({ title: 'Curadoria indisponível', text: error.message });
    toast(error.message, 'error');
  }
}

function renderSemanticIndex(summary = {}) {
  const target = $('#semanticIndexOverview');
  if (!target) return;
  const coverage = Number(summary.coverage ?? 0);
  target.innerHTML = `<div class="semantic-index-summary">
    <div class="semantic-index-metrics">
      <div><span>Cobertura</span><strong>${coverage.toFixed(1)}%</strong><small>${formatNumber(summary.indexed_questions || 0)} / ${formatNumber(summary.total_questions || summary.indexed_questions || 0)} questões</small></div>
      <div><span>Chunks RAG</span><strong>${formatNumber(summary.rag_chunks || 0)}</strong><small>enunciados e comentários pesquisáveis</small></div>
      <div><span>Nós de conhecimento</span><strong>${formatNumber(summary.knowledge_nodes || 0)}</strong><small>${formatNumber(summary.knowledge_edges || 0)} relações</small></div>
      <div><span>Motor</span><strong>${escapeHtml(summary.version || 'qf-semantic')}</strong><small>${summary.offline_ready ? 'offline-first' : 'requer conectividade'}</small></div>
    </div>
    <div class="semantic-engine-note"><strong>Como ranqueia:</strong> busca lexical + vetor semântico local + metadados/taxonomia. A arquitetura permite substituir o vetor local por embeddings externos posteriormente, sem migrar o banco novamente.</div>
  </div>`;
}

async function loadSemanticIndex() {
  const target = $('#semanticIndexOverview');
  if (target) target.innerHTML = '<div class="skeleton" style="height:8rem"></div>';
  try {
    const result = await bridge.call('get_semantic_index_summary');
    if (!result.ok) throw new Error(result.error || 'Não foi possível ler o índice semântico.');
    renderSemanticIndex(result.summary || {});
  } catch (error) {
    if (target) target.innerHTML = emptyStateHtml({ title: 'Índice indisponível', text: error.message, compact: true });
  }
}

async function rebuildSemanticIndex() {
  const button = $('#rebuildSemanticIndex');
  setBusy(button, true, 'Reindexando conhecimento');
  try {
    const started = await bridge.call('start_semantic_rebuild');
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a reindexação.');
    const result = await monitorTask(started.task_id, (task) => {
      if (task.message) button.title = task.message;
    }, { timeoutMs: 600000, intervalMs: 650 });
    renderSemanticIndex(result || {});
    toast('Índice híbrido, grafo e contexto RAG reconstruídos.', 'success');
  } catch (error) { toast(error.message, 'error', 7000); }
  finally { setBusy(button, false); }
}

async function rebuildLearnerModel() {
  const button = $('#rebuildLearnerModel');
  setBusy(button, true, 'Reconstruindo modelo');
  try {
    const started = await bridge.call('start_learner_model_rebuild');
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a reconstrução do modelo do aluno.');
    await monitorTask(started.task_id, (task) => { if (task.message && button) button.title = task.message; }, { timeoutMs: 600000, intervalMs: 500 });
    toast('Modelo do aluno reconstruído a partir do histórico real de respostas.', 'success');
    await loadDashboard({ force: true });
  } catch (error) { toast(error.message, 'error', 8000); }
  finally { setBusy(button, false); }
}

function tutorTextHtml(value) {
  let html = escapeHtml(String(value || ''));
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  return html.replace(/\n/g, '<br>');
}

function renderEngineArchitecture(architecture = {}) {
  const target = $('#engineArchitecture');
  if (!target) return;
  const domain = architecture.domain_engines || architecture;
  const engines = Array.isArray(domain.engines) ? domain.engines : [];
  if (!engines.length) {
    target.innerHTML = emptyStateHtml({ title: 'Arquitetura indisponível', text: 'Os motores ainda não responderam.', compact: true });
    return;
  }
  const metricText = (metrics = {}) => Object.entries(metrics).slice(0, 3).map(([key, value]) => `${key.replaceAll('_',' ')}: ${value}`).join(' · ');
  target.innerHTML = `<div class="engine-grid">${engines.map((engine, index) => `<article class="engine-card ${engine.status === 'ready' ? 'is-ready' : 'is-degraded'}">
    <div class="engine-card-head"><span>${index + 1}</span><div><strong>${escapeHtml(engine.name || engine.id)}</strong><small>${escapeHtml(engine.version || '')}</small></div><b>${engine.status === 'ready' ? '✓' : '!'}</b></div>
    <p>${escapeHtml(metricText(engine.metrics || {}) || 'Motor encapsulado e disponível pela API interna.')}</p>
  </article>`).join('')}</div>`;
  const moduleCount = Number(architecture.modules?.module_count || engines.length);
  target.innerHTML += `<div class="architecture-note"><strong>${moduleCount} módulos registrados · registro extensível</strong><span>${domain.all_ready ? 'Motores históricos operacionais.' : 'Há módulo em estado degradado.'}</span><small>${escapeHtml((domain.principles || architecture.principles || []).join(' • '))}</small></div>`;
}

function renderTutorGovernance(summary = {}) {
  const target = $('#tutorGovernanceMetrics');
  if (!target) return;
  const metrics = [
    ['Interações IA', summary.interactions || 0, 'todas auditadas'],
    ['Rascunhos', summary.drafts || 0, 'aguardando decisão humana'],
    ['Aprovadas', summary.approved || 0, 'revisadas explicitamente'],
    ['Avaliação média', `${Number(summary.average_evaluation || 0).toFixed(1)}/100`, `${formatNumber(summary.diagnoses || 0)} diagnósticos`],
  ];
  target.innerHTML = metrics.map(([label, value, detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
  const badge = $('#tutorDraftBadge');
  if (badge) { badge.textContent = String(summary.drafts || 0); badge.hidden = !Number(summary.drafts || 0); }
}

function tutorCompactText(value, limit = 96) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, Math.max(1, limit - 1)).trimEnd()}…` : text;
}

function tutorLooksLikeUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || '').trim());
}

function tutorCandidateCode(item = {}) {
  const raw = String(item.code || item.source_code || item.codigo || item.codigo_origem || '').trim();
  return raw && !tutorLooksLikeUuid(raw) ? raw : 'Questão sem código visível';
}

function tutorCandidateLabel(item = {}) {
  const code = tutorCandidateCode(item);
  const subject = tutorCompactText(item.subject || item.materia || '', 42) || 'Matéria não informada';
  const topic = tutorCompactText(item.topic || item.primary_topic || item.assunto || item.lesson || item.aula_planilha || '', 58) || 'Assunto não informado';
  const statement = tutorCompactText(item.statement || item.enunciado || '', 92);
  return `${code} — ${subject} — ${topic}${statement ? ` — ${statement}` : ''}`;
}

function tutorCandidateSearchText(item = {}) {
  return [
    tutorCandidateCode(item), item.subject, item.materia, item.topic, item.primary_topic,
    item.assunto, item.lesson, item.aula_planilha, item.statement, item.enunciado,
  ].filter(Boolean).join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
}

function renderTutorQuestionOptions(candidates = [], selectedUid = '', query = '') {
  const selector = $('#tutorQuestionSelect');
  if (!selector) return;
  const normalizedQuery = String(query || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLocaleLowerCase('pt-BR');
  const all = Array.isArray(candidates) ? candidates : [];
  let visible = normalizedQuery ? all.filter((item) => tutorCandidateSearchText(item).includes(normalizedQuery)) : all;
  const selected = all.find((item) => String(item.uid || '') === String(selectedUid || ''));
  if (selected && !visible.some((item) => String(item.uid || '') === String(selectedUid || ''))) visible = [selected, ...visible];
  selector.innerHTML = `<option value="">Selecione uma questão pelo conteúdo…</option>${visible.map((item) => `<option value="${escapeHtml(item.uid || '')}">${escapeHtml(tutorCandidateLabel(item))}</option>`).join('')}`;
  selector.value = selectedUid || '';
  const help = $('#tutorQuestionChoiceHelp');
  if (help) {
    if (normalizedQuery) help.textContent = `${formatNumber(visible.length - (selected && !tutorCandidateSearchText(selected).includes(normalizedQuery) ? 1 : 0))} resultado(s) encontrado(s). Selecione a questão que corresponde ao conteúdo que você quer entender.`;
    else help.textContent = `${formatNumber(all.length)} questão(ões) disponíveis. As opções mostram código, matéria, assunto/aula e o começo do enunciado.`;
  }
}

function renderTutorWorkspace(workspace = {}) {
  const recentTarget = $('#tutorRecentErrors');
  const treatedTarget = $('#tutorTreatedErrors');
  const recent = Array.isArray(workspace.error_review_queue) ? workspace.error_review_queue : (Array.isArray(workspace.recent_errors) ? workspace.recent_errors : []);
  const treated = Array.isArray(workspace.treated_errors) ? workspace.treated_errors : [];
  const selectedUid = String(state.tutorSelectedUid || workspace.selected?.uid || '');
  if (recentTarget) {
    recentTarget.innerHTML = recent.length ? recent.map((item) => `<button type="button" class="tutor-error-item${String(item.question_uid) === selectedUid ? ' is-active' : ''}" data-tutor-question="${escapeHtml(item.question_uid)}">
      <strong>${escapeHtml(textOrMissing(item.source_code, 'Sem código'))}</strong><span>${escapeHtml(textOrMissing(item.subject, 'Matéria não informada'))}</span><small>${escapeHtml(textOrMissing(item.primary_topic, 'Sem assunto'))} · erro em ${escapeHtml(formatDate(item.answered_at))}</small>
    </button>`).join('') : emptyStateHtml({ title: 'Nenhum erro aguardando revisão', text: 'Os erros tratados saem desta fila após a aprovação da orientação. Um novo erro na mesma questão faz ela voltar automaticamente.', compact: true });
    $$('[data-tutor-question]', recentTarget).forEach((button) => button.addEventListener('click', () => loadTutorPage(button.dataset.tutorQuestion || '')));
  }
  if (treatedTarget) {
    treatedTarget.innerHTML = treated.length ? treated.map((item) => `<button type="button" class="tutor-error-item tutor-error-item--treated${String(item.question_uid) === selectedUid ? ' is-active' : ''}" data-tutor-treated-question="${escapeHtml(item.question_uid)}">
      <strong>${escapeHtml(textOrMissing(item.source_code, 'Sem código'))}</strong><span>${escapeHtml(textOrMissing(item.subject, 'Matéria não informada'))}</span><small>${escapeHtml(textOrMissing(item.primary_topic, 'Sem assunto'))} · tratado em ${escapeHtml(formatDate(item.treated_at))}</small>
    </button>`).join('') : emptyStateHtml({ title: 'Nenhum erro tratado ainda', text: 'Quando uma orientação for aprovada, a questão aparecerá aqui e sairá da fila de revisão.', compact: true });
    $$('[data-tutor-treated-question]', treatedTarget).forEach((button) => button.addEventListener('click', () => loadTutorPage(button.dataset.tutorTreatedQuestion || '')));
  }

  renderTutorGovernance(workspace.governance || {});
  const selector = $('#tutorQuestionSelect');
  const search = $('#tutorQuestionSearch');
  const candidates = Array.isArray(workspace.candidates) ? workspace.candidates : [];
  state.tutorCandidates = candidates;
  if (selector) {
    renderTutorQuestionOptions(candidates, workspace.selected?.uid || '', search?.value || '');
    selector.onchange = () => {
      if (!selector.value) return;
      if (search) search.value = '';
      loadTutorPage(selector.value);
    };
  }
  if (search) {
    search.oninput = () => renderTutorQuestionOptions(state.tutorCandidates, state.tutorSelectedUid || workspace.selected?.uid || '', search.value || '');
  }
  const selected = workspace.selected;
  state.tutorSelectedUid = selected?.uid || null;
  const generate = $('#generateTutorAnswer');
  const refreshDiagnosis = $('#refreshTutorDiagnosis');
  if (generate) { generate.disabled = !selected; generate.title = selected ? 'Gerar orientação com o contexto atual' : 'Selecione uma questão acima para habilitar'; }
  if (refreshDiagnosis) { refreshDiagnosis.disabled = !selected; refreshDiagnosis.title = selected ? 'Recalcular a hipótese diagnóstica' : 'Selecione uma questão acima para habilitar'; }
  $$('[data-tutor-quick-prompt]').forEach((button) => { button.disabled = !selected; });
  const meta = $('#tutorSelectedMeta');
  const questionTarget = $('#tutorSelectedQuestion');
  const diagnosisTarget = $('#tutorDiagnosis');
  if (!selected) {
    if (meta) meta.textContent = 'Selecione uma questão com histórico de resposta.';
    if (questionTarget) questionTarget.innerHTML = emptyStateHtml({ title: 'Aguardando questão', text: 'Escolha um erro recente ou abra uma questão pelo editor.', compact: true });
    if (diagnosisTarget) diagnosisTarget.innerHTML = '';
    return;
  }
  if (meta) meta.textContent = `${selected.code || 'Questão'} · ${selected.subject || 'Matéria não informada'} · ${selected.topic || 'Sem assunto'}`;
  const support = selected.scaffolding || selected.learner?.scaffolding || {};
  if (questionTarget) questionTarget.innerHTML = `<div class="tutor-question-head"><span>${escapeHtml(selected.code || 'Questão')}</span><strong>${escapeHtml(selected.topic || selected.subject || 'Questão selecionada')}</strong></div><p>${escapeHtml(selected.statement || '')}</p>
    ${selected.image?.src ? `<div class="tutor-multimodal-preview"><img src="${selected.image.src}" alt="Imagem associada à questão"><div><strong>Fonte visual local</strong><small>A imagem permanece neste computador e pode ser usada na representação Visual do scaffolding.</small><small>${escapeHtml(selected.image?.name || '')}</small></div></div>` : ''}
    <div class="tutor-support-signal"><span>Histórico de pistas: ${Number(support.sessions || 0)}</span><span>Independência: ${Math.round(Number(support.independence_score ?? 1)*100)}%</span>${support.last_level != null ? `<span>Último nível: ${Number(support.last_level)}/5</span>` : ''}</div>`;
  state.tutorScaffoldSessionId = null; state.tutorScaffoldLevel = null;
  const scaffoldStatus = $('#tutorScaffoldStatus'); if (scaffoldStatus) scaffoldStatus.innerHTML = '';
  renderTutorDiagnosis(selected.diagnosis || {});
  updateTutorModeUi();
  const latestInteraction = workspace.latest_interaction && String(workspace.latest_interaction.question_uid || '') === String(selected.uid || '') ? workspace.latest_interaction : null;
  const answerTarget = $('#tutorAnswer');
  if (latestInteraction) renderTutorAnswer(tutorInteractionAsResult(latestInteraction));
  else if (answerTarget) { answerTarget.innerHTML = ''; state.tutorInteractionId = null; }
  loadTutorPrivacyPreview().catch(()=>{});
}

function renderTutorDiagnosis(diagnosis = {}) {
  const target = $('#tutorDiagnosis');
  if (!target) return;
  const signals = Array.isArray(diagnosis.signals) ? diagnosis.signals : [];
  target.innerHTML = `<article class="diagnosis-card"><div class="diagnosis-head"><span>Diagnóstico provável do erro</span><strong>${escapeHtml(textOrMissing(diagnosis.label, 'Indeterminado'))}</strong><b>${Math.round(Number(diagnosis.confidence || 0) * 100)}% confiança</b></div>
    <p>${escapeHtml(diagnosis.explanation || 'O diagnóstico é uma hipótese pedagógica baseada nos sinais disponíveis.')}</p>
    ${signals.length ? `<ul>${signals.slice(0,6).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
    <div class="diagnosis-intervention"><strong>Intervenção recomendada</strong><span>${escapeHtml(diagnosis.intervention || 'Colete mais evidências na próxima tentativa.')}</span></div>
  </article>`;
}


function stage4Pct(value, digits = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(digits)}%` : '—';
}

function stage4UrgencyLabel(bucket) {
  const value = Number(bucket);
  if (value === 0) return 'Revisão marcada';
  if (value === 1) return 'Recuperar agora';
  if (value === 2) return 'Revisar agora';
  if (value === 3) return 'Conteúdo novo';
  if (value === 4) return 'Antecipar revisão';
  return 'Prioridade calculada';
}

function stage4ComponentLabel(key) {
  const labels = {
    mastery_gap: 'Domínio', forgetting_risk: 'Memória', coverage_gap: 'Cobertura',
    board_incidence: 'Banca', irt_information: 'Valor diagnóstico', exam_urgency: 'Urgência',
    uncertainty: 'Incerteza', recency: 'Recência',
  };
  return labels[key] || String(key || '').replaceAll('_', ' ');
}

function renderRecommendationDashboard(data = {}) {
  const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
  const projections = Array.isArray(data.projections) ? data.projections : [];
  const boards = Array.isArray(data.board_incidence) ? data.board_incidence : [];
  const overall = data.overall_projection || {};
  const urgent = recommendations.filter((item) => Number(item.bucket) <= 2).length;
  const metrics = $('#recommendationMetrics');
  if (metrics) {
    const estimate = overall.estimate == null ? '—' : stage4Pct(overall.estimate);
    const interval = overall.low == null || overall.high == null ? 'Sem intervalo ainda' : `${stage4Pct(overall.low)}–${stage4Pct(overall.high)}`;
    metrics.innerHTML = [
      ['Projeção de acerto', estimate, interval],
      ['Ações priorizadas', formatNumber(recommendations.length), `${urgent} pedem revisão primeiro`],
      ['Matérias modeladas', formatNumber(projections.length), 'domínio + histórico real'],
      ['Bancas observadas', formatNumber(boards.length), data.active_simulation ? 'simulado em andamento' : 'distribuição do banco local'],
    ].map(([label, value, detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
  }

  const list = $('#recommendationList');
  if (list) {
    list.innerHTML = recommendations.length ? `<div class="stage4-recommendation-list">${recommendations.map((item, index) => {
      const components = Object.entries(item.components || {}).sort((a,b) => Number(b[1] || 0) - Number(a[1] || 0)).slice(0, 6);
      const reasons = Array.isArray(item.reasons) ? item.reasons.slice(0, 3) : [];
      return `<article class="stage4-recommendation-card" data-recommend-uid="${escapeHtml(item.uid)}">
        <div class="stage4-recommendation-rank"><span>${index + 1}</span><strong>${Number(item.score || 0).toFixed(0)}</strong><small>/100</small></div>
        <div class="stage4-recommendation-main">
          <div class="stage4-recommendation-head"><div><strong>${escapeHtml(textOrMissing(item.code, 'Questão'))}</strong><span>${escapeHtml(textOrMissing(item.subject, 'Matéria não informada'))} · ${escapeHtml(textOrMissing(item.topic, 'Sem assunto'))}</span></div><span class="status-pill" title="Classe interna de urgência ${escapeHtml(String(item.bucket ?? '—'))}">${escapeHtml(stage4UrgencyLabel(item.bucket))}</span></div>
          <p>${escapeHtml(String(item.statement || '').slice(0, 210))}${String(item.statement || '').length > 210 ? '…' : ''}</p>
          ${reasons.length ? `<div class="stage4-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
          <div class="stage4-components">${components.map(([key, value]) => `<div title="${escapeHtml(stage4ComponentLabel(key))}: ${Number(value || 0).toFixed(2)}"><span>${escapeHtml(stage4ComponentLabel(key))}</span><div><i style="width:${Math.max(0, Math.min(100, Number(value || 0) * 4))}%"></i></div></div>`).join('')}</div>
        </div>
      </article>`;
    }).join('')}</div>` : emptyStateHtml({ title: 'Sem recomendações elegíveis', text: 'Revise filtros, conteúdo estudado ou aprove questões no banco.', compact: true });
    $$('[data-recommend-uid]', list).forEach((card) => card.addEventListener('click', async () => {
      const uid = card.dataset.recommendUid;
      if (!uid) return;
      await navigate('review');
      await selectQuestion(uid);
    }));
  }

  const projectionTarget = $('#projectionTable');
  if (projectionTarget) {
    projectionTarget.innerHTML = projections.length ? `<div class="stage4-projection-list">${projections.map((item) => {
      const p = item.projection || {};
      return `<article><div><strong>${escapeHtml(item.subject)}</strong><small>${formatNumber(item.attempts)} tentativas · ${formatNumber(item.question_count)} questões</small></div><div class="stage4-projection-value"><strong>${stage4Pct(p.estimate)}</strong><small>${stage4Pct(p.low)}–${stage4Pct(p.high)}</small></div></article>`;
    }).join('')}</div><p class="field-help">Intervalos incorporam tamanho da amostra e sinais do modelo do aluno. Não representam chance de aprovação.</p>` : emptyStateHtml({ title: 'Sem projeções', text: 'As projeções surgem conforme o banco e o histórico acumulam evidências.', compact: true });
  }

  const boardTarget = $('#boardIncidence');
  if (boardTarget) {
    const maxShare = Math.max(...boards.map((item) => Number(item.share || 0)), 0.01);
    boardTarget.innerHTML = boards.length ? `<div class="stage4-board-list">${boards.map((item) => `<div class="stage4-board-row"><span>${escapeHtml(item.board)}</span><div><i style="width:${Math.max(2, Number(item.share || 0) / maxShare * 100)}%"></i></div><strong>${stage4Pct(item.share, 1)}</strong><small>${formatNumber(item.questions)}</small></div>`).join('')}</div>` : emptyStateHtml({ title: 'Sem banca cadastrada', text: 'Preencha a banca nas questões para habilitar este sinal.', compact: true });
  }

  const subjectSelect = $('#simulationSubject');
  if (subjectSelect) {
    const previous = subjectSelect.value;
    subjectSelect.innerHTML = '<option value="">Todas as matérias estudadas</option>' + projections.map((item) => `<option value="${escapeHtml(item.subject)}">${escapeHtml(item.subject)}</option>`).join('');
    if ([...subjectSelect.options].some((option) => option.value === previous)) subjectSelect.value = previous;
  }
  const boardSelect = $('#simulationBoard');
  if (boardSelect) {
    const previous = boardSelect.value;
    boardSelect.innerHTML = '<option value="">Todas as bancas</option>' + boards.filter((item) => item.board !== 'Não informada').map((item) => `<option value="${escapeHtml(item.board)}">${escapeHtml(item.board)}</option>`).join('');
    if ([...boardSelect.options].some((option) => option.value === previous)) boardSelect.value = previous;
  }
  const resume = $('#resumeAdaptiveSimulation');
  if (resume) {
    const active = data.active_simulation || null;
    resume.hidden = !active;
    resume.dataset.sessionId = active?.id || '';
    if (active) resume.textContent = `Retomar ${active.answered_count || 0}/${active.target_count || 0}`;
  }
}

async function loadRecommendationPage() {
  const metrics = $('#recommendationMetrics');
  const list = $('#recommendationList');
  if (metrics) metrics.innerHTML = Array.from({length:4}, () => '<article class="metric-card"><div class="skeleton" style="height:3.8rem"></div></article>').join('');
  if (list) list.innerHTML = '<div class="skeleton" style="height:12rem"></div>';
  try {
    const mode = $('#recommendationMode')?.value || 'equilibrado';
    const result = await bridge.call('get_recommendation_dashboard', mode);
    if (!result.ok) throw new Error(result.error || 'Não foi possível calcular as recomendações.');
    renderRecommendationDashboard(result.dashboard || result.data || result);
    const activeId = state.adaptiveSimulationId || result.dashboard?.active_simulation?.id || result.active_simulation?.id;
    if (activeId) await resumeAdaptiveSimulation(activeId, { quiet: true });
  } catch (error) {
    if (list) list.innerHTML = emptyStateHtml({ title: 'Recomendador indisponível', text: error.message, compact: true });
    toast(error.message, 'error', 7000);
  }
}

async function startAdaptiveSimulation() {
  const button = $('#startAdaptiveSimulation');
  setBusy(button, true, 'Iniciando simulado');
  try {
    const subject = $('#simulationSubject')?.value || '';
    const payload = {
      mode: $('#simulationMode')?.value || 'equilibrado',
      target_count: Number($('#simulationCount')?.value || 10),
      subjects: subject ? [subject] : [],
      board: $('#simulationBoard')?.value || '',
    };
    const result = await bridge.call('start_adaptive_simulation', payload);
    if (!result.ok) throw new Error(result.error || 'Não foi possível iniciar o simulado.');
    const simulation = result.simulation || result.data || result;
    state.adaptiveSimulationId = simulation.session?.id || null;
    state.adaptiveSimulationQuestionUid = null;
    renderAdaptiveSimulation(simulation);
    toast('Simulado adaptativo iniciado. A próxima questão será escolhida após cada resposta.', 'success');
    await loadRecommendationPage();
  } catch (error) { toast(error.message, 'error', 7000); }
  finally { setBusy(button, false); }
}

async function resumeAdaptiveSimulation(sessionId = '', { quiet = false } = {}) {
  const id = String(sessionId || $('#resumeAdaptiveSimulation')?.dataset.sessionId || state.adaptiveSimulationId || '').trim();
  if (!id) return;
  try {
    const result = await bridge.call('get_adaptive_simulation', id);
    if (!result.ok) throw new Error(result.error || 'Não foi possível retomar o simulado.');
    const simulation = result.simulation || result.data || result;
    state.adaptiveSimulationId = simulation.session?.id || id;
    renderAdaptiveSimulation(simulation);
  } catch (error) { if (!quiet) toast(error.message, 'error', 6500); }
}

function renderAdaptiveSimulation(simulation = {}, feedback = null) {
  const target = $('#simulationWorkspace');
  const statusText = $('#simulationStatusText');
  const abandon = $('#abandonAdaptiveSimulation');
  if (!target) return;
  const session = simulation.session || {};
  const current = simulation.current || null;
  const actualFeedback = feedback || simulation.feedback || null;
  const answered = Number(session.answered_count || 0);
  const targetCount = Number(session.target_count || 0);
  const status = String(session.status || '');
  const isEvidencePractice = String(session.config?.purpose || '') === 'coleta_evidencia';
  if (statusText) statusText.textContent = targetCount ? `${isEvidencePractice ? 'Coleta de evidência' : 'Simulado'} · ${answered}/${targetCount} respondidas · ${session.accuracy == null ? 'sem acurácia ainda' : `${stage4Pct(session.accuracy)} de acerto`} · modo ${session.mode || 'equilibrado'}` : 'Nenhuma sessão ativa.';
  if (abandon) abandon.hidden = status !== 'em_andamento';

  const feedbackHtml = actualFeedback ? `<div class="sim-feedback ${actualFeedback.is_correct ? 'is-correct' : 'is-wrong'}"><strong>${actualFeedback.is_correct ? '✓ Resposta correta' : '✕ Resposta incorreta'}</strong><span>${actualFeedback.is_correct ? 'Os modelos FSRS, KT e IRT foram atualizados antes da escolha da próxima questão.' : `Gabarito: ${escapeHtml(textOrMissing(actualFeedback.answer, String.fromCharCode(65 + Number(actualFeedback.correct_index || 0))))}`}</span>${actualFeedback.explanation ? `<p>${escapeHtml(actualFeedback.explanation)}</p>` : ''}</div>` : '';

  if (status !== 'em_andamento' || !current) {
    state.adaptiveSimulationQuestionUid = null;
    const label = status === 'concluido' ? (isEvidencePractice ? 'Coleta diagnóstica concluída' : 'Simulado concluído') : status === 'abandonado' ? (isEvidencePractice ? 'Coleta diagnóstica encerrada' : 'Simulado encerrado') : 'Sem outras questões elegíveis';
    const evidenceDone = isEvidencePractice && Boolean(simulation.evidence_complete);
    const conclusion = evidenceDone ? 'O modelo já possui evidência suficiente para deixar de se abster neste conceito. Atualize o Painel visual para ver a nova estimativa.' : 'O histórico desta sessão já alimentou FSRS, Knowledge Tracing e IRT.';
    target.innerHTML = `${feedbackHtml}<div class="adaptive-sim-summary"><span>✓</span><h3>${escapeHtml(label)}</h3><strong>${answered}/${targetCount || answered} questões · ${session.accuracy == null ? '—' : stage4Pct(session.accuracy)} de acerto</strong><p>${escapeHtml(conclusion)}</p><button type="button" class="button button--primary" id="newAdaptiveSimulation">${isEvidencePractice ? 'Voltar ao recomendador' : 'Criar novo simulado'}</button></div>`;
    $('#newAdaptiveSimulation')?.addEventListener('click', () => { state.adaptiveSimulationId = null; target.innerHTML = emptyStateHtml({title:'Pronto para começar', text:'Configure um novo objetivo acima.', compact:true}); $('#startAdaptiveSimulation')?.focus(); });
    return;
  }

  if (String(current.uid) !== String(state.adaptiveSimulationQuestionUid || '')) {
    state.adaptiveSimulationQuestionUid = current.uid;
    state.adaptiveSimulationStartedAt = Date.now();
  }
  const recommendation = current.recommendation || {};
  const reasons = Array.isArray(recommendation.reasons) ? recommendation.reasons.slice(0,3) : [];
  target.innerHTML = `${feedbackHtml}<article class="adaptive-sim-question">
    <div class="adaptive-sim-progress"><div><i style="width:${Math.max(0, Math.min(100, Number(session.progress || 0) * 100))}%"></i></div><span>${answered + 1} de ${targetCount}</span></div>
    <div class="adaptive-sim-meta"><span>${escapeHtml(textOrMissing(current.code, 'Questão'))}</span><strong>${escapeHtml(textOrMissing(current.subject, 'Matéria não informada'))}</strong><small>${escapeHtml(textOrMissing(current.topic, 'Sem assunto'))}${current.board ? ` · ${escapeHtml(current.board)}` : ''}</small><b>Prioridade ${Number(recommendation.score || 0).toFixed(0)}/100</b></div>
    ${reasons.length ? `<div class="stage4-reasons">${reasons.map((reason) => `<span>${escapeHtml(reason)}</span>`).join('')}</div>` : ''}
    <p class="adaptive-sim-statement">${escapeHtml(current.statement || '')}</p>
    <fieldset class="adaptive-sim-alternatives"><legend>Escolha uma alternativa</legend>${(current.alternatives || []).map((alt) => `<label><input type="radio" name="adaptiveSimAlternative" value="${Number(alt.index)}"><strong>${escapeHtml(alt.key || String.fromCharCode(65 + Number(alt.index)))}</strong><span>${escapeHtml(alt.text || '')}</span></label>`).join('')}</fieldset>
    <div class="adaptive-sim-signals"><label><span>Confiança</span><select id="adaptiveConfidence"><option value="">Não informar</option><option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option></select></label><label><span>Dificuldade percebida</span><select id="adaptiveDifficulty"><option value="">Não informar</option><option value="facil">Fácil</option><option value="media">Média</option><option value="dificil">Difícil</option></select></label><label class="adaptive-gap"><input type="checkbox" id="adaptiveLearningGap"><span>Falta estudar este conteúdo</span></label></div>
    <button type="button" class="button button--primary" id="submitAdaptiveAnswer">${isEvidencePractice ? 'Responder e atualizar evidência' : 'Responder e adaptar próxima questão'}</button>
  </article>`;
  $('#submitAdaptiveAnswer')?.addEventListener('click', submitAdaptiveSimulationAnswer);
}

async function submitAdaptiveSimulationAnswer() {
  const selected = $('input[name="adaptiveSimAlternative"]:checked');
  if (!selected) { toast('Selecione uma alternativa antes de responder.', 'warning'); return; }
  const button = $('#submitAdaptiveAnswer');
  setBusy(button, true, 'Atualizando modelos e escolhendo a próxima questão');
  try {
    const seconds = state.adaptiveSimulationStartedAt ? Math.max(1, (Date.now() - state.adaptiveSimulationStartedAt) / 1000) : null;
    const result = await bridge.call(
      'submit_adaptive_simulation_answer', state.adaptiveSimulationId, Number(selected.value), seconds,
      $('#adaptiveConfidence')?.value || '', $('#adaptiveDifficulty')?.value || '', Boolean($('#adaptiveLearningGap')?.checked)
    );
    if (!result.ok) throw new Error(result.error || 'Não foi possível registrar a resposta.');
    const simulation = result.simulation || result.data || result;
    state.adaptiveSimulationId = simulation.session?.id || state.adaptiveSimulationId;
    state.adaptiveSimulationQuestionUid = null;
    renderAdaptiveSimulation(simulation, simulation.feedback || null);
    const dash = await bridge.call('get_recommendation_dashboard', $('#recommendationMode')?.value || 'equilibrado');
    if (dash.ok) renderRecommendationDashboard(dash.dashboard || dash.data || dash);
  } catch (error) { toast(error.message, 'error', 7000); setBusy(button, false); }
}

async function abandonAdaptiveSimulation() {
  if (!state.adaptiveSimulationId) return;
  if (!window.confirm('Encerrar este simulado? As respostas já registradas permanecem no seu histórico de aprendizagem.')) return;
  try {
    const result = await bridge.call('abandon_adaptive_simulation', state.adaptiveSimulationId);
    if (!result.ok) throw new Error(result.error || 'Não foi possível encerrar o simulado.');
    const simulation = result.simulation || result.data || result;
    renderAdaptiveSimulation(simulation);
    state.adaptiveSimulationId = null;
    await loadRecommendationPage();
  } catch (error) { toast(error.message, 'error', 6500); }
}

async function loadAiAudit() {
  const target = $('#aiAuditTable');
  if (!target) return;
  target.innerHTML = '<div class="skeleton" style="height:6rem"></div>';
  try {
    const result = await bridge.call('get_ai_audit', 30);
    if (!result.ok) throw new Error(result.error || 'Não foi possível carregar a auditoria de IA.');
    renderTutorGovernance(result.summary || {});
    const items = Array.isArray(result.items) ? result.items : [];
    target.innerHTML = items.length ? `<div class="ai-audit-list">${items.map((item) => `<article class="ai-audit-row" data-ai-interaction="${escapeHtml(item.id)}">
      <div><strong>${escapeHtml(textOrMissing(item.source_code, 'Questão'))}</strong><span>${escapeHtml(item.subject || '')}</span><small>${escapeHtml(item.tutor_mode || item.interaction_type || '')} · ${escapeHtml(item.provider || '')}</small></div>
      <div class="ai-audit-score"><strong>${item.overall_score == null ? '—' : `${Number(item.overall_score).toFixed(0)}/100`}</strong><small>avaliação independente</small></div>
      <div class="ai-audit-badges"><span class="status-pill status-${escapeHtml(item.status || 'rascunho')}">${escapeHtml(item.status || 'rascunho')}</span>${item.has_human_edit ? '<span class="status-pill status-neutral">editado</span>' : ''}${item.question_changed ? '<span class="status-pill status-warning">questão alterada</span>' : ''}</div>
      <small>${escapeHtml(formatDate(item.created_at))}</small>
    </article>`).join('')}</div>` : emptyStateHtml({ title: 'Auditoria vazia', text: 'As respostas do Tutor aparecerão aqui com prompt, modelo, fontes e avaliação.', compact: true });
    $$('[data-ai-interaction]', target).forEach((row) => row.addEventListener('click', () => showAiInteractionAudit(row.dataset.aiInteraction)));
  } catch (error) {
    target.innerHTML = emptyStateHtml({ title: 'Auditoria indisponível', text: error.message, compact: true });
  }
}

async function showAiInteractionAudit(interactionId) {
  if (!interactionId) return;
  try {
    const result = await bridge.call('get_ai_interaction', interactionId);
    if (!result.ok) throw new Error(result.error || 'Interação não encontrada.');
    const item = result.interaction || {};
    const evaluation = item.evaluation?.details || item.evaluation || {};
    const sources = Array.isArray(item.sources) ? item.sources : [];
    openModal({
      title: 'Auditoria completa da IA', eyebrow: `${item.provider || 'Provedor'} · ${item.model || 'modelo não informado'}`,
      body: `<div class="ai-audit-detail"><div class="architecture-note"><strong>Status: ${escapeHtml(item.status || 'rascunho')}</strong><span>Prompt SHA-256: ${escapeHtml(String(item.prompt_sha256 || '').slice(0,20))}…</span></div>
        ${String(item.question_snapshot_origin || '').startsWith('legacy_upgrade_baseline') ? '<div class="notice notice--info"><strong>Orientação criada antes do versionamento de questões do Tutor.</strong><span>A 6.17.1 registrou a versão da questão existente no momento da atualização como referência para detectar mudanças futuras. Esse baseline não é apresentado como uma reconstrução exata da questão no dia em que esta orientação antiga foi gerada.</span></div>' : ''}
        ${item.question_changed ? '<div class="notice notice--warning"><strong>Questão alterada depois desta orientação.</strong><span>Este registro permanece na auditoria como histórico. Gere uma nova orientação no Tutor para trabalhar com a versão atual da questão.</span></div>' : ''}
        <h3>Prompt auditado</h3><pre>${escapeHtml(item.prompt_text || '')}</pre>
        <h3>${item.has_human_edit ? 'Versão atual revisada pelo usuário' : 'Resposta do Tutor'}</h3><div class="tutor-response-text">${tutorTextHtml(item.display_response_text || item.response_text || '')}</div>
        ${item.has_human_edit ? `<details class="tutor-original-ai"><summary>Ver texto original gerado pela IA</summary><div class="tutor-response-text">${tutorTextHtml(item.response_text || '')}</div></details>` : ''}
        <h3>Avaliação independente</h3><div class="evaluation-grid">${['groundedness','answer_alignment','source_coverage','pedagogical_quality','overall_score'].map((key) => `<div><span>${escapeHtml(key.replaceAll('_',' '))}</span><strong>${Number(evaluation[key] || 0).toFixed(0)}</strong></div>`).join('')}</div>
        ${renderClaimEvaluation(evaluation, item.claims || evaluation.claims || [])}
        <h3>Fontes</h3>${sources.length ? sources.map((src) => `<p><strong>${escapeHtml(src.title || 'Fonte')}</strong> · ${escapeHtml(src.provider || '')}</p>`).join('') : '<p>Sem fontes registradas.</p>'}
      </div>`,
      footer: '<button class="button button--secondary" data-modal-close>Fechar</button>',
    });
  } catch (error) { toast(error.message, 'error'); }
}


function stage5CandidateLabel(item = {}) {
  return `${textOrMissing(item.source_code || item.code, 'Questão')} · ${textOrMissing(item.subject, 'Sem matéria')} · ${textOrMissing(item.primary_topic || item.topic, 'Sem assunto')}`;
}

function renderStage5Metrics(workspace = {}) {
  const target = $('#stage5Metrics');
  if (!target) return;
  const legislation = workspace.legislation_summary || {};
  const gold = workspace.gold || {};
  const drafts = Array.isArray(workspace.drafts) ? workspace.drafts : [];
  const ready = drafts.filter((item) => ['validado','aprovado'].includes(String(item.status))).length;
  const metrics = [
    ['Fontes RAG disponíveis', formatNumber((workspace.source_pool || []).length), 'somente fontes marcadas entram no prompt'],
    ['Versões legislativas', formatNumber(legislation.versions || 0), `${formatNumber(legislation.canonical_norms || 0)} normas canônicas`],
    ['Rascunhos recentes', formatNumber(drafts.length), `${formatNumber(ready)} validados/aprovados`],
    ['Questões ouro', formatNumber(gold.active_gold_questions || 0), gold.last_run ? `última regressão ${Number(gold.last_run.average_score || 0).toFixed(0)}/100` : 'sem regressão executada'],
  ];
  target.innerHTML = metrics.map(([label,value,detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
}

function renderStage5SourcePool(items = []) {
  const target = $('#stage5SourcePool');
  if (!target) return;
  target.innerHTML = items.length ? items.map((src,index) => {
    const meta = src.metadata || {};
    const temporal = src.source_kind === 'legislation' ? `<small>Vigência: ${escapeHtml(meta.effective_from || '—')} → ${escapeHtml(meta.effective_to || 'atual')}</small>` : '';
    return `<label class="stage5-source-card"><input type="checkbox" name="stage5Source" value="${escapeHtml(src.id)}" ${index < 2 ? 'checked' : ''}><span><strong>${escapeHtml(textOrMissing(src.title, 'Evidência'))}</strong><small>${escapeHtml(src.source_kind || 'fonte')} · ${escapeHtml(textOrMissing(src.subject, 'sem matéria'))}</small>${temporal}<p>${escapeHtml(String(src.content || '').slice(0,420))}</p></span></label>`;
  }).join('') : emptyStateHtml({title:'Nenhuma evidência recuperada',text:'Selecione outra questão-base ou cadastre uma versão legislativa para indexá-la no Knowledge Engine.',compact:true});
}

function renderLegislationTimeline(items = []) {
  const target = $('#legislationTimeline');
  if (!target) return;
  target.innerHTML = items.length ? `<div class="stage5-section-label"><strong>Versões cadastradas</strong><span>${items.length} registro(s)</span></div>${items.map(item => `<article class="stage5-timeline-item"><div><strong>${escapeHtml(textOrMissing(item.title,item.canonical_key))}</strong><span>${escapeHtml(item.canonical_key || '')} · ${escapeHtml(item.subject || '')}</span></div><div><b>${escapeHtml(item.effective_from || '—')}</b><span>até ${escapeHtml(item.effective_to || 'vigente')}</span></div></article>`).join('')}` : '<p class="field-help">Nenhuma versão legislativa cadastrada.</p>';
}

function renderGoldPanel(summary = {}, items = [], result = null) {
  const target = $('#goldRegressionPanel');
  if (!target) return;
  const selectedUid = state.stage5SelectedUid || '';
  const last = result || summary.last_run || null;
  target.innerHTML = `<div class="stage5-gold-summary"><div><strong>${formatNumber(summary.active_gold_questions || items.length || 0)}</strong><span>questões ouro ativas</span></div>${last ? `<div><strong>${Number(last.average_score || 0).toFixed(0)}/100</strong><span>${formatNumber(last.correct || 0)}/${formatNumber(last.cases || 0)} gabaritos · suporte ${Number(last.claim_support_score || 0).toFixed(0)}/100</span></div>` : '<div><strong>—</strong><span>nenhuma regressão executada</span></div>'}</div>
    <div class="stage5-gold-actions"><button class="button button--secondary button--compact" type="button" id="addSelectedGold" ${selectedUid ? '' : 'disabled'}>Adicionar questão-base ao conjunto ouro</button></div>
    <div class="stage5-gold-list">${items.length ? items.slice(0,12).map(item => `<article><strong>${escapeHtml(item.label || item.source_code || 'Questão ouro')}</strong><span>${escapeHtml(item.subject || '')}</span><small>Gabarito esperado: ${escapeHtml(item.expected_answer || '—')}</small></article>`).join('') : '<p class="field-help">Adicione questões estáveis e bem fundamentadas para formar sua suíte permanente de regressão.</p>'}</div>
    ${result?.items?.length ? `<details class="stage5-regression-results" open><summary>Resultado da execução ${escapeHtml(result.run_id || '')}</summary>${result.items.map(item => `<div><strong>${escapeHtml(item.source_code || 'Questão')}</strong><span>esperado ${escapeHtml(item.expected_answer || '—')} · previsto ${escapeHtml(item.predicted_answer || '—')} · ${Number(item.score || 0).toFixed(0)}/100 · suporte ${Number(item.claim_support_score || 0).toFixed(0)} · contraditas ${formatNumber(item.claim_summary?.contradicted || 0)}</span></div>`).join('')}</details>` : ''}`;
  $('#addSelectedGold')?.addEventListener('click', addSelectedGoldQuestion);
}

function renderStage5Draft(item = {}) {
  const target = $('#stage5DraftWorkspace');
  if (!target) return;
  if (!item || !item.draft) {
    target.innerHTML = emptyStateHtml({title:'Nenhum rascunho nesta sessão',text:'Selecione fontes e gere uma questão para iniciar a validação independente.',compact:true});
    return;
  }
  state.stage5DraftId = item.id || state.stage5DraftId;
  const q = item.draft || {};
  const v = item.validation || {};
  const alternatives = Array.isArray(q.alternativas) ? q.alternativas : [];
  const flags = [...(v.flags || []), ...(v.critical_flags || [])];
  const status = String(item.status || 'rascunho');
  target.innerHTML = `<article class="stage5-draft-card">
    <div class="stage5-draft-head"><div><span>${escapeHtml(q.codigo_origem || 'Rascunho')}</span><strong>${escapeHtml(q.materia || '')} · ${escapeHtml(q.assunto || '')}</strong><small>Status: ${escapeHtml(status)} · gerador ${escapeHtml(item.generator_model || 'qf-controlled-generator')}</small></div><b class="${Number(v.overall_score || item.validation_score || 0) >= 78 ? 'score-good' : 'score-warn'}">${Number(v.overall_score || item.validation_score || 0).toFixed(0)}/100</b></div>
    <div class="stage5-validation-grid"><div><span>Fundamentação</span><strong>${Number(v.groundedness || 0).toFixed(0)}</strong></div><div><span>Fontes</span><strong>${Number(v.source_score || 0).toFixed(0)}</strong></div><div><span>Redação</span><strong>${Number(v.wording || 0).toFixed(0)}</strong></div><div><span>Distratores</span><strong>${Number(v.distractor_quality || 0).toFixed(0)}</strong></div></div>
    <h3>${escapeHtml(q.enunciado || '')}</h3>
    ${alternatives.length ? `<div class="stage5-alternatives">${alternatives.map(alt => `<div class="${String(alt.chave).toUpperCase()===String(q.gabarito).toUpperCase()?'is-answer':''}"><b>${escapeHtml(alt.chave || '')}</b><span>${escapeHtml(alt.texto || '')}</span></div>`).join('')}</div>` : `<div class="stage5-ce-answer"><strong>Gabarito: ${escapeHtml(q.gabarito || '—')}</strong></div>`}
    <details><summary>Explicação e proveniência</summary><p>${escapeHtml(q.explicacao || '')}</p><p><strong>Fontes selecionadas:</strong> ${(item.source_snapshot || []).map(src => escapeHtml(src.title || src.id || 'Fonte')).join('; ') || '—'}</p></details>
    ${flags.length ? `<div class="stage5-flags">${flags.map(flag => `<span>${escapeHtml(flag)}</span>`).join('')}</div>` : '<p class="success-note">O segundo modelo não encontrou bloqueios críticos.</p>'}
    <div class="stage5-review-actions">
      <button class="button button--success" type="button" id="approveStage5Draft" ${status==='validado'?'':'disabled'}>Aprovar rascunho</button>
      <button class="button button--danger-ghost" type="button" id="rejectStage5Draft" ${['publicado','rejeitado'].includes(status)?'disabled':''}>Rejeitar</button>
      <button class="button button--primary" type="button" id="publishStage5Draft" ${status==='aprovado'?'':'disabled'}>Publicar no Banco Editorial</button>
    </div>
  </article>`;
  $('#approveStage5Draft')?.addEventListener('click', () => reviewStage5Draft('aprovar'));
  $('#rejectStage5Draft')?.addEventListener('click', () => reviewStage5Draft('rejeitar'));
  $('#publishStage5Draft')?.addEventListener('click', publishStage5Draft);
}

async function loadStage5Page(uid = '') {
  const target = $('#stage5SourcePool');
  if (target) target.innerHTML = '<div class="skeleton" style="height:8rem"></div>';
  try {
    const result = await bridge.call('get_stage5_workspace', uid || state.stage5SelectedUid || '');
    if (!result.ok) throw new Error(result.error || 'Não foi possível carregar a Etapa 5.');
    const workspace = result.workspace || {};
    state.stage5LastWorkspace = workspace;
    state.stage5SelectedUid = workspace.selected?.uid || state.stage5SelectedUid || null;
    renderStage5Metrics(workspace);
    const select = $('#stage5SeedQuestion');
    if (select) {
      select.innerHTML = '<option value="">Selecione uma questão</option>' + (workspace.candidates || []).map(item => `<option value="${escapeHtml(item.uid)}">${escapeHtml(stage5CandidateLabel(item))}</option>`).join('');
      if (state.stage5SelectedUid) select.value = state.stage5SelectedUid;
    }
    if (workspace.selected) {
      if ($('#stage5Subject') && !$('#stage5Subject').value) $('#stage5Subject').value = workspace.selected.subject || '';
      if ($('#stage5Topic') && !$('#stage5Topic').value) $('#stage5Topic').value = workspace.selected.topic || '';
      if ($('#stage5BoardStyle') && !$('#stage5BoardStyle').value) $('#stage5BoardStyle').value = workspace.selected.board || '';
    }
    renderStage5SourcePool(workspace.source_pool || []);
    renderLegislationTimeline(workspace.legislation || []);
    const gold = await bridge.call('get_gold_dashboard');
    renderGoldPanel(gold.summary || workspace.gold || {}, gold.items || []);
    const latestDraft = (workspace.drafts || [])[0];
    if (latestDraft && state.stage5DraftId === latestDraft.id) renderStage5Draft(latestDraft);
  } catch (error) {
    if (target) target.innerHTML = emptyStateHtml({title:'Etapa 5 indisponível',text:error.message,compact:true});
    toast(error.message, 'error');
  }
}

async function generateStage5Draft() {
  const sourceIds = $$('input[name="stage5Source"]:checked').map(input => input.value);
  const payload = {
    seed_uid: state.stage5SelectedUid || '', source_chunk_ids: sourceIds,
    question_type: $('#stage5QuestionType')?.value || 'multipla_escolha', board_style: $('#stage5BoardStyle')?.value || '',
    exam_date: $('#stage5ExamDate')?.value || '', subject: $('#stage5Subject')?.value || '', topic: $('#stage5Topic')?.value || '',
  };
  if (!sourceIds.length) { toast('Selecione ao menos uma fonte. A geração controlada não permite prompt sem evidência.', 'warning'); return; }
  const button = $('#generateControlledQuestion');
  if (button) button.disabled = true;
  try {
    const result = await bridge.call('generate_controlled_question', payload);
    if (!result.ok) throw new Error(result.error || 'Falha na geração controlada.');
    const draft = result.draft || {};
    state.stage5DraftId = draft.id || null;
    renderStage5Draft(draft);
    toast('Rascunho gerado e submetido ao segundo modelo de validação.', 'success');
    await loadStage5Page(state.stage5SelectedUid || '');
    if (state.stage5DraftId) {
      const refreshed = await bridge.call('get_generation_draft', state.stage5DraftId);
      if (refreshed.ok) renderStage5Draft(refreshed.draft || {});
    }
  } catch (error) { toast(error.message, 'error'); }
  finally { if (button) button.disabled = false; }
}

async function reviewStage5Draft(decision) {
  if (!state.stage5DraftId) return;
  try {
    const result = await bridge.call('review_generation_draft', state.stage5DraftId, decision, 'Decisão humana realizada na Etapa 5.');
    if (!result.ok) throw new Error(result.error || 'Não foi possível registrar a decisão.');
    renderStage5Draft(result.draft || {});
    toast(decision === 'aprovar' ? 'Rascunho aprovado. A publicação no banco continua sendo uma ação separada.' : 'Rascunho rejeitado.', decision === 'aprovar' ? 'success' : 'warning');
  } catch (error) { toast(error.message, 'error'); }
}

async function publishStage5Draft() {
  if (!state.stage5DraftId) return;
  try {
    const result = await bridge.call('publish_generation_draft', state.stage5DraftId);
    if (!result.ok) throw new Error(result.error || 'Não foi possível publicar.');
    renderStage5Draft(result.draft || {});
    toast(`Questão ${result.published?.question?.codigo_origem || ''} publicada no Banco Editorial.`, 'success');
  } catch (error) { toast(error.message, 'error'); }
}

async function saveLegislationVersion() {
  const payload = {
    canonical_key: $('#legCanonicalKey')?.value || '', title: $('#legTitle')?.value || '', subject: $('#legSubject')?.value || '',
    source_label: $('#legSourceLabel')?.value || '', source_url: $('#legSourceUrl')?.value || '',
    effective_from: $('#legEffectiveFrom')?.value || '', effective_to: $('#legEffectiveTo')?.value || '', text_content: $('#legText')?.value || '',
  };
  try {
    const result = await bridge.call('create_legislation_version', payload);
    if (!result.ok) throw new Error(result.error || 'Não foi possível salvar a versão legislativa.');
    toast('Versão legislativa salva e indexada no Knowledge Engine.', 'success');
    await loadStage5Page(state.stage5SelectedUid || '');
  } catch (error) { toast(error.message, 'error'); }
}

async function resolveLegislationVersion() {
  const key = $('#legResolveKey')?.value || '';
  const date = $('#legResolveDate')?.value || '';
  const target = $('#legResolveResult');
  if (!key || !date) { toast('Informe a chave canônica e a data que deseja consultar.', 'warning'); return; }
  try {
    const result = await bridge.call('resolve_legislation_version', key, date);
    if (!result.ok) throw new Error(result.error || 'Falha ao resolver a vigência.');
    const item = result.version;
    if (target) target.innerHTML = item ? `<div class="stage5-resolved-version"><strong>${escapeHtml(item.title || key)}</strong><span>Versão vigente em ${escapeHtml(date)}: ${escapeHtml(item.effective_from || '—')} → ${escapeHtml(item.effective_to || 'atual')}</span><p>${escapeHtml(String(item.text_content || '').slice(0,900))}</p></div>` : '<p class="warning-note">Nenhuma versão cadastrada cobre essa data.</p>';
  } catch (error) { if (target) target.textContent = error.message; toast(error.message,'error'); }
}

async function addSelectedGoldQuestion() {
  if (!state.stage5SelectedUid) return;
  try {
    const result = await bridge.call('add_gold_question', state.stage5SelectedUid, '', 'Incluída manualmente pela Etapa 5.');
    if (!result.ok) throw new Error(result.error || 'Não foi possível adicionar ao conjunto ouro.');
    const gold = await bridge.call('get_gold_dashboard');
    renderGoldPanel(gold.summary || result.summary || {}, gold.items || []);
    toast('Questão adicionada ao conjunto ouro permanente.', 'success');
  } catch (error) { toast(error.message,'error'); }
}

async function runGoldRegression() {
  const button = $('#runGoldRegression');
  if (button) button.disabled = true;
  try {
    const result = await bridge.call('run_gold_regression', 50);
    if (!result.ok) throw new Error(result.error || 'Falha na regressão da IA.');
    const gold = await bridge.call('get_gold_dashboard');
    renderGoldPanel(gold.summary || result.summary || {}, gold.items || [], result.result || null);
    toast(`Regressão concluída: ${Number(result.result?.average_score || 0).toFixed(0)}/100.`, 'success');
  } catch (error) { toast(error.message,'error'); }
  finally { if (button) button.disabled = false; }
}

async function loadTutorPage(uid = '') {
  const architectureTarget = $('#engineArchitecture');
  if (architectureTarget) architectureTarget.innerHTML = '<div class="skeleton" style="height:8rem"></div>';
  try {
    const [architectureResult, workspaceResult] = await Promise.all([
      bridge.call('get_engine_architecture'), bridge.call('get_tutor_workspace', uid || state.tutorSelectedUid || ''),
    ]);
    if (!architectureResult.ok) throw new Error(architectureResult.error || 'Falha ao ler a arquitetura.');
    if (!workspaceResult.ok) throw new Error(workspaceResult.error || 'Falha ao montar o Tutor IA.');
    renderEngineArchitecture(architectureResult.architecture || {});
    renderTutorWorkspace(workspaceResult.workspace || {});
    await loadAiAudit();
  } catch (error) {
    if (architectureTarget) architectureTarget.innerHTML = emptyStateHtml({ title: 'Tutor indisponível', text: error.message, compact: true });
    toast(error.message, 'error', 7000);
  }
}

async function refreshTutorDiagnosis() {
  if (!state.tutorSelectedUid) return;
  const button = $('#refreshTutorDiagnosis');
  setBusy(button, true, 'Recalculando diagnóstico');
  try {
    const result = await bridge.call('diagnose_question_error', state.tutorSelectedUid);
    if (!result.ok) throw new Error(result.error || 'Falha ao diagnosticar o erro.');
    renderTutorDiagnosis(result.diagnosis || {});
    toast('Diagnóstico atualizado com os sinais atuais de aprendizagem.', 'success');
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(button, false); }
}

function claimVerdictLabel(value = '') {
  return ({suporta:'Suportada', contradiz:'Contradita', insuficiente:'Evidência insuficiente'})[String(value)] || textOrMissing(value,'Sem avaliação');
}

function renderClaimEvaluation(evaluation = {}, claimsOverride = null) {
  const summary = evaluation.claim_summary || {};
  const claims = Array.isArray(claimsOverride) ? claimsOverride : (Array.isArray(evaluation.claims) ? evaluation.claims : []);
  if (!claims.length && !Number(summary.total || 0)) return '';
  const badges = `<div class="claim-summary">
    <span class="claim-badge is-supported"><b>${formatNumber(summary.supported || 0)}</b> suportada(s)</span>
    <span class="claim-badge is-contradicted"><b>${formatNumber(summary.contradicted || 0)}</b> contradita(s)</span>
    <span class="claim-badge is-insufficient"><b>${formatNumber(summary.insufficient || 0)}</b> sem evidência suficiente</span>
  </div>`;
  const rows = claims.slice(0,18).map((claim,index) => {
    const verdict = claim.verdict || claim.details?.verdict || 'insuficiente';
    const evidence = Array.isArray(claim.evidence) ? claim.evidence : [];
    const temporal = claim.temporal_status || claim.details?.temporal_status || '';
    const official = claim.official_answer_status || claim.details?.official_answer_status || '';
    return `<article class="claim-evaluation-row is-${escapeHtml(verdict)}">
      <div class="claim-evaluation-head"><strong>Afirmação ${index+1} · ${escapeHtml(claimVerdictLabel(verdict))}</strong><span>${Math.round(Number(claim.confidence || 0)*100)}% confiança</span></div>
      <p>${escapeHtml(claim.text || claim.claim_text || '')}</p>
      <small>${temporal && temporal !== 'nao_aplicavel' ? `Temporal: ${escapeHtml(temporal.replaceAll('_',' '))}` : ''}${official && official !== 'nao_aplicavel' ? ` · Gabarito: ${escapeHtml(official.replaceAll('_',' '))}` : ''}</small>
      ${evidence.length ? `<details><summary>Melhor evidência</summary>${evidence.slice(0,2).map(ev => `<blockquote><b>${escapeHtml(ev.source_title || 'Fonte')}</b><span>${Math.round(Number(ev.score || 0)*100)}% · ${escapeHtml(claimVerdictLabel(ev.relation || ''))}</span><p>${escapeHtml(String(ev.excerpt || '').slice(0,700))}</p></blockquote>`).join('')}</details>` : ''}
    </article>`;
  }).join('');
  return `<div class="claim-evaluation-panel"><div class="claim-evaluation-title"><strong>Avaliação por afirmação → evidência</strong><span>${formatNumber(summary.total || claims.length)} afirmação(ões)</span></div>${badges}${rows ? `<details><summary>Ver análise das afirmações</summary><div class="claim-evaluation-list">${rows}</div></details>` : ''}</div>`;
}

function updateTutorModeUi() {
  const mode = $('input[name="tutorMode"]:checked')?.value || 'professor';
  const box = $('#tutorScaffoldOptions');
  if (box) box.hidden = mode !== 'socratico';
  const button = $('#generateTutorAnswer');
  if (button) button.textContent = mode === 'socratico' ? 'Iniciar escada de pistas' : 'Gerar orientação';
  if (mode !== 'socratico') {
    state.tutorScaffoldSessionId = null;
    state.tutorScaffoldLevel = null;
    const status = $('#tutorScaffoldStatus'); if (status) status.innerHTML = '';
  }
}

function renderScaffoldStatus(session = {}) {
  const target = $('#tutorScaffoldStatus');
  if (!target) return;
  const level = Number(session.current_level ?? 0);
  const independence = Number(session.independence_score ?? (1 - level/5));
  target.innerHTML = `<strong>Scaffolding ativo</strong><span>Nível ${level}/5</span><span>Independência estimada ${Math.round(independence*100)}%</span><span>${escapeHtml(session.status || 'em andamento')}</span>`;
}

function renderScaffoldStep(result = {}) {
  const target = $('#tutorAnswer'); if (!target) return;
  const session = result.session || {};
  const step = result.step || {};
  state.tutorScaffoldSessionId = session.id || state.tutorScaffoldSessionId;
  state.tutorScaffoldLevel = Number(step.level ?? session.current_level ?? 0);
  renderScaffoldStatus(session);
  if (step.final_tutor) {
    renderTutorAnswer(step.final_tutor);
    const finalTarget = $('#tutorAnswer');
    finalTarget?.insertAdjacentHTML('afterbegin', `<div class="network-note"><strong>Escada concluída no nível 5/5.</strong> A explicação completa foi revelada e o Learner Model registrou alta necessidade de apoio nesta sessão.</div>`);
    return;
  }
  const content = step.content || {};
  const level = Number(step.level ?? 0);
  const progress = Array.from({length:6},(_,i)=>`<i class="${i<=level?'is-done':''}"></i>`).join('');
  target.innerHTML = `<article class="tutor-scaffold-card">
    <div class="tutor-scaffold-head"><div><span>Scaffolding progressivo · ${escapeHtml(step.representation || 'texto')}</span><strong>${escapeHtml(step.level_label || `Nível ${level}`)}</strong><small>${escapeHtml(step.level_description || '')}</small></div><b class="tutor-scaffold-level">${level}/5</b></div>
    <div class="tutor-scaffold-body"><div class="tutor-scaffold-progress">${progress}</div><div class="tutor-response-text">${tutorTextHtml(content.hint || '')}</div><div class="tutor-scaffold-question"><strong>Recuperação ativa</strong><div>${escapeHtml(content.question_to_student || 'Formule sua hipótese antes de avançar.')}</div></div>${(content.warnings||[]).length?`<div class="network-note">${escapeHtml((content.warnings||[]).join(' • '))}</div>`:''}</div>
    <div class="tutor-scaffold-actions"><button class="button button--success" type="button" data-scaffold-action="solved">Consegui resolver</button><button class="button button--primary" type="button" data-scaffold-action="next">Próxima pista</button><button class="button button--secondary" type="button" data-scaffold-action="reveal">Mostrar explicação completa</button></div>
  </article>`;
  $$('[data-scaffold-action]', target).forEach(btn=>btn.addEventListener('click',()=>advanceTutorScaffold(btn.dataset.scaffoldAction||'next', btn)));
}

async function startTutorScaffolding() {
  if (!state.tutorSelectedUid) return;
  const button = $('#generateTutorAnswer');
  const userPrompt = $('#tutorUserPrompt')?.value || '';
  const representation = $('#tutorRepresentation')?.value || 'texto';
  const mediaNotes = $('#tutorMediaNotes')?.value || '';
  const online = Boolean($('#tutorOnlineAi')?.checked);
  setBusy(button, true, 'Criando primeira pista');
  const target = $('#tutorAnswer'); if (target) target.innerHTML = '<div class="skeleton" style="height:9rem"></div>';
  try {
    const started = await bridge.call('start_tutor_scaffolding', state.tutorSelectedUid, userPrompt, representation, mediaNotes, online);
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar o scaffolding.');
    const result = await monitorTask(started.task_id, null, { timeoutMs: online ? 900000 : 180000, intervalMs: 500 });
    renderScaffoldStep(result || {});
  } catch (error) { if(target) target.innerHTML=emptyStateHtml({title:'Falha no scaffolding',text:error.message,compact:true}); toast(error.message,'error',8000); }
  finally { setBusy(button,false); }
}

async function advanceTutorScaffold(action='next', button=null) {
  if (!state.tutorScaffoldSessionId) return;
  const online = Boolean($('#tutorOnlineAi')?.checked);
  setBusy(button, true, action==='solved'?'Registrando resolução':'Gerando próxima pista');
  try {
    const started = await bridge.call('advance_tutor_scaffolding', state.tutorScaffoldSessionId, action, online);
    if (!started.ok) throw new Error(started.error || 'Não foi possível avançar o scaffolding.');
    const result = await monitorTask(started.task_id, null, { timeoutMs: online ? 900000 : 180000, intervalMs: 500 });
    if (result.completed && !result.step) {
      const signal = result.signal || result.learner?.scaffolding || {};
      const target=$('#tutorAnswer'); if(target) target.innerHTML=`<article class="tutor-scaffold-card"><div class="tutor-scaffold-body"><h3>✓ Resolução registrada</h3><p>Você informou que conseguiu prosseguir no nível <strong>${Number(result.session?.solved_level ?? result.session?.current_level ?? 0)}/5</strong>.</p><div class="tutor-support-signal"><span>Independência ${Math.round(Number(signal.independence_score ?? 1)*100)}%</span><span>${escapeHtml(signal.signal || 'sinal registrado')}</span></div><p>Esse dado agora integra o Learner Model sem substituir FSRS, KT ou IRT.</p></div></article>`;
      renderScaffoldStatus(result.session||{});
      await loadTutorPage(state.tutorSelectedUid || '');
      return;
    }
    renderScaffoldStep(result || {});
  } catch(error){toast(error.message,'error',8000);} finally{setBusy(button,false);}
}

function tutorInteractionAsResult(item = {}) {
  const evaluation = item.evaluation?.details || item.evaluation || {};
  return {
    interaction_id: item.id || item.interaction_id || '',
    provider: item.provider || 'QuestFlow AI Engine', model: item.model || '',
    response: item.display_response_text || item.edited_response_text || item.response_text || '',
    original_response: item.response_text || '', has_human_edit: Boolean(item.has_human_edit),
    status: item.status || 'rascunho', edited_at: item.edited_at || '', created_at: item.created_at || '',
    question_changed: Boolean(item.question_changed), current_question: item.current_question || {},
    question_snapshot: item.question_snapshot || {}, revisions: item.revisions || [],
    evaluation, sources: Array.isArray(item.sources) ? item.sources : [], warnings: [],
  };
}

function renderTutorAnswer(result = {}) {
  const target = $('#tutorAnswer');
  if (!target) return;
  state.tutorInteractionId = result.interaction_id || null;
  const evaluation = result.evaluation?.details || result.evaluation || {};
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const stale = Boolean(result.question_changed);
  const hasHumanEdit = Boolean(result.has_human_edit);
  const response = String(result.response || '');
  const original = String(result.original_response || response);
  const current = result.current_question || {};
  target.innerHTML = `<article class="tutor-result-card${stale ? ' is-stale' : ''}">
    <div class="tutor-result-head"><div><span>Rascunho editável do Tutor IA</span><strong>${escapeHtml(result.provider || 'QuestFlow AI Engine')}</strong><small>${escapeHtml(result.model || '')}${hasHumanEdit ? ' · revisado por você' : ''}</small></div><b>${Number(evaluation.overall_score || 0).toFixed(0)}/100</b></div>
    ${stale ? `<div class="notice notice--warning tutor-stale-warning"><strong>A questão foi alterada em Revisar banco depois que esta orientação foi gerada.</strong><span>O texto abaixo é preservado como histórico e não é considerado a orientação atual. A questão atual começa por: “${escapeHtml(tutorCompactText(current.enunciado || '', 150) || 'conteúdo atualizado')}”.</span><button class="button button--primary button--compact" type="button" data-tutor-regenerate>Gerar novamente com a questão atual</button></div>` : ''}
    <div class="tutor-draft-editor">
      <div class="tutor-draft-editor__head"><div><strong>Texto do Tutor</strong><small>Você pode corrigir, complementar ou reorganizar o rascunho. O texto original da IA continua preservado na auditoria.</small></div>${hasHumanEdit ? '<span class="status-pill status-neutral">editado por você</span>' : '<span class="status-pill">rascunho IA</span>'}</div>
      <textarea id="tutorDraftEditor" rows="14" spellcheck="true">${escapeHtml(response)}</textarea>
      <div class="tutor-draft-actions"><button class="button button--primary" type="button" data-tutor-save-draft>Salvar alterações</button>${hasHumanEdit ? '<button class="button button--secondary" type="button" data-tutor-restore-ai>Restaurar texto original no editor</button>' : ''}<small id="tutorDraftSaveStatus">Salvar uma alteração retorna o conteúdo ao estado de rascunho e executa novamente a avaliação independente.</small></div>
    </div>
    <div class="evaluation-grid">
      <div><span>Fundamentação</span><strong>${Number(evaluation.groundedness || 0).toFixed(0)}</strong></div>
      <div><span>Gabarito</span><strong>${Number(evaluation.answer_alignment || 0).toFixed(0)}</strong></div>
      <div><span>Fontes</span><strong>${Number(evaluation.source_coverage || 0).toFixed(0)}</strong></div>
      <div><span>Pedagogia</span><strong>${Number(evaluation.pedagogical_quality || 0).toFixed(0)}</strong></div>
    </div>
    ${renderClaimEvaluation(evaluation)}
    ${(evaluation.flags || []).length ? `<div class="evaluation-flags"><strong>Alertas do avaliador</strong>${evaluation.flags.map((flag) => `<span>${escapeHtml(flag)}</span>`).join('')}</div>` : ''}
    ${warnings.length ? `<div class="network-note"><strong>Avisos:</strong> ${escapeHtml(warnings.join(' • '))}</div>` : ''}
    ${hasHumanEdit ? `<details class="tutor-original-ai"><summary>Ver texto original gerado pela IA</summary><div class="tutor-response-text">${tutorTextHtml(original)}</div></details>` : ''}
    <details class="tutor-sources"><summary>${sources.length} fonte(s) auditadas</summary>${sources.map((src) => `<article><strong>${escapeHtml(src.title || 'Fonte')}</strong><small>${escapeHtml(src.provider || '')}${src.score != null ? ` · ${Math.round(Number(src.score)*100)}%` : ''}</small><p>${escapeHtml(String(src.content || '').slice(0,650))}</p></article>`).join('')}</details>
    <div class="human-review-banner"><div><strong>Human-in-the-loop</strong><span>${stale ? 'A aprovação está bloqueada porque a questão mudou. Gere uma nova orientação antes de aprovar.' : 'Esta resposta continua como rascunho até sua decisão explícita.'}</span></div><button class="button button--success" type="button" data-tutor-approve ${stale ? 'disabled' : ''}>Aprovar</button><button class="button button--danger-ghost" type="button" data-tutor-reject>Rejeitar</button></div>
  </article>`;
  $('[data-tutor-save-draft]', target)?.addEventListener('click', (event) => saveTutorDraftText(event.currentTarget));
  $('[data-tutor-restore-ai]', target)?.addEventListener('click', () => { const editor=$('#tutorDraftEditor'); if(editor){editor.value=original; editor.focus();} });
  $('[data-tutor-regenerate]', target)?.addEventListener('click', () => generateTutorAnswer());
  $('[data-tutor-approve]', target)?.addEventListener('click', () => reviewTutorInteraction('aprovar'));
  $('[data-tutor-reject]', target)?.addEventListener('click', () => reviewTutorInteraction('rejeitar'));
  loadAiTelemetry().catch(()=>{});
}

async function saveTutorDraftText(button = null) {
  if (!state.tutorInteractionId) return;
  const editor = $('#tutorDraftEditor');
  const text = String(editor?.value || '').trim();
  if (!text) { toast('O texto do Tutor não pode ficar vazio.', 'warning'); return; }
  setBusy(button, true, 'Salvando rascunho');
  try {
    const result = await bridge.call('save_ai_interaction_text', state.tutorInteractionId, text, 'Edição manual realizada no Tutor IA.');
    if (!result.ok) throw new Error(result.error || 'Não foi possível salvar o texto do Tutor.');
    renderTutorAnswer(tutorInteractionAsResult(result.interaction || {}));
    await loadAiAudit();
    toast('Alterações salvas. O texto original da IA foi preservado na auditoria.', 'success');
  } catch (error) { toast(error.message, 'error', 8000); }
  finally { setBusy(button, false); }
}

async function generateTutorAnswer() {
  if (!state.tutorSelectedUid) return;
  const button = $('#generateTutorAnswer');
  const mode = $('input[name="tutorMode"]:checked')?.value || 'professor';
  const userPrompt = $('#tutorUserPrompt')?.value || '';
  const online = Boolean($('#tutorOnlineAi')?.checked);
  if (mode === 'socratico') return startTutorScaffolding();
  setBusy(button, true, 'Gerando orientação');
  const target = $('#tutorAnswer');
  if (target) target.innerHTML = '<div class="skeleton" style="height:10rem"></div>';
  try {
    const started = await bridge.call('start_tutor_assist', state.tutorSelectedUid, mode, userPrompt, online);
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar o Tutor IA.');
    const result = await monitorTask(started.task_id, (task) => { if (task.message && button) button.title = task.message; }, { timeoutMs: online ? 900000 : 180000, intervalMs: 550 });
    renderTutorAnswer(result || {});
    await loadAiAudit();
  } catch (error) {
    if (target) target.innerHTML = emptyStateHtml({ title: 'Falha no Tutor', text: error.message, compact: true });
    toast(error.message, 'error', 8000);
  } finally { setBusy(button, false); }
}

async function reviewTutorInteraction(decision) {
  if (!state.tutorInteractionId) return;
  try {
    const result = await bridge.call('review_ai_interaction', state.tutorInteractionId, decision, 'Decisão realizada na tela Tutor IA.');
    if (!result.ok) throw new Error(result.error || 'Não foi possível registrar a decisão humana.');
    toast(decision === 'aprovar' ? 'Rascunho aprovado e registrado na auditoria.' : 'Rascunho rejeitado e preservado para auditoria.', decision === 'aprovar' ? 'success' : 'warning');
    await loadAiAudit();
    const banner = $('.human-review-banner', $('#tutorAnswer'));
    if (banner) banner.innerHTML = `<strong>Decisão registrada: ${escapeHtml(result.review?.status || decision)}</strong>`;
    // Recalcula a fila de trabalho imediatamente. Ao aprovar, a questão sai de
    // "Revisão de Erros com o Tutor IA" e entra em "Erros Tratados".
    await loadTutorPage(state.tutorSelectedUid || '');
  } catch (error) { toast(error.message, 'error'); }
}



function groundingMetric(value, suffix='') {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)}${suffix}`;
}

async function openGroundingBenchmark() {
  openModal({
    title: 'Benchmark Multimodal & Grounding',
    eyebrow: `QuestFlow ${state.bootstrap?.app?.version || '—'} · Benchmark multimodal`,
    body: '<div id="groundingBenchmarkBody"><div class="skeleton" style="height:14rem"></div></div>',
    footer: '<button class="button button--secondary" type="button" data-modal-close>Fechar</button><button class="button button--primary" type="button" id="rerunGroundingBenchmark">Executar novamente</button>',
    onOpen: () => {
      $('#rerunGroundingBenchmark')?.addEventListener('click', () => loadGroundingBenchmark(true));
      loadGroundingBenchmark(false).catch(()=>{});
    },
  });
}

async function loadGroundingBenchmark(force = false) {
  const target = $('#groundingBenchmarkBody');
  const button = $('#rerunGroundingBenchmark');
  if (target) target.innerHTML = '<div class="skeleton" style="height:14rem"></div>';
  setBusy(button, true, 'Medindo grounding');
  try {
    const result = await bridge.call('run_multimodal_grounding_benchmark', 30);
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível executar o benchmark multimodal.');
    const b = result.benchmark || {};
    const backends = Array.isArray(b.backends) ? b.backends : [];
    const names = {text:'Textual',visual:'Visual',hybrid:'Híbrido'};
    const rows = backends.map(item => `<article class="grounding-benchmark-row ${item.backend==='hybrid'?'is-hybrid':''}">
      <div><strong>${escapeHtml(names[item.backend] || item.backend || 'Backend')}</strong><small>${formatNumber(item.cases || 0)} caso(s)</small></div>
      <span><small>Score</small><b>${groundingMetric(item.score)}</b></span>
      <span><small>Grounding</small><b>${groundingMetric(item.grounding_rate,'%')}</b></span>
      <span><small>Suporte</small><b>${groundingMetric(item.commentary_support,'%')}</b></span>
      <span><small>Recall ouro</small><b>${groundingMetric(item.recall,'%')}</b></span>
      <span><small>Visual</small><b>${groundingMetric(item.visual_coverage,'%')}</b></span>
    </article>`).join('');
    const recs = (b.recommendations || []).map(text => `<li>${escapeHtml(text)}</li>`).join('');
    if (target) target.innerHTML = `<div class="grounding-benchmark-summary">
      <div><span>Questões Ouro</span><strong>${formatNumber(b.cases || 0)}</strong><small>${escapeHtml(b.sample_status || '—')}</small></div>
      <div><span>Casos visuais</span><strong>${formatNumber(b.visual_cases || 0)}</strong><small>imagem/PDF</small></div>
      <div><span>Ganho híbrido</span><strong>${Number(b.hybrid_gain || 0) >= 0 ? '+' : ''}${groundingMetric(b.hybrid_gain)}</strong><small>pontos vs melhor isolado</small></div>
      <div><span>Leitura atual</span><strong>${escapeHtml(b.quality_label || '—')}</strong><small>${escapeHtml(b.version || '')}</small></div>
    </div><div class="grounding-benchmark-list">${rows || '<div class="muted">Sem resultados.</div>'}</div>
    <div class="grounding-benchmark-advice"><strong>Recomendações</strong><ul>${recs || '<li>Sem recomendações adicionais.</li>'}</ul><small>${escapeHtml(b.caveat || '')}</small></div>`;
  } catch (error) {
    if (target) target.innerHTML = emptyStateHtml({title:'Benchmark indisponível',text:error.message,compact:true});
    if (force) toast(error.message, 'error', 7000);
  } finally { setBusy(button, false); }
}


function retrievalWeightsHtml(profile = {}) {
  const w = profile.weights || {};
  const parts = [
    ['Score original', w.original_score], ['Sobreposição', w.query_overlap],
    ['Grounding', w.grounding], ['Visual', w.visual_context],
  ];
  return parts.map(([label,value]) => `<span><small>${escapeHtml(label)}</small><b>${value == null ? '—' : `${(Number(value)*100).toFixed(0)}%`}</b></span>`).join('');
}

async function openRetrievalCalibration() {
  openModal({
    title: 'Calibração e regressão de retrieval',
    eyebrow: `QuestFlow ${state.bootstrap?.app?.version || '—'} · Calibração de retrieval`,
    body: '<div id="retrievalCalibrationBody"><div class="skeleton" style="height:16rem"></div></div>',
    footer: '<button class="button button--secondary" type="button" data-modal-close>Fechar</button><button class="button button--secondary" type="button" id="saveRetrievalBaseline">Salvar baseline</button><button class="button button--tertiary" type="button" id="rollbackRetrievalProfile">Rollback</button><button class="button button--primary" type="button" id="runRetrievalCalibration">Recalibrar</button>',
    onOpen: () => {
      $('#runRetrievalCalibration')?.addEventListener('click', () => loadRetrievalCalibration(true));
      $('#saveRetrievalBaseline')?.addEventListener('click', saveRetrievalBaseline);
      $('#rollbackRetrievalProfile')?.addEventListener('click', rollbackRetrievalProfile);
      loadRetrievalCalibration(false).catch(()=>{});
    },
  });
}

async function loadRetrievalCalibration(force=false) {
  const target=$('#retrievalCalibrationBody');
  const button=$('#runRetrievalCalibration');
  if(target) target.innerHTML='<div class="skeleton" style="height:16rem"></div>';
  setBusy(button,true,'Comparando perfis');
  try {
    const [calResult, regResult] = await Promise.all([
      bridge.call('run_retrieval_calibration',30), bridge.call('get_retrieval_regression_status',30),
    ]);
    if(!calResult?.ok) throw new Error(calResult?.error || 'Não foi possível calibrar o retrieval.');
    const c=calResult.calibration || {};
    const current=c.current || {};
    const recommended=c.recommended || current;
    const currentProfile=current.profile || {};
    const recommendedProfile=recommended.profile || {};
    const reg=regResult?.status?.comparison || {};
    const alerts=Array.isArray(reg.alerts)?reg.alerts:[];
    const alertHtml=alerts.length ? alerts.map(a=>`<li>${escapeHtml(a.scope==='subject' ? `${a.subject}: ` : '')}${escapeHtml(a.metric || 'métrica')} ${Number(a.delta||0).toFixed(1)} p.p. (limite ${Number(a.threshold||0).toFixed(1)})</li>`).join('') : '<li>Nenhuma regressão acima dos thresholds versionados.</li>';
    const applyButton=c.recommended_change
      ? `<button class="button button--success" type="button" id="applyRecommendedRetrieval" data-profile-id="${escapeHtml(recommendedProfile.id || '')}" title="Aplicar o perfil recomendado; o perfil anterior continuará disponível para rollback">Aplicar perfil recomendado</button>`
      : `<button class="button button--success" type="button" id="applyRecommendedRetrieval" disabled title="Nenhuma mudança foi recomendada para a amostra atual">Aplicar perfil recomendado</button>`;
    if(target) target.innerHTML=`<div class="retrieval-calibration-summary">
      <article><small>Perfil atual</small><strong>${escapeHtml(currentProfile.label || currentProfile.id || '—')}</strong><span>objetivo ${Number(current.objective||0).toFixed(2)}</span></article>
      <article><small>Melhor candidato</small><strong>${escapeHtml(recommendedProfile.label || recommendedProfile.id || '—')}</strong><span>${c.recommended_change ? `+${Number(c.objective_gain||0).toFixed(2)} no objetivo` : 'manter perfil atual'}</span></article>
      <article><small>Amostra</small><strong>${formatNumber(c.cases||0)}</strong><span>${escapeHtml(c.sample_status||'—')}</span></article>
      <article><small>Regressão</small><strong>${escapeHtml(reg.status||'sem_baseline')}</strong><span>${alerts.length} alerta(s)</span></article>
    </div>
    <div class="retrieval-profile-compare"><section><h4>Atual</h4><div class="retrieval-weight-grid">${retrievalWeightsHtml(currentProfile)}</div><small>score ${groundingMetric(current.score)} · recall ${groundingMetric(current.recall,'%')} · grounding ${groundingMetric(current.grounding_rate,'%')}</small></section><section><h4>Recomendado</h4><div class="retrieval-weight-grid">${retrievalWeightsHtml(recommendedProfile)}</div><small>score ${groundingMetric(recommended.score)} · recall ${groundingMetric(recommended.recall,'%')} · grounding ${groundingMetric(recommended.grounding_rate,'%')}</small></section></div>
    <div class="grounding-benchmark-advice"><strong>Regressão contínua</strong><ul>${alertHtml}</ul><small>${escapeHtml(reg.message || c.caveat || '')}</small></div>
    <div class="retrieval-calibration-actions">${applyButton}</div>`;
    $('#applyRecommendedRetrieval')?.addEventListener('click', async (event)=>{
      const id=event.currentTarget?.dataset?.profileId || '';
      if(!id) return;
      if(!window.confirm('Aplicar este perfil de reranking? O perfil anterior ficará disponível para rollback.')) return;
      const r=await bridge.call('apply_retrieval_calibration',id);
      if(!r?.ok) return toast(r?.error || 'Falha ao aplicar perfil.','error');
      toast('Perfil aplicado. O anterior permanece disponível para rollback.','success');
      await loadRetrievalCalibration(true);
    });
  } catch(error) {
    if(target) target.innerHTML=emptyStateHtml({title:'Calibração indisponível',text:error.message,compact:true});
    if(force) toast(error.message,'error',7000);
  } finally { setBusy(button,false); }
}

async function saveRetrievalBaseline() {
  const button=$('#saveRetrievalBaseline'); setBusy(button,true,'Salvando baseline');
  try { const r=await bridge.call('save_retrieval_regression_baseline',30); if(!r?.ok) throw new Error(r?.error||'Falha ao salvar baseline.'); toast('Baseline de retrieval salvo para comparação das próximas releases.','success'); await loadRetrievalCalibration(false); }
  catch(error){toast(error.message,'error',7000);} finally{setBusy(button,false);}
}

async function rollbackRetrievalProfile() {
  if(!window.confirm('Restaurar o perfil de reranking anterior?')) return;
  const button=$('#rollbackRetrievalProfile'); setBusy(button,true,'Restaurando');
  try { const r=await bridge.call('rollback_retrieval_calibration'); if(!r?.ok) throw new Error(r?.error||'Falha no rollback.'); toast(r.result?.warning || 'Perfil anterior restaurado.','success'); await loadRetrievalCalibration(false); }
  catch(error){toast(error.message,'error',7000);} finally{setBusy(button,false);}
}


function observabilityDelta(value, suffix='') {
  if(value == null || Number.isNaN(Number(value))) return '—';
  const n=Number(value); return `${n>0?'+':''}${n.toFixed(1)}${suffix}`;
}

function retrievalEngineEyebrow(payload={}) {
  const release=String(payload.release || state.bootstrap?.app?.version || '').trim();
  const engine=payload.engine || {};
  const rawVersion=String(engine.version || '').trim();
  const engineVersion=rawVersion.replace(/^qf-knowledge-engine-/i,'');
  const engineName=String(engine.name || 'Knowledge Engine');
  return `QuestFlow ${release || '—'} · ${engineName}${engineVersion ? ` ${engineVersion}` : ''}`;
}

function retrievalProfileDisplay(profile={}) {
  const id=String(profile.id || '').trim();
  let label=String(profile.label || id || '—').trim();
  if(id === 'balanced-v1') label = label.replace(/\s+6\.8\.2$/,'') || 'Balanceado';
  return label;
}

function retrievalMetricState(value,{cases=0,suffix='',emptyLabel='Não avaliada'}={}) {
  if(Number(cases||0) <= 0) return emptyLabel;
  return groundingMetric(value,suffix);
}

function retrievalDriftView(drift={}) {
  const status=String(drift.status || '').toLowerCase();
  const chunks=Number(drift.changed_chunks||0);
  const sources=Number(drift.changed_sources||0);
  if(status==='stable') return {label:'Estável',detail:'Nenhuma alteração relevante no índice desde o último snapshot.'};
  if(status==='baseline') return {label:'Baseline',detail:'Primeiro snapshot disponível; as próximas avaliações permitirão medir drift.'};
  if(status==='drift' && chunks===0 && sources>0) return {label:'Pequena alteração',detail:`${formatNumber(sources)} fonte(s) mudou(aram), sem alteração nos chunks indexados.`};
  if(status==='drift') return {label:'Alteração detectada',detail:`${formatNumber(chunks)} chunks e ${formatNumber(sources)} fonte(s) alterados.`};
  return {label:'Não avaliado',detail:'Registre um snapshot para estabelecer o estado atual do índice.'};
}

function downloadRetrievalReport(report={}) {
  const content=String(report.content||'');
  if(!content) return toast('Relatório vazio.','error');
  const blob=new Blob([content],{type:report.mime||'text/plain;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');
  anchor.href=url; anchor.download=report.filename||'QuestFlow_Retrieval_Observability.txt';
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1200);
}

async function openRetrievalObservability() {
  openModal({
    title:'Observabilidade de retrieval', eyebrow:`QuestFlow ${state.bootstrap?.app?.version || '—'} · Retrieval`,
    body:'<div id="retrievalObservabilityBody"><div class="skeleton" style="height:18rem"></div></div>',
    footer:'<button class="button button--secondary" type="button" data-modal-close>Fechar</button><button class="button button--secondary" type="button" id="exportRetrievalCsv">Exportar CSV</button><button class="button button--secondary" type="button" id="exportRetrievalJson">Exportar JSON</button><button class="button button--primary" type="button" id="recordRetrievalSnapshot">Reavaliar e registrar</button>',
    onOpen:()=>{
      $('#recordRetrievalSnapshot')?.addEventListener('click',()=>recordRetrievalSnapshot());
      $('#exportRetrievalCsv')?.addEventListener('click',()=>exportRetrievalObservability('csv'));
      $('#exportRetrievalJson')?.addEventListener('click',()=>exportRetrievalObservability('json'));
      loadRetrievalObservability().catch(()=>{});
    },
  });
}

async function loadRetrievalObservability() {
  const target=$('#retrievalObservabilityBody');
  if(target) target.innerHTML='<div class="skeleton" style="height:18rem"></div>';
  try {
    const [obsResult,goldResult]=await Promise.all([
      bridge.call('get_retrieval_observability',30), bridge.call('suggest_gold_question_expansion',12),
    ]);
    if(!obsResult?.ok) throw new Error(obsResult?.error||'Não foi possível ler a observabilidade de retrieval.');
    const o=obsResult.observability||{}; const r=o.retrieval||{}; const h=r.hybrid||{}; const index=o.index||{}; const d=o.drift||{};
    const history=Array.isArray(o.history)?o.history:[]; const cmp=o.release_comparison||{}; const cases=Number(r.cases||0);
    const suggestions=goldResult?.suggestions?.suggestions||[];
    const subjectRows=Object.entries(r.subjects||{}).sort((a,b)=>Number(b[1]?.cases||0)-Number(a[1]?.cases||0)).slice(0,12).map(([subject,row])=>`<tr><td>${escapeHtml(subject)}</td><td>${formatNumber(row.cases||0)}</td><td>${retrievalMetricState(row.score,{cases:row.cases})}</td><td>${retrievalMetricState(row.recall,{cases:row.cases,suffix:'%'})}</td><td>${retrievalMetricState(row.grounding_rate,{cases:row.cases,suffix:'%'})}</td></tr>`).join('');
    const trend=history.slice(0,10).map(row=>`<tr><td>${escapeHtml(String(row.at||'').replace('T',' ').slice(0,19))}</td><td>${escapeHtml(row.release||'—')}</td><td>${escapeHtml(retrievalProfileDisplay({id:row.profile_id,label:row.profile_label||row.profile_id}))}</td><td>${retrievalMetricState(row.score,{cases:row.cases})}</td><td>${retrievalMetricState(row.recall,{cases:row.cases,suffix:'%'})}</td><td>${retrievalMetricState(row.grounding_rate,{cases:row.cases,suffix:'%'})}</td><td>${groundingMetric(row.index_coverage,'%')}</td><td>${escapeHtml(retrievalDriftView(row.drift||{}).label)}</td></tr>`).join('');
    const candidateHtml=suggestions.length?suggestions.map(item=>`<article class="retrieval-gold-candidate"><div><strong>${escapeHtml(item.code||'Sem código')}</strong><span>${escapeHtml([item.subject,item.topic].filter(Boolean).join(' · '))}</span><small>${escapeHtml((item.reasons||[]).join(' • '))}</small></div><div><b>${Number(item.quality_score||0).toFixed(0)}/100</b><button class="button button--small button--secondary" type="button" data-add-observability-gold="${escapeHtml(item.uid||'')}">Adicionar ao Ouro</button></div></article>`).join(''):'<p class="field-help">Nenhum candidato adicional encontrado.</p>';
    const driftView=retrievalDriftView(d);
    const snapshotCurrent=Boolean(o.snapshot_current);
    const snapshotRelease=String(o.snapshot_release||'').trim();
    const snapshotAt=o.snapshot_at?formatDate(o.snapshot_at):'ainda não registrado';
    const snapshotNotice = snapshotCurrent
      ? `<div class="retrieval-snapshot-notice is-current"><strong>Leitura instantânea do último snapshot</strong><span>Consulta ao Metrics Snapshot Store; o AI Engine não executa benchmark ao abrir. Última avaliação: ${escapeHtml(snapshotAt)}.</span></div>`
      : `<div class="retrieval-snapshot-notice"><strong>${snapshotRelease ? `Último snapshot pertence à release ${escapeHtml(snapshotRelease)}` : 'Esta release ainda não possui snapshot'}</strong><span>Os números abaixo vêm do Snapshot Store. Use “Reavaliar e registrar” para acionar o Evaluator Worker e medir a release ${escapeHtml(o.release||state.bootstrap?.app?.version||'atual')}.</span></div>`;
    $('#modalEyebrow').textContent=retrievalEngineEyebrow(o);
    if(target) target.innerHTML=`${snapshotNotice}<div class="retrieval-observability-summary">
      <article><small>Release / perfil</small><strong>${escapeHtml(o.release||'—')}</strong><span>${escapeHtml(retrievalProfileDisplay(o.profile||{}))}</span></article>
      <article><small>Qualidade híbrida</small><strong>${escapeHtml(retrievalMetricState(h.score,{cases,emptyLabel:'Não avaliada'}))}</strong><span>${cases>0?`recall ${retrievalMetricState(h.recall,{cases,suffix:'%'})} · grounding ${retrievalMetricState(h.grounding_rate,{cases,suffix:'%'})}`:`${formatNumber(cases)} Questões Ouro medidas`}</span></article>
      <article><small>Cobertura do índice</small><strong>${groundingMetric(index.coverage,'%')}</strong><span>${formatNumber(index.rag_chunks||0)} chunks · ${formatNumber(index.source_count||0)} fontes</span></article>
      <article><small>Estado do índice</small><strong>${escapeHtml(driftView.label)}</strong><span>${escapeHtml(driftView.detail)}</span></article>
    </div>
    <details class="retrieval-advanced-details"><summary>Mostrar detalhes técnicos e histórico</summary><div class="retrieval-advanced-details__body">
      <div class="retrieval-release-deltas"><strong>Comparação entre releases</strong><span>score ${observabilityDelta(cmp.deltas?.score,' p.p.')} · recall ${observabilityDelta(cmp.deltas?.recall,' p.p.')} · grounding ${observabilityDelta(cmp.deltas?.grounding_rate,' p.p.')} · cobertura ${observabilityDelta(cmp.deltas?.index_coverage,' p.p.')}</span></div>
      <div class="retrieval-observability-table"><table><thead><tr><th>Data</th><th>Release</th><th>Perfil</th><th>Score</th><th>Recall</th><th>Grounding</th><th>Cobertura</th><th>Drift</th></tr></thead><tbody>${trend||'<tr><td colspan="8">Ainda sem histórico temporal.</td></tr>'}</tbody></table></div>
      <div class="retrieval-subject-observability"><h4>Qualidade por matéria</h4><div class="retrieval-observability-table"><table><thead><tr><th>Matéria</th><th>Casos</th><th>Score</th><th>Recall</th><th>Grounding</th></tr></thead><tbody>${subjectRows||'<tr><td colspan="5">Amostra por matéria ainda insuficiente.</td></tr>'}</tbody></table></div></div>
    </div></details>
    <section class="retrieval-gold-expansion"><div><h4>Expandir dataset de regressão</h4><p>Questões sugeridas não entram no conjunto Ouro automaticamente. Cada inclusão exige sua confirmação.</p></div>${candidateHtml}</section>
    <p class="field-help">${escapeHtml(o.caveat||'')}</p>`;
    $$('[data-add-observability-gold]',target).forEach(button=>button.addEventListener('click',async()=>{
      const uid=button.dataset.addObservabilityGold||''; if(!uid) return;
      if(!window.confirm('Adicionar esta questão ao conjunto Ouro? Esta é uma aprovação humana explícita.')) return;
      setBusy(button,true,'Adicionando');
      try { const result=await bridge.call('add_gold_question',uid,'',`Incluída manualmente pela Observabilidade QuestFlow ${o.release||state.bootstrap?.app?.version||''}.`); if(!result?.ok) throw new Error(result?.error||'Falha ao adicionar Questão Ouro.'); toast('Questão adicionada ao conjunto Ouro.','success'); await loadRetrievalObservability(); }
      catch(error){toast(error.message,'error',7000);} finally{setBusy(button,false);}
    }));
  } catch(error) { if(target) target.innerHTML=emptyStateHtml({title:'Observabilidade indisponível',text:error.message,compact:true}); }
}

async function runRetrievalEvaluator(source='manual',button=null,busyLabel='Avaliando') {
  const started=await bridge.call('start_retrieval_evaluation',30,source);
  if(!started?.ok) throw new Error(started?.error||'Não foi possível iniciar o Evaluator Worker.');
  let job=started.job||{};
  const jobId=String(job.id||'');
  if(!jobId) throw new Error('O serviço de retrieval não retornou o identificador da avaliação.');
  const deadline=Date.now()+120000;
  while(['queued','running'].includes(String(job.status||'').toLowerCase())) {
    if(button) {
      const pct=Math.max(0,Math.min(100,Math.round(Number(job.progress||0)*100)));
      button.textContent=`${busyLabel} ${pct}%`;
    }
    if(Date.now()>deadline) throw new Error('A avaliação continua em execução. Feche a janela e consulte novamente em alguns instantes.');
    await new Promise(resolve=>setTimeout(resolve,550));
    const polled=await bridge.call('get_retrieval_evaluation_job',jobId);
    if(!polled?.ok) throw new Error(polled?.error||'Falha ao consultar o Evaluator Worker.');
    job=polled.job||{};
  }
  if(String(job.status||'').toLowerCase()==='failed') throw new Error(job.error||job.message||'A avaliação de retrieval falhou.');
  if(String(job.status||'').toLowerCase()!=='completed') throw new Error(job.message||'A avaliação não foi concluída.');
  return job;
}

async function recordRetrievalSnapshot() {
  const button=$('#recordRetrievalSnapshot'); setBusy(button,true,'Avaliando');
  try {
    await runRetrievalEvaluator('observability',button,'Avaliando');
    toast('Snapshot único publicado para Observabilidade e Quality Gates.','success');
    await loadRetrievalObservability();
  } catch(error){toast(error.message,'error',7000);} finally{setBusy(button,false);}
}

async function exportRetrievalObservability(format='json') {
  const result=await bridge.call('export_retrieval_observability_report',format,30);
  if(!result?.ok) return toast(result?.error||'Falha ao exportar relatório.','error',7000);
  downloadRetrievalReport(result.report||{});
}


function qualityGateStatusLabel(status='') {
  return ({pass:'APTO',promoted:'PROMOVIDO',overridden:'OVERRIDE',quarantine:'QUARENTENA',baseline_required:'BASELINE INICIAL',pending_evaluation:'NÃO AVALIADO'})[status] || String(status||'—').toUpperCase();
}

function qualityGateMetricRow(label,current,baseline,delta,limit,blocked=false,evaluable=true,evaluated=true) {
  const deltaText=delta==null?'—':observabilityDelta(delta,' p.p.');
  const gateLabel = !evaluated ? 'Não avaliado' : (!evaluable ? 'Aguardando amostra' : (blocked ? 'Bloqueado' : 'Dentro do limite'));
  const currentText = !evaluated && label !== 'Cobertura' ? 'Não avaliado' : (!evaluable && label !== 'Cobertura' ? 'Não avaliado' : groundingMetric(current, label==='Score'?'':'%'));
  return `<tr class="${blocked?'is-blocked':''} ${!evaluated||!evaluable?'is-pending':''}"><td>${escapeHtml(label)}</td><td>${currentText}</td><td>${groundingMetric(baseline, label==='Score'?'':'%')}</td><td>${escapeHtml(deltaText)}</td><td>${limit==null?'—':`${Number(limit).toFixed(1)} p.p.`}</td><td>${escapeHtml(gateLabel)}</td></tr>`;
}


async function openRetrievalQualityGate() {
  openModal({
    title:'Quality Gates de retrieval', eyebrow:`QuestFlow ${state.bootstrap?.app?.version || '—'} · proteção de qualidade`,
    body:'<div id="retrievalQualityGateBody"><div class="skeleton" style="height:18rem"></div></div>',
    footer:'<button class="button button--secondary" type="button" data-modal-close>Fechar</button><button class="button button--secondary" type="button" id="exportQualityGateJson">Exportar relatório</button><button class="button button--tertiary" type="button" id="toggleRetrievalAdminMode">Modo avançado</button><button class="button button--tertiary retrieval-admin-action" hidden type="button" id="rollbackQualityGate">Rollback</button><button class="button button--danger-ghost retrieval-admin-action" hidden type="button" id="overrideQualityGate">Override auditado</button><button class="button button--success retrieval-admin-action" hidden type="button" id="promoteQualityGate">Promover release</button><button class="button button--primary" type="button" id="reevaluateQualityGate">Reavaliar gates</button>',
    onOpen:()=>{
      $('#reevaluateQualityGate')?.addEventListener('click',()=>loadRetrievalQualityGate(true));
      $('#promoteQualityGate')?.addEventListener('click',promoteRetrievalRelease);
      $('#overrideQualityGate')?.addEventListener('click',overrideRetrievalQualityGate);
      $('#rollbackQualityGate')?.addEventListener('click',rollbackRetrievalQualityGate);
      $('#exportQualityGateJson')?.addEventListener('click',()=>exportRetrievalQualityGate('json'));
      $('#toggleRetrievalAdminMode')?.addEventListener('click',(event)=>{
        const actions=$$('.retrieval-admin-action',$('#modalFooter'));
        const show=actions.some(action=>action.hidden);
        actions.forEach(action=>action.hidden=!show);
        event.currentTarget.textContent=show?'Ocultar avançado':'Modo avançado';
        event.currentTarget.setAttribute('aria-pressed',show?'true':'false');
      });
      loadRetrievalQualityGate(false).catch(()=>{});
    },
  });
}

async function loadRetrievalQualityGate(force=false) {
  const target=$('#retrievalQualityGateBody'); const button=$('#reevaluateQualityGate');
  if(target) target.innerHTML='<div class="skeleton" style="height:18rem"></div>';
  setBusy(button,true,force?'Reavaliando gates':'Lendo último gate');
  try {
    if(force) {
      await runRetrievalEvaluator('quality_gate',button,'Reavaliando');
      toast('Uma única avaliação atualizou Observabilidade e Quality Gates.','success');
    }
    const result=await bridge.call('get_retrieval_quality_gate',30);
    if(!result?.ok) throw new Error(result?.error||'Não foi possível ler os Quality Gates.');
    const g=result.gate||{}; const cur=g.current||{}; const h=cur.hybrid||{}; const base=g.approved_baseline||g.comparison_baseline||{}; const bh=base.hybrid||{}; const deltas=g.comparison?.deltas||{}; const policy=g.policy||{};
    const blockers=Array.isArray(g.blockers)?g.blockers:[]; const warnings=Array.isArray(g.warnings)?g.warnings:[];
    const blocked=(metric)=>blockers.some(x=>x.metric===metric);
    const hasEvaluation=Boolean(g.evaluated_at) && g.status!=='pending_evaluation';
    const sampleEnough=Number(cur.cases||0) >= Number(policy.min_cases||3);
    const evaluable=hasEvaluation && sampleEnough;
    const statusClass=g.status==='pending_evaluation'?'is-pending':g.status==='quarantine'?'is-quarantine':(g.status==='promoted'||g.status==='pass'?'is-pass':g.status==='overridden'?'is-override':'');
    const blockerHtml=blockers.length?blockers.map(x=>`<li><strong>${escapeHtml(x.scope==='subject'?`${x.subject} · `:'')}${escapeHtml(x.metric||'gate')}</strong> — ${escapeHtml(x.reason||'bloqueado')}${x.delta!=null?` (${observabilityDelta(x.delta,' p.p.')})`:''}</li>`).join(''):'<li>Nenhum bloqueio acima dos limites.</li>';
    const warningHtml=warnings.length?warnings.map(x=>`<li>${escapeHtml(x.reason||x.metric||'aviso')}</li>`).join(''):'<li>Sem avisos adicionais.</li>';
    const rows=[
      qualityGateMetricRow('Score',h.score,bh.score,deltas.score,policy.score_drop_warn,blocked('score'),evaluable,hasEvaluation),
      qualityGateMetricRow('Recall',h.recall,bh.recall,deltas.recall,policy.recall_drop_warn,blocked('recall'),evaluable,hasEvaluation),
      qualityGateMetricRow('Grounding',h.grounding_rate,bh.grounding_rate,deltas.grounding_rate,policy.grounding_drop_warn,blocked('grounding_rate'),evaluable,hasEvaluation),
      qualityGateMetricRow('Cobertura',cur.index_coverage,base.index_coverage,deltas.index_coverage,policy.coverage_drop_warn,blocked('index_coverage'),hasEvaluation,hasEvaluation),
    ].join('');
    let gateExplanation;
    if(!hasEvaluation) gateExplanation=`<div class="quality-gate-explainer notice notice--warning"><strong>Esta release ainda não foi avaliada.</strong><span>A tela lê somente o Metrics Snapshot Store; nenhum benchmark é executado pela consulta. Clique em Reavaliar gates para acionar o Evaluator Worker da release ${escapeHtml(g.release||state.bootstrap?.app?.version||'atual')}.</span></div>`;
    else if(!sampleEnough) gateExplanation=`<div class="quality-gate-explainer notice notice--warning"><strong>Não há defeito de retrieval comprovado.</strong><span>Existem ${formatNumber(cur.cases||0)} Questões Ouro e são necessárias pelo menos ${formatNumber(policy.min_cases||3)} para medir Score, Recall e Grounding com segurança. O próximo passo é ampliar a amostra Ouro e reavaliar.</span></div>`;
    else gateExplanation=`<div class="quality-gate-explainer notice notice--info"><strong>Como ler esta tela</strong><span>O gate compara a release atual com a última baseline aprovada. Só bloqueia promoção quando há amostra suficiente e queda acima do limite configurado.</span></div>`;
    const baselineRelease=(g.approved_baseline||{}).release;
    const baselineSource=({approved_release:'Release aprovada',legacy_regression_baseline:'Baseline legada',none:'Nenhuma baseline aprovada'})[g.baseline_source]||String(g.baseline_source||'—');
    $('#modalEyebrow').textContent=retrievalEngineEyebrow(g);
    if(target) target.innerHTML=`${gateExplanation}<div class="retrieval-quality-gate-status ${statusClass}"><div><small>Status da release</small><strong>${escapeHtml(!hasEvaluation?'NÃO AVALIADO':(!sampleEnough&&g.status==='quarantine'?'AGUARDANDO AMOSTRA':qualityGateStatusLabel(g.status)))}</strong><span>${escapeHtml(g.message||'')}</span></div><div><small>Release avaliada</small><strong>${escapeHtml(g.release||'—')}</strong><span>${formatNumber(cur.cases||0)} Questões Ouro · perfil ${escapeHtml(retrievalProfileDisplay(g.profile||{}))}${g.evaluated_at?` · ${escapeHtml(formatDate(g.evaluated_at))}`:''}</span></div><div><small>Baseline aprovada</small><strong>${escapeHtml(baselineRelease||'Ainda não promovida')}</strong><span>${escapeHtml(baselineSource)}</span></div></div>
      <p class="field-help"><strong>O que fazer:</strong> ${!hasEvaluation?'clique em Reavaliar gates para executar o benchmark somente quando desejar.':(!sampleEnough?'adicione Questões Ouro representativas até atingir a amostra mínima; depois reavalie.':'se todos os limites estiverem aprovados, a promoção humana pode ser realizada no Modo avançado.')}</p>
      <details class="retrieval-advanced-details"><summary>Mostrar métricas, bloqueios e detalhes técnicos</summary><div class="retrieval-advanced-details__body">
        <div class="retrieval-observability-table quality-gate-table"><table><thead><tr><th>Métrica</th><th>Atual</th><th>Baseline</th><th>Δ</th><th>Limite de queda</th><th>Gate</th></tr></thead><tbody>${rows}</tbody></table></div>
        <div class="quality-gate-notes"><section><h4>Bloqueios</h4><ul>${blockerHtml}</ul></section><section><h4>Avisos</h4><ul>${warningHtml}</ul></section></div>
        <p class="field-help">Promoção nunca é automática. Override exige justificativa humana auditável. Rollback restaura a baseline/perfil de retrieval aprovado anterior; o rollback do executável continua protegido pelo atualizador seguro.</p>
      </div></details>`;
    const promote=$('#promoteQualityGate'); if(promote){promote.disabled=!g.can_promote; promote.title=g.can_promote?'Promover esta release e torná-la a nova baseline aprovada':'Os gates ainda não permitem promoção normal.';}
    const override=$('#overrideQualityGate'); if(override){override.disabled=!g.can_override; override.title=g.can_override?'Liberar excepcionalmente uma release em quarentena, registrando justificativa':'Override só fica disponível para release em quarentena com evidência mensurável.';}
    const rollback=$('#rollbackQualityGate'); if(rollback){rollback.disabled=!g.can_rollback; rollback.title=g.can_rollback?'Restaurar a baseline e o perfil da promoção anterior':'Ainda não existe promoção anterior para rollback.';}
  } catch(error){ if(target) target.innerHTML=emptyStateHtml({title:'Quality Gate indisponível',text:error.message,compact:true}); if(force) toast(error.message,'error',7000); }
  finally { setBusy(button,false); }
}

async function promoteRetrievalRelease() {
  if(!window.confirm('Promover esta release? Ela passará a ser a baseline aprovada para as próximas comparações de retrieval.')) return;
  const button=$('#promoteQualityGate'); setBusy(button,true,'Promovendo');
  try { const r=await bridge.call('promote_retrieval_release',30,'Promoção humana após aprovação explícita dos Quality Gates da release atual.'); if(!r?.ok) throw new Error(r?.error||'Falha ao promover release.'); toast('Release promovida e baseline aprovada atualizada.','success'); await loadRetrievalQualityGate(false); }
  catch(error){toast(error.message,'error',8000);} finally{setBusy(button,false);}
}

async function overrideRetrievalQualityGate() {
  const reason=window.prompt('Justifique o override humano da quarentena. A justificativa será registrada na auditoria:','');
  if(reason==null) return;
  if(String(reason).trim().length<15) return toast('Informe uma justificativa com pelo menos 15 caracteres.','error',7000);
  if(!window.confirm('Confirmar override? A release será promovida excepcionalmente apesar dos gates bloqueados.')) return;
  const button=$('#overrideQualityGate'); setBusy(button,true,'Registrando override');
  try { const r=await bridge.call('override_retrieval_quality_gate',String(reason).trim(),30); if(!r?.ok) throw new Error(r?.error||'Falha no override.'); toast('Override humano registrado e release promovida excepcionalmente.','warning',8000); await loadRetrievalQualityGate(false); }
  catch(error){toast(error.message,'error',8000);} finally{setBusy(button,false);}
}

async function rollbackRetrievalQualityGate() {
  if(!window.confirm('Restaurar a baseline e o perfil de retrieval da promoção anterior?')) return;
  const button=$('#rollbackQualityGate'); setBusy(button,true,'Restaurando');
  try { const r=await bridge.call('rollback_retrieval_release_gate'); if(!r?.ok) throw new Error(r?.error||'Falha no rollback do Quality Gate.'); if(!r.result?.restored) throw new Error(r.result?.warning||'Não existe promoção anterior para rollback.'); toast(`Retrieval restaurado para a baseline aprovada ${r.result.restored.release||'anterior'}.`,'success'); await loadRetrievalQualityGate(false); }
  catch(error){toast(error.message,'error',8000);} finally{setBusy(button,false);}
}

async function exportRetrievalQualityGate(format='json') {
  const result=await bridge.call('export_retrieval_quality_gate_report',format,30);
  if(!result?.ok) return toast(result?.error||'Falha ao exportar relatório dos Quality Gates.','error',7000);
  downloadRetrievalReport(result.report||{});
}

async function openCurrentQuestionInTutor() {
  if (!state.currentUid) return;
  state.tutorSelectedUid = state.currentUid;
  await navigate('tutor');
}

function renderQuestionIntelligence(intelligence = {}) {
  state.questionIntelligence = intelligence;
  const panel = $('#questionIntelligencePanel');
  if (!panel) return;
  const quality = intelligence.quality || {};
  const difficulty = intelligence.difficulty || {};
  const learning = intelligence.learning_model || {};
  const currency = intelligence.currency || {};
  const review = intelligence.curation_review || {};
  const duplicates = intelligence.duplicate_candidates || [];
  const missing = Array.isArray(quality.missing) ? quality.missing : [];
  const blockers = Array.isArray(review.blocking_missing) ? review.blocking_missing : [];
  const reviewBanner = intelligence.curation_status === 'pronta'
    ? '<div class="curation-review-state is-ready"><strong>✓ Curadoria concluída</strong><span>Esta questão não conta mais como pendência de revisão.</span></div>'
    : blockers.length
      ? `<div class="curation-review-state is-blocked"><strong>Por que esta questão ainda está pendente</strong><span>Clique em um requisito para ir exatamente ao campo que precisa ser corrigido.</span><div class="curation-blocker-links">${blockers.map(item=>curationIssueButtonHtml(item, { compact: true })).join('')}</div></div>`
      : review.can_complete_review
        ? `<div class="curation-review-state is-action"><strong>${review.auto_approved ? 'Aprovação automática não encerra a revisão humana' : 'Questão apta para concluir a revisão'}</strong><span>${review.auto_approved ? 'Ela pode ser usada no fluxo, mas ainda precisa da sua confirmação humana na Curadoria.' : 'Os campos críticos estão íntegros.'} Use “Concluir revisão”.</span></div>`
        : '<div class="curation-review-state"><strong>Curadoria ainda em análise</strong><span>Complete os requisitos mostrados abaixo para liberar a conclusão.</span></div>';
  const dupHtml = duplicates.length ? `<div class="duplicate-candidates"><strong>Candidatos a duplicidade</strong>${duplicates.map((item) => `<div class="duplicate-candidate" data-duplicate-id="${escapeHtml(item.id)}"><span><b>${escapeHtml(textOrMissing(item.code, 'Sem código'))}</b><small>${escapeHtml(textOrMissing(item.subject, 'Matéria não informada'))} · ${Number(item.similarity || 0).toFixed(1)}% semelhante</small></span><div><button type="button" class="button button--small button--secondary" data-open-duplicate="${escapeHtml(item.uid)}">Comparar</button><button type="button" class="button button--small" data-confirm-duplicate="${escapeHtml(item.id)}">Marcar duplicata</button><button type="button" class="button button--small button--tertiary" data-dismiss-duplicate="${escapeHtml(item.id)}">Não é duplicata</button></div></div>`).join('')}</div>` : '<p class="curation-ok">Nenhuma duplicidade forte aberta para esta questão.</p>';
  panel.innerHTML = `${reviewBanner}<div class="intelligence-cards">
    <div><span>Qualidade editorial</span><strong>${Number(quality.score || 0).toFixed(0)}/100 · ${escapeHtml(quality.grade || '—')}</strong><small>${escapeHtml(intelligenceLabel(quality.status || intelligence.curation_status, 'curation'))}</small></div>
    <div><span>Origem</span><strong>${escapeHtml(intelligenceLabel(intelligence.origin_type, 'origin'))}</strong><small>${escapeHtml(intelligence.rights_status || 'origem não verificada')}</small></div>
    <div><span>Dificuldade real</span><strong>${escapeHtml(intelligenceLabel(difficulty.label, 'difficulty'))}</strong><small>${difficulty.accuracy == null ? 'Ainda sem respostas' : `${Number(difficulty.accuracy).toFixed(1)}% de acerto · amostra ${escapeHtml(difficulty.confidence || '—')}`}</small></div>
    <div><span>Comentário</span><strong>${escapeHtml(intelligenceLabel(intelligence.commentary_source, 'commentary'))}</strong><small>${formatNumber(intelligence.attempts?.attempts || 0)} tentativa(s) registradas</small></div>
    <div><span>Domínio estimado (KT)</span><strong>${learning.mastery == null ? 'Sem evidência' : `${(Number(learning.mastery) * 100).toFixed(0)}%`}</strong><small>${escapeHtml(textOrMissing(learning.mastery_label, 'Aguardando histórico'))}${learning.mastery_confidence != null ? ` · confiança ${(Number(learning.mastery_confidence) * 100).toFixed(0)}%` : ''}</small></div>
    <div><span>IRT pessoal</span><strong>${escapeHtml(textOrMissing(learning.item_difficulty_label, 'Sem dados'))}</strong><small>${learning.theta_scale == null ? 'Habilidade ainda não estimada' : `habilidade ${Number(learning.theta_scale).toFixed(0)}/100 · informação ${Number(learning.item_information || 0).toFixed(2)}`}</small></div>
    <div><span>Atualidade</span><strong>${escapeHtml(textOrMissing(currency.label, 'Vigente'))}</strong><small>${escapeHtml(textOrMissing(currency.reason, currency.reference_date ? `Referência ${currency.reference_date}` : 'Sem alerta temporal'))}</small></div>
  </div>
  ${missing.length ? `<div class="quality-checklist"><strong>Para elevar a qualidade</strong><span>Os itens abaixo são atalhos para os campos correspondentes.</span><div class="curation-quality-links">${missing.map((item) => curationIssueButtonHtml(item, { compact: true })).join('')}</div></div>` : '<div class="quality-checklist is-ok"><strong>Checklist editorial completo</strong><span>A questão possui os principais metadados e elementos pedagógicos esperados.</span></div>'}
  ${dupHtml}`;
  bindCurationIssueJumps(panel);
  $$('[data-open-duplicate]', panel).forEach((button) => button.addEventListener('click', async () => {
    const uid = button.dataset.openDuplicate;
    if (!uid) return;
    await selectQuestion(uid);
  }));
  $$('[data-confirm-duplicate]', panel).forEach((button) => button.addEventListener('click', async () => {
    const result = await bridge.call('resolve_duplicate_candidate', button.dataset.confirmDuplicate, true);
    if (result?.ok) {
      toast('Candidato marcado como duplicata. Nenhuma questão foi apagada.', 'success');
      await loadQuestionIntelligence(state.selectedQuestionUid, false);
      await loadBankIntelligence();
    } else {
      toast(result?.error || 'Não foi possível confirmar a duplicidade.', 'error');
    }
  }));

  $$('[data-dismiss-duplicate]', panel).forEach((button) => button.addEventListener('click', async () => {
    const result = await bridge.call('resolve_duplicate_candidate', button.dataset.dismissDuplicate, false);
    if (result.ok) { toast('Candidato descartado sem remover nenhuma questão.', 'success'); await loadQuestionIntelligence(state.currentUid, { scanDuplicates: false }); }
  }));
}

async function loadQuestionIntelligence(uid = state.currentUid, { scanDuplicates = true } = {}) {
  if (!uid || uid !== state.currentUid) return;
  const panel = $('#questionIntelligencePanel');
  if (panel) panel.innerHTML = '<div class="skeleton" style="height:5rem"></div>';
  try {
    const result = await bridge.call('get_question_intelligence', uid, scanDuplicates);
    if (!result.ok) throw new Error(result.error || 'Falha ao analisar a questão.');
    if (uid !== state.currentUid) return;
    renderQuestionIntelligence(result.intelligence || {});
  } catch (error) {
    if (panel && uid === state.currentUid) panel.innerHTML = emptyStateHtml({ text: error.message, compact: true });
  }
}

async function showAiCommentaryBrief() {
  if (!state.currentUid) return;
  try {
    const result = await bridge.call('get_ai_commentary_brief', state.currentUid);
    if (!result.ok) throw new Error(result.error || 'Não foi possível montar o contexto.');
    const brief = result.brief || {};
    const context = brief.context || {};
    const retrievalItems = Array.isArray(brief.hybrid_retrieval?.items) ? brief.hybrid_retrieval.items : [];
    const retrievalHtml = retrievalItems.length ? `<div class="hybrid-evidence-list"><strong>Evidências recuperadas no índice híbrido local</strong>${retrievalItems.map((item) => `<article><div><b>${escapeHtml(item.title || 'Contexto local')}</b><span>${Number((item.scores?.score || 0) * 100).toFixed(0)}% relevância</span></div><p>${escapeHtml(String(item.content || '').slice(0, 700))}</p></article>`).join('')}</div>` : '<div class="network-note">Nenhuma evidência local adicional atingiu o limiar de relevância.</div>';
    openModal({
      title: 'Contexto auditável para IA', eyebrow: 'RAG híbrido / evidências',
      body: `<div class="ai-brief"><p>${escapeHtml(brief.instruction || '')}</p><dl>${Object.entries(context).filter(([, value]) => value != null && String(value).length).map(([key, value]) => `<div><dt>${escapeHtml(key.replaceAll('_', ' '))}</dt><dd>${escapeHtml(Array.isArray(value) ? value.join(' | ') : String(value))}</dd></div>`).join('')}</dl>${retrievalHtml}<div class="network-note"><strong>Política:</strong> ${escapeHtml(brief.publication_policy || 'rascunho requer revisão humana')}. Evidências recomendadas: ${escapeHtml((brief.recommended_evidence || []).join(' • '))}.</div></div>`,
      footer: '<button class="button button--secondary" data-modal-close>Fechar</button>',
    });
  } catch (error) { toast(error.message, 'error'); }
}

async function showKnowledgeGraph() {
  if (!state.currentUid) return;
  try {
    const result = await bridge.call('get_question_knowledge_graph', state.currentUid);
    if (!result.ok) throw new Error(result.error || 'Não foi possível montar o grafo da questão.');
    const graph = result.graph || {};
    const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
    const edges = Array.isArray(graph.edges) ? graph.edges : [];
    const byId = new Map(nodes.map((node) => [String(node.id), node]));
    openModal({
      title: 'Mapa de conceitos da questão', eyebrow: 'Taxonomia em grafo',
      body: `<div class="knowledge-graph-view">
        <div class="knowledge-node-cloud">${nodes.length ? nodes.map((node) => `<span data-node-type="${escapeHtml(node.node_type || node.type || 'conceito')}"><small>${escapeHtml(node.node_type || node.type || 'conceito')}</small>${escapeHtml(node.label || '')}</span>`).join('') : '<p class="muted">Nenhum conceito estruturado nesta questão.</p>'}</div>
        <div class="knowledge-edge-list"><strong>Relações</strong>${edges.length ? edges.map((edge) => { const left = byId.get(String(edge.source_node_id || edge.source)); const right = byId.get(String(edge.target_node_id || edge.target)); return `<div><span>${escapeHtml(left?.label || edge.source_node_id || edge.source || '—')}</span><b>${escapeHtml(edge.relation || 'relaciona')}</b><span>${escapeHtml(right?.label || edge.target_node_id || edge.target || '—')}</span></div>`; }).join('') : '<span class="muted">Sem relações explícitas adicionais.</span>'}</div>
      </div>`,
      footer: '<button class="button button--secondary" data-modal-close>Fechar</button>',
    });
  } catch (error) { toast(error.message, 'error'); }
}

async function showHybridEvidence() {
  if (!state.currentUid) return;
  try {
    const question = state.originalQuestion || {};
    const query = [question.materia, question.assunto, question.enunciado].filter(Boolean).join(' ').slice(0, 2600);
    const result = await bridge.call('get_rag_context', state.currentUid, query, 10);
    if (!result.ok) throw new Error(result.error || 'Não foi possível recuperar evidências.');
    const retrieval = result.retrieval || {};
    const items = Array.isArray(retrieval.items) ? retrieval.items : [];
    openModal({
      title: 'Evidências híbridas', eyebrow: retrieval.engine || 'RAG local',
      body: `<div class="hybrid-evidence-list">${items.length ? items.map((item, index) => `<article><div><b>${index + 1}. ${escapeHtml(item.title || item.source_ref || 'Fonte local')}</b><span>${Number((item.scores?.score || 0) * 100).toFixed(0)}%</span></div><small>${escapeHtml([item.subject, item.topic].filter(Boolean).join(' · '))}</small><p>${escapeHtml(String(item.content || '').slice(0, 1200))}</p><footer>lexical ${Number((item.scores?.lexical || 0) * 100).toFixed(0)}% · semântico ${Number((item.scores?.semantic || 0) * 100).toFixed(0)}% · metadados ${Number((item.scores?.metadata || 0) * 100).toFixed(0)}%</footer></article>`).join('') : '<p class="muted">Nenhum chunk relevante foi recuperado.</p>'}</div>`,
      footer: '<button class="button button--secondary" data-modal-close>Fechar</button>',
    });
  } catch (error) { toast(error.message, 'error'); }
}

async function assistCommentaryWithAi() {
  if (!state.currentUid) return;
  const button = $('#assistCommentaryAi');
  setBusy(button, true, 'Pesquisando e preparando rascunho');
  try {
    const started = await bridge.call('start_ai_commentary_assist', state.currentUid);
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a assistência por IA.');
    const result = await monitorTask(started.task_id, (task) => {
      if (task.message) $('#editorValidation').textContent = task.message;
    }, { timeoutMs: 600000, intervalMs: 700 });
    const draft = String(result.explanation || '').trim();
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    const sources = Array.isArray(result.sources) ? result.sources : [];
    const evaluation = result.evaluation || {};
    const flags = Array.isArray(evaluation.flags) ? evaluation.flags : [];
    openModal({
      title: 'Rascunho assistido por IA', eyebrow: result.provider || 'IA assistida',
      body: `<div class="ai-draft-review"><div class="network-note"><strong>Revisão obrigatória:</strong> este texto é um rascunho auditado. Confira gabarito, fundamento e fontes antes de aceitar.</div>${warnings.length ? `<div class="validation-message is-error">${escapeHtml(warnings.join(' • '))}</div>` : ''}<div class="evaluation-grid"><div><span>Fundamentação</span><strong>${Number(evaluation.groundedness || 0).toFixed(0)}</strong></div><div><span>Gabarito</span><strong>${Number(evaluation.answer_alignment || 0).toFixed(0)}</strong></div><div><span>Fontes</span><strong>${Number(evaluation.source_coverage || 0).toFixed(0)}</strong></div><div><span>Pedagogia</span><strong>${Number(evaluation.pedagogical_quality || 0).toFixed(0)}</strong></div></div>${flags.length ? `<div class="evaluation-flags"><strong>Alertas do avaliador independente</strong>${flags.map((flag) => `<span>${escapeHtml(flag)}</span>`).join('')}</div>` : ''}<textarea id="aiDraftText" rows="14">${escapeHtml(draft)}</textarea><div class="ai-source-list"><strong>Fontes/sinais recuperados</strong>${sources.length ? sources.map((item) => `<span>${escapeHtml(item.provider || 'Fonte')} · ${escapeHtml(item.title || item.url || 'resultado')}</span>`).join('') : '<span>Nenhuma fonte estruturada retornada.</span>'}</div></div>`,
      footer: '<button class="button button--secondary" data-modal-close>Manter como rascunho</button><button class="button button--primary" id="acceptAiDraft">Usar como explicação</button>',
      onOpen: () => $('#acceptAiDraft')?.addEventListener('click', async () => {
        const text = $('#aiDraftText')?.value.trim() || '';
        if (!text) return toast('O rascunho está vazio.', 'warning');
        $('#explanationInput').value = text;
        const sourceField = $('#field-origem_comentario');
        if (sourceField) sourceField.value = 'ia_assistida';
        if (result.interaction_id) {
          try {
            await bridge.call('review_ai_interaction', result.interaction_id, 'aprovar', 'Rascunho aceito explicitamente na Curadoria como explicação; a questão ainda requer salvamento editorial.');
          } catch (auditError) { console.warn('Auditoria da aceitação do rascunho:', auditError); }
        }
        markDirty(); autoResize($('#explanationInput')); updateCharacterCounts(); closeModal();
        toast('Rascunho aceito e registrado na auditoria. Revise e salve/aprove a questão quando estiver correto.', 'success');
      }, { once: true }),
    });
  } catch (error) {
    toast(error.message, 'error', 7000);
  } finally { setBusy(button, false); }
}

async function researchCommentaryOnGoogle() {
  if (!state.currentUid) return toast('Selecione uma questão antes de pesquisar.', 'warning');
  const button = $('#researchGoogleCommentary');
  const explanationField = $('#explanationInput');
  const existing = String(explanationField?.value || '').trim();
  if (existing) {
    const replace = window.confirm('Esta questão já possui uma explicação. Deseja substituir o texto atual pelo resultado pesquisado no Google?\n\nO QuestFlow não salvará a substituição automaticamente.');
    if (!replace) return;
  }
  setBusy(button, true, 'Pesquisando no Google');
  try {
    const started = await bridge.call('start_google_commentary_research', state.currentUid, collectQuestionForm());
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a pesquisa no Google.');
    const result = await monitorTask(started.task_id, (task) => {
      if (task.message) {
        const validation = $('#editorValidation');
        if (validation) { validation.textContent = task.message; validation.className = 'validation-message'; }
      }
    }, { timeoutMs: 600000, intervalMs: 700 });
    const text = String(result.explanation || '').trim();
    if (!text) throw new Error('O Google não retornou uma explicação utilizável para esta questão.');
    if (explanationField) {
      explanationField.value = text;
      autoResize(explanationField);
    }
    const sourceField = $('#field-origem_comentario');
    if (sourceField) sourceField.value = 'ia_assistida';
    state.pendingEditorialAiInteractionId = result.interaction_id || null;
    markDirty();
    updateCharacterCounts();

    const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
    const sources = Array.isArray(result.sources) ? result.sources : [];
    const googleAnswer = String(result.suggested_answer || '').trim();
    const officialAnswer = String(result.official_answer || '').trim();
    const evaluation = result.evaluation || {};
    const sourceSummary = sources.slice(0, 6).map((item) =>
      `<li><strong>${escapeHtml(item.provider || 'Google')}</strong> · ${escapeHtml(item.title || item.url || 'fonte pesquisada')}</li>`
    ).join('');
    openModal({
      title: 'Resposta pesquisada no Google adicionada',
      eyebrow: 'IA assistida + revisão humana',
      body: `<div class="ai-draft-review">
        <div class="network-note"><strong>Texto preenchido no editor.</strong> Confira a explicação e depois use “Salvar rascunho” ou “Concluir revisão”. Nada foi salvo automaticamente.</div>
        <div class="evaluation-grid">
          <div><span>Correspondência</span><strong>${result.verified_match ? 'Verificada' : 'Revisar'}</strong></div>
          <div><span>Gabarito local</span><strong>${escapeHtml(officialAnswer || '—')}</strong></div>
          <div><span>Gabarito encontrado</span><strong>${escapeHtml(googleAnswer || '—')}</strong></div>
          <div><span>Avaliação</span><strong>${Number(evaluation.overall_score || 0).toFixed(0)}</strong></div>
          <div><span>Confiança da extração</span><strong>${Math.round(Number(result.explanation_confidence || 0) * 100)}%</strong></div>
          <div><span>Método</span><strong>${escapeHtml(String(result.explanation_method || 'extração focada').replaceAll('_', ' '))}</strong></div>
          <div><span>Ruído descartado</span><strong>${Number(result.noise_removed || 0)}</strong></div>
        </div>
        ${warnings.length ? `<div class="evaluation-flags"><strong>Alertas</strong>${warnings.map((item) => `<span>${escapeHtml(item)}</span>`).join('')}</div>` : ''}
        <div class="ai-source-list"><strong>Fontes/sinais da pesquisa</strong>${sourceSummary ? `<ul>${sourceSummary}</ul>` : '<span>Nenhuma fonte estruturada foi retornada.</span>'}</div>
      </div>`,
      footer: '<button class="button button--primary" data-modal-close>Conferir no editor</button>',
    });
    const validation = $('#editorValidation');
    if (validation) {
      const confidence = Math.round(Number(result.explanation_confidence || 0) * 100);
      validation.textContent = `Explicação adicionada para revisão humana · confiança automática ${confidence}% · ${Number(result.noise_removed || 0)} item(ns) de ruído removido(s).`;
      validation.className = confidence >= 62 ? 'validation-message is-success' : 'validation-message is-warning';
    }
    toast('Explicação preenchida e origem definida como “IA assistida + revisão humana”. Revise antes de salvar.', 'success', 7500);
  } catch (error) {
    const validation = $('#editorValidation');
    if (validation) { validation.textContent = error.message; validation.className = 'validation-message is-error'; }
    toast(error.message, 'error', 9000);
  } finally {
    setBusy(button, false);
  }
}

function applyQuestionHeaderCollapsed(collapsed, persist = true) {
  state.questionHeaderCollapsed = Boolean(collapsed);
  const editor = $('#questionEditor');
  const button = $('#toggleQuestionHeader');
  editor?.classList.toggle('is-header-collapsed', state.questionHeaderCollapsed);
  if (button) {
    button.textContent = state.questionHeaderCollapsed ? '⌄' : '⌃';
    button.setAttribute('aria-expanded', state.questionHeaderCollapsed ? 'false' : 'true');
    button.setAttribute('aria-label', state.questionHeaderCollapsed ? 'Mostrar detalhes da questão' : 'Recolher detalhes da questão');
    button.title = state.questionHeaderCollapsed ? 'Mostrar detalhes da questão' : 'Recolher detalhes da questão';
  }
  if (persist) localStorage.setItem('qf-question-header-collapsed', state.questionHeaderCollapsed ? '1' : '0');
}

function databaseHealthTone(health) {
  if (health?.synchronized && health?.local_healthy) return 'success';
  if (!health?.local_healthy) return 'danger';
  if (!health?.cloud_reachable || !health?.counts_equal || Number(health?.status?.pending || 0) > 0) return 'warning';
  return 'neutral';
}

function cloudOperationLabel(value) {
  return String(value || '') === 'delete' ? 'Exclusão' : 'Alteração';
}

function renderSyncQueueGroups(queue) {
  const groups = Array.isArray(queue?.groups) ? queue.groups : [];
  if (!groups.length) return '<span class="muted">Nenhuma alteração local pendente.</span>';
  return groups.map((group) => `<span class="sync-queue-chip${Number(group.errors || 0) ? ' sync-queue-chip--error' : ''}"><strong>${formatNumber(group.count || 0)}</strong> ${escapeHtml(group.label || group.table_name || 'Dados')} · ${escapeHtml(cloudOperationLabel(group.operation))}${Number(group.errors || 0) ? ` · ${formatNumber(group.errors)} com erro` : ''}</span>`).join('');
}

function renderSyncQueueItems(queue) {
  const items = Array.isArray(queue?.items) ? queue.items : [];
  if (!items.length) return '';
  return `<div class="sync-pending-list">${items.map((item) => `<div class="sync-pending-row">
    <div><strong>${escapeHtml(item.label || item.table_name || 'Alteração')}</strong><span>${escapeHtml(item.row || 'Registro local')}</span></div>
    <div><span>${escapeHtml(cloudOperationLabel(item.operation))}</span><small>${escapeHtml(item.changed_at ? formatDate(item.changed_at) : 'data não registrada')}</small></div>
    <div class="sync-pending-attempt"><strong>${formatNumber(item.attempts || 0)}</strong><small>tentativa(s)</small></div>
    ${item.last_error ? `<div class="sync-pending-error"><strong>Erro</strong><span>${escapeHtml(item.last_error)}</span></div>` : ''}
  </div>`).join('')}</div>`;
}

async function showCloudSyncPendingDetails() {
  try {
    const result = await bridge.call('get_cloud_sync_pending', 120);
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível ler a fila de sincronização.');
    const queue = result.queue || {};
    openModal({
      title: `Alterações locais pendentes · ${formatNumber(queue.total || 0)}`,
      eyebrow: 'Cloud Sync · diagnóstico da outbox',
      body: `<div class="stack">
        <p>Esta lista mostra <strong>o que ainda não foi confirmado no Turso</strong>. A igualdade da quantidade de questões não representa estes outros registros de estudo/editoriais.</p>
        <div class="sync-queue-groups">${renderSyncQueueGroups(queue)}</div>
        ${queue.with_error ? `<div class="notice notice--danger"><strong>${formatNumber(queue.with_error)} registro(s) já falharam em pelo menos uma tentativa.</strong><span>O erro de cada item aparece abaixo.</span></div>` : ''}
        ${queue.deadletter ? `<div class="notice notice--warning"><strong>${formatNumber(queue.deadletter)} item(ns) foram colocados em quarentena técnica.</strong><span>Eles não bloqueiam mais a fila ativa e permanecem preservados localmente para auditoria.</span></div>` : ''}
        ${renderSyncQueueItems(queue) || '<div class="empty-state"><strong>Fila ativa vazia.</strong><span>Não há alterações locais aguardando envio.</span></div>'}
      </div>`,
      footer: `<button class="button button--secondary" data-modal-close>Fechar</button>${Number(queue.total || 0) ? '<button class="button button--primary" id="syncPendingFromModal">Sincronizar agora</button>' : ''}`,
      onOpen: () => $('#syncPendingFromModal')?.addEventListener('click', async () => { closeModal(); await syncCloudNow({ refreshHealth: true }); }),
    });
  } catch (error) { toast(error.message || 'Não foi possível abrir as pendências.', 'error', 8000); }
}

function renderDatabaseHealth(health) {
  const container = $('#databaseHealthPanel');
  if (!container) return;
  const tone = databaseHealthTone(health);
  const localCount = formatNumber(health?.local_question_count ?? 0);
  const remoteCount = health?.remote_question_count == null ? 'Não verificado' : formatNumber(health.remote_question_count);
  const status = health?.status || {};
  const queue = health?.queue || { total: Number(status.pending || 0), groups: [], items: [] };
  const pending = Number(queue.total ?? status.pending ?? 0);
  const conflicts = Number(status.conflicts ?? 0);
  const lastError = String(status.last_error || '').trim();
  const lastSync = status.last_sync_at ? formatDate(status.last_sync_at) : 'Ainda não registrada';
  const lastAttempt = status.last_attempt_at ? formatDate(status.last_attempt_at) : 'Ainda não registrada';
  const localLabel = health?.local_healthy ? 'Saudável' : 'Atenção';
  const activationCompleted = Boolean(health?.activation?.completed || status?.activation?.completed);
  const activationRequired = Boolean((health?.activation?.required || status?.activation?.required) && !activationCompleted);
  const cloudLabel = health?.synchronized ? 'Sincronizado' : activationRequired ? 'Aguardando ativação segura' : lastError ? 'Falha na última tentativa' : pending ? 'Fila pendente' : health?.cloud_reachable ? 'Conferindo eventos' : 'Não verificado';
  const countMatch = health?.counts_equal ? 'Questões iguais' : health?.remote_question_count == null ? 'Aguardando Turso' : 'Questões diferentes';
  const headline = health?.synchronized && health?.local_healthy
    ? 'Banco saudável, atualizado e totalmente sincronizado'
    : textOrMissing(health?.message, 'Verificação do banco concluída.');
  const questionCountNote = health?.counts_equal && pending
    ? 'A quantidade de questões é igual, mas ainda há outros registros locais aguardando confirmação.'
    : health?.counts_equal ? 'Questões local = Turso' : 'Apenas a contagem de questões está sendo comparada aqui.';
  const pendingBlock = pending || lastError || Number(queue.deadletter || 0) ? `
    <div class="sync-queue-panel">
      <div class="sync-queue-header">
        <div><strong>${pending ? `${formatNumber(pending)} alteração(ões) local(is) aguardando sincronização` : 'Diagnóstico da sincronização'}</strong><span>${pending ? 'Veja exatamente quais tipos de dados estão na fila.' : 'A fila ativa está vazia, mas há informação de diagnóstico.'}</span></div>
        <div class="sync-queue-actions">${activationRequired ? '<button class="button button--primary button--compact" id="databaseSafeActivate" type="button">Ativar Cloud Sync</button>' : pending ? '<button class="button button--primary button--compact" id="databaseSyncNow" type="button">Sincronizar agora</button>' : ''}<button class="button button--secondary button--compact" id="databaseShowPending" type="button">Ver detalhes</button></div>
      </div>
      <div class="sync-queue-groups">${renderSyncQueueGroups(queue)}</div>
      ${lastError ? `<div class="sync-error-box"><strong>Último erro de sincronização</strong><span>${escapeHtml(lastError)}</span><small>Última tentativa: ${escapeHtml(lastAttempt)}</small></div>` : ''}
      ${Number(queue.deadletter || 0) ? `<div class="sync-deadletter-note"><strong>${formatNumber(queue.deadletter)} item(ns) em quarentena técnica</strong><span>Eventos antigos/impossíveis de transmitir foram preservados fora da fila ativa para não deixá-la travada.</span></div>` : ''}
      <details class="sync-queue-details"${Number(queue.with_error || 0) ? ' open' : ''}><summary>Mostrar amostra das alterações pendentes</summary>${renderSyncQueueItems(queue) || '<p class="muted">Nenhum item ativo na fila.</p>'}</details>
    </div>` : '';
  container.innerHTML = `<div class="database-health-summary database-health-summary--${escapeHtml(tone)}">
    <div class="database-health-main">
      <span class="database-health-icon" aria-hidden="true">${tone === 'success' ? '✓' : tone === 'danger' ? '!' : '↻'}</span>
      <div><strong>${escapeHtml(headline)}</strong><span>${escapeHtml(textOrMissing(health?.message, headline))}</span></div>
    </div>
    <div class="database-health-grid">
      <div><span>Banco local</span><strong>${escapeHtml(localLabel)}</strong><small>quick_check: ${escapeHtml(textOrMissing(health?.quick_check, 'não executado'))}</small></div>
      <div><span>Questões locais</span><strong>${localCount}</strong><small>SQLite deste computador</small></div>
      <div><span>Questões no Turso</span><strong>${remoteCount}</strong><small>Somente questões</small></div>
      <div><span>Comparação de questões</span><strong>${escapeHtml(countMatch)}</strong><small>${escapeHtml(questionCountNote)}</small></div>
      <div><span>Cloud Sync</span><strong>${escapeHtml(cloudLabel)}</strong><small>${formatNumber(pending)} eventos pendentes · ${formatNumber(conflicts)} conflitos</small></div>
      <div><span>Última sincronização concluída</span><strong>${escapeHtml(lastSync)}</strong><small>${health?.synchronized ? 'Estado confirmado' : `Última tentativa: ${escapeHtml(lastAttempt)}`}</small></div>
    </div>
    ${pendingBlock}
  </div>`;
  $('#databaseSyncNow')?.addEventListener('click', () => syncCloudNow({ refreshHealth: true }));
  $('#databaseSafeActivate')?.addEventListener('click', openCloudSafeActivation);
  $('#databaseShowPending')?.addEventListener('click', showCloudSyncPendingDetails);
}

async function loadDatabaseHealth({ quiet = false } = {}) {
  const container = $('#databaseHealthPanel');
  if (!container) return;
  if (state.databaseHealthPromise) return state.databaseHealthPromise;
  if (!quiet) container.innerHTML = '<div class="skeleton" style="height:4.5rem"></div>';
  state.databaseHealthPromise = (async () => {
    try {
      const result = await bridge.call('get_database_health');
      if (!result?.ok) throw new Error(result?.error || 'Não foi possível verificar os bancos.');
      renderDatabaseHealth(result.health || {});
      return result;
    } catch (error) {
      if (!quiet) {
        container.innerHTML = `<div class="database-health-summary database-health-summary--warning"><div class="database-health-main"><span class="database-health-icon" aria-hidden="true">!</span><div><strong>Verificação incompleta</strong><span>${escapeHtml(error.message || 'Não foi possível comparar o banco local com o Turso.')}</span></div></div></div>`;
      }
      return null;
    } finally {
      state.databaseHealthPromise = null;
    }
  })();
  return state.databaseHealthPromise;
}

async function requestSafeClose() {
  const unsaved = state.dirty ? '<p class="text-warning"><strong>Atenção:</strong> existem alterações visuais não salvas no editor atual.</p>' : '';
  openModal({
    title: 'Fechar QuestFlow com segurança',
    eyebrow: 'Encerramento protegido',
    body: `<div class="stack">${identityPicture('empty-state-art empty-state-art--small', true)}<p>O QuestFlow vai interromper novos trabalhos, finalizar o fluxo do Telegram, tentar sincronizar pendências com o Turso, executar checkpoint do WAL e verificar o SQLite antes de encerrar.</p>${unsaved}<p class="muted">Se a Internet estiver indisponível, as alterações continuam preservadas na fila local e serão sincronizadas na próxima abertura.</p></div>`,
    footer: '<button class="button button--secondary" type="button" data-modal-close>Cancelar</button><button class="button button--danger" type="button" id="confirmSafeClose">Sincronizar e fechar</button>',
    onOpen: (layer) => {
      const confirm = $('#confirmSafeClose', layer);
      confirm?.addEventListener('click', async () => {
        if (confirm) { confirm.disabled = true; confirm.textContent = 'Fechando com segurança…'; }
        $('#modalBody').innerHTML = '<div class="closing-state"><div class="closing-spinner" aria-hidden="true"></div><h3>Finalizando QuestFlow…</h3><p>Salvando o banco local, sincronizando o Turso e fechando conexões. Não force o encerramento por alguns segundos.</p></div>';
        try {
          await bridge.call('request_close');
          setSystemStatus('Fechamento seguro em andamento…', 'loading');
        } catch (error) {
          toast(error.message || 'Não foi possível iniciar o fechamento seguro.', 'error', 8000);
          closeModal();
        }
      }, { once: true });
    },
  });
}

function analyticsPct(value, digits = 0) {
  return value == null || Number.isNaN(Number(value)) ? '—' : `${Number(value).toFixed(digits)}%`;
}

function analyticsRelativeReview(days) {
  if (days == null || Number.isNaN(Number(days))) return 'Ainda não revisada';
  const value = Number(days);
  if (value < 1 / 24) return 'há menos de 1h';
  if (value < 1) return `há ${Math.max(1, Math.round(value * 24))}h`;
  if (value < 2) return 'ontem';
  return `há ${Math.round(value)} dias`;
}

function analyticsTrendText(delta) {
  if (delta == null || Number.isNaN(Number(delta))) return 'Sem janela anterior';
  const value = Number(delta);
  if (Math.abs(value) < 1) return 'Estável';
  return `${value > 0 ? '↑' : '↓'} ${Math.abs(value).toFixed(0)} p.p.`;
}

function analyticsTrendClass(delta) {
  return delta == null ? '' : Number(delta) >= 1 ? 'text-success' : Number(delta) <= -1 ? 'text-danger' : '';
}

function analyticsSparkline(points, label) {
  const rows = Array.isArray(points) ? points.filter((item) => Number.isFinite(Number(item.accuracy))) : [];
  if (!rows.length) return `<div class="subject-trend-empty">Ainda não existe uma janela com respostas.</div>`;
  if (rows.length === 1) {
    const value = Math.max(0, Math.min(100, Number(rows[0].accuracy)));
    return `<div class="subject-trend-baseline" role="img" aria-label="${escapeHtml(label)}: linha de base de ${value.toFixed(0)} por cento">
      <span>Linha de base</span><strong>${value.toFixed(0)}%</strong><small>${escapeHtml(rows[0].label || 'Janela inicial')} · ${formatNumber(rows[0].attempts || 0)} respostas</small>
    </div>`;
  }
  const width = 260, height = 58, pad = 5;
  const values = rows.map((item) => Math.max(0, Math.min(100, Number(item.accuracy))));
  const min = Math.max(0, Math.min(...values) - 8);
  const max = Math.min(100, Math.max(...values) + 8);
  const span = Math.max(10, max - min);
  const coords = values.map((value, index) => {
    const x = pad + (index * (width - pad * 2) / Math.max(1, values.length - 1));
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return [x, y];
  });
  const polyline = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const dots = coords.map(([x, y], index) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5"><title>${escapeHtml(rows[index].label || '')}: ${values[index].toFixed(0)}% (${formatNumber(rows[index].attempts || 0)} respostas)</title></circle>`).join('');
  return `<div class="subject-trend-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}"><polyline points="${polyline}" vector-effect="non-scaling-stroke"></polyline>${dots}</svg>
      <div class="subject-trend-axis"><span>${escapeHtml(rows[0].label || '')}</span><span>${escapeHtml(rows.at(-1)?.label || '')}</span></div>
    </div>`;
}

function analyticsWeakAreaHtml(items, empty) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return `<span class="muted">${escapeHtml(empty)}</span>`;
  return rows.map((item) => `<span class="analytics-chip"><strong>${escapeHtml(textOrMissing(item.name, 'Não informado'))}</strong><small>${analyticsPct(item.accuracy)} · ${formatNumber(item.attempts)} resp.</small></span>`).join('');
}

function analyticsAggregateTrend(items) {
  const map = new Map();
  (Array.isArray(items) ? items : []).forEach((item) => {
    (Array.isArray(item.trend) ? item.trend : []).forEach((point, index) => {
      const label = String(point.label || `P${index + 1}`);
      const accuracy = Number(point.accuracy);
      if (!Number.isFinite(accuracy)) return;
      const attempts = Math.max(1, numberOrZero(point.attempts));
      const current = map.get(label) || { label, total: 0, weight: 0, order: index };
      current.total += accuracy * attempts;
      current.weight += attempts;
      current.order = Math.min(current.order, index);
      map.set(label, current);
    });
  });
  return Array.from(map.values()).sort((a, b) => a.order - b.order).map((row) => ({
    label: row.label,
    accuracy: row.weight ? row.total / row.weight : null,
    attempts: row.weight,
  }));
}

function analyticsLineChart(rows, label) {
  const clean = Array.isArray(rows) ? rows.filter((item) => Number.isFinite(Number(item.accuracy))) : [];
  if (!clean.length) return `<div class="analytics-empty-chart analytics-empty-chart--compact"><strong>Sem janela respondida</strong><span>O primeiro ponto aparecerá assim que houver uma resposta confirmada.</span></div>`;
  const width = 640, height = 210, padX = 42, padTop = 18, padBottom = 28;
  const values = clean.map((item) => Math.max(0, Math.min(100, Number(item.accuracy))));
  const min = Math.max(0, Math.min(...values) - 8);
  const max = Math.min(100, Math.max(...values) + 8);
  const span = Math.max(12, max - min);
  const xStep = (width - padX * 2) / Math.max(1, clean.length - 1);
  const baseY = (v) => height - padBottom - ((v - min) / span) * (height - padBottom - padTop);
  const coords = values.map((value, index) => [clean.length === 1 ? width / 2 : padX + index * xStep, baseY(value)]);
  const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = clean.length > 1 ? `${padX},${height - padBottom} ` + coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ') + ` ${padX + (clean.length - 1) * xStep},${height - padBottom}` : '';
  const yTicks = [0, 25, 50, 75, 100].map((tick) => ({ value: tick, y: baseY(tick) }));
  const delta = clean.length > 1 ? values.at(-1) - values.at(-2) : null;
  const maturity = clean.length === 1 ? 'Linha de base · confiança inicial' : clean.length < 4 ? 'Direção inicial · confiança baixa' : clean.length < 8 ? 'Tendência emergente · confiança moderada' : 'Tendência consolidada';
  return `<div class="analytics-line-chart">
      <div class="analytics-sample-status"><span>${escapeHtml(maturity)}</span><strong>${delta == null ? `${values[0].toFixed(0)}% inicial` : `${delta >= 0 ? '+' : ''}${delta.toFixed(0)} p.p. na última janela`}</strong></div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}">
        ${yTicks.map((tick) => `<g><line x1="${padX}" y1="${tick.y.toFixed(1)}" x2="${width - padX}" y2="${tick.y.toFixed(1)}"></line><text x="${padX - 10}" y="${(tick.y + 4).toFixed(1)}">${tick.value}%</text></g>`).join('')}
        ${area ? `<polyline class="analytics-line-chart__area" points="${area}"></polyline>` : ''}
        ${clean.length > 1 ? `<polyline class="analytics-line-chart__stroke" points="${points}"></polyline>` : `<line class="analytics-line-chart__baseline" x1="${padX}" x2="${width-padX}" y1="${coords[0][1].toFixed(1)}" y2="${coords[0][1].toFixed(1)}"></line>`}
        ${coords.map(([x, y], index) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4"><title>${escapeHtml(clean[index].label)}: ${values[index].toFixed(0)}% (${formatNumber(clean[index].attempts || 0)} respostas)</title></circle>`).join('')}
        ${clean.map((item, index) => `<text class="analytics-line-chart__x" x="${(clean.length === 1 ? width / 2 : padX + index * xStep).toFixed(1)}" y="${height - 8}">${escapeHtml(String(item.label || ''))}</text>`).join('')}
      </svg>
    </div>`;
}

function analyticsDonutChart(segments, centerLabel, centerValue) {
  const clean = (Array.isArray(segments) ? segments : []).filter((item) => Number(item.value) > 0);
  const total = clean.reduce((sum, item) => sum + Number(item.value || 0), 0);
  if (!total) return `<div class="analytics-empty-chart">Sem proporções consolidadas ainda.</div>`;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const circles = clean.map((item) => {
    const fraction = Number(item.value || 0) / total;
    const length = circumference * fraction;
    const circle = `<circle r="${radius}" cx="70" cy="70" stroke="${item.color}" stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}"></circle>`;
    offset += length;
    return circle;
  }).join('');
  return `<div class="analytics-donut-wrap">
      <div class="analytics-donut-chart">
        <svg viewBox="0 0 140 140" role="img" aria-label="${escapeHtml(centerLabel)}">
          <circle class="analytics-donut-chart__base" r="${radius}" cx="70" cy="70"></circle>
          ${circles}
        </svg>
        <div class="analytics-donut-center"><small>${escapeHtml(centerLabel)}</small><strong>${escapeHtml(centerValue)}</strong></div>
      </div>
      <div class="analytics-donut-legend">${clean.map((item) => `<span><i style="background:${item.color}"></i><strong>${formatNumber(item.value)}</strong>${escapeHtml(item.label)}</span>`).join('')}</div>
    </div>`;
}

function analyticsBuildContext(data) {
  const subjects = Array.isArray(data?.subjects) ? data.subjects : [];
  const answered = subjects.filter((item) => Boolean(item.has_answers));
  const studiedOnly = subjects.filter((item) => Boolean(item.studied));
  const dueTotal = subjects.reduce((sum, item) => sum + numberOrZero(item.due_count), 0);
  const due7Total = subjects.reduce((sum, item) => sum + numberOrZero(item.due_7d), 0);
  const due30Total = subjects.reduce((sum, item) => sum + numberOrZero(item.due_30d), 0);
  const recentRows = answered.filter((item) => item.recent_accuracy != null);
  const recentWeighted = recentRows.length
    ? recentRows.reduce((sum, item) => sum + Number(item.recent_accuracy) * Math.max(1, numberOrZero(item.attempts)), 0) /
      recentRows.reduce((sum, item) => sum + Math.max(1, numberOrZero(item.attempts)), 0)
    : null;
  const retentionRows = subjects.filter((item) => item.retention != null && numberOrZero(item.retention_sample) > 0);
  const retentionWeighted = retentionRows.length
    ? retentionRows.reduce((sum, item) => sum + Number(item.retention) * numberOrZero(item.retention_sample), 0) /
      retentionRows.reduce((sum, item) => sum + numberOrZero(item.retention_sample), 0)
    : null;
  const studiedRows = subjects.filter((item) => item.studied_coverage != null);
  const studiedCoverage = studiedRows.length
    ? studiedRows.reduce((sum, item) => sum + Number(item.studied_coverage), 0) / studiedRows.length
    : null;
  const totalQuestions = subjects.reduce((sum, item) => sum + numberOrZero(item.questions), 0);
  const totalUnique = subjects.reduce((sum, item) => sum + numberOrZero(item.unique_practiced), 0);
  const totalAttempts = subjects.reduce((sum, item) => sum + numberOrZero(item.attempts), 0);
  const highPriority = subjects.filter((item) => String(item.priority_tone) === 'danger').length;
  const mediumPriority = subjects.filter((item) => String(item.priority_tone) === 'warning').length;
  const waitingSubjects = subjects.filter((item) => !item.has_answers && Boolean(item.studied)).length;
  const aggregateTrend = analyticsAggregateTrend(subjects);
  const prioritized = [...subjects].sort((a, b) => Number(b.priority_score || 0) - Number(a.priority_score || 0));
  const strongest = [...answered].sort((a, b) => Number(b.recent_accuracy ?? -1) - Number(a.recent_accuracy ?? -1))[0] || null;
  const mostUrgent = [...subjects].sort((a, b) => numberOrZero(b.due_count) - numberOrZero(a.due_count))[0] || null;
  return { subjects, answered, studiedOnly, dueTotal, due7Total, due30Total, recentWeighted, retentionWeighted, studiedCoverage, totalQuestions, totalUnique, totalAttempts, highPriority, mediumPriority, waitingSubjects, aggregateTrend, prioritized, strongest, mostUrgent };
}

function analyticsSubjectModalBody(item) {
  if (!item) return '<p class="muted">Nenhuma matéria encontrada.</p>';
  const coverage = item.studied_coverage != null ? Number(item.studied_coverage) : Number(item.bank_coverage || 0);
  const coverageLabel = item.studied_coverage != null ? 'Cobertura estudada' : 'Cobertura do banco';
  const reasons = Array.isArray(item.priority_reasons) ? item.priority_reasons : [];
  return `<div class="stack analytics-modal-body">
    <div class="analytics-modal-hero analytics-modal-hero--${escapeHtml(String(item.priority_tone || 'neutral'))}">
      <div><small>Prioridade</small><strong>${escapeHtml(textOrMissing(item.priority_label, '—'))}</strong><span>${Number(item.priority_score || 0).toFixed(0)}/100</span></div>
      <div><small>Última revisão</small><strong>${escapeHtml(analyticsRelativeReview(item.days_since_review))}</strong><span>${formatNumber(numberOrZero(item.due_count))} vencidas agora</span></div>
    </div>
    <div class="analytics-modal-grid">
      <div><span>Desempenho recente</span><strong>${analyticsPct(item.recent_accuracy)}</strong></div>
      <div><span>Histórico</span><strong>${analyticsPct(item.historical_accuracy)}</strong></div>
      <div><span>Retenção hoje</span><strong>${analyticsPct(item.retention)}</strong></div>
      <div><span>${escapeHtml(coverageLabel)}</span><strong>${analyticsPct(coverage)}</strong></div>
      <div><span>Questões no banco</span><strong>${formatNumber(numberOrZero(item.questions))}</strong></div>
      <div><span>Respostas</span><strong>${formatNumber(numberOrZero(item.attempts))}</strong></div>
    </div>
    <div><strong>Tendência</strong>${analyticsSparkline(item.trend, `Tendência de ${textOrMissing(item.subject || item.materia, 'Matéria')}`)}</div>
    <div><strong>Por que está nesta prioridade</strong><div class="analytics-chip-row">${reasons.length ? reasons.map((reason) => `<span class="analytics-chip">${escapeHtml(reason)}</span>`).join('') : '<span class="muted">Ainda sem fatores suficientes.</span>'}</div></div>
    <div><strong>Aulas que merecem atenção</strong><div class="analytics-chip-row">${analyticsWeakAreaHtml(item.weak_lessons, 'Ainda sem histórico por aula.')}</div></div>
    <div><strong>Assuntos que merecem atenção</strong><div class="analytics-chip-row">${analyticsWeakAreaHtml(item.weak_topics, 'Ainda sem histórico por assunto.')}</div></div>
  </div>`;
}

function openAnalyticsInfoModal(kind, context) {
  if (kind === 'focus') return openFocusSubjectsModal(context);
  const { subjects, prioritized, strongest, mostUrgent, highPriority, mediumPriority, waitingSubjects, totalQuestions, totalUnique, dueTotal, due7Total, due30Total, recentWeighted, retentionWeighted, studiedCoverage } = context;
  const subjectList = (items, emptyText = 'Sem itens.') => (items && items.length)
    ? `<ul class="analytics-bullet-list">${items.map((item) => `<li><strong>${escapeHtml(textOrMissing(item.subject || item.materia, 'Matéria'))}</strong> — ${escapeHtml(textOrMissing(item.priority_label, '—'))} · recente ${analyticsPct(item.recent_accuracy)} · retenção ${analyticsPct(item.retention)}</li>`).join('')}</ul>`
    : `<p class="muted">${escapeHtml(emptyText)}</p>`;
  const modals = {
    practiced: {
      title: 'Questões únicas praticadas',
      eyebrow: 'Cobertura do banco',
      body: `<div class="stack"><p>Você praticou <strong>${formatNumber(totalUnique)}</strong> questões únicas de um total de <strong>${formatNumber(totalQuestions)}</strong> disponíveis no banco.</p><p>Cobertura geral atual: <strong>${analyticsPct(totalQuestions ? (totalUnique / totalQuestions) * 100 : 0)}</strong>.</p></div>`,
    },
    reviews: {
      title: 'Revisões próximas',
      eyebrow: 'Carga de repetição espaçada',
      body: `<div class="stack"><p><strong>${formatNumber(dueTotal)}</strong> revisões estão vencidas agora, <strong>${formatNumber(due7Total)}</strong> até 7 dias e <strong>${formatNumber(due30Total)}</strong> até 30 dias.</p>${subjectList([...subjects].sort((a,b)=>numberOrZero(b.due_count)-numberOrZero(a.due_count)).slice(0,8), 'Sem revisões previstas.')}</div>`,
    },
    leader: {
      title: 'Resumo rápido',
      eyebrow: 'Melhor desempenho recente',
      body: strongest ? analyticsSubjectModalBody(strongest) : '<p class="muted">Ainda não há respostas suficientes para identificar uma matéria líder.</p>',
    },
    trend: {
      title: 'Evolução temporal consolidada',
      eyebrow: 'Linha do tempo do desempenho',
      body: `<div class="stack"><p>Esta visão consolida as janelas temporais de desempenho das matérias respondidas.</p>${analyticsLineChart(context.aggregateTrend, 'Evolução temporal consolidada')}</div>`,
    },
    composition: {
      title: 'Proporção de matérias',
      eyebrow: 'Estado do escopo estudado',
      body: `<div class="stack"><p>O painel separa matérias com respostas, matérias estudadas sem respostas e matérias ainda fora do escopo estudado.</p>${subjectList(prioritized, 'Nenhuma matéria disponível.')}</div>`,
    },
    completion: {
      title: 'Proporção de conclusão',
      eyebrow: 'Relação entre prática e banco',
      body: `<div class="stack"><p>Cobertura estudada média: <strong>${analyticsPct(studiedCoverage)}</strong>. Retenção média: <strong>${analyticsPct(retentionWeighted)}</strong>. Desempenho recente consolidado: <strong>${analyticsPct(recentWeighted)}</strong>.</p></div>`,
    },
    compare: {
      title: 'Comparativo por matéria',
      eyebrow: 'Recente, retenção e cobertura',
      body: `<div class="stack"><p>Clique em qualquer linha da lista comparativa para abrir o detalhamento completo daquela matéria.</p>${subjectList(prioritized.slice(0, 8), 'Ainda sem matérias comparáveis.')}</div>`,
    },
    summary: {
      title: 'Resumo condensado',
      eyebrow: 'Visão executiva',
      body: `<div class="stack"><p>Este resumo foi criado para apontar rapidamente onde focar, sem precisar abrir cada matéria.</p>${subjectList(prioritized.slice(0, 8), 'Sem resumo disponível.')}</div>`,
    },
    insights: {
      title: 'Insights rápidos',
      eyebrow: 'Leituras imediatas do painel',
      body: `<div class="stack"><p>Matéria mais urgente: <strong>${mostUrgent ? escapeHtml(textOrMissing(mostUrgent.subject || mostUrgent.materia, '—')) : '—'}</strong>.</p><p>Melhor desempenho recente: <strong>${strongest ? escapeHtml(textOrMissing(strongest.subject || strongest.materia, '—')) : '—'}</strong>.</p></div>`,
    },
  };
  const modal = modals[kind];
  if (!modal) return;
  openModal({ title: modal.title, eyebrow: modal.eyebrow, body: modal.body, footer: '<button class="button button--secondary" type="button" data-modal-close>Fechar</button>' });
}

function openFocusSubjectsModal(context) {
  const prioritized = Array.isArray(context?.prioritized) ? context.prioritized : [];
  const priorityItems = prioritized.filter((item) => ['danger', 'warning'].includes(String(item.priority_tone)));
  const allItems = priorityItems.length
    ? priorityItems
    : prioritized.filter((item) => item.studied || item.has_answers);
  const body = `<div class="focus-modal-layout">
    <div class="focus-modal-controls" role="search" aria-label="Filtrar matérias em foco">
      <label><span>Buscar matéria</span><input id="focusSubjectSearch" type="search" placeholder="Digite o nome da matéria" autocomplete="off"></label>
      <label><span>Prioridade</span><select id="focusPriorityFilter"><option value="all">Todas</option><option value="danger">Alta</option><option value="warning">Média</option></select></label>
    </div>
    <div class="focus-modal-summary" id="focusSubjectSummary" aria-live="polite"></div>
    <div class="focus-subject-results" id="focusSubjectResults"></div>
  </div>`;
  openModal({
    title: 'Todas as matérias em foco',
    eyebrow: 'Prioridade do estudo · lista completa',
    body,
    footer: '<button class="button button--secondary" type="button" data-modal-close>Fechar</button>',
    onOpen: (layer) => {
      const search = $('#focusSubjectSearch', layer);
      const filter = $('#focusPriorityFilter', layer);
      const summary = $('#focusSubjectSummary', layer);
      const results = $('#focusSubjectResults', layer);
      const render = () => {
        const term = String(search?.value || '').trim().toLocaleUpperCase('pt-BR');
        const tone = String(filter?.value || 'all');
        const filtered = allItems.filter((item) => {
          const label = String(item.subject || item.materia || '').toLocaleUpperCase('pt-BR');
          return (!term || label.includes(term)) && (tone === 'all' || String(item.priority_tone) === tone);
        });
        summary.textContent = `Exibindo ${formatNumber(filtered.length)} de ${formatNumber(allItems.length)} matérias em foco`;
        results.replaceChildren();
        if (!filtered.length) {
          const empty = document.createElement('p');
          empty.className = 'learning-pulse-empty';
          empty.textContent = 'Nenhuma matéria corresponde aos filtros.';
          results.append(empty);
          return;
        }
        const fragment = document.createDocumentFragment();
        filtered.forEach((item) => {
          const sourceIndex = context.subjects.indexOf(item);
          const row = document.createElement('button');
          row.type = 'button';
          row.className = `focus-modal-row focus-modal-row--${String(item.priority_tone || 'neutral')}`;
          row.dataset.focusSubjectKey = String(sourceIndex);
          row.setAttribute('aria-label', `Abrir detalhes de ${textOrMissing(item.subject || item.materia, 'matéria')}`);
          const reason = (Array.isArray(item.priority_reasons) && item.priority_reasons[0]) || 'Prioridade calculada pelo desempenho, memória e cobertura.';
          row.innerHTML = `<div><strong>${escapeHtml(textOrMissing(item.subject || item.materia, 'Matéria'))}</strong><span>${escapeHtml(textOrMissing(item.priority_label, 'Em acompanhamento'))} · ${escapeHtml(reason)}</span></div><b>${analyticsPct(item.recent_accuracy)}</b><small>${Number(item.priority_score || 0).toFixed(0)}/100</small>`;
          row.addEventListener('click', () => {
            closeModal();
            openSubjectAnalyticsModal(context, sourceIndex);
          });
          fragment.append(row);
        });
        results.append(fragment);
      };
      search?.addEventListener('input', render);
      filter?.addEventListener('change', render);
      render();
    },
  });
}

function openSubjectAnalyticsModal(context, key) {
  const item = context.subjects[Number(key)];
  if (!item) return;
  openModal({
    title: textOrMissing(item.subject || item.materia, 'Matéria não informada'),
    eyebrow: 'Detalhamento da matéria e das aulas',
    body: analyticsSubjectModalBody(item),
    footer: '<button class="button button--secondary" type="button" data-modal-close>Fechar</button>',
  });
}

function bindVisualAnalyticsInteractions(container, context) {
  if (!container) return;
  container.querySelectorAll('[data-analytics-info]').forEach((element) => {
    element.addEventListener('click', () => openAnalyticsInfoModal(element.dataset.analyticsInfo, context));
  });
  container.querySelectorAll('[data-subject-key]').forEach((element) => {
    element.addEventListener('click', (event) => {
      if (event.target.closest('button, summary, details')) return;
      openSubjectAnalyticsModal(context, element.dataset.subjectKey);
    });
  });
}

function renderAdaptivePanel(data) {
  const context = analyticsBuildContext(data);
  const learnerModel = data.learner_model || {};
  const subjects = context.subjects;
  if (!subjects.length) {
    $('#adaptivePanel').innerHTML = `<div class="empty-state">Sem dados para performance por matéria.</div>`;
    return;
  }

  const overview = `<div class="learning-analytics-overview" aria-label="Resumo de learning analytics">
    <div class="learning-analytics-kpi"><span>Retenção estimada hoje</span><strong>${analyticsPct(context.retentionWeighted)}</strong><small>${context.retentionWeighted == null ? 'Será calculada após as primeiras revisões' : `${subjects.filter((item) => item.retention != null).length} matéria(s) com memória FSRS`}</small></div>
    <div class="learning-analytics-kpi"><span>Revisões vencidas</span><strong>${formatNumber(context.dueTotal)}</strong><small>Prioridade real do scheduler</small></div>
    <div class="learning-analytics-kpi"><span>Desempenho recente</span><strong>${analyticsPct(context.recentWeighted)}</strong><small>${context.recentWeighted == null ? 'Ainda sem respostas' : 'Janela recente ponderada por respostas'}</small></div>
    <div class="learning-analytics-kpi"><span>Cobertura estudada</span><strong>${analyticsPct(context.studiedCoverage)}</strong><small>${context.studiedCoverage == null ? 'Aguardando sincronização/estudo' : 'Aulas estudadas já praticadas'}</small></div>
  </div>`;

  const explainer = `<div class="adaptive-legend adaptive-legend--analytics">
    <div><strong>Como ler este painel</strong><span>A prioridade combina retenção FSRS, desempenho atual, cobertura, recência e proximidade da prova. A média histórica fica como contexto, não como decisão isolada.</span></div>
    <div class="adaptive-legend-items">
      <span><i class="legend-dot legend-dot--danger"></i>Alta</span>
      <span><i class="legend-dot legend-dot--warning"></i>Média</span>
      <span><i class="legend-dot legend-dot--success"></i>Baixa</span>
      <span><i class="legend-dot legend-dot--neutral"></i>Aguardando estudo/dados</span>
    </div>
  </div>`;

  const rows = subjects.map((item, index) => {
    const subject = textOrMissing(item.subject || item.materia, 'Matéria não informada');
    const questions = numberOrZero(item.questions);
    const attempts = numberOrZero(item.attempts);
    const unique = numberOrZero(item.unique_practiced);
    const studied = Boolean(item.studied);
    const hasAnswers = Boolean(item.has_answers);
    const tone = ['neutral', 'danger', 'warning', 'success'].includes(String(item.priority_tone)) ? String(item.priority_tone) : 'neutral';
    const priorityLabel = textOrMissing(item.priority_label, studied ? 'Calculando' : 'Aguardando estudo');
    const priorityScore = Number(item.priority_score || 0);
    const recent = item.recent_accuracy;
    const retention = item.retention;
    const historical = item.historical_accuracy;
    const coverage = item.studied_coverage != null ? Number(item.studied_coverage) : Number(item.bank_coverage || 0);
    const coverageLabel = item.studied_coverage != null ? 'Cobertura estudada' : 'Cobertura do banco';
    const delta = item.trend_delta_pp;
    const dueNow = numberOrZero(item.due_count);
    const due7 = numberOrZero(item.due_7d);
    const due30 = numberOrZero(item.due_30d);
    const reasons = Array.isArray(item.priority_reasons) ? item.priority_reasons : [];
    const projection = item.projection && typeof item.projection === 'object' ? item.projection : null;
    const difficulty = item.difficulty_recent || {};
    const gap = item.learning_gap_recent || {};
    const confidenceLabel = ({ sem_amostra: 'Sem amostra', baixa: 'Amostra baixa', moderada: 'Amostra moderada', boa: 'Boa amostra' })[item.sample_confidence] || '';
    const emptyCopy = !hasAnswers
      ? studied
        ? 'Ainda sem estimativa confiável. A matéria já foi estudada; responda algumas questões para o QuestFlow estimar tendência, retenção e domínio.'
        : 'A matéria existe no banco, mas ainda não consta como estudada. Ela não entra na rotação normal enquanto o filtro de conteúdos estudados estiver ativo.'
      : '';
    const goals = `<div class="subject-goals">
      <span><small>Recente</small><strong>${analyticsPct(recent)} / ${analyticsPct(item.performance_target)}</strong></span>
      <span><small>Retenção</small><strong>${analyticsPct(retention)} / ${analyticsPct(item.retention_target)}</strong></span>
      <span><small>${escapeHtml(coverageLabel)}</small><strong>${analyticsPct(coverage)} / ${analyticsPct(item.coverage_target)}</strong></span>
    </div>`;
    const projectionHtml = projection
      ? `<div class="subject-projection"><strong>Projeção até a prova</strong><span>No ritmo recente, cobertura do banco ≈ <b>${analyticsPct(Number(projection.projected_bank_coverage || 0) * 100)}</b>. Para a meta de ${analyticsPct(Number(projection.target_bank_coverage || 0) * 100)}, seriam necessárias ≈ <b>${Number(projection.needed_new_questions_day || 0).toFixed(1)} questões novas/dia</b>.</span></div>`
      : '';
    const metaHtml = Number(difficulty.known || 0) || Number(gap.known || 0)
      ? `<div class="subject-metacognition"><span>Dificuldade recente: ${formatNumber(difficulty.facil || 0)} fácil · ${formatNumber(difficulty.media || 0)} média · ${formatNumber(difficulty.dificil || 0)} difícil</span><span>${Number(gap.marked || 0) ? `${formatNumber(gap.marked)} resposta(s) marcadas como “preciso estudar”` : 'Nenhuma lacuna de estudo marcada recentemente'}</span></div>`
      : '<div class="subject-metacognition muted">Os botões de dificuldade e “preciso estudar” do Telegram alimentarão este diagnóstico.</div>';
    return `<details class="subject-performance subject-performance--${tone} subject-performance--compact" data-subject-key="${index}">
      <summary class="subject-summary-toggle">
        <div class="subject-summary-main">
          <strong>${escapeHtml(subject)}</strong>
          <span>${formatNumber(questions)} questões · ${formatNumber(attempts)} respostas · ${escapeHtml(analyticsRelativeReview(item.days_since_review))}</span>
        </div>
        <div class="subject-summary-quick">
          <span class="summary-chip summary-chip--tone-${tone}">${escapeHtml(priorityLabel)} ${priorityLabel === 'Aguardando estudo' ? '' : `· ${priorityScore.toFixed(0)}/100`}</span>
          <span class="summary-chip">Recente ${analyticsPct(recent)}</span>
          <span class="summary-chip">Retenção ${analyticsPct(retention)}</span>
          <span class="summary-chip">${escapeHtml(coverageLabel)} ${analyticsPct(coverage)}</span>
          <span class="summary-chip">Vencidas ${formatNumber(dueNow)}</span>
        </div>
      </summary>
      <div class="subject-summary-expanded">
        ${emptyCopy ? `<div class="subject-empty-analytics"><strong>${studied ? 'Comece a medir esta matéria' : 'Fora do escopo estudado'}</strong><span>${escapeHtml(emptyCopy)}</span></div>` : ''}
        <div class="subject-analytics-grid">
          <div><span>Retenção hoje</span><strong>${analyticsPct(retention)}</strong><small>${retention == null ? 'Aguardando memória FSRS' : `${formatNumber(item.retention_sample)} cartões com estimativa`}</small></div>
          <div><span>Desempenho recente</span><strong>${analyticsPct(recent)}</strong><small class="${analyticsTrendClass(delta)}">${escapeHtml(analyticsTrendText(delta))} · últimas ${Math.min(30, attempts)} respostas</small></div>
          <div><span>Histórico</span><strong>${analyticsPct(historical)}</strong><small>${escapeHtml(confidenceLabel)} · ${formatNumber(attempts)} respostas</small></div>
          <div><span>${escapeHtml(coverageLabel)}</span><strong>${analyticsPct(coverage)}</strong><small>${formatNumber(unique)} / ${formatNumber(questions)} questões únicas</small></div>
        </div>
        <div class="subject-analytics-mid">
          <div class="subject-trend-block"><div class="subject-section-label"><strong>Tendência</strong><span>${escapeHtml(analyticsTrendText(delta))}</span></div>${analyticsSparkline(item.trend, `Tendência de desempenho em ${subject}`)}</div>
          <div class="subject-review-status">
            <div><span>Última revisão</span><strong>${escapeHtml(analyticsRelativeReview(item.days_since_review))}</strong></div>
            <div><span>Vencidas agora</span><strong>${formatNumber(dueNow)}</strong></div>
            <div><span>Até 7 dias</span><strong>${formatNumber(due7)}</strong></div>
            <div><span>Até 30 dias</span><strong>${formatNumber(due30)}</strong></div>
          </div>
        </div>
        ${goals}
        <div class="subject-analytics-details-body">
          <div><strong>Principais fatores</strong><div class="analytics-chip-row">${reasons.length ? reasons.map((reason) => `<span class="analytics-chip">${escapeHtml(reason)}</span>`).join('') : '<span class="muted">Ainda sem fatores suficientes.</span>'}</div></div>
          <div><strong>Aulas mais frágeis</strong><div class="analytics-chip-row">${analyticsWeakAreaHtml(item.weak_lessons, 'Ainda sem histórico por aula.')}</div></div>
          <div><strong>Assuntos mais frágeis</strong><div class="analytics-chip-row">${analyticsWeakAreaHtml(item.weak_topics, 'Ainda sem histórico por assunto.')}</div></div>
          ${metaHtml}${projectionHtml}
        </div>
      </div>
    </details>`;
  }).join('');

  $('#adaptivePanel').innerHTML = `${overview}${explainer}<div class="subject-performance-list subject-performance-list--analytics">${rows}</div>`;
}

function learnerModelPanelHtml(model = {}) {
  const events = Number(model.events || 0);
  if (!events) {
    return `<section class="learner-model-shell analytics-card">
      <div class="learner-model-head"><div><h3>Modelo do aluno · FSRS + KT + IRT + incerteza</h3><p>O QuestFlow só conclui domínio quando existe evidência suficiente. No início, ele prefere coletar respostas diagnósticas a apresentar uma porcentagem com falsa precisão.</p></div><span class="analytics-pill">Aguardando evidências</span></div>
      <div class="learner-model-caveat">FSRS continua responsável pelo momento da revisão; KT estima domínio e IRT mede informação pessoal. A camada seletiva pode se abster quando a amostra ainda é pequena.</div>
    </section>`;
  }
  const mastery = Math.max(0, Math.min(100, Number(model.avg_mastery || 0) * 100));
  const confidence = Math.max(0, Math.min(100, Number(model.avg_confidence || 0) * 100));
  const weakest = Array.isArray(model.weakest_concepts) ? model.weakest_concepts.slice(0, 6) : [];
  const uncertain = Array.isArray(model.uncertain_concepts) ? model.uncertain_concepts.slice(0, 6) : [];
  const abilities = Array.isArray(model.abilities) ? model.abilities.slice(0, 6) : [];
  const calibration = model.calibration || {};
  const selective = calibration.selective || {};
  const scaffoldBenchmark = model.scaffolding_benchmark || {};
  const planItems = Array.isArray(model.counterfactual_plan?.items) ? model.counterfactual_plan.items.slice(0, 6) : [];
  const conceptRows = weakest.length ? weakest.map((item) => {
    const value = Math.max(0, Math.min(100, Number(item.mastery || 0) * 100));
    const evidence = item.evidence || {};
    return `<div class="learner-concept-row"><div><strong>${escapeHtml(textOrMissing(item.label, 'Conceito'))}</strong><small>${escapeHtml(textOrMissing(item.subject, 'Matéria'))} · ${escapeHtml(textOrMissing(item.mastery_label, 'Domínio estimado'))} · ${formatNumber(item.exposure_count || 0)} evidências · ${escapeHtml(evidence.label || '')}</small></div><b>${value.toFixed(0)}%</b><div class="learner-meter"><i style="width:${value}%"></i></div></div>`;
  }).join('') : '<div class="muted">Ainda não há conceitos com evidência suficiente para diagnóstico de domínio.</div>';
  const uncertainRows = uncertain.length ? uncertain.map((item) => {
    const reasons = Array.isArray(item.evidence?.reasons) ? item.evidence.reasons.join(' · ') : 'A amostra ainda é pequena.';
    return `<div class="learner-uncertain-row"><div><strong>${escapeHtml(textOrMissing(item.label, 'Conceito'))}</strong><small>${escapeHtml(textOrMissing(item.subject, 'Matéria'))} · ${formatNumber(item.exposure_count || 0)} evidências · ${escapeHtml(reasons)}</small></div><button type="button" class="analytics-pill is-warning learner-evidence-action" data-evidence-concept="${escapeHtml(item.concept_key || '')}">Entender e coletar evidência</button></div>`;
  }).join('') : '<div class="muted">Nenhum conceito está atualmente em abstenção por falta de evidência.</div>';
  const abilityRows = abilities.length ? abilities.map((item) => `<div class="learner-ability-row"><div><strong>${escapeHtml(textOrMissing(item.subject, 'Matéria'))}</strong><small>${formatNumber(item.attempt_count || 0)} respostas · acerto ${analyticsPct(item.accuracy, 1)} · incerteza local ±${Number(item.standard_error || 0).toFixed(2)}</small></div><b>${Number(item.theta_scale || 50).toFixed(0)}/100</b></div>`).join('') : '<div class="muted">Sem habilidade estimada por matéria.</div>';
  const planRows = planItems.length ? planItems.map((item) => {
    const p = item.plan || {};
    const target = Math.round(Number(p.target_mastery || .8) * 100);
    const current = Math.round(Number(item.mastery || 0) * 100);
    const diagnostic = Number(p.diagnostic_questions_first || 0);
    const practices = p.estimated_successful_practices == null ? 'reavaliar após diagnóstico' : `${formatNumber(p.estimated_successful_practices)} práticas corretas estimadas`;
    const action = p.action === 'coletar_evidencia' ? `${diagnostic || 2} questões diagnósticas primeiro` : practices;
    return `<div class="learner-plan-row"><div><strong>${escapeHtml(textOrMissing(item.label, 'Conceito'))}</strong><small>${escapeHtml(textOrMissing(item.subject, 'Matéria'))} · atual ${current}% → alvo ${target}%</small></div><span>${escapeHtml(action)}</span></div>`;
  }).join('') : '<div class="muted">Sem intervenção contrafactual necessária com os dados atuais.</div>';
  const accepted = Number(calibration.accepted_samples || 0);
  const coverage = Number(calibration.coverage || 0) * 100;
  const brier = Number(selective.brier);
  const ece = Number(selective.expected_calibration_error);
  const calibrationText = accepted
    ? `${escapeHtml(calibration.quality_label || 'Calibração em acompanhamento')} · cobertura ${coverage.toFixed(0)}% · Brier ${Number.isFinite(brier) ? brier.toFixed(3) : '—'} · ECE ${Number.isFinite(ece) ? ece.toFixed(3) : '—'}`
    : 'Ainda não há previsões não-abstidas suficientes para avaliar calibração.';
  const benchmarkGroups = Array.isArray(scaffoldBenchmark.by_support) ? scaffoldBenchmark.by_support : [];
  const benchmarkRows = benchmarkGroups.length ? benchmarkGroups.map((item) => {
    const labels = { independente:'Pouco apoio · níveis 0–1', apoio_moderado:'Apoio moderado · níveis 2–3', apoio_alto:'Apoio alto · níveis 4–5' };
    const delayed = Number(item.delayed_samples || 0);
    const acc = item.delayed_accuracy == null ? '—' : `${(Number(item.delayed_accuracy) * 100).toFixed(0)}%`;
    return `<div class="learner-benchmark-row"><div><strong>${escapeHtml(labels[item.key] || item.key || 'Estratégia')}</strong><small>${formatNumber(item.samples || 0)} observações · ${formatNumber(delayed)} revisões posteriores</small></div><b>${acc}</b></div>`;
  }).join('') : '<div class="muted">O benchmark começa automaticamente depois que sessões do Tutor forem seguidas por novas revisões.</div>';
  const benchmarkAdvice = Array.isArray(scaffoldBenchmark.recommendations) && scaffoldBenchmark.recommendations.length ? scaffoldBenchmark.recommendations[0] : 'O QuestFlow ainda está acumulando dados para comparar as estratégias de ajuda.';
  return `<section class="learner-model-shell analytics-card analytics-card--wide">
    <div class="learner-model-head"><div><h3>Modelo do aluno · FSRS + KT + IRT + incerteza</h3><p>O modelo mede domínio, memória e informação da questão, mas agora também mede a própria incerteza e pode se abster.</p></div><span class="analytics-pill">${escapeHtml(model.version || 'qf-learner')}</span></div>
    <div class="learner-model-grid">
      <div class="learner-model-metric"><span>Domínio médio</span><strong>${mastery.toFixed(0)}%</strong><small>confiança média ${confidence.toFixed(0)}%</small></div>
      <div class="learner-model-metric"><span>Estimativas utilizáveis</span><strong>${formatNumber(model.reliable_concepts || 0)}</strong><small>${formatNumber(model.cautious_concepts || 0)} ainda cautelosas</small></div>
      <div class="learner-model-metric"><span>Evidência insuficiente</span><strong>${formatNumber(model.abstained_concepts || 0)}</strong><small>o modelo prefere diagnosticar</small></div>
      <div class="learner-model-metric"><span>Calibração</span><strong>${accepted ? `${coverage.toFixed(0)}%` : '—'}</strong><small>cobertura das previsões aceitas</small></div>
    </div>
    <div class="learner-calibration-note"><strong>Calibração probabilística</strong><span>${calibrationText}</span></div>
    <div class="learner-model-detail-grid"><div><h4>Lacunas com evidência suficiente</h4><div class="learner-concept-list">${conceptRows}</div></div><div><h4>Conceitos em que o modelo se abstém</h4><div class="learner-concept-list">${uncertainRows}</div></div></div>
    <div class="learner-model-detail-grid"><div><h4>Plano contrafactual para chegar a 80%</h4><div class="learner-plan-list">${planRows}</div></div><div><h4>Habilidade pessoal por matéria</h4><div class="learner-ability-list">${abilityRows}</div></div></div>
    <div class="learner-benchmark-card"><div><h4>Benchmark pedagógico do Tutor</h4><p>Compara, de forma observacional, quanto apoio foi necessário e se você acertou novamente depois.</p></div><div class="learner-benchmark-metrics"><span><b>${formatNumber(scaffoldBenchmark.sessions || 0)}</b><small>sessões concluídas</small></span><span><b>${formatNumber(scaffoldBenchmark.delayed_observations || 0)}</b><small>revisões posteriores</small></span><span><b>${scaffoldBenchmark.delayed_accuracy == null ? '—' : `${(Number(scaffoldBenchmark.delayed_accuracy)*100).toFixed(0)}%`}</b><small>acerto posterior observado</small></span></div><div class="learner-benchmark-list">${benchmarkRows}</div><div class="learner-benchmark-advice"><strong>Leitura atual</strong><span>${escapeHtml(benchmarkAdvice)}</span><small>${escapeHtml(scaffoldBenchmark.caveat || 'Associação observacional; não é prova causal.')}</small></div></div>
    <div class="learner-model-caveat">${escapeHtml(model.decision_rule || '')} ${escapeHtml(model.caveat || '')}</div>
  </section>`;
}

async function openEvidenceCollection(conceptKey) {
  const key = String(conceptKey || '').trim();
  if (!key) { toast('Conceito não identificado.', 'warning'); return; }
  openModal({ title:'Coleta de evidência', eyebrow:'Learner Model · diagnóstico', body:'<div class="skeleton" style="height:12rem"></div>', footer:'<button class="button button--secondary" data-modal-close>Fechar</button>' });
  try {
    const result = await bridge.call('get_evidence_collection_plan', key);
    if (!result.ok) throw new Error(result.error || 'Não foi possível montar o plano de evidência.');
    const plan = result.plan || {};
    const evidence = plan.evidence || {};
    const reasons = Array.isArray(evidence.reasons) ? evidence.reasons : [];
    const candidates = Array.isArray(plan.candidates) ? plan.candidates.slice(0,6) : [];
    const candidateHtml = candidates.length ? candidates.map((item) => `<article class="evidence-candidate"><div><strong>${escapeHtml(item.code || 'Questão')}</strong><span>${escapeHtml([item.lesson,item.topic,item.board].filter(Boolean).join(' · ') || plan.subject || '')}</span></div><small>${formatNumber(item.attempts || 0)} tentativa(s) · valor diagnóstico ${Number(item.diagnostic_score || 0).toFixed(0)}/100</small></article>`).join('') : '<div class="muted">Nenhuma questão elegível deste conceito foi encontrada no banco.</div>';
    $('#modalBody').innerHTML = `<div class="evidence-plan"><div class="evidence-plan-hero"><span>i</span><div><strong>Isso não é um erro.</strong><p>${escapeHtml(plan.explanation || '')}</p></div></div><div class="evidence-plan-grid"><div><span>Conceito</span><strong>${escapeHtml(plan.label || 'Conceito')}</strong><small>${escapeHtml(plan.subject || '')}</small></div><div><span>Evidências atuais</span><strong>${formatNumber(plan.exposures || 0)}</strong><small>mínimo operacional: ${formatNumber(plan.minimum_evidence || 3)}</small></div><div><span>Confiança KT</span><strong>${Math.round(Number(plan.confidence || 0)*100)}%</strong><small>${escapeHtml(evidence.label || 'Evidência insuficiente')}</small></div><div><span>Próxima ação</span><strong>${formatNumber(plan.recommended_questions || 0)} questão(ões)</strong><small>diagnósticas, não punição</small></div></div>${reasons.length ? `<div class="evidence-reasons"><strong>Por que o modelo se absteve?</strong>${reasons.map((reason)=>`<span>${escapeHtml(reason)}</span>`).join('')}</div>`:''}<div><h4>Questões sugeridas</h4><div class="evidence-candidate-list">${candidateHtml}</div></div><div class="evidence-plan-note">Depois de responder, FSRS, KT e IRT são atualizados normalmente. O painel deixa de mostrar “coletar evidência” quando a amostra se torna suficiente.</div></div>`;
    const evidenceAction = plan.can_start
      ? '<button class="button button--primary" id="startEvidencePractice" title="Iniciar mini-simulado para coletar evidências diagnósticas">Iniciar prática diagnóstica</button>'
      : '<button class="button button--primary" id="startEvidencePractice" disabled title="A prática não pode ser iniciada agora; consulte o motivo e as evidências no plano acima">Iniciar prática diagnóstica</button>';
    $('#modalFooter').innerHTML = `<button class="button button--secondary" data-modal-close>Agora não</button>${evidenceAction}`;
    $$('[data-modal-close]', $('#modalLayer')).forEach((element)=>element.addEventListener('click', closeModal, {once:true}));
    $('#startEvidencePractice')?.addEventListener('click', async () => {
      const button = $('#startEvidencePractice'); setBusy(button,true,'Preparando questões');
      try {
        const started = await bridge.call('start_evidence_collection', key);
        if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a coleta.');
        const simulation = started.simulation || {};
        state.adaptiveSimulationId = simulation.session?.id || null;
        state.adaptiveSimulationQuestionUid = null;
        closeModal();
        await navigate('recommend');
        renderAdaptiveSimulation(simulation);
        toast('Prática diagnóstica iniciada. Não é um erro: estas respostas servem para reduzir a incerteza do modelo.', 'success', 7000);
      } catch (error) { toast(error.message,'error',7000); setBusy(button,false); }
    });
  } catch (error) {
    $('#modalBody').innerHTML = emptyStateHtml({title:'Plano indisponível',text:error.message,compact:true});
  }
}

function handleLearnerModelAction(event) {
  const button = event.target.closest('[data-evidence-concept]');
  if (button) openEvidenceCollection(button.dataset.evidenceConcept || '');
}

function renderVisualAnalyticsPanel(data) {
  const container = $('#visualAnalyticsPanel');
  if (!container) return;
  const learnerModel = data?.learner_model || {};
  const context = analyticsBuildContext(data);
  const subjects = context.subjects;
  if (!subjects.length) {
    container.innerHTML = `${learnerModelPanelHtml(learnerModel)}<div class="empty-state">Sem dados de matérias para os demais gráficos.</div>`;
    return;
  }

  const practicedCoverage = context.totalQuestions ? (context.totalUnique / context.totalQuestions) * 100 : 0;
  const studiedDonut = analyticsDonutChart([
    { label: 'Com respostas', value: context.answered.length, color: 'var(--chart-accent-1)' },
    { label: 'Estudadas sem respostas', value: context.waitingSubjects, color: 'var(--chart-accent-2)' },
    { label: 'Fora do escopo estudado', value: Math.max(0, subjects.length - context.answered.length - context.waitingSubjects), color: 'var(--chart-accent-4)' },
  ], 'Matérias', formatNumber(subjects.length));
  const bankCoverageDonut = analyticsDonutChart([
    { label: 'Questões únicas praticadas', value: context.totalUnique, color: 'var(--chart-accent-3)' },
    { label: 'Restante do banco', value: Math.max(0, context.totalQuestions - context.totalUnique), color: 'var(--chart-accent-4)' },
  ], 'Banco', analyticsPct(practicedCoverage));

  const comparisonRows = context.prioritized.slice(0, 8).map((item, index) => `
    <div class="analytics-bar-chart__row is-clickable" data-subject-key="${subjects.indexOf(item)}">
      <div class="analytics-bar-chart__label"><strong>${escapeHtml(textOrMissing(item.subject || item.materia, 'Matéria'))}</strong><small>${escapeHtml(textOrMissing(item.priority_label, 'Prioridade'))}</small></div>
      <div class="analytics-bar-chart__bars">
        <div class="analytics-bar-chart__metric"><span>Recente</span><div class="analytics-bar-chart__track"><i style="width:${Math.max(0, Math.min(100, Number(item.recent_accuracy || 0)))}%; background:var(--chart-accent-1)"></i></div><strong>${analyticsPct(item.recent_accuracy)}</strong></div>
        <div class="analytics-bar-chart__metric"><span>Retenção</span><div class="analytics-bar-chart__track"><i style="width:${Math.max(0, Math.min(100, Number(item.retention || 0)))}%; background:var(--chart-accent-2)"></i></div><strong>${analyticsPct(item.retention)}</strong></div>
        <div class="analytics-bar-chart__metric"><span>Cobertura</span><div class="analytics-bar-chart__track"><i style="width:${Math.max(0, Math.min(100, Number(item.studied_coverage != null ? item.studied_coverage : item.bank_coverage || 0)))}%; background:var(--chart-accent-3)"></i></div><strong>${analyticsPct(item.studied_coverage != null ? item.studied_coverage : item.bank_coverage)}</strong></div>
      </div>
    </div>`).join('');

  const summaryRows = context.prioritized.slice(0, 10).map((item) => {
    const key = subjects.indexOf(item);
    const coverage = item.studied_coverage != null ? item.studied_coverage : item.bank_coverage;
    return `<tr class="is-clickable" data-subject-key="${key}"><td><strong>${escapeHtml(textOrMissing(item.subject || item.materia, 'Matéria'))}</strong><small>${formatNumber(numberOrZero(item.questions))} questões</small></td><td><span class="analytics-pill analytics-pill--${escapeHtml(String(item.priority_tone || 'neutral'))}">${escapeHtml(textOrMissing(item.priority_label, '—'))} · ${Number(item.priority_score || 0).toFixed(0)}</span></td><td>${analyticsPct(item.recent_accuracy)}</td><td>${analyticsPct(item.retention)}</td><td>${analyticsPct(coverage)}</td><td>${escapeHtml(analyticsRelativeReview(item.days_since_review))}</td></tr>`;
  }).join('');

  const activity=data.activity_summary||{};
  const top=context.prioritized[0]||null;
  const topName=top?textOrMissing(top.subject||top.materia,'Matéria prioritária'):'Sem prioridade definida';
  const actionReason=top&&Array.isArray(top.priority_reasons)&&top.priority_reasons.length?top.priority_reasons[0]:'Ainda faltam respostas suficientes para uma recomendação forte.';
  const accuracyText=activity.accuracy==null?'Sem amostra':`${Number(activity.accuracy).toFixed(1)}%`;
  const memoryMax=Math.max(1, context.dueTotal, context.due7Total, context.due30Total);
  const memoryHorizon=`<div class="analytics-memory-horizon">
    <div><span>Agora</span><div><i style="width:${Math.max(2,(context.dueTotal/memoryMax)*100)}%"></i></div><strong>${formatNumber(context.dueTotal)}</strong></div>
    <div><span>Até 7 dias</span><div><i style="width:${Math.max(2,(context.due7Total/memoryMax)*100)}%"></i></div><strong>${formatNumber(context.due7Total)}</strong></div>
    <div><span>Até 30 dias</span><div><i style="width:${Math.max(2,(context.due30Total/memoryMax)*100)}%"></i></div><strong>${formatNumber(context.due30Total)}</strong></div>
  </div>`;
  const visualGuide=`<section class="analytics-decision-guide"><div class="analytics-decision-guide__main"><span class="eyebrow">Decisão de estudo</span><h3>${escapeHtml(topName)}</h3><p><strong>Por que aparece:</strong> ${escapeHtml(actionReason)}</p><p><strong>O que fazer:</strong> ${top?`responda/revise primeiro esta matéria e depois volte ao painel para verificar se a prioridade caiu.`:'responda algumas questões no aplicativo para formar evidência.'}</p></div><div class="analytics-decision-guide__facts"><div><span>Seu acerto</span><strong>${escapeHtml(accuracyText)}</strong><small>${formatNumber(activity.correct||0)} certas · ${formatNumber(activity.wrong||0)} erradas</small></div><div><span>Tempo médio ativo</span><strong>${activity.avg_active_seconds==null?'—':`${Number(activity.avg_active_seconds).toFixed(1)} s`}</strong><small>só ${formatNumber(activity.speed_samples||0)} amostra(s) confiáveis</small></div><div><span>Origem das respostas</span><strong>${formatNumber(activity.mobile_attempts||0)} app</strong><small>${formatNumber(activity.telegram_attempts||0)} Telegram · histórico unificado</small></div></div></section>`;
  container.innerHTML = `
    ${visualGuide}
    <div class="analytics-dashboard-grid analytics-dashboard-grid--cards">
      <article class="analytics-hero-card is-clickable" data-analytics-info="focus"><span>Matérias em foco</span><strong>${formatNumber(context.highPriority)}</strong><small>${formatNumber(context.mediumPriority)} média prioridade · ${formatNumber(context.waitingSubjects)} aguardando primeira resposta</small></article>
      <article class="analytics-hero-card is-clickable" data-analytics-info="practiced"><span>Questões únicas praticadas</span><strong>${formatNumber(context.totalUnique)}</strong><small>${formatNumber(context.totalQuestions)} no banco · ${analyticsPct(practicedCoverage)} de cobertura</small></article>
      <article class="analytics-hero-card is-clickable" data-analytics-info="reviews"><span>Revisões próximas</span><strong>${formatNumber(context.due7Total)}</strong><small>${formatNumber(context.dueTotal)} agora · ${formatNumber(context.due30Total)} em 30 dias</small></article>
      <article class="analytics-hero-card is-clickable" data-analytics-info="leader"><span>Resumo rápido</span><strong>${context.strongest ? escapeHtml(textOrMissing(context.strongest.subject || context.strongest.materia, 'Sem líder')) : 'Sem líder'}</strong><small>${context.strongest ? `Melhor recente: ${analyticsPct(context.strongest.recent_accuracy)} · ${formatNumber(context.strongest.attempts)} resp.` : 'Sem respostas suficientes ainda'}</small></article>
    </div>
    <div class="analytics-dashboard-grid analytics-dashboard-grid--main">
      <article class="analytics-card analytics-card--wide is-clickable" data-analytics-info="trend"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Evolução</span><h3>Desempenho ao longo do tempo</h3><p>Média ponderada do desempenho recente por janelas temporais das matérias respondidas.</p></div></div>${analyticsLineChart(context.aggregateTrend, 'Evolução temporal consolidada do desempenho')}</article>
      <article class="analytics-card is-clickable analytics-card--insight" data-analytics-info="insights"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Agora</span><h3>Onde agir primeiro</h3><p>Os três sinais mais úteis para decidir o próximo bloco de estudo.</p></div></div><div class="analytics-insights"><div><span>Matéria mais urgente</span><strong>${context.mostUrgent ? escapeHtml(textOrMissing(context.mostUrgent.subject || context.mostUrgent.materia, '—')) : '—'}</strong><small>${context.mostUrgent ? `${formatNumber(numberOrZero(context.mostUrgent.due_count))} vencidas agora` : 'Sem revisões vencidas'}</small></div><div><span>Melhor tendência</span><strong>${context.strongest ? escapeHtml(textOrMissing(context.strongest.subject || context.strongest.materia, '—')) : '—'}</strong><small>${context.strongest ? `${analyticsPct(context.strongest.recent_accuracy)} recente` : 'Sem amostra'}</small></div><div><span>Janela de atenção</span><strong>${escapeHtml(context.recentWeighted != null ? `${analyticsPct(context.recentWeighted)} recente` : 'Sem dados')}</strong><small>${formatNumber(context.studiedOnly.length)} matéria(s) já estudadas</small></div></div></article>
      <article class="analytics-card analytics-card--wide is-clickable" data-analytics-info="compare"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Comparação</span><h3>Matérias lado a lado</h3><p>Compare desempenho recente, retenção e cobertura; clique em uma linha para aprofundar.</p></div></div><div class="analytics-bar-legend"><span><i style="background:var(--chart-accent-1)"></i>Recente</span><span><i style="background:var(--chart-accent-2)"></i>Retenção</span><span><i style="background:var(--chart-accent-3)"></i>Cobertura</span></div><div class="analytics-bar-chart">${comparisonRows || '<div class="analytics-empty-chart">Sem matérias suficientes para comparação.</div>'}</div></article>
      <article class="analytics-card is-clickable" data-analytics-info="composition"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Escopo</span><h3>Estado das matérias</h3><p>Como as matérias se distribuem entre prática, estudo e espera.</p></div></div>${studiedDonut}</article>
      <article class="analytics-card analytics-card--wide is-clickable" data-analytics-info="summary"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Diagnóstico</span><h3>Resumo por matéria</h3><p>Prioridade, desempenho, memória e cobertura em uma leitura única.</p></div></div><div class="analytics-summary-table-wrap"><table class="analytics-summary-table"><thead><tr><th>Matéria</th><th>Prioridade</th><th>Recente</th><th>Retenção</th><th>Cobertura</th><th>Última revisão</th></tr></thead><tbody>${summaryRows}</tbody></table></div></article>
      <article class="analytics-card is-clickable" data-analytics-info="completion"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Cobertura</span><h3>Prática do banco</h3><p>Questões únicas já praticadas em relação ao banco disponível.</p></div></div>${bankCoverageDonut}</article>
      <article class="analytics-card analytics-card--full is-clickable" data-analytics-info="reviews"><div class="analytics-card__head"><div><span class="analytics-card__kicker">Memória</span><h3>Horizonte de revisões</h3><p>Volume previsto pelo scheduler agora, até 7 dias e até 30 dias. As janelas são cumulativas.</p></div></div>${memoryHorizon}</article>
    </div>
    <details class="analytics-advanced-disclosure"><summary><div><strong>Análise avançada do modelo do aluno</strong><span>FSRS, Knowledge Tracing, IRT, incerteza e calibração. Abra somente quando quiser entender o diagnóstico técnico.</span></div><b>Ver detalhes</b></summary>${learnerModelPanelHtml(learnerModel)}</details>`;
  bindVisualAnalyticsInteractions(container, context);
}

function renderFlowHealth(flow) {
  const items = [
    ['Agendador', flow.running ? 'Ativo' : 'Parado', flow.running ? 'text-success' : 'text-warning'],
    ['Listener', flow.listening ? 'Conectado' : 'Desconectado', flow.listening ? 'text-success' : 'text-warning'],
    ['Motor', flow.paused ? 'Pausado' : 'Operacional', flow.paused ? 'text-warning' : 'text-success'],
    ['Questões Telegram', flow.telegram_questions_paused ? 'Pausadas' : 'Permitidas', flow.telegram_questions_paused ? 'text-warning' : 'text-success'],
    ['Próxima execução', formatDate(flow.next_run), ''],
  ];
  $('#flowHealthPanel').innerHTML = `<div class="stack">${items.map(([label, value, cls]) => `<div class="inline-cluster"><span class="muted">${label}</span><strong class="${cls}" style="margin-left:auto">${escapeHtml(value)}</strong></div>`).join('')}</div>`;
}

function normalizeDelivery(item) {
  return {
    ...item,
    question_uid: item.question_uid || item.uid || '',
    codigo: textOrMissing(item.codigo || item.source_code, 'Código não encontrado'),
    materia: textOrMissing(item.materia || item.subject, 'Matéria não encontrada'),
    status: textOrMissing(item.status, 'Status não informado'),
    answers: numberOrZero(item.answers),
    correct: numberOrZero(item.correct ?? item.correct_answers),
    attempts: numberOrZero(item.attempts ?? item.attempt_count),
    last_error: textOrMissing(item.last_error || item.error_text, 'Sem erro registrado'),
  };
}

async function openHistoryQuestion(uid) {
  const questionUid = String(uid || '').trim();
  if (!questionUid) return toast('O histórico não possui vínculo com uma questão do banco.', 'warning');
  await navigate('review');
  $('#questionSearch').value = '';
  $('#questionStatus').value = 'todos';
  await loadQuestions();
  await selectQuestion(questionUid);
}

function bindHistoryQuestionRows(container) {
  $$('tr[data-question-uid]', container).forEach((row) => {
    const open = () => openHistoryQuestion(row.dataset.questionUid);
    row.addEventListener('click', (event) => { if (!event.target.closest('button, a, input, select')) open(); });
    row.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } });
    $$('[data-open-question]', row).forEach((button) => button.addEventListener('click', (event) => { event.stopPropagation(); open(); }));
  });
}

function renderRecentActivity(items) {
  if (!items.length) {
    $('#recentActivity').innerHTML = emptyStateHtml({ text: 'Nenhuma resposta registrada ainda. Quando você responder no aplicativo ou Telegram, ela aparecerá aqui.' });
    return;
  }
  const container = $('#recentActivity');
  const looksLikeAttempts = items.some(item => Object.prototype.hasOwnProperty.call(item,'is_correct'));
  if (looksLikeAttempts) {
    const rows=items.slice(0,12).map(item=>({
      ...item,
      question_uid:item.question_uid||'',
      answered_at:item.answered_at||'',
      codigo:textOrMissing(item.codigo,'Sem código'),
      materia:textOrMissing(item.materia,'Matéria não informada'),
      resultado:Number(item.is_correct)===1?'Acertou':'Errou',
      canal:String(item.source||'telegram').startsWith('mobile_')?'Aplicativo':String(item.source||'telegram')==='telegram'?'Telegram':'Desktop',
      tempo:item.response_seconds==null?'—':`${Number(item.response_seconds).toFixed(1)} s`,
      tempo_status:['valid','active_filtered'].includes(String(item.timing_quality||''))?'ativo confiável':'não usado na velocidade',
    }));
    container.innerHTML = `<div class="recent-study-note"><strong>Histórico unificado</strong><span>Respostas do aplicativo e do Telegram alimentam o mesmo modelo. O tempo só aparece como velocidade quando passa pelo Quality Gate de atividade.</span></div>` + tableHtml([
      {label:'Quando',key:'answered_at',type:'date'},
      {label:'Código',key:'codigo',render:(value)=>`<button type="button" class="table-link" data-open-question>${escapeHtml(value)}</button>`},
      {label:'Matéria',key:'materia'},
      {label:'Resultado',key:'resultado',render:(value)=>`<span class="result-chip ${value==='Acertou'?'is-correct':'is-wrong'}">${escapeHtml(value)}</span>`},
      {label:'Canal',key:'canal'},
      {label:'Tempo ativo',key:'tempo',render:(value,row)=>`<span title="${escapeHtml(row.tempo_status)}">${escapeHtml(value)}</span>`},
    ],rows,{id:'dashboard-attempts',rowUidKey:'question_uid'});
    enhanceManagedTables(container); bindHistoryQuestionRows(container); return;
  }
  const normalized = items.slice(0, 15).map(normalizeDelivery);
  container.innerHTML = tableHtml([
    { label: 'Data', key: 'sent_at', type: 'date' },
    { label: 'Código', key: 'codigo', render: (value) => `<button type="button" class="table-link" data-open-question>${escapeHtml(value)}</button>` },
    { label: 'Matéria', key: 'materia' },
    { label: 'Status', key: 'status' },
    { label: 'Respostas', key: 'answers', type: 'number' },
    { label: 'Certas', key: 'correct', type: 'number' },
  ], normalized, { id: 'dashboard-recent', rowUidKey: 'question_uid' });
  enhanceManagedTables(container); bindHistoryQuestionRows(container);
}

async function loadRecentImports() {
  // Existing core exposes recent imports through the dashboard bootstrap only in the classic UI.
  $('#recentImports').innerHTML = emptyStateHtml({ text: 'As importações desta sessão aparecerão aqui. O histórico completo continua preservado no banco.' });
}

function renderImportContext() {
  const panel = $('#importContextPanel');
  if (!panel) return;
  const context = state.importContext;
  if (!context) {
    panel.hidden = true;
    panel.innerHTML = '';
    return;
  }
  const missing = context.faltam_display ?? context.faltam_adicionar ?? 'A definir';
  panel.hidden = false;
  panel.innerHTML = `
    <div class="context-import-icon" aria-hidden="true">↳</div>
    <div class="context-import-copy">
      <span class="eyebrow">Importação vinculada à aula estudada</span>
      <strong>${escapeHtml(context.materia || 'Matéria não informada')} • ${escapeHtml(context.aula || 'Aula não informada')}</strong>
      <p>${escapeHtml(context.task_count > 1 ? `${context.task_count} partes/tarefas estudadas agrupadas nesta aula` : (context.conteudo || 'Conteúdo estudado não informado'))}</p>
      <div class="context-import-meta">
        <span>${escapeHtml(trailLabel(context.trilha))}</span>
        ${Array.isArray(context.tarefas) && context.tarefas.length ? `<span>Tarefas ${escapeHtml(context.tarefas.join(', '))}</span>` : (context.tarefa ? `<span>Tarefa ${escapeHtml(context.tarefa)}</span>` : '')}
        <span>Faltam adicionar: ${escapeHtml(String(missing))}</span>
      </div>
      <small>As questões deste lote serão vinculadas automaticamente à matéria e à aula. Quando várias tarefas da mesma aula foram estudadas, o PDF é tratado como pertencente à aula inteira; o extrator continua identificando os assuntos específicos de cada questão.</small>
    </div>
    <div class="context-import-actions">
      <button class="button button--secondary button--small" type="button" id="returnCoverageFromImport">Voltar à cobertura</button>
      <button class="button button--secondary button--small" type="button" id="clearImportContext">Importação normal</button>
    </div>`;
  $('#returnCoverageFromImport')?.addEventListener('click', () => navigate('coverage'));
  $('#clearImportContext')?.addEventListener('click', () => {
    state.importContext = null;
    renderImportContext();
    toast('Vínculo com o conteúdo estudado removido. A próxima importação será normal.', 'info');
  });
}

async function beginCoverageImport(item) {
  if (state.selectedImportFiles.length) {
    const replaceQueue = window.confirm('Há arquivos na fila de importação. Deseja limpar a fila atual e preparar a importação desta aula estudada?');
    if (!replaceQueue) return;
  }
  const groupId = item?.group_id || '';
  const taskId = item?.task_id || '';
  if (!groupId && !taskId) {
    toast('Essa aula não possui referência suficiente para iniciar a importação.', 'warning');
    return;
  }
  state.importContext = {
    group_id: groupId,
    task_ids: Array.isArray(item.task_ids) ? item.task_ids : (taskId ? [taskId] : []),
    task_id: groupId ? '' : taskId,
    trilha: item.trilha || '',
    tarefas: Array.isArray(item.tarefas) ? item.tarefas : (item.tarefa ? [item.tarefa] : []),
    materia: item.materia || item.subject || '',
    aula: item.aula || item.lesson || '',
    conteudo: item.conteudo || item.content || item.description || '',
    conteudos: Array.isArray(item.content_parts) ? item.content_parts : [],
    task_count: Number(item.task_count || item.task_ids?.length || 1),
    faltam_adicionar: item.faltam_adicionar ?? item.missing_question_count ?? null,
    faltam_display: item.faltam_display ?? item.faltam_adicionar ?? item.missing_question_count ?? 'A definir',
  };
  state.selectedImportFiles = [];
  await navigate('import');
  renderImportContext();
  const result = await bridge.call('choose_import_files', true);
  if (result.paths?.length) {
    state.selectedImportFiles = [...new Set(result.paths)];
    renderImportFiles();
    $('#startImport')?.focus();
  } else {
    toast('Importação da aula preparada. Clique em “Escolher arquivos” quando estiver com o PDF de questões.', 'info');
  }
}

function bindCoverageImportActions(container, rows) {
  const byGroup = new Map((rows || []).map((item) => [String(item.group_id || item.task_id || ''), item]));
  $$('tr[data-study-group-id]', container).forEach((row) => {
    const item = byGroup.get(String(row.dataset.studyGroupId || ''));
    if (!item?.needs_attention) return;

    row.addEventListener('click', (event) => {
      // Preserve native controls and allow the user to select/copy text without
      // accidentally opening the file picker at the end of a drag selection.
      if (event.target?.closest('button, a, input, select, textarea, [contenteditable="true"]')) return;
      const selection = window.getSelection?.();
      if (selection && String(selection).trim()) return;
      beginCoverageImport(item);
    });

    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        beginCoverageImport(item);
      }
    });
  });
}

function renderImportFiles() {
  const list = $('#importFileList');
  $('#importSummary').textContent = state.selectedImportFiles.length ? `${state.selectedImportFiles.length} arquivo(s) na fila.` : 'Nenhum arquivo selecionado.';
  $('#startImport').disabled = !state.selectedImportFiles.length;
  if (!state.selectedImportFiles.length) {
    list.className = 'file-list empty-state';
    list.textContent = 'A fila está vazia.';
    return;
  }
  list.className = 'file-list';
  list.innerHTML = state.selectedImportFiles.map((path, index) => `<div class="file-item"><span title="${escapeHtml(path)}">${escapeHtml(path.split(/[\\/]/).at(-1))}</span><button type="button" data-remove-file="${index}" aria-label="Remover arquivo">×</button></div>`).join('');
  $$('[data-remove-file]', list).forEach((button) => button.addEventListener('click', () => {
    state.selectedImportFiles.splice(Number(button.dataset.removeFile), 1);
    renderImportFiles();
  }));
}

async function chooseImportFiles() {
  const result = await bridge.call('choose_import_files', Boolean(state.importContext));
  if (result.paths?.length) {
    state.selectedImportFiles = [...new Set([...state.selectedImportFiles, ...result.paths])];
    renderImportFiles();
  }
}

async function startImport() {
  const button = $('#startImport');
  setBusy(button, true, 'Processando arquivos');
  try {
    const started = await bridge.call('start_import', state.selectedImportFiles, state.importContext);
    if (!started.ok) throw new Error(started.error || 'Não foi possível iniciar a importação.');
    state.importTask = started.task_id;
    $('#importProgress').hidden = false;
    const completed = await monitorTask(started.task_id, ({ progress, message }) => {
      const percent = Math.round(Number(progress || 0) * 100);
      $('#importProgressValue').textContent = `${percent}%`;
      $('#importProgressText').textContent = message || 'Processando…';
      $('#importProgress .progress-track span').style.width = `${percent}%`;
    });
    if (numberOrZero(completed?.extracted) === 0) {
      const failed = (completed?.reports || []).find((item) => item?.ok === false);
      throw new Error(failed?.error || 'Nenhuma questão foi reconhecida nos arquivos selecionados.');
    }
    const contextual = Boolean(completed?.import_context || state.importContext);
    const after = completed?.coverage_after || null;
    const inserted = numberOrZero(completed?.inserted);
    const duplicates = numberOrZero(completed?.duplicates);
    const repaired = numberOrZero(completed?.repaired);
    const repairedText = repaired ? `, ${formatNumber(repaired)} existente(s) reparada(s)` : '';
    if (contextual && after) {
      const remaining = after.missing_question_count == null ? 'A definir' : formatNumber(after.missing_question_count);
      toast(`Importação vinculada concluída: ${formatNumber(inserted)} nova(s)${repairedText}, ${formatNumber(duplicates)} duplicada(s). Faltam agora: ${remaining}.`, 'success', 8000);
    } else {
      toast(`Importação concluída: ${formatNumber(inserted)} nova(s)${repairedText}, ${formatNumber(duplicates)} duplicada(s).`, 'success');
    }
    state.selectedImportFiles = [];
    renderImportFiles();
    await refreshBootstrap();
    if (contextual) {
      state.coverageSyncedSession = true;
      state.importContext = null;
      renderImportContext();
      await checkStudyGuideWatch({ sync: false }).catch(() => {});
    }
  } catch (error) {
    toast(error.message, 'error', 7000);
  } finally {
    setBusy(button, false);
  }
}

async function monitorTask(taskId, onProgress = () => {}, options = {}) {
  const startedAt = performance.now();
  const timeoutMs = Number(options.timeoutMs || 300000);
  const intervalMs = Number(options.intervalMs || 450);
  while (true) {
    const task = await bridge.call('poll_task', taskId);
    onProgress(task);
    if (task.status === 'done') return task.result;
    if (task.status === 'error') throw new Error(task.error || task.message || 'A tarefa falhou.');
    if (task.status === 'missing') throw new Error('A tarefa não foi encontrada.');
    if (performance.now() - startedAt > timeoutMs) {
      throw new Error('O banco está ocupado ou a operação ultrapassou o tempo esperado. A interface permaneceu ativa; tente novamente em instantes.');
    }
    await sleep(intervalMs);
  }
}

function questionCellHtml(item, key) {
  const lesson = textOrMissing(item.aula, 'Aula não informada');
  const year = textOrMissing(item.ano, 'Ano não informado');
  const cells = {
    codigo: `<span class="cell-code code" role="cell" title="${escapeHtml(textOrMissing(item.codigo))}"><span class="cell-primary">${escapeHtml(textOrMissing(item.codigo))}</span><small class="cell-submeta">${escapeHtml(year)}</small></span>`,
    materia: `<span class="cell-subject" role="cell" title="${escapeHtml(`${textOrMissing(item.materia, 'Matéria não encontrada')} • ${lesson}`)}"><span class="cell-primary">${escapeHtml(textOrMissing(item.materia, 'Matéria não encontrada'))}</span><small class="cell-submeta">${escapeHtml(lesson)}</small></span>`,
    aula: `<span class="cell-lesson" role="cell" title="${escapeHtml(lesson)}">${escapeHtml(lesson)}</span>`,
    assunto: `<span class="cell-topic" role="cell" title="${escapeHtml(textOrMissing(item.assunto || item.enunciado, 'Assunto não encontrado'))}">${escapeHtml(textOrMissing(item.assunto || item.enunciado, 'Assunto não encontrado'))}</span>`,
    ano: `<span class="cell-year" role="cell">${escapeHtml(year)}</span>`,
    status: `<span class="cell-status" role="cell"><span class="status-pill" data-status="${escapeHtml(item.status)}">${escapeHtml(formatStatus(item.status))}</span></span>`,
    origem: `<span class="cell-origin" role="cell">${escapeHtml(intelligenceLabel(item.origem, 'origin'))}</span>`,
    qualidade: `<span class="cell-quality" role="cell"><strong>${Number(item.qualidade || 0).toFixed(0)}</strong><small>/100</small></span>`,
    dificuldade: `<span class="cell-difficulty" role="cell">${escapeHtml(intelligenceLabel(item.dificuldade, 'difficulty'))}</span>`,
  };
  return cells[key] || '';
}

function renderQuestionTableHeader() {
  const head = $('#questionTableHead');
  if (!head) return;
  const order = normalizedQuestionColumnOrder();
  state.questionColumnOrder = order;
  head.style.gridTemplateColumns = questionGridTemplate();
  head.style.width = `${questionGridWidth()}px`;
  syncQuestionHorizontalGeometry();
  syncQuestionHorizontalPosition($('#questionViewport')?.scrollLeft || 0, 'viewport');
  head.innerHTML = order.map((key) => {
    const column = questionColumnDefinitions[key];
    const active = state.questionSort?.key === key;
    const direction = active ? state.questionSort.direction : 'none';
    const arrow = !active ? '↕' : direction === 'asc' ? '↑' : '↓';
    return `<span class="question-head-cell ${column.className}" role="columnheader" data-question-column="${key}" draggable="true" aria-sort="${direction === 'none' ? 'none' : direction === 'asc' ? 'ascending' : 'descending'}"><button type="button" class="question-sort-button" title="Clique para ordenar; arraste para mover; use a borda para redimensionar">${escapeHtml(column.label)} <span aria-hidden="true">${arrow}</span></button><span class="column-resizer" data-question-resize="${key}" aria-hidden="true"></span></span>`;
  }).join('');

  $$('[data-question-column]', head).forEach((cell) => {
    const key = cell.dataset.questionColumn;
    $('.question-sort-button', cell).addEventListener('click', () => {
      const direction = state.questionSort?.key === key && state.questionSort.direction === 'asc' ? 'desc' : 'asc';
      state.questionSort = { key, direction };
      localStorage.setItem('qf-question-sort', JSON.stringify(state.questionSort));
      state.questions = sortQuestionItems(state.questions);
      virtualList?.setItems(state.questions);
      renderQuestionTableHeader();
    });
    cell.addEventListener('dragstart', (event) => {
      event.dataTransfer.setData('text/qf-column', key);
      event.dataTransfer.effectAllowed = 'move';
      cell.classList.add('is-dragging');
    });
    cell.addEventListener('dragend', () => cell.classList.remove('is-dragging'));
    cell.addEventListener('dragover', (event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; });
    cell.addEventListener('drop', (event) => {
      event.preventDefault();
      const source = event.dataTransfer.getData('text/qf-column');
      if (!source || source === key) return;
      const next = normalizedQuestionColumnOrder();
      const from = next.indexOf(source);
      const to = next.indexOf(key);
      next.splice(to, 0, next.splice(from, 1)[0]);
      state.questionColumnOrder = next;
      localStorage.setItem('qf-question-column-order', JSON.stringify(next));
      renderQuestionTableHeader();
      virtualList?.render(true);
    });
  });

  $$('[data-question-resize]', head).forEach((handle) => {
    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const key = handle.dataset.questionResize;
      const column = questionColumnDefinitions[key];
      const startX = event.clientX;
      const startWidth = handle.parentElement.getBoundingClientRect().width;
      const move = (moveEvent) => {
        state.questionColumnWidths[key] = Math.max(column.min, Math.round(startWidth + moveEvent.clientX - startX));
        head.style.gridTemplateColumns = questionGridTemplate();
        head.style.width = `${questionGridWidth()}px`;
        $$('.virtual-row', $('#questionRows')).forEach((row) => {
          row.style.gridTemplateColumns = questionGridTemplate();
          row.style.width = `${questionGridWidth()}px`;
        });
        if (virtualList?.spacer) virtualList.spacer.style.width = `${questionGridWidth()}px`;
        syncQuestionHorizontalGeometry();
      };
      const up = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        localStorage.setItem('qf-question-column-widths', JSON.stringify(state.questionColumnWidths));
        virtualList?.render(true);
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up, { once: true });
    });
  });
}

class VirtualQuestionList {
  constructor(viewport, spacer, rows) {
    this.viewport = viewport;
    this.spacer = spacer;
    this.rows = rows;
    this.items = [];
    this.rowHeight = 54;
    this.buffer = 8;
    this.onSelect = () => {};
    const horizontalScroller = $('#questionHorizontalScroll');
    viewport.addEventListener('scroll', () => {
      this.render();
      syncQuestionHorizontalPosition(viewport.scrollLeft, 'viewport');
    }, { passive: true });
    horizontalScroller?.addEventListener('scroll', () => {
      syncQuestionHorizontalPosition(horizontalScroller.scrollLeft, 'scroller');
    }, { passive: true });
    viewport.addEventListener('wheel', (event) => {
      if (!event.shiftKey || viewport.scrollWidth <= viewport.clientWidth) return;
      event.preventDefault();
      viewport.scrollLeft += event.deltaY || event.deltaX;
    }, { passive: false });
    viewport.addEventListener('keydown', (event) => this.handleKey(event));
    new ResizeObserver(() => this.measure()).observe(viewport);
  }
  measure() {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--list-row-height').trim();
    const numeric = Number.parseFloat(raw);
    const rootFontSize = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const measured = raw.endsWith('rem') ? numeric * rootFontSize : numeric;
    this.rowHeight = Math.max(38, Number.isFinite(measured) ? measured : 54);
    this.spacer.style.height = `${this.items.length * this.rowHeight}px`;
    this.spacer.style.width = `${questionGridWidth()}px`;
    syncQuestionHorizontalGeometry();
    this.render();
  }
  setItems(items) {
    this.items = items || [];
    this.viewport.scrollTop = 0;
    this.spacer.style.height = `${this.items.length * this.rowHeight}px`;
    this.spacer.style.width = `${questionGridWidth()}px`;
    syncQuestionHorizontalGeometry();
    syncQuestionHorizontalPosition(0, 'viewport');
    this.render(true);
  }
  render(force = false) {
    const height = this.viewport.clientHeight || 500;
    const start = Math.max(0, Math.floor(this.viewport.scrollTop / this.rowHeight) - this.buffer);
    const end = Math.min(this.items.length, Math.ceil((this.viewport.scrollTop + height) / this.rowHeight) + this.buffer);
    const key = `${start}:${end}:${state.currentUid}:${force}`;
    if (this.lastKey === key && !force) return;
    this.lastKey = key;
    const fragment = document.createDocumentFragment();
    for (let index = start; index < end; index += 1) {
      const item = this.items[index];
      const row = document.createElement('div');
      row.className = `virtual-row${item.uid === state.currentUid ? ' is-selected' : ''}`;
      row.style.transform = `translateY(${index * this.rowHeight}px)`;
      row.dataset.uid = item.uid;
      row.setAttribute('role', 'row');
      row.setAttribute('tabindex', item.uid === state.currentUid ? '0' : '-1');
      row.setAttribute('aria-selected', item.uid === state.currentUid ? 'true' : 'false');
      const lesson = item.aula || 'Aula não informada';
      const year = item.ano || 'Ano não informado';
      row.setAttribute('aria-label', `${item.codigo || 'Sem código'}; ${item.materia || 'Sem matéria'}; ${lesson}; ${item.assunto || item.enunciado || 'Sem assunto'}; ${formatStatus(item.status)}`);
      row.style.gridTemplateColumns = questionGridTemplate();
      row.style.width = `${questionGridWidth()}px`;
      row.innerHTML = normalizedQuestionColumnOrder().map((key) => questionCellHtml(item, key)).join('');
      row.addEventListener('click', () => this.onSelect(item.uid));
      row.addEventListener('dblclick', () => showTelegramPreview());
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.onSelect(item.uid); }
      });
      fragment.append(row);
    }
    this.rows.replaceChildren(fragment);
  }
  handleKey(event) {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || !this.items.length) return;
    event.preventDefault();
    let index = Math.max(0, this.items.findIndex((item) => item.uid === state.currentUid));
    if (event.key === 'ArrowDown') index = Math.min(this.items.length - 1, index + 1);
    if (event.key === 'ArrowUp') index = Math.max(0, index - 1);
    if (event.key === 'Home') index = 0;
    if (event.key === 'End') index = this.items.length - 1;
    const item = this.items[index];
    this.viewport.scrollTop = Math.max(0, index * this.rowHeight - this.rowHeight * 2);
    this.onSelect(item.uid);
  }
}

let virtualList;

async function loadQuestions() {
  const requestId = ++state.questionRequestId;
  $('#questionCount').textContent = 'Carregando…';
  try {
    const search = $('#questionSearch').value;
    const status = $('#questionStatus').value;
    const query = new URLSearchParams({
      search,
      status,
      offset: '0',
      limit: '2000',
    });
    const result = await bridge.studioGet(
      `questions?${query.toString()}`,
      'list_questions',
      [search, status, 0, 2000],
    );
    if (requestId !== state.questionRequestId) return;
    state.questions = sortQuestionItems(result.items || []);
    state.questionTotal = result.total || state.questions.length;
    $('#questionCount').textContent = state.questionTotal > state.questions.length
      ? `Mostrando ${formatNumber(state.questions.length)} de ${formatNumber(state.questionTotal)} questões`
      : `${formatNumber(state.questionTotal)} questão(ões)`;
    virtualList.setItems(state.questions);
    if (state.currentUid && !state.questions.some((item) => item.uid === state.currentUid)) clearQuestionEditor();
  } catch (error) {
    if (requestId !== state.questionRequestId) return;
    $('#questionCount').textContent = 'Falha ao carregar';
    toast(error.message, 'error');
  }
}

async function ensureMatterOptions(currentValue = '') {
  const existing = Array.isArray(state.taxonomy?.materias) ? state.taxonomy.materias.filter(Boolean) : [];
  if (existing.length) {
    if (currentValue && !existing.includes(currentValue)) {
      state.taxonomy.materias = [...existing, currentValue].sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
    }
    return state.taxonomy.materias;
  }
  if (!state.taxonomyLoading) {
    state.taxonomyLoading = bridge.call('list_materias')
      .then((result) => {
        const items = Array.isArray(result?.items) ? result.items.filter(Boolean) : [];
        state.taxonomy = { ...(state.taxonomy || {}), loaded: true, materias: items };
        return items;
      })
      .finally(() => { state.taxonomyLoading = null; });
  }
  const items = await state.taxonomyLoading;
  if (currentValue && !items.includes(currentValue)) {
    state.taxonomy.materias = [...items, currentValue].sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
  }
  return state.taxonomy.materias;
}

async function selectQuestion(uid) {
  if (state.dirty && uid !== state.currentUid) {
    const proceed = window.confirm('Descartar alterações não salvas e abrir outra questão?');
    if (!proceed) return;
  }
  state.currentUid = uid;
  state.pendingEditorialAiInteractionId = null;
  state.dirty = false;
  virtualList.render(true);
  $('#editorEmpty').hidden = true;
  $('#questionForm').hidden = false;
  $('#questionForm').classList.add('is-loading');
  try {
    const result = await bridge.studioGet(
      `questions/${encodeURIComponent(uid)}`,
      'get_question',
      [uid],
    );
    await ensureMatterOptions(result.question?.materia || '');
    state.currentQuestion = structuredClone(result.question);
    state.originalQuestion = structuredClone(result.question);
    state.currentImage = result.image;
    renderQuestionEditor(result.question, result.image);
  } catch (error) {
    clearQuestionEditor();
    toast(error.message, 'error');
  } finally {
    $('#questionForm').classList.remove('is-loading');
  }
}

const metadataFields = [
  { key: 'codigo_origem', label: 'Código da questão', type: 'code' },
  { key: 'materia', label: 'Matéria da planilha', type: 'matter' },
  { key: 'aula_planilha', label: 'Aula da planilha' },
  { key: 'assunto', label: 'Assunto principal' },
  { key: 'assuntos', label: 'Subassuntos', transform: (value) => Array.isArray(value) ? value.join(' | ') : value },
  { key: 'banca', label: 'Banca' }, { key: 'ano', label: 'Ano', type: 'number' },
  { key: 'orgao', label: 'Órgão' }, { key: 'prova', label: 'Prova completa' },
  { key: 'cargo', label: 'Cargo' }, { key: 'area', label: 'Área' },
  { key: 'especialidade', label: 'Especialidade' }, { key: 'turno', label: 'Turno' },
  { key: 'origem_questao', label: 'Origem editorial', type: 'origin' },
  { key: 'fonte_primaria', label: 'Fonte primária / referência' },
  { key: 'tags', label: 'Tags', transform: (value) => Array.isArray(value) ? value.join(' | ') : value },
  { key: 'referencias_legais', label: 'Referências legais', transform: (value) => Array.isArray(value) ? value.join(' | ') : value },
  { key: 'origem_comentario', label: 'Origem do comentário', type: 'commentary' },
  { key: 'curadoria_responsavel', label: 'Responsável pela curadoria' },
  { key: 'curadoria_notas', label: 'Notas de curadoria' },
  { key: 'tipo', label: 'Tipo', type: 'type' }, { key: 'gabarito', label: 'Gabarito', type: 'answer' },
];

function renderQuestionEditor(question, image) {
  question.origem_questao = question.origem_questao || question.proveniencia?.tipo || 'nao_informada';
  question.fonte_primaria = question.fonte_primaria || question.proveniencia?.fonte_primaria || '';
  question.origem_comentario = question.origem_comentario || question.comentario_meta?.origem || (question.explicacao ? 'manual_nao_classificado' : 'sem_comentario');
  question.curadoria_responsavel = question.curadoria_responsavel || question.curadoria?.responsavel || '';
  question.curadoria_notas = question.curadoria_notas || question.curadoria?.notas || '';
  $('#editorTitle').textContent = question.codigo_origem || 'Questão sem código';
  $('#editorSubtitle').textContent = [question.materia, question.aula_planilha, question.assunto].filter(Boolean).join(' • ') || 'Classificação pendente';
  const status = question.revisao?.status || 'pendente';
  const statusNode = $('#editorStatus');
  statusNode.hidden = false;
  statusNode.dataset.status = status;
  statusNode.textContent = formatStatus(status);
  $('#metadataGrid').innerHTML = metadataFields.map((field) => renderMetadataField(field, question)).join('');
  $('#statementInput').value = question.enunciado || '';
  $('#explanationInput').value = question.explicacao || '';
  const questionType = normalizeQuestionTypeClient(question.tipo);
  state.multipleChoiceDraft = questionType === 'multipla_escolha'
    ? { alternatives: structuredClone(question.alternativas || []), answer: question.gabarito || '' }
    : null;
  renderAlternatives(question.alternativas || [], question.gabarito || '', questionType);
  renderQuestionImage(image);
  if (!question.external_read_only) {
    void loadQuestionIntelligence(question.database_uid || state.currentUid, { scanDuplicates: false });
  }
  updateCharacterCounts();
  autoResizeAll();
  updateEditorActionState();
  $('#editorValidation').textContent = question.revisao?.alertas?.length ? question.revisao.alertas.join(' • ') : 'Pronta para edição.';
  $('#editorValidation').className = `validation-message${question.revisao?.alertas?.length ? ' is-error' : ''}`;
  $$('input, select, textarea', $('#questionForm')).forEach((element) => element.addEventListener('input', markDirty));
  $('#field-tipo')?.addEventListener('change', handleQuestionTypeChange);
  applyCurationReviewActionState();
  if (question.external_read_only) {
    $$('input, select, textarea, button', $('#questionForm')).forEach((element) => {
      if (!element.hasAttribute('data-modal-close')) element.disabled = true;
    });
    $('#editorValidation').textContent = 'Questão consultada na APIdasQuestões. A visualização é somente leitura; o conteúdo externo não é gravado no SQLite.';
    $('#editorValidation').className = 'validation-message';
    const statusNode = $('#editorStatus');
    statusNode.textContent = 'Fonte externa';
    statusNode.dataset.status = 'external';
  }
}

function normalizeQuestionTypeClient(value) {
  return String(value || '').trim().toLocaleLowerCase('pt-BR') === 'certo_errado' ? 'certo_errado' : 'multipla_escolha';
}

function trueFalseOptionsClient() {
  return [{ chave: 'C', texto: 'Certo' }, { chave: 'E', texto: 'Errado' }];
}

function handleQuestionTypeChange() {
  const type = normalizeQuestionTypeClient($('#field-tipo')?.value);
  const currentRows = $$('.alternative-row').map((row, index) => ({
    chave: $('.alternative-key', row)?.value.trim().toUpperCase() || String.fromCharCode(65 + index),
    texto: $('.alternative-text', row)?.value.trim() || '',
  })).filter((item) => item.texto);
  const currentAnswer = $('#field-gabarito')?.value || '';

  if (type === 'certo_errado') {
    const currentlyMultipleChoice = currentRows.some((item) => !['C', 'E'].includes(item.chave) || !['Certo', 'Errado'].includes(item.texto));
    if (currentlyMultipleChoice) {
      state.multipleChoiceDraft = { alternatives: structuredClone(currentRows), answer: currentAnswer };
    }
    const answer = ['C', 'E'].includes(String(currentAnswer).toUpperCase()) ? String(currentAnswer).toUpperCase() : '';
    renderAlternatives(trueFalseOptionsClient(), answer, type);
    toast('Formato alterado para Certo / Errado. As opções agora são somente Certo e Errado.', 'info');
  } else {
    const draft = state.multipleChoiceDraft;
    const alternatives = draft?.alternatives?.length >= 2
      ? structuredClone(draft.alternatives)
      : [{ chave: 'A', texto: '' }, { chave: 'B', texto: '' }];
    const keys = alternatives.map((item) => String(item.chave || '').toUpperCase());
    const answer = draft?.answer && keys.includes(String(draft.answer).toUpperCase()) ? String(draft.answer).toUpperCase() : '';
    renderAlternatives(alternatives, answer, type);
  }
  markDirty();
}

function renderMetadataField(field, question) {
  const raw = question[field.key] ?? '';
  const value = field.transform ? field.transform(raw) : raw;
  let control;
  let help = '';
  if (field.type === 'code') {
    const history = Array.isArray(question.historico_codigos) ? question.historico_codigos : [];
    const last = history[0] || history[history.length - 1] || null;
    const historyText = last
      ? `Última troca registrada: ${textOrMissing(last.old_code || last.codigo_anterior)} → ${textOrMissing(last.new_code || last.codigo_novo)} em ${formatDate(last.changed_at || last.alterado_em)}.`
      : 'Ao alterar e salvar, o novo código será sincronizado em todo o banco e a troca ficará registrada.';
    control = `<input id="field-${field.key}" name="${field.key}" type="text" maxlength="240" autocomplete="off" value="${escapeHtml(value)}" aria-describedby="field-${field.key}-help">`;
    help = `<small class="field-help code-history-help" id="field-${field.key}-help">${escapeHtml(historyText)}</small>`;
  } else if (field.type === 'origin') {
    const options = [
      ['oficial', 'Prova oficial'], ['inedita_propria', 'Inédita própria'], ['adaptada', 'Adaptada'],
      ['literal_norma', 'Literal de norma'], ['manual', 'Manual'], ['nao_informada', 'Não informada'],
    ].map(([key, label]) => `<option value="${key}" ${String(value) === key ? 'selected' : ''}>${label}</option>`).join('');
    control = `<select id="field-${field.key}" name="${field.key}">${options}</select>`;
  } else if (field.type === 'commentary') {
    const options = [
      ['sem_comentario', 'Sem comentário'], ['manual_nao_classificado', 'Comentário humano/manual'],
      ['ia_assistida', 'IA assistida + revisão humana'], ['professor', 'Professor/especialista'], ['fonte_oficial', 'Fonte oficial'],
    ].map(([key, label]) => `<option value="${key}" ${String(value) === key ? 'selected' : ''}>${label}</option>`).join('');
    control = `<select id="field-${field.key}" name="${field.key}">${options}</select>`;
  } else if (field.type === 'matter') {
    const matters = Array.isArray(state.taxonomy?.materias) ? state.taxonomy.materias : [];
    const options = ['', ...matters].map((item) => `<option value="${escapeHtml(item)}" ${item === value ? 'selected' : ''}>${escapeHtml(item || (matters.length ? 'Selecione' : 'Carregando matérias…'))}</option>`).join('');
    control = `<select id="field-${field.key}" name="${field.key}">${options}</select>`;
  } else if (field.type === 'type') {
    control = `<select id="field-${field.key}" name="${field.key}"><option value="multipla_escolha" ${value === 'multipla_escolha' ? 'selected' : ''}>Múltipla escolha</option><option value="certo_errado" ${value === 'certo_errado' ? 'selected' : ''}>Certo / Errado</option></select>`;
  } else if (field.type === 'answer') {
    const keys = (question.alternativas || []).map((item) => item.chave).filter(Boolean);
    const options = ['', ...keys].map((item) => `<option value="${escapeHtml(item)}" ${String(item) === String(value) ? 'selected' : ''}>${escapeHtml(item || 'Sem gabarito')}</option>`).join('');
    control = `<select id="field-${field.key}" name="${field.key}">${options}</select>`;
  } else {
    control = `<input id="field-${field.key}" name="${field.key}" type="${field.type === 'number' ? 'number' : 'text'}" value="${escapeHtml(value)}" ${field.readonly ? 'readonly' : ''}>`;
  }
  return `<div class="form-field${field.type === 'code' ? ' form-field--code' : ''}"><label for="field-${field.key}">${escapeHtml(field.label)}</label>${control}${help}</div>`;
}

function renderAlternatives(alternatives, answer, type = null) {
  const list = $('#alternativesList');
  const resolvedType = normalizeQuestionTypeClient(type || $('#field-tipo')?.value);
  const trueFalse = resolvedType === 'certo_errado';
  const normalized = trueFalse
    ? trueFalseOptionsClient()
    : (alternatives.length ? alternatives : [{ chave: 'A', texto: '' }, { chave: 'B', texto: '' }]);
  const normalizedAnswer = trueFalse && !['C', 'E'].includes(String(answer || '').toUpperCase()) ? '' : String(answer || '').toUpperCase();
  list.dataset.questionType = resolvedType;
  list.innerHTML = normalized.map((item, index) => alternativeRowHtml(item, index, normalizedAnswer, { locked: trueFalse })).join('');
  const addButton = $('#addAlternative');
  if (addButton) addButton.hidden = trueFalse;
  const title = $('#alternativesTitle');
  const subtitle = $('#alternativesSubtitle');
  if (title) title.textContent = trueFalse ? 'Opções de julgamento' : 'Alternativas';
  if (subtitle) subtitle.textContent = trueFalse
    ? 'Questões de Certo / Errado usam somente as opções Certo e Errado.'
    : 'Edite cada opção separadamente. A ordem é preservada no Telegram.';
  bindAlternativeActions();
  updateAnswerOptions(normalizedAnswer);
}

function alternativeRowHtml(item, index, answer, options = {}) {
  const isAnswer = String(item.chave).toUpperCase() === String(answer).toUpperCase();
  const locked = Boolean(options.locked);
  return `<div class="alternative-row${isAnswer ? ' is-answer' : ''}${locked ? ' alternative-row--locked' : ''}" data-alternative-index="${index}">
    <input class="alternative-key" maxlength="4" value="${escapeHtml(item.chave || String.fromCharCode(65 + index))}" aria-label="Chave da alternativa ${index + 1}" ${locked ? 'readonly' : ''}>
    <textarea class="alternative-text" rows="2" aria-label="Texto da alternativa ${index + 1}" ${locked ? 'readonly' : ''}>${escapeHtml(item.texto || '')}</textarea>
    <div class="alternative-actions">
      <button class="mark-answer${isAnswer ? ' is-active' : ''}" type="button" title="Marcar como gabarito" aria-label="Marcar alternativa como correta">✓</button>
      ${locked ? '' : '<button class="remove-alternative" type="button" title="Remover alternativa" aria-label="Remover alternativa">×</button>'}
    </div>
  </div>`;
}

function bindAlternativeActions() {
  $$('.alternative-row', $('#alternativesList')).forEach((row) => {
    $('.mark-answer', row)?.addEventListener('click', () => {
      const key = $('.alternative-key', row).value.trim().toUpperCase();
      $('#field-gabarito').value = key;
      $$('.alternative-row').forEach((item) => item.classList.toggle('is-answer', item === row));
      $$('.mark-answer').forEach((button) => button.classList.toggle('is-active', button.closest('.alternative-row') === row));
      markDirty();
    });
    $('.remove-alternative', row)?.addEventListener('click', () => {
      if ($$('.alternative-row').length <= 2) return toast('A questão deve manter pelo menos duas alternativas.', 'warning');
      row.remove();
      reindexAlternatives();
      markDirty();
    });
    $$('.alternative-key, .alternative-text', row).forEach((element) => element.addEventListener('input', () => {
      updateAnswerOptions($('#field-gabarito').value);
      autoResize(element);
      markDirty();
    }));
  });
}

function reindexAlternatives() {
  $$('.alternative-row').forEach((row, index) => row.dataset.alternativeIndex = index);
  updateAnswerOptions($('#field-gabarito').value);
}

function updateAnswerOptions(selected = '') {
  const select = $('#field-gabarito');
  if (!select) return;
  const keys = $$('.alternative-key').map((input) => input.value.trim().toUpperCase()).filter(Boolean);
  select.innerHTML = `<option value="">Sem gabarito</option>${keys.map((key) => `<option value="${escapeHtml(key)}" ${key === selected ? 'selected' : ''}>${escapeHtml(key)}</option>`).join('')}`;
}

function addAlternative() {
  if (normalizeQuestionTypeClient($('#field-tipo')?.value) === 'certo_errado') {
    return toast('Questões de Certo / Errado possuem apenas as opções Certo e Errado.', 'info');
  }
  const list = $('#alternativesList');
  const index = $$('.alternative-row', list).length;
  list.insertAdjacentHTML('beforeend', alternativeRowHtml({ chave: String.fromCharCode(65 + index), texto: '' }, index, ''));
  bindAlternativeActions();
  updateAnswerOptions($('#field-gabarito').value);
  markDirty();
  $('.alternative-text', list.lastElementChild).focus();
}

function renderQuestionImage(image) {
  state.currentImage = image;
  const img = $('#questionImage');
  const empty = $('#imageEmpty');
  if (image?.src) {
    img.src = image.src;
    img.hidden = false;
    empty.hidden = true;
    $('#removeImage').disabled = false;
  } else {
    img.removeAttribute('src');
    img.hidden = true;
    empty.hidden = false;
    $('#removeImage').disabled = true;
  }
}

function collectQuestionForm() {
  const payload = {};
  metadataFields.forEach((field) => {
    const element = $(`#field-${field.key}`);
    if (element) payload[field.key] = element.value;
  });
  payload.enunciado = $('#statementInput').value.trim();
  payload.explicacao = $('#explanationInput').value.trim();
  payload.alternativas = $$('.alternative-row').map((row, index) => ({
    chave: $('.alternative-key', row).value.trim().toUpperCase() || String.fromCharCode(65 + index),
    texto: $('.alternative-text', row).value.trim(),
  })).filter((item) => item.texto);
  return payload;
}

function validateQuestion(payload) {
  const errors = [];
  const code = String(payload.codigo_origem || '').trim();
  if (!code) errors.push('Informe o código da questão.');
  if (code.length > 240 || /[\u0000-\u001f]/.test(code)) errors.push('O código da questão é inválido.');
  if (!payload.enunciado) errors.push('Informe o enunciado.');
  const trueFalse = normalizeQuestionTypeClient(payload.tipo) === 'certo_errado';
  if (payload.alternativas.length < 2) errors.push(trueFalse ? 'A questão deve possuir as opções Certo e Errado.' : 'Informe pelo menos duas alternativas.');
  const keys = payload.alternativas.map((item) => item.chave);
  if (new Set(keys).size !== keys.length) errors.push('As chaves das alternativas devem ser únicas.');
  if (trueFalse && (keys.join('|') !== 'C|E')) errors.push('Questões de Certo / Errado devem usar somente C (Certo) e E (Errado).');
  if (payload.gabarito && !keys.includes(payload.gabarito.toUpperCase())) errors.push('O gabarito não corresponde a uma alternativa.');
  if (payload.ano && !/^\d{4}$/.test(String(payload.ano))) errors.push('O ano deve ter quatro dígitos.');
  return errors;
}

function applyCurationReviewActionState() {
  const approveButton = $('#approveQuestion');
  const saveButton = $('#saveQuestion');
  if (state.curationReviewContext) {
    if (approveButton) {
      approveButton.textContent = 'Concluir revisão';
      approveButton.title = 'Salva os dados, valida os requisitos críticos e só então conclui a revisão humana.';
    }
    if (saveButton) {
      saveButton.textContent = 'Salvar rascunho';
      saveButton.title = 'Salva as alterações sem concluir a revisão humana; a questão continuará na Curadoria.';
    }
  } else {
    if (approveButton) { approveButton.textContent = 'Salvar e aprovar'; approveButton.title = ''; }
    if (saveButton) { saveButton.textContent = 'Salvar alterações'; saveButton.title = ''; }
  }
}

async function saveCurrentQuestion(approve = false) {
  if (!state.currentUid) return;
  if (state.currentQuestion?.external_read_only) {
    return toast('Questões da APIdasQuestões são somente leitura no Studio.', 'info');
  }
  const payload = collectQuestionForm();
  payload.codigo_origem = String(payload.codigo_origem || '').trim();
  const previousCode = String(state.originalQuestion?.codigo_origem || '').trim();
  const codeChanged = Boolean(previousCode && payload.codigo_origem && previousCode !== payload.codigo_origem);
  const classificationChanged = String(payload.materia || '').trim().toLocaleLowerCase('pt-BR') !== String(state.originalQuestion?.materia || '').trim().toLocaleLowerCase('pt-BR')
    || String(payload.aula_planilha || '').trim().toLocaleLowerCase('pt-BR') !== String(state.originalQuestion?.aula_planilha || '').trim().toLocaleLowerCase('pt-BR');
  const errors = validateQuestion(payload);
  if (errors.length) {
    $('#editorValidation').textContent = errors.join(' ');
    $('#editorValidation').className = 'validation-message is-error';
    return toast(errors[0], 'error');
  }
  if (codeChanged) {
    const proceed = window.confirm(`Alterar o código de ${previousCode} para ${payload.codigo_origem}?\n\nO QuestFlow atualizará a identificação em todo o banco, preservará o UID e registrará esta troca no histórico.`);
    if (!proceed) return;
  }
  const button = approve ? $('#approveQuestion') : $('#saveQuestion');
  setBusy(button, true, 'Salvando questão');
  try {
    const completingCuration = Boolean(approve && state.curationReviewContext);
    // Na Curadoria, salvar e concluir são duas operações deliberadamente
    // separadas: primeiro persiste o que o usuário editou; depois o backend
    // valida os requisitos reais antes de registrar a decisão humana.
    const approveOnSave = completingCuration ? false : approve;
    const result = await bridge.studioPost(
      `questions/${encodeURIComponent(state.currentUid)}`,
      { question: payload, approve: approveOnSave },
      'save_question',
      [state.currentUid, payload, approveOnSave],
    );

    let finalResult = result;
    if (completingCuration) {
      const completion = await bridge.call('complete_curation_review', state.currentUid, 'Revisão humana pelo editor da Curadoria');
      if (!completion?.ok) {
        state.currentQuestion = structuredClone(result.question);
        state.originalQuestion = structuredClone(result.question);
        state.dirty = false;
        renderQuestionEditor(result.question, state.currentImage);
        applyCurationReviewActionState();
        const blockers = Array.isArray(completion?.blocking_missing) ? completion.blocking_missing : [];
        const detail = blockers.length ? ` Pendência crítica: ${blockers.join(' • ')}.` : '';
        if (blockers.length) showEditorCurationBlockers(blockers);
        toast(`Alterações salvas, mas esta questão continua na Curadoria.${detail} ${blockers.length ? 'Use “Ir ao campo” no rodapé ou na Inteligência e curadoria.' : ''} ${completion?.error || ''}`.trim(), 'warning', 10000);
        await Promise.allSettled([loadQuestions(), refreshBootstrap(), loadBankIntelligence(), loadQuestionIntelligence(state.currentUid, { scanDuplicates: false })]);
        return;
      }
      finalResult = { ...result, question: completion.question || result.question, curation_summary: completion.summary, curation_completed: true };
    }

    state.currentQuestion = structuredClone(finalResult.question);
    state.originalQuestion = structuredClone(finalResult.question);
    state.dirty = false;
    if (state.pendingEditorialAiInteractionId && (completingCuration || approve)) {
      try {
        await bridge.call('review_ai_interaction', state.pendingEditorialAiInteractionId, 'aprovar', 'Explicação pesquisada no Google conferida e salva explicitamente pelo usuário no editor.');
      } catch (auditError) { console.warn('Auditoria da revisão humana do comentário Google:', auditError); }
      state.pendingEditorialAiInteractionId = null;
    }
    renderQuestionEditor(finalResult.question, state.currentImage);
    const change = result.code_change || {};
    const successMessage = change.code_changed
      ? `Código alterado de ${change.old_code} para ${change.new_code}; referências e histórico sincronizados.`
      : classificationChanged
        ? 'Classificação corrigida. Matéria/aula foram atualizadas no banco e a cobertura foi recalculada.'
        : (completingCuration ? 'Revisão humana concluída. A questão foi retirada da pendência da Curadoria.' : (approve ? 'Questão aprovada.' : (state.curationReviewContext ? 'Rascunho salvo. A questão continua pendente até você concluir a revisão.' : 'Alterações salvas.')));
    toast(successMessage, completingCuration ? 'success' : 'success', completingCuration ? 6500 : 4500);
    if (completingCuration) {
      state.curationReviewContext = false;
      applyCurationReviewActionState();
    } else if (state.curationReviewContext) {
      applyCurationReviewActionState();
      const curation = result.curation || {};
      if (curation.can_complete_review && !curation.human_approved) {
        toast('Os dados foram salvos, mas esta questão ainda conta como pendente. Use “Concluir revisão”.', 'info', 7000);
      }
    }
    if (classificationChanged) await Promise.allSettled([loadQuestions(), refreshBootstrap(), loadCoverage({ sync: false }), loadBankIntelligence()]);
    else { await Promise.allSettled([loadQuestions(), refreshBootstrap(), loadBankIntelligence()]); }
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    setBusy(button, false);
  }
}

function clearQuestionEditor() {
  state.currentUid = null;
  state.pendingEditorialAiInteractionId = null;
  state.currentQuestion = null;
  state.originalQuestion = null;
  state.currentImage = null;
  state.questionIntelligence = null;
  state.multipleChoiceDraft = null;
  state.dirty = false;
  state.curationReviewContext = false;
  applyCurationReviewActionState();
  $('#editorEmpty').hidden = false;
  $('#questionForm').hidden = true;
  $('#editorTitle').textContent = 'Selecione uma questão';
  $('#editorSubtitle').textContent = 'Os campos aparecerão aqui.';
  $('#editorStatus').hidden = true;
  updateEditorActionState();
  virtualList?.render(true);
}

function updateEditorActionState() {
  const active = Boolean(state.currentUid);
  ['#deleteQuestion', '#annulQuestion', '#rereadQuestion', '#reviewPreview', '#showAiBrief', '#showKnowledgeGraph', '#showHybridEvidence'].forEach((selector) => {
    const element = $(selector);
    if (element) element.disabled = !active;
  });
  const contextualTitles = {
    '#showAiBrief': ['Abrir contexto/RAG da questão selecionada', 'Selecione uma questão para visualizar o contexto/RAG'],
    '#showKnowledgeGraph': ['Abrir mapa de conceitos da questão selecionada', 'Selecione uma questão para abrir o mapa de conceitos'],
    '#showHybridEvidence': ['Visualizar evidências híbridas da questão selecionada', 'Selecione uma questão para visualizar evidências híbridas'],
  };
  Object.entries(contextualTitles).forEach(([selector, titles]) => { const element=$(selector); if(element) element.title=active ? titles[0] : titles[1]; });
}

function markDirty() {
  state.dirty = true;
  $('#editorValidation').textContent = 'Há alterações não salvas.';
  $('#editorValidation').className = 'validation-message text-warning';
  updateCharacterCounts();
}

function updateCharacterCounts() {
  $('#statementCount').textContent = `${formatNumber($('#statementInput').value.length)} caracteres`;
  $('#explanationCount').textContent = `${formatNumber($('#explanationInput').value.length)} caracteres`;
}

function autoResize(textarea) {
  if (!(textarea instanceof HTMLTextAreaElement) || textarea.classList.contains('alternative-text') === false && !textarea.closest('.rich-text-field')) return;
  textarea.style.height = 'auto';
  const max = Math.max(220, window.innerHeight * 0.7);
  textarea.style.height = `${Math.min(max, textarea.scrollHeight + 2)}px`;
}

function autoResizeAll() {
  $$('#questionForm textarea').forEach(autoResize);
}

function normalizeText(text) {
  return text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/[ \t]{2,}/g, ' ').trim();
}

function setupRichTextTools() {
  $$('.rich-text-field').forEach((field) => {
    const textarea = $('textarea', field);
    $('.text-toolbar', field).addEventListener('click', async (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      const action = button.dataset.action;
      if (action === 'copy') {
        await navigator.clipboard.writeText(textarea.value);
        toast('Texto copiado.', 'success');
      } else if (action === 'expand') {
        field.classList.toggle('is-expanded');
        button.textContent = field.classList.contains('is-expanded') ? 'Fechar expansão' : 'Expandir';
        textarea.focus();
      } else if (action === 'format') {
        textarea.value = normalizeText(textarea.value);
        autoResize(textarea);
        markDirty();
      }
    });
  });
}

async function createQuestion() {
  try {
    const result = await bridge.studioPost('questions', {}, 'create_manual_question');
    await loadQuestions();
    await selectQuestion(result.uid);
  } catch (error) {
    toast(error.message || 'Não foi possível criar a questão.', 'error');
  }
}

async function deleteQuestion() {
  if (!state.currentUid || !window.confirm('Excluir definitivamente esta questão da base ativa?')) return;
  const result = await bridge.call('delete_question', state.currentUid);
  if (!result.ok) return toast(result.error || 'Não foi possível excluir.', 'error');
  clearQuestionEditor();
  await loadQuestions();
  await refreshBootstrap();
  toast('Questão excluída.', 'success');
}

async function annulQuestion() {
  if (!state.currentUid) return;
  const reason = window.prompt('Motivo da anulação:', 'Questão anulada pela banca');
  if (reason === null) return;
  const result = await bridge.call('annul_question', state.currentUid, reason);
  if (!result.ok) return toast(result.error || 'Não foi possível arquivar.', 'error');
  clearQuestionEditor();
  await loadQuestions();
  await refreshBootstrap();
  toast('Questão marcada como anulada e removida da base ativa.', 'success');
}

async function attachImage() {
  if (!state.currentUid) return;
  const result = await bridge.call('attach_image', state.currentUid);
  if (result.ok) { renderQuestionImage(result.image); toast('Imagem associada.', 'success'); }
  else if (!result.cancelled) toast(result.error || 'Não foi possível anexar.', 'error');
}

async function removeImage() {
  if (!state.currentUid || !window.confirm('Remover a imagem desta questão?')) return;
  const result = await bridge.call('remove_image', state.currentUid);
  if (result.ok) { renderQuestionImage(null); toast('Imagem removida.', 'success'); }
}

async function rereadQuestion() {
  if (!state.currentUid) return;
  const button = $('#rereadQuestion');
  setBusy(button, true, 'Relendo arquivo original');
  $('#reviewToolbarStatus').textContent = 'Preparando releitura…';
  try {
    const result = await bridge.call('start_reread', state.currentUid);
    if (!result.ok) {
      if (result.cancelled) return;
      throw new Error(result.error || 'Não foi possível iniciar a releitura.');
    }
    await monitorTask(result.task_id, (task) => {
      $('#reviewToolbarStatus').textContent = `${Math.round(Number(task.progress || 0) * 100)}% • ${task.message || ''}`;
    });
    await selectQuestion(state.currentUid);
    await loadQuestions();
    toast('Questão relida e atualizada para conferência.', 'success');
  } catch (error) {
    toast(error.message, 'error', 7000);
  } finally {
    setBusy(button, false);
    $('#reviewToolbarStatus').textContent = '';
  }
}

function showTelegramPreview() {
  if (!state.currentUid) return;
  const question = collectQuestionForm();
  const answer = String(question.gabarito || '').toUpperCase();
  const code = textOrMissing(question.codigo_origem, 'Código não informado');
  const subject = textOrMissing(question.materia, 'Matéria não informada');
  const details = [question.aula_planilha, question.assunto].filter(Boolean).join(' • ');
  const source = [question.banca, question.ano, question.orgao].filter(Boolean).join(' • ');
  const options = question.alternativas.map((item) => `<div class="telegram-poll-option${item.chave === answer ? ' is-correct' : ''}"><span class="telegram-option-marker">${item.chave === answer ? '✓' : '○'}</span><span><strong>${escapeHtml(item.chave)}</strong> ${escapeHtml(item.texto)}</span></div>`).join('');
  const explanation = question.explicacao
    ? `<div class="telegram-message telegram-message--explanation"><div class="telegram-message-label">💡 POR QUE ESSA É A RESPOSTA?</div><div class="telegram-explanation-text">${escapeHtml(question.explicacao).replaceAll('\n', '<br>')}</div><div class="telegram-message-time">agora ✓✓</div></div>`
    : `<div class="telegram-message telegram-message--notice"><strong>Explicação não cadastrada</strong><span>Use “Corrigir questão” para completar este conteúdo antes do próximo envio.</span><div class="telegram-message-time">agora ✓✓</div></div>`;
  const image = state.currentImage?.src ? `<div class="telegram-message telegram-message--image"><img src="${state.currentImage.src}" alt="Imagem da questão" loading="lazy"><div class="telegram-message-time">agora ✓✓</div></div>` : '';
  openModal({
    eyebrow: 'Prévia visual', title: 'Novo formato do Telegram',
    body: `<div class="telegram-preview telegram-preview--modern">
      <div class="telegram-day-separator"><span>Hoje</span></div>
      <div class="telegram-message telegram-message--header">
        <div class="telegram-brand-line"><span class="telegram-brand-icon">Q</span><div><strong>QUESTFLOW • QUESTÃO</strong><span>Treino adaptativo</span></div></div>
        <div class="telegram-question-meta"><strong>📚 ${escapeHtml(subject)}</strong>${details ? `<span>🗂 ${escapeHtml(details)}</span>` : ''}${source ? `<span>🏛 ${escapeHtml(source)}</span>` : ''}<code>🔖 ${escapeHtml(code)}</code></div>
        <div class="telegram-message-time">agora ✓✓</div>
      </div>
      ${image}
      <div class="telegram-message telegram-message--poll">
        ${normalizeQuestionTypeClient(question.tipo) === 'certo_errado' ? '<div class="telegram-message-label">📝 JULGUE O ITEM: CERTO OU ERRADO</div>' : '<div class="telegram-message-label">📝 MARQUE A ALTERNATIVA CORRETA</div>'}
        <h3>${escapeHtml(question.enunciado || 'Enunciado não informado')}</h3>
        <div class="telegram-poll-options">${options}</div>
        <div class="telegram-poll-note">Quiz • a alternativa marcada em verde representa o gabarito após a resposta</div>
        <div class="telegram-message-time">agora ✓✓</div>
      </div>
      <div class="telegram-message telegram-message--result is-correct">
        <div class="telegram-result-title">✅ <strong>RESPOSTA CORRETA</strong></div>
        <div class="telegram-answer-row"><span>Sua resposta</span><strong>${escapeHtml(answer || 'Não informada')}</strong></div>
        <div class="telegram-answer-row"><span>Gabarito</span><strong>${escapeHtml(answer || 'Não informado')}</strong></div>
        <div class="telegram-progress-chip">🎯 +12 XP • resposta registrada</div>
        <div class="telegram-message-time">agora ✓✓</div>
      </div>
      ${explanation}
      <div class="telegram-inline-actions" aria-label="Botões que aparecem no Telegram"><span>🛠 Corrigir questão</span><span>➡ Próxima</span><span>📊 Desempenho</span></div>
    </div>`,
    footer: '<button class="button button--primary" data-modal-close>Fechar prévia</button>',
  });
}

function formatStatus(status) {
  const labels = { aprovado: 'Aprovada', aprovado_automaticamente: 'Aprovada auto.', pendente: 'Pendente', enviada: 'Enviada', erro: 'Erro' };
  return labels[status] || status || 'Pendente';
}

async function loadFlow() {
  $('#flowStatusPanel').innerHTML = '<div class="skeleton" style="height:8rem"></div>';
  try {
    const data = await bridge.call('get_flow');
    renderFlowStatus(data.status || {});
    renderFsrsStatus(data.optimizer || {}, data.adaptive || {}, data.learning || {});
    renderFlowSettings(data.settings || state.config);
    renderTelegramBotSettings(data.settings || state.config);
    renderFlowHistory(data.recent || []);
  } catch (error) {
    toast(error.message, 'error');
  }
}

function renderFlowStatus(status) {
  const qPaused=Boolean(status.telegram_questions_paused);
  $('#flowStatusPanel').innerHTML = `<div class="stack">
    <div class="inline-cluster"><span class="status-dot ${status.running ? 'status-dot--ok' : ''}"></span><strong>${status.running ? 'Agendador ativo' : 'Agendador parado'}</strong></div>
    <div class="inline-cluster"><span class="muted">Listener</span><strong class="flow-value">${status.listening ? 'Conectado' : 'Desconectado'}</strong></div>
    <div class="inline-cluster"><span class="muted">Novas questões pelo Telegram</span><strong class="flow-value ${qPaused?'text-warning':'text-success'}">${qPaused?'PAUSADAS':'ATIVAS'}</strong></div>
    <div class="notice ${qPaused?'notice--info':'notice--warning'}"><strong>${qPaused?'Aplicativo como canal principal':'Telegram e aplicativo podem enviar questões'}</strong><span>${qPaused?'O histórico e o listener continuam ativos; apenas novos envios/reenvios de questões ficam bloqueados.':'Se você está validando o aplicativo, pause o envio de questões para não misturar os ciclos de estudo.'}</span></div>
    <div class="inline-cluster"><span class="muted">Próxima execução</span><strong class="flow-value">${qPaused?'Suspensa para questões':escapeHtml(formatDate(status.next_run))}</strong></div>
  </div>`;
  if($('#telegramQuestionsPause')) $('#telegramQuestionsPause').disabled=qPaused;
  if($('#telegramQuestionsResume')) $('#telegramQuestionsResume').disabled=!qPaused;
  if($('#sendCycleNow')) $('#sendCycleNow').disabled=qPaused;
}

function renderFsrsStatus(optimizer, adaptive, learning) {
  const panel = $('#fsrsStatusPanel');
  if (!panel) return;
  const available = Boolean(optimizer.available && optimizer.optimizer_available);
  const retention = Number(optimizer.effective_retention || adaptive.effective_target_retention || learning.manual_retention || 0.88);
  const days = adaptive.days_to_exam;
  const trained = optimizer.trained_at ? formatDate(optimizer.trained_at) : 'Ainda não personalizado';
  const calibration = adaptive.calibration_comparison || {};
  const adaptiveBrier = Number(calibration.adaptive?.brier);
  const fsrsBrier = Number(calibration.fsrs?.brier);
  const calibrationText = Number.isFinite(fsrsBrier) && Number(calibration.fsrs?.samples || 0) > 0
    ? `Brier FSRS ${fsrsBrier.toFixed(3)} • adaptativo ${Number.isFinite(adaptiveBrier) ? adaptiveBrier.toFixed(3) : '—'} • melhor: ${escapeHtml(calibration.best_calibrated || '—')}`
    : 'Calibração FSRS será comparada após acumular respostas agendadas pelo novo motor.';
  panel.innerHTML = `<div class="stack">
    <div class="inline-cluster"><span class="status-dot ${available ? 'status-dot--ok' : ''}"></span><strong>${available ? 'Py-FSRS 6 + otimizador ativos' : 'FSRS/otimizador indisponível'}</strong><span class="muted">${escapeHtml(optimizer.fsrs_version || '')}</span></div>
    <div class="inline-cluster"><span class="muted">Retenção efetiva</span><strong>${Math.round(retention * 100)}%</strong><span class="muted">Parâmetros personalizados: ${optimizer.parameters_active ? 'sim' : 'ainda não'}</span></div>
    <div class="inline-cluster"><span class="muted">Histórico para otimização</span><strong>${Number(optimizer.total_reviews || 0)} revisões</strong><span class="muted">${Number(optimizer.question_count || 0)} questões • treino: ${escapeHtml(trained)}</span></div>
    <div class="inline-cluster"><span class="muted">Carga estimada</span><strong>${Number(adaptive.recommended_daily_questions || 0)} questões/dia</strong><span class="muted">capacidade aproximada ${Number(adaptive.daily_capacity || 0)}/dia${days == null ? '' : ` • ${days} dia(s) até a prova`}</span></div>
    <div class="inline-cluster"><span class="muted">Conteúdo estudado</span><strong>${Number(adaptive.studied_groups || 0)} matéria/aula</strong><span class="muted">Relearning vencido: ${Number(adaptive.relearning_due || 0)}</span></div>
    <div class="inline-cluster"><span class="muted">Calibração</span><span>${calibrationText}</span></div>
  </div>`;
}

const flowSettingFields = [
  { key: 'flow_enabled', label: 'Ciclo diário ativo', type: 'checkbox' },
  { key: 'flow_daily_time', label: 'Horário diário', type: 'time' },
  { key: 'flow_questions_per_cycle', label: 'Questões por ciclo', type: 'number', min: 1, max: 100 },
  { key: 'flow_target_retention_mode', label: 'Retenção', type: 'select', options: [['optimized', 'Otimizada automaticamente pelo FSRS'], ['manual', 'Manual']] },
  { key: 'flow_target_retention', label: 'Retenção manual', type: 'number', min: 0.7, max: 0.97, step: 0.01, help: 'Usada no modo manual e como valor inicial antes da primeira otimização.' },
  { key: 'flow_exam_date', label: 'Data da prova', type: 'date', help: 'O scheduler limita intervalos para que a revisão não ultrapasse o horizonte da prova.' },
  { key: 'flow_daily_study_minutes', label: 'Tempo diário para questões (min)', type: 'number', min: 5, max: 600 },
  { key: 'flow_studied_only', label: 'Revisar somente conteúdo já estudado', type: 'checkbox' },
  { key: 'flow_relearning_enabled', label: 'Recuperação automática após erro', type: 'checkbox' },
  { key: 'flow_relearning_minutes', label: 'Primeira recuperação após erro (min)', type: 'number', min: 1, max: 1440 },
  { key: 'flow_fsrs_auto_optimize', label: 'Otimizar FSRS automaticamente', type: 'checkbox' },
  { key: 'flow_dynamic_cycle_size', label: 'Ajustar tamanho do ciclo à carga estimada', type: 'checkbox' },
  { key: 'flow_early_review_enabled', label: 'Permitir revisão antes do vencimento', type: 'checkbox' },
  { key: 'flow_fsrs_max_interval_days', label: 'Intervalo máximo FSRS (dias)', type: 'number', min: 1, max: 36500 },
  { key: 'flow_approved_only', label: 'Somente aprovadas', type: 'checkbox' },
  { key: 'flow_unanswered_resend_enabled', label: 'Reenviar sem resposta', type: 'checkbox' },
  { key: 'flow_unanswered_resend_hours', label: 'Prazo sem resposta (h)', type: 'number', min: 1, max: 720 },
  { key: 'flow_delay_seconds', label: 'Intervalo entre questões (s)', type: 'number', min: 1, max: 600 },
  { key: 'flow_question_card_enabled', label: 'Mostrar cartão com matéria, aula e código', type: 'checkbox' },
  {
    key: 'flow_explanation_mode', label: 'Depois que eu responder', type: 'select',
    options: [
      ['automatico', 'Mostrar resultado e explicação completa'],
      ['resultado_curto', 'Mostrar resultado curto e botão de explicação'],
      ['somente_botao', 'Mostrar explicação somente quando eu pedir'],
    ],
    help: 'O formato novo destaca sua marcação, o gabarito e a explicação em blocos separados.',
  },
];

function renderFlowSettings(settings) {
  const form = $('#flowSettingsForm');
  form.innerHTML = flowSettingFields.map((field) => {
    const value = settings[field.key];
    if (field.type === 'checkbox') return `<div class="form-field form-field--switch"><label class="switch-field" for="flow-${field.key}"><input id="flow-${field.key}" type="checkbox" name="${field.key}" ${value ? 'checked' : ''}><span class="switch-control" aria-hidden="true"></span><span>${escapeHtml(field.label)}</span></label></div>`;
    if (field.type === 'select') {
      const options = (field.options || []).map(([optionValue, optionLabel]) => `<option value="${escapeHtml(optionValue)}" ${String(optionValue) === String(value) ? 'selected' : ''}>${escapeHtml(optionLabel)}</option>`).join('');
      return `<div class="form-field form-field--wide"><label for="flow-${field.key}">${escapeHtml(field.label)}</label><select id="flow-${field.key}" name="${field.key}">${options}</select>${field.help ? `<small class="field-help">${escapeHtml(field.help)}</small>` : ''}</div>`;
    }
    return `<div class="form-field"><label for="flow-${field.key}">${escapeHtml(field.label)}</label><input id="flow-${field.key}" name="${field.key}" type="${field.type}" value="${escapeHtml(value ?? '')}" ${field.min != null ? `min="${field.min}"` : ''} ${field.max != null ? `max="${field.max}"` : ''} ${field.step != null ? `step="${field.step}"` : ''}>${field.help ? `<small class="field-help">${escapeHtml(field.help)}</small>` : ''}</div>`;
  }).join('');
}

function collectFlowSettings() {
  const payload = {};
  flowSettingFields.forEach((field) => {
    const input = $(`[name="${field.key}"]`, $('#flowSettingsForm'));
    if (!input) return;
    payload[field.key] = field.type === 'checkbox' ? input.checked : field.type === 'number' ? Number(input.value) : input.value;
  });
  return payload;
}

function renderTelegramBotSettings(settings) {
  const tokenInput = $('#telegramBotToken');
  const chatInput = $('#telegramChatId');
  if (!tokenInput || !chatInput) return;
  tokenInput.value = '';
  chatInput.value = settings.telegram_chat_id || '';
  const masked = settings.telegram_bot_token_masked || '';
  $('#telegramTokenHint').textContent = masked
    ? `Token atual: ${masked}. Deixe o campo vazio para mantê-lo.`
    : 'Nenhum token configurado.';
  const configured = Boolean(masked && String(settings.telegram_chat_id || '').trim());
  const status = $('#telegramConfigStatus');
  status.textContent = configured ? 'Configurado' : 'Configuração incompleta';
  status.dataset.status = configured ? 'aprovado' : 'pendente';
}

function collectTelegramSettings() {
  const token = $('#telegramBotToken').value.trim();
  const chatId = $('#telegramChatId').value.trim();
  const payload = { telegram_chat_id: chatId };
  if (token) payload.telegram_bot_token = token;
  return payload;
}

async function saveTelegramSettings() {
  const button = $('#saveTelegramSettings');
  setBusy(button, true, 'Salvando configuração do Telegram');
  try {
    const payload = collectTelegramSettings();
    if (!payload.telegram_chat_id) throw new Error('Informe o Chat ID do Telegram.');
    const result = await bridge.call('save_flow_settings', payload);
    if (!result.ok) throw new Error(result.error || 'Não foi possível salvar o bot.');
    state.config = { ...state.config, ...(result.settings || payload) };
    renderTelegramBotSettings(result.settings || state.config);
    toast('Configuração do bot salva.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  } finally { setBusy(button, false); }
}

async function testTelegramConnection() {
  const button = $('#testTelegramConnection');
  setBusy(button, true, 'Testando conexão com o Telegram');
  const status = $('#telegramConfigStatus');
  try {
    const payload = collectTelegramSettings();
    const result = await bridge.call('test_telegram_connection', payload.telegram_bot_token || '', payload.telegram_chat_id || '');
    if (!result.ok) throw new Error(result.error || 'O Telegram não respondeu.');
    status.textContent = result.username ? `Conectado: @${result.username}` : textOrMissing(result.bot_name, 'Bot conectado');
    status.dataset.status = 'aprovado';
    toast(`Conexão confirmada com ${result.username ? `@${result.username}` : result.bot_name}.`, 'success');
  } catch (error) {
    status.textContent = 'Falha na conexão';
    status.dataset.status = 'pendente';
    toast(error.message, 'error', 7000);
  } finally { setBusy(button, false); }
}

function renderFlowHistory(items) {
  const container = $('#flowHistory');
  if (!items.length) {
    container.innerHTML = emptyStateHtml({ text: 'Nenhum envio registrado.' });
    return;
  }
  const normalized = items.slice(0, 100).map(normalizeDelivery);
  container.innerHTML = tableHtml([
    { label: 'Data', key: 'sent_at', type: 'date' },
    { label: 'Código', key: 'codigo', render: (value) => `<button type="button" class="table-link" data-open-question>${escapeHtml(value)}</button>` },
    { label: 'Matéria', key: 'materia' },
    { label: 'Status', key: 'status' },
    { label: 'Tentativas', key: 'attempts', type: 'number' },
    { label: 'Motivo', key: 'last_error', fallback: 'Sem erro registrado' },
  ], normalized, { id: 'flow-history', rowUidKey: 'question_uid' });
  enhanceManagedTables(container);
  bindHistoryQuestionRows(container);
}

async function flowAction(action, button = null) {
  setBusy(button, true);
  try {
    const result = await bridge.call('flow_action', action);
    if (!result.ok) throw new Error(result.error || 'A ação falhou.');
    if (result.task_id) await monitorTask(result.task_id);
    toast(action === 'send_now' ? 'Ciclo enviado.' : 'Estado do fluxo atualizado.', 'success');
    await loadFlow();
  } catch (error) {
    toast(error.message, 'error');
  } finally { setBusy(button, false); }
}

async function saveFlowSettings() {
  const result = await bridge.call('save_flow_settings', collectFlowSettings());
  if (result.ok) toast('Configuração do fluxo salva.', 'success');
  else toast(result.error || 'Falha ao salvar.', 'error');
}

async function loadCorrections() {
  try {
    const result = await bridge.call('list_corrections', 'ativas');
    state.corrections = result.items || [];
    state.correctionsSummary = result.summary || { editorial: 0, not_studied: 0, total: state.corrections.length };
    $('#correctionsBadge').hidden = !state.corrections.length;
    $('#correctionsBadge').textContent = state.corrections.length;
    renderCorrections();
  } catch (error) { toast(error.message, 'error'); }
}

function correctionTypeBadge(item = {}) {
  if (item.item_type === 'not_studied') return '<span class="status-pill correction-kind correction-kind--study">Ainda não estudado</span>';
  return '<span class="status-pill correction-kind correction-kind--editorial">Correção da questão</span>';
}

function openNotStudiedCorrection(item) {
  if (!item) return;
  const markedCount = Math.max(1, Number(item.mark_count || 1));
  const code = textOrMissing(item.question_code || item.codigo, 'Questão sem código');
  const subject = textOrMissing(item.materia, 'Matéria não informada');
  const topic = textOrMissing(item.assunto, 'Assunto não informado');
  const lesson = textOrMissing(item.aula, 'Aula não informada');
  const statement = textOrMissing(item.statement, 'O enunciado da questão não está mais disponível na base local.');
  const markedAt = formatDate(item.updated_at || item.created_at);
  const firstAt = formatDate(item.created_at);
  openModal({
    title: 'Assunto ainda não estudado',
    eyebrow: 'Mobile → Studio · triagem pedagógica',
    body: `<div class="not-studied-modal">
      <div class="not-studied-callout"><strong>Esta marcação não conta como erro.</strong><span>O aluno indicou no aplicativo que ainda não estudou este assunto. A questão foi retirada da sessão e o conteúdo ficou pendente para estudo.</span></div>
      <div class="not-studied-meta-grid">
        <div><span>Questão</span><strong>${escapeHtml(code)}</strong></div>
        <div><span>Matéria</span><strong>${escapeHtml(subject)}</strong></div>
        <div><span>Assunto</span><strong>${escapeHtml(topic)}</strong></div>
        <div><span>Aula</span><strong>${escapeHtml(lesson)}</strong></div>
        <div><span>Última marcação</span><strong>${escapeHtml(markedAt)}</strong></div>
        <div><span>Vezes marcada</span><strong>${markedCount}</strong></div>
      </div>
      <div class="not-studied-question"><span>Questão que originou a marcação</span><p>${escapeHtml(statement)}</p></div>
      <div class="not-studied-guidance"><strong>O que fazer no Studio</strong><p>Estude o conteúdo indicado e, quando ele já tiver sido coberto, use <b>Marcar como estudado</b>. O QuestFlow então poderá voltar a considerar questões desse assunto nas próximas sessões adaptativas.</p><small>Primeira marcação: ${escapeHtml(firstAt)} · Origem: QuestFlow Mobile</small></div>
    </div>`,
    footer: `<button class="button button--secondary" type="button" data-modal-close>Fechar</button>
      ${item.question_uid ? '<button class="button button--secondary" type="button" data-not-studied-open-question>Abrir questão no banco</button>' : ''}
      <button class="button button--success" type="button" data-not-studied-resolve>Marcar como estudado</button>`,
    onOpen: (layer) => {
      const openQuestion = $('[data-not-studied-open-question]', layer);
      if (openQuestion) openQuestion.addEventListener('click', async () => {
        closeModal();
        await navigate('review');
        await selectQuestion(item.question_uid);
      }, { once: true });
      const resolve = $('[data-not-studied-resolve]', layer);
      if (resolve) resolve.addEventListener('click', async () => {
        setBusy(resolve, true, 'Marcando conteúdo como estudado');
        try {
          const result = await bridge.call('correction_action', item.id, 'mark_studied');
          if (!result?.ok) throw new Error(result?.error || 'Não foi possível concluir a pendência.');
          closeModal();
          toast('Assunto marcado como estudado. Ele poderá voltar às próximas sessões adaptativas.', 'success', 7000);
          await loadCorrections();
          await loadDashboard({ force: true });
        } catch (error) { toast(error.message, 'error', 7000); }
        finally { setBusy(resolve, false); }
      }, { once: true });
    },
  });
}

function correctionRowsHtml(items, kind) {
  if (!items.length) {
    return emptyStateHtml({
      title: kind === 'not_studied' ? 'Nenhuma matéria pendente de estudo' : 'Nenhuma correção pendente',
      text: kind === 'not_studied'
        ? 'Quando você marcar no Mobile que ainda não estudou um conteúdo, ele aparecerá aqui separado das correções.'
        : 'Questões marcadas para correção editorial aparecerão aqui.',
    });
  }
  const columns = [
    { label: 'Data', key: 'created_at', type: 'date' },
    { label: 'Código', key: 'question_code', className: 'mono', fallback: 'Código não encontrado' },
    { label: 'Matéria / assunto', key: 'materia', render: (_value, item) => `<div class="correction-topic-cell"><strong>${escapeHtml(textOrMissing(item.materia, 'Matéria não encontrada'))}</strong><small>${escapeHtml(textOrMissing(item.assunto || item.primary_topic, kind === 'not_studied' ? 'Assunto não informado' : '—'))}${item.aula ? ` · ${escapeHtml(item.aula)}` : ''}</small></div>` },
    { label: 'Status', key: 'status', render: (value) => kind === 'not_studied' ? '<span class="status-pill" data-tone="warning">Aguardando estudo</span>' : escapeHtml(textOrMissing(value, 'Status não informado')) },
    { label: 'Ações', key: 'id', render: (_value, item) => kind === 'not_studied'
      ? `<div class="inline-cluster"><button class="button button--small button--primary" data-not-studied-window="${escapeHtml(item.id)}">Ver detalhes</button><button class="button button--small button--success" data-correction-study-resolve="${escapeHtml(item.id)}">Marcar estudado</button><button class="button button--small button--danger-ghost" data-correction-delete="${escapeHtml(item.id)}">Remover marcação</button></div>`
      : `<div class="inline-cluster"><button class="button button--small button--secondary" data-correction-open="${escapeHtml(item.id)}" data-question-uid="${escapeHtml(item.question_uid)}">Abrir</button><button class="button button--small button--success" data-correction-resolve="${escapeHtml(item.id)}">Resolver</button><button class="button button--small button--danger-ghost" data-correction-delete="${escapeHtml(item.id)}">Excluir fila</button></div>` },
  ];
  return tableHtml(columns, items.map((item) => ({ ...item, question_code: item.question_code || item.codigo, user_name: item.user_name || item.user_id })), { id: kind === 'not_studied' ? 'not-studied-corrections' : 'editorial-corrections' });
}

function bindCorrectionActions(container) {
  $$('[data-not-studied-window]', container).forEach((button) => button.addEventListener('click', () => {
    openNotStudiedCorrection(state.corrections.find((item) => String(item.id) === String(button.dataset.notStudiedWindow)));
  }));
  $$('[data-correction-open]', container).forEach((button) => button.addEventListener('click', async () => {
    await bridge.call('correction_action', button.dataset.correctionOpen, 'open');
    await navigate('review');
    await selectQuestion(button.dataset.questionUid);
  }));
  $$('[data-correction-resolve]', container).forEach((button) => button.addEventListener('click', async () => {
    await bridge.call('correction_action', button.dataset.correctionResolve, 'resolve');
    await loadCorrections();
    await loadDashboard({ force: true });
  }));
  $$('[data-correction-study-resolve]', container).forEach((button) => button.addEventListener('click', async () => {
    const result = await bridge.call('correction_action', button.dataset.correctionStudyResolve, 'mark_studied');
    if (!result?.ok) return toast(result?.error || 'Não foi possível marcar o assunto como estudado.', 'error');
    toast('Assunto marcado como estudado.', 'success');
    await loadCorrections();
    await loadDashboard({ force: true });
  }));
  $$('[data-correction-delete]', container).forEach((button) => button.addEventListener('click', async () => {
    const isStudy = String(button.dataset.correctionDelete || '').startsWith('not_studied:');
    if (isStudy && !window.confirm('Remover esta marcação? O assunto poderá voltar a ser selecionado mesmo sem ser marcado como estudado.')) return;
    await bridge.call('correction_action', button.dataset.correctionDelete, 'delete');
    await loadCorrections();
    await loadDashboard({ force: true });
  }));
}

function renderCorrections() {
  const editorialContainer = $('#editorialCorrectionsTable');
  const studyContainer = $('#notStudiedCorrectionsTable');
  const overview = $('#correctionsOverview');
  if (!editorialContainer || !studyContainer) return;

  const editorial = state.corrections.filter((item) => item.item_type !== 'not_studied');
  const notStudied = state.corrections.filter((item) => item.item_type === 'not_studied');
  const summary = state.correctionsSummary || { editorial: editorial.length, not_studied: notStudied.length, total: state.corrections.length };

  if (overview) overview.innerHTML = `
    <article><span>Correções</span><strong>${Number(summary.editorial || editorial.length || 0)}</strong><small>Questões que precisam de ajuste no banco.</small></article>
    <article class="is-study"><span>Matérias não estudadas</span><strong>${Number(summary.not_studied || notStudied.length || 0)}</strong><small>Conteúdos que ainda precisam ser estudados, sem penalizar desempenho.</small></article>`;

  const editorialCount = $('#editorialCorrectionsCount');
  const studyCount = $('#notStudiedCorrectionsCount');
  if (editorialCount) editorialCount.textContent = `${editorial.length} ${editorial.length === 1 ? 'pendência' : 'pendências'}`;
  if (studyCount) studyCount.textContent = `${notStudied.length} ${notStudied.length === 1 ? 'pendência' : 'pendências'}`;

  editorialContainer.innerHTML = correctionRowsHtml(editorial, 'correction');
  studyContainer.innerHTML = correctionRowsHtml(notStudied, 'not_studied');
  enhanceManagedTables(editorialContainer);
  enhanceManagedTables(studyContainer);
  bindCorrectionActions(editorialContainer);
  bindCorrectionActions(studyContainer);
}

function trailLabel(value) {
  const match = String(value ?? '').match(/(?:TRILHA\s*)?(\d{1,3})/i);
  if (!match) return textOrMissing(value, '—');
  return `Trilha ${String(Number(match[1])).padStart(2, '0')}`;
}

function renderTrailGuideStatus(status = {}) {
  state.guideStatus = status || {};
  const missing = Array.isArray(status?.missing_studied_trails) ? status.missing_studied_trails : [];
  const badge = $('#coverageGuideBadge');
  if (badge) {
    badge.textContent = String(missing.length || 0);
    badge.hidden = missing.length === 0;
    badge.title = missing.length ? `${missing.length} trilha(s) estudada(s) sem PDF explicativo` : '';
  }

  const available = textOrMissing(status?.available_label, 'Nenhuma trilha documentada');
  const next = textOrMissing(status?.next_expected_label, 'próxima trilha');
  const studiedTrailLabels = (status?.studied_trails || []).map(trailLabel).join(', ');
  let title = `Explicações incorporadas: ${available}`;
  let detail = `Você informou PDFs explicativos somente até ${textOrMissing(status?.documented_through_label, 'a trilha atual')}. Quando avançar, incorpore os PDFs das novas trilhas.`;
  let tone = 'ok';

  if (missing.length) {
    tone = 'warning';
    const labels = missing.map((item) => item.label || trailLabel(item.trail)).join(', ');
    title = `Atenção: falta a explicação de ${labels}`;
    detail = missing.map((item) => {
      const subjects = (item.subjects || []).slice(0, 6).join(', ');
      const tasks = (item.tasks || []).slice(0, 12).join(', ');
      const suffix = `${subjects ? ` Matérias já registradas: ${subjects}.` : ''}${tasks ? ` Tarefas detectadas: ${tasks}.` : ''}`;
      return `${item.message || `Você já registrou estudo em ${item.label || trailLabel(item.trail)}, mas o PDF dessa trilha ainda não foi incorporado.`}${suffix}`;
    }).join(' ');
  } else if (status?.documented_through != null) {
    detail = `As explicações disponíveis vão até ${textOrMissing(status.documented_through_label, trailLabel(status.documented_through))}. O próximo documento esperado é ${next}. ${studiedTrailLabels ? `Trilhas com estudo registrado: ${studiedTrailLabels}.` : 'Ainda não há trilhas estudadas no snapshot atual.'}`;
  }

  const statusPanel = $('#trailGuideStatus');
  if (statusPanel) {
    statusPanel.dataset.tone = tone;
    statusPanel.innerHTML = `<div class="trail-guide-status-main"><span class="trail-guide-status-icon" aria-hidden="true">${missing.length ? '!' : '✓'}</span><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p></div></div><div class="trail-guide-status-actions"><button class="button button--secondary button--compact" type="button" data-add-trail-guide>Adicionar PDF explicativo</button></div>`;
  }

  const dashboardPanel = $('#trailGuideDashboardPanel');
  if (dashboardPanel) {
    dashboardPanel.innerHTML = `<div class="trail-guide-dashboard-state" data-tone="${escapeHtml(tone)}"><span class="trail-guide-status-icon" aria-hidden="true">${missing.length ? '!' : '✓'}</span><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p></div>${missing.length ? '<button class="button button--secondary button--compact" type="button" data-go-coverage>Ver pendência</button>' : ''}</div>`;
  }

  const knowledge = status?.knowledge || {};
  const cycle = knowledge?.sheet_roles?.ciclo || {};
  const map = knowledge?.sheet_roles?.mapa || {};
  const knowledgeBody = $('#trailGuideKnowledgeBody');
  if (knowledgeBody) {
    knowledgeBody.innerHTML = `<div class="trail-guide-knowledge-grid">
      <div><strong>CICLO_REG</strong><p>O QuestFlow considera a tarefa estudada quando você registra evidência real de execução. Campos usados: ${escapeHtml((cycle.study_evidence || cycle.fill_fields || ['DATA', 'CH EFETIVA', 'TOT QUEST FEITAS', 'TOT ACERTOS']).join(', '))}.</p><small>DESEMPENHO é lido como resultado; a quantidade de questões e acertos alimenta a análise.</small></div>
      <div><strong>MAPA_AF</strong><p>É a visão de evolução por aula. A lógica incorporada reconhece ${escapeHtml((map.fill_fields || ['T+R = SIM', 'QTD EXE', 'ACERTOS']).join(', '))}.</p><small>A cobertura de questões continua sendo calculada no nível de tarefa/conteúdo do CICLO_REG.</small></div>
      <div><strong>Documentação das trilhas</strong><p>${escapeHtml(available)} estão incorporadas. ${missing.length ? `Há ${missing.length} trilha(s) estudada(s) sem explicação.` : `O próximo PDF esperado é ${next}.`}</p><small>Os PDFs são analisados para registrar metadados e regras; não precisam ficar carregados na interface.</small></div>
    </div>`;
  }

  $$('[data-add-trail-guide]').forEach((button) => button.addEventListener('click', addTrailGuidePdfs));
  $$('[data-go-coverage]').forEach((button) => button.addEventListener('click', () => navigate('coverage')));
}

function notifyMissingTrailGuides(status = {}) {
  const missing = Array.isArray(status?.missing_studied_trails) ? status.missing_studied_trails : [];
  if (!missing.length) {
    state.lastGuideWarningSignature = '';
    return;
  }
  const signature = missing.map((item) => Number(item.trail)).sort((a, b) => a - b).join(',');
  if (signature === state.lastGuideWarningSignature) return;
  state.lastGuideWarningSignature = signature;
  const labels = missing.map((item) => item.label || trailLabel(item.trail)).join(', ');
  toast(`Você já registrou estudo em ${labels}, mas ainda não adicionou o PDF explicativo dessa(s) trilha(s).`, 'warning', 12000);
}

async function addTrailGuidePdfs(event = null) {
  const trigger = event?.currentTarget || $('#addTrailGuide');
  if (trigger) setBusy(trigger, true, 'Selecionando PDF');
  try {
    const selected = await bridge.call('choose_trail_guide_files');
    const paths = selected?.paths || [];
    if (!paths.length) return;
    if (trigger) setBusy(trigger, true, 'Incorporando explicação');
    const result = await bridge.call('import_trail_guides', paths);
    if (!result?.imported?.length) throw new Error(result?.error || result?.errors?.[0]?.error || 'Nenhuma trilha foi incorporada.');
    toast(result.message || 'Explicação da trilha incorporada.', result.errors?.length ? 'warning' : 'success', 9000);
    if (result.status) {
      renderTrailGuideStatus(result.status);
      notifyMissingTrailGuides(result.status);
    }
    await loadCoverage({ sync: false });
  } catch (error) {
    toast(error.message || 'Não foi possível incorporar o PDF da trilha.', 'error', 9000);
  } finally {
    if (trigger) setBusy(trigger, false);
  }
}

async function checkStudyGuideWatch({ sync = true } = {}) {
  if (state.guideWatchPromise) return state.guideWatchPromise;
  state.guideWatchPromise = (async () => {
    try {
      const result = await bridge.call(sync ? 'sync_study_coverage' : 'get_coverage');
      if (result?.guide_status) {
        renderTrailGuideStatus(result.guide_status);
        notifyMissingTrailGuides(result.guide_status);
      }
      if (result?.synced) state.coverageSyncedSession = true;
      if (state.route === 'coverage' && Array.isArray(result?.items)) {
        state.coverage = result.items;
        state.coverageSummary = result.summary || {};
        state.coverageSource = result.source || {};
        state.coverageGeneratedAt = result.generated_at || '';
        state.guideStatus = result.guide_status || state.guideStatus || {};
        renderCoverageSummary(result);
        renderCoverage();
      }
      return result;
    } catch (_) {
      return null;
    } finally {
      state.guideWatchPromise = null;
    }
  })();
  return state.guideWatchPromise;
}

function startStudyGuideWatch() {
  // Não existe push direto do Google Sheets nesta aplicação. Enquanto o QuestFlow
  // estiver aberto, verificamos a planilha em intervalos curtos e também quando
  // o usuário volta para a janela. A trava em checkStudyGuideWatch evita sobreposição.
  const intervalMs = 2 * 60 * 1000;
  const minFocusGapMs = 45 * 1000;
  const run = async () => {
    if (document.hidden) return null;
    state.lastGuideWatchAt = Date.now();
    return checkStudyGuideWatch({ sync: true });
  };
  const loop = async () => {
    await run();
    window.setTimeout(loop, document.hidden ? intervalMs * 2 : intervalMs);
  };
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && Date.now() - Number(state.lastGuideWatchAt || 0) >= minFocusGapMs) run();
  });
  window.addEventListener('focus', () => {
    if (Date.now() - Number(state.lastGuideWatchAt || 0) >= minFocusGapMs) run();
  });
  window.setTimeout(loop, 5000);
}

async function loadCoverage(options = {}) {
  const shouldSync = options.sync ?? !state.coverageSyncedSession;
  $('#coverageTable').innerHTML = '<div class="coverage-loading"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>';
  $('#coverageSummary').innerHTML = Array.from({ length: 4 }, () => '<article class="metric-card"><div class="skeleton"></div><div class="skeleton"></div></article>').join('');
  const syncButton = $('#syncCoverage');
  if (syncButton) {
    syncButton.disabled = shouldSync;
    syncButton.textContent = shouldSync ? 'Sincronizando…' : 'Sincronizar planilha';
  }
  try {
    const result = await bridge.call(shouldSync ? 'sync_study_coverage' : 'get_coverage');
    state.coverage = result.items || [];
    state.coverageSummary = result.summary || {};
    state.coverageSource = result.source || {};
    state.coverageGeneratedAt = result.generated_at || '';
    state.guideStatus = result.guide_status || state.guideStatus || {};
    if (result.synced) state.coverageSyncedSession = true;
    renderCoverageSummary(result);
    renderTrailGuideStatus(state.guideStatus);
    notifyMissingTrailGuides(state.guideStatus);
    renderCoverage();
    if (shouldSync && result.ok === false) {
      toast(result.message || result.error || 'Não foi possível sincronizar a planilha.', 'warning');
    } else if (shouldSync && result.synced) {
      toast('Planilha de estudos sincronizada.', 'success');
    }
  } catch (error) {
    $('#coverageSummary').innerHTML = '';
    $('#coverageTable').innerHTML = emptyStateHtml({ title: 'Não foi possível analisar os estudos', text: error.message });
    $('#coverageSyncNote').textContent = `Falha ao carregar: ${error.message}`;
    toast(error.message, 'error');
  } finally {
    if (syncButton) {
      syncButton.disabled = false;
      syncButton.textContent = 'Sincronizar planilha';
    }
  }
}

function renderCoverageSummary(result = {}) {
  const summary = state.coverageSummary || {};
  const metrics = [
    ['Aulas estudadas', formatNumber(numberOrZero(summary.studied_groups ?? summary.studied_contents)), `${formatNumber(numberOrZero(summary.studied_subjects))} matérias • ${formatNumber(numberOrZero(summary.studied_tasks ?? summary.studied_contents))} tarefas`],
    ['Aulas com pendência', formatNumber(numberOrZero(summary.contents_needing_questions)), 'Agrupadas por trilha + matéria + aula'],
    ['Faltam adicionar', formatNumber(numberOrZero(summary.known_missing_questions)), 'Quantidade conhecida pela planilha'],
    ['Cobertos', formatNumber(numberOrZero(summary.covered_contents)), 'Já possuem cobertura no banco'],
  ];
  $('#coverageSummary').innerHTML = metrics.map(([label, value, detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
  const source = state.coverageSource?.title || 'planilha configurada';
  const generated = state.coverageGeneratedAt ? formatDate(state.coverageGeneratedAt) : 'snapshot local';
  const prefix = result.synced ? 'Sincronizado agora' : 'Último snapshot';
  $('#coverageSyncNote').innerHTML = `<strong>${escapeHtml(prefix)}:</strong> ${escapeHtml(source)} • ${escapeHtml(generated)}. A análise considera somente linhas com evidência de estudo e agrupa tarefas da mesma trilha, matéria e aula para importar o PDF da aula uma única vez.`;
}

function renderCoverage() {
  const search = $('#coverageSearch').value.trim().toLocaleLowerCase('pt-BR');
  const statusFilter = $('#coverageStatus').value;
  const rows = state.coverage.filter((item) => {
    const haystack = `${item.materia || item.subject || ''} ${item.aula || item.lesson || ''} ${item.conteudo || item.content || ''} ${item.description || ''}`.toLocaleLowerCase('pt-BR');
    const itemStatus = item.status_code || item.status || '';
    const statusMatch = statusFilter === 'todos'
      || (statusFilter === 'pendentes' && Boolean(item.needs_attention))
      || (statusFilter === 'cobertos' && ['coberto', 'coberto_sem_meta'].includes(itemStatus))
      || itemStatus === statusFilter;
    return (!search || haystack.includes(search)) && statusMatch;
  });
  if (!rows.length) {
    const text = statusFilter === 'pendentes'
      ? 'Nenhuma pendência encontrada entre os conteúdos marcados como estudados.'
      : 'Nenhum conteúdo estudado corresponde aos filtros.';
    $('#coverageTable').innerHTML = emptyStateHtml({ text });
    return;
  }
  const normalized = rows.map((item) => ({
    ...item,
    trilha_display: trailLabel(item.trilha),
    materia_display: item.materia || item.subject,
    aula_display: item.aula || item.lesson || '—',
    conteudo_display: item.conteudo || item.content || item.description,
    group_id: item.group_id || item.task_id || '',
    task_ids: Array.isArray(item.task_ids) ? item.task_ids : (item.task_id ? [item.task_id] : []),
    partes_display: Number(item.task_count || item.task_ids?.length || 1),
    questoes_planilha_display: item.questoes_planilha ?? item.questions_done ?? 0,
    questoes_banco_display: item.questoes_banco ?? item.bank_question_count ?? 0,
    faltam_display_value: item.faltam_display ?? (item.faltam_adicionar ?? item.missing_question_count ?? 'A definir'),
    acertos_display: item.acertos_planilha ?? item.correct_answers ?? 0,
    desempenho_display: `${Number(item.desempenho_planilha ?? item.performance ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`,
    situacao_display: item.situacao || item.status,
  }));
  const container = $('#coverageTable');
  container.innerHTML = tableHtml([
    { label: 'Trilha', key: 'trilha_display', className: 'coverage-trail', fallback: '—' },
    { label: 'Matéria', key: 'materia_display', className: 'coverage-subject', fallback: 'Matéria não encontrada' },
    { label: 'Aula', key: 'aula_display', className: 'coverage-lesson', fallback: '—' },
    { label: 'Conteúdo estudado', key: 'conteudo_display', className: 'coverage-topics', fallback: 'Conteúdo não informado', render: (value, item) => `<div class="coverage-content-group">${item.partes_display > 1 ? `<span class="coverage-group-badge">${escapeHtml(String(item.partes_display))} partes da mesma aula</span>` : ''}<span>${escapeHtml(textOrMissing(value, 'Conteúdo não informado'))}</span></div>` },
    { label: 'CH efetiva', key: 'ch_efetiva', fallback: '—' },
    { label: 'Questões feitas', key: 'questoes_planilha_display', type: 'number' },
    { label: 'No banco', key: 'questoes_banco_display', type: 'number' },
    { label: 'Faltam adicionar', key: 'faltam_display_value', render: (value, item) => item.needs_attention
      ? `<strong class="coverage-missing coverage-missing--row-action" data-attention="1" title="Clique em qualquer ponto desta linha para adicionar o PDF">${escapeHtml(String(value))}<span aria-hidden="true"> ↗</span></strong>`
      : `<strong class="coverage-missing" data-attention="0">${escapeHtml(String(value))}</strong>` },
    { label: 'Acertos', key: 'acertos_display', type: 'number' },
    { label: 'Desempenho', key: 'desempenho_display' },
    { label: 'Situação', key: 'situacao_display', render: (value, item) => `<span class="coverage-status" data-status="${escapeHtml(item.status_code || item.status || '')}">${escapeHtml(textOrMissing(value, 'Situação não informada'))}</span>` },
  ], normalized, {
    id: 'coverage-studied',
    wrapClass: 'data-table-wrap--coverage',
    tableClass: 'data-table--coverage',
    rowDataKey: 'group_id',
    rowDataAttribute: 'study-group-id',
    rowInteractive: true,
    rowInteractiveWhen: (item) => Boolean(item.needs_attention),
    rowInteractiveTitle: 'Clique em qualquer ponto desta linha para adicionar o PDF de questões desta aula',
  });
  enhanceManagedTables(container);
  bindCoverageImportActions(container, normalized);
}


async function loadBankFixOptions({ resetLesson = false } = {}) {
  const matterSelect = $('#bankFixMatter');
  const lessonSelect = $('#bankFixLesson');
  if (!matterSelect || !lessonSelect) return;
  const currentMatter = matterSelect.value || '';
  const currentLesson = resetLesson ? '' : (lessonSelect.value || '');
  const result = await bridge.call('get_bank_classification_options', currentMatter, '');
  if (!result?.ok) throw new Error(result?.error || 'Não foi possível carregar as matérias e aulas do banco.');
  state.bankFixOptions = result;
  state.bankFixOptionsSubject = currentMatter;
  const filterSubjects = result.bank_subjects || result.subjects || [];
  const subjectOptions = ['<option value="">Todas as matérias</option>', ...filterSubjects.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)];
  matterSelect.innerHTML = subjectOptions.join('');
  matterSelect.value = filterSubjects.includes(currentMatter) ? currentMatter : '';
  const filterLessons = result.bank_lessons || result.lessons || [];
  const lessonOptions = ['<option value="">Todas as aulas</option>', ...filterLessons.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)];
  lessonSelect.innerHTML = lessonOptions.join('');
  lessonSelect.value = !resetLesson && filterLessons.includes(currentLesson) ? currentLesson : '';
}

function renderBankFixSummary() {
  const total = numberOrZero(state.bankFixTotal);
  const shown = state.bankFixQuestions.length;
  const matter = $('#bankFixMatter')?.value || 'Todas';
  const lesson = $('#bankFixLesson')?.value || 'Todas';
  const metrics = [
    ['Encontradas', formatNumber(total), 'Com os filtros atuais'],
    ['Carregadas', formatNumber(shown), total > shown ? `Mostrando as primeiras ${formatNumber(shown)}` : 'Todas as encontradas'],
    ['Matéria', matter, matter === 'Todas' ? 'Banco completo' : 'Filtro ativo'],
    ['Aula', lesson, lesson === 'Todas' ? 'Todas as aulas' : 'Filtro ativo'],
  ];
  $('#bankFixSummary').innerHTML = metrics.map(([label, value, detail]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`).join('');
}

function bankFixGroupKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleUpperCase('pt-BR')
    .replace(/[^A-Z0-9]+/g, ' ')
    .trim();
}

function bankFixLessonKey(value) {
  const text = bankFixGroupKey(value);
  const match = text.match(/^(?:AULA\s*)?(\d{1,3})$/);
  return match ? `AULA ${String(Number(match[1])).padStart(2, '0')}` : text;
}

function bankFixCanonicalLesson(value) {
  const key = bankFixLessonKey(value);
  return /^AULA \d{2,3}$/.test(key) ? `Aula ${key.slice(5)}` : (String(value || '').trim() || 'Sem aula');
}

function groupBankFixQuestions(items) {
  const subjects = new Map();
  (items || []).forEach((item) => {
    const matter = String(item.materia || '').trim() || 'Sem matéria';
    const lesson = String(item.aula || '').trim() || 'Sem aula';
    const matterKey = bankFixGroupKey(matter) || 'SEM MATERIA';
    const lessonKey = bankFixLessonKey(lesson) || 'SEM AULA';
    if (!subjects.has(matterKey)) subjects.set(matterKey, { matter, matterKey, lessons: new Map(), count: 0 });
    const subject = subjects.get(matterKey);
    if (!subject.lessons.has(lessonKey)) subject.lessons.set(lessonKey, { matter, lesson, lessonKey, items: [], titles: new Map(), topics: new Map() });
    const group = subject.lessons.get(lessonKey);
    group.items.push(item);
    subject.count += 1;
    const title = String(item.titulo_aula || '').trim();
    const topic = String(item.assunto || '').trim();
    if (title) group.titles.set(title, (group.titles.get(title) || 0) + 1);
    if (topic) group.topics.set(topic, (group.topics.get(topic) || 0) + 1);
  });
  const mostFrequent = (values) => [...values.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'pt-BR'))[0]?.[0] || '';
  return [...subjects.values()]
    .sort((a, b) => a.matter.localeCompare(b.matter, 'pt-BR', { numeric: true }))
    .map((subject) => ({
      ...subject,
      lessons: [...subject.lessons.values()]
        .map((group) => ({ ...group, title: mostFrequent(group.titles), suggestedTitle: mostFrequent(group.topics), topicCount: group.topics.size }))
        .sort((a, b) => a.lessonKey.localeCompare(b.lessonKey, 'pt-BR', { numeric: true })),
    }));
}

function bankFixLessonTable(group, index) {
  return tableHtml([
    { label: 'Código', key: 'codigo', className: 'cell-code', render: (value) => `<strong class="mono">${escapeHtml(textOrMissing(value, 'Sem código'))}</strong>` },
    { label: 'Assunto da questão', key: 'assunto', className: 'cell-topic', fallback: 'Sem assunto' },
    { label: 'Banca', key: 'banca', fallback: '—' },
    { label: 'Ano', key: 'ano', type: 'number', fallback: '—' },
    { label: 'Status', key: 'status', render: (value) => `<span class="status-pill" data-status="${escapeHtml(value)}">${escapeHtml(formatStatus(value))}</span>` },
    { label: 'Ações', key: 'uid', className: 'bank-fix-actions', render: (_value, item) => `<div class="inline-cluster"><button class="button button--small button--primary" type="button" data-bank-fix-correct="${escapeHtml(item.uid)}">Corrigir</button><button class="button button--small button--secondary" type="button" data-bank-fix-editor="${escapeHtml(item.uid)}">Editor completo</button><button class="button button--small button--danger-ghost" type="button" data-bank-fix-delete="${escapeHtml(item.uid)}" data-question-code="${escapeHtml(item.codigo || '')}">Excluir</button></div>` },
  ], group.items, { id: `bank-fix-${index}`, rowUidKey: 'uid', emptyText: 'Nenhuma questão nesta aula.' });
}

function renderBankFixTable() {
  const container = $('#bankFixTable');
  const items = state.bankFixQuestions || [];
  if (!items.length) {
    container.innerHTML = emptyStateHtml({ title: 'Nenhuma questão encontrada', text: 'Ajuste a matéria, aula, status ou termo de busca.' });
    return;
  }
  let lessonIndex = 0;
  const groups = groupBankFixQuestions(items);
  container.innerHTML = `<div class="bank-fix-groups">${groups.map((subject, subjectIndex) => `
    <details class="bank-fix-subject" ${subjectIndex < 2 || groups.length === 1 ? 'open' : ''}>
      <summary><span><small>MATÉRIA</small><strong>${escapeHtml(subject.matter)}</strong></span><span class="bank-fix-count-badge">${formatNumber(subject.count)} questões · ${formatNumber(subject.lessons.length)} aulas</span></summary>
      <div class="bank-fix-lessons">${subject.lessons.map((group, groupIndex) => {
        lessonIndex += 1;
        const title = group.title || group.suggestedTitle || 'Título da aula ainda não definido';
        const inferred = !group.title && Boolean(group.suggestedTitle);
        const canOrganize = group.lessonKey !== 'SEM AULA' && subject.matterKey !== 'SEM MATERIA';
        return `<details class="bank-fix-lesson" ${groupIndex === 0 ? 'open' : ''}>
          <summary>
            <span class="bank-fix-lesson-identity"><strong>${escapeHtml(bankFixCanonicalLesson(group.lesson))}</strong><span>${escapeHtml(title)}</span>${inferred ? '<small>Sugestão a confirmar</small>' : ''}</span>
            <span class="bank-fix-lesson-meta"><span>${formatNumber(group.items.length)} questões</span><span>${formatNumber(group.topicCount)} assuntos</span>${canOrganize ? `<button class="button button--small button--secondary" type="button" data-bank-fix-group="${escapeHtml(`${subject.matterKey}::${group.lessonKey}`)}">Organizar aula</button>` : ''}</span>
          </summary>
          <div class="bank-fix-lesson-body">${bankFixLessonTable(group, lessonIndex)}</div>
        </details>`;
      }).join('')}</div>
    </details>`).join('')}</div>`;
  enhanceManagedTables(container);
  bindBankFixRows(container);
  $$('[data-bank-fix-group]', container).forEach((button) => button.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const [matterKey, lessonKey] = String(button.dataset.bankFixGroup || '').split('::');
    const subject = groups.find((item) => item.matterKey === matterKey);
    const group = subject?.lessons.find((item) => item.lessonKey === lessonKey);
    if (group) openBankFixLessonGroup(subject, group);
  }));
}

function openBankFixLessonGroup(subject, group) {
  const sourceMatter = subject?.matter || group?.matter || '';
  const sourceLesson = group?.lesson || '';
  const suggestedTitle = group?.title || group?.suggestedTitle || '';
  const subjects = state.bankFixOptions?.subjects || state.bankFixOptions?.bank_subjects || [];
  openModal({
    title: `${bankFixCanonicalLesson(sourceLesson)} · ${sourceMatter}`,
    eyebrow: 'Organizar matéria e aula',
    body: `<div class="bank-fix-modal">
      <div class="bank-fix-question-preview">
        <strong>${formatNumber(group?.items?.length || 0)} questões serão organizadas juntas</strong>
        <span>Origem atual: ${escapeHtml(sourceMatter)} • ${escapeHtml(sourceLesson)}</span>
        <p>O título da aula organiza o grupo. Os assuntos específicos de cada questão continuam preservados.</p>
      </div>
      <div class="form-grid bank-fix-classification-grid">
        <div class="form-field"><label for="bankFixGroupMatter">Matéria correta</label><input id="bankFixGroupMatter" list="bankFixGroupMatterOptions" value="${escapeHtml(sourceMatter)}" autocomplete="off"><datalist id="bankFixGroupMatterOptions">${subjects.map((item) => `<option value="${escapeHtml(item)}"></option>`).join('')}</datalist><small class="field-help">Você pode selecionar uma matéria existente ou escrever uma nova.</small></div>
        <div class="form-field"><label for="bankFixGroupLesson">Número da aula</label><input id="bankFixGroupLesson" value="${escapeHtml(bankFixCanonicalLesson(sourceLesson))}" placeholder="Aula 00" autocomplete="off"><small class="field-help">Aula 0, Aula 00 e 00 serão reconhecidas como o mesmo grupo.</small></div>
        <div class="form-field form-field--wide"><label for="bankFixGroupTitle">Título canônico da aula</label><input id="bankFixGroupTitle" value="${escapeHtml(suggestedTitle)}" placeholder="Ex.: CONCEITO DE TRIBUTOS" autocomplete="off"><small class="field-help">Exibido como “Aula 00: CONCEITO DE TRIBUTOS”. Não substitui o assunto individual das questões.</small></div>
      </div>
      <div class="viz-callout bank-fix-note"><strong>Esta regra também será aplicada a importações futuras.</strong><span>Questões que chegarem com esta matéria e aula serão agrupadas automaticamente. UID, respostas, histórico e origem do PDF serão preservados.</span></div>
    </div>`,
    footer: `<button class="button button--secondary" type="button" data-modal-close>Cancelar</button><button class="button button--primary" type="button" id="bankFixSaveGroup">Aplicar ao grupo</button>`,
    onOpen: (layer) => {
      $('#bankFixSaveGroup', layer).addEventListener('click', async (event) => {
        const button = event.currentTarget;
        const materia = $('#bankFixGroupMatter', layer).value.trim();
        const aula = $('#bankFixGroupLesson', layer).value.trim();
        const titulo = $('#bankFixGroupTitle', layer).value.trim();
        if (!materia || !aula || !titulo) {
          toast('Preencha matéria, aula e título canônico.', 'error');
          return;
        }
        setBusy(button, true, 'Organizando aula');
        try {
          const result = await bridge.call('organize_bank_lesson_group', {
            source_matter: sourceMatter,
            source_lesson: sourceLesson,
            materia,
            aula,
            titulo_aula: titulo,
          });
          if (!result?.ok) throw new Error(result?.error || 'Não foi possível organizar a aula.');
          closeModal();
          const count = numberOrZero(result.group?.updated);
          toast(`${formatNumber(count)} questão(ões) organizadas em ${result.group?.subject || materia} • ${result.group?.lesson || aula}.`, 'success', 8000);
          state.bankFixOptionsSubject = null;
          await Promise.allSettled([loadBankFix(), loadCoverage({ sync: false }), refreshBootstrap()]);
        } catch (error) {
          toast(error.message || 'Falha ao organizar a aula.', 'error', 8000);
          setBusy(button, false);
        }
      });
    },
  });
}

async function loadBankFix() {
  const requestId = ++state.bankFixRequestId;
  $('#bankFixCount').textContent = 'Carregando questões…';
  $('#bankFixTable').innerHTML = '<div class="coverage-loading"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>';
  try {
    const requestedMatter = $('#bankFixMatter')?.value || '';
    if (state.bankFixOptionsSubject !== requestedMatter || !(state.bankFixOptions?.bank_subjects || state.bankFixOptions?.subjects || []).length) {
      await loadBankFixOptions();
    }
    const result = await bridge.call(
      'list_questions',
      $('#bankFixSearch')?.value || '',
      $('#bankFixStatus')?.value || 'todos',
      0,
      2000,
      $('#bankFixMatter')?.value || '',
      $('#bankFixLesson')?.value || '',
    );
    if (requestId !== state.bankFixRequestId) return;
    state.bankFixQuestions = result.items || [];
    state.bankFixTotal = result.total || 0;
    $('#bankFixCount').textContent = state.bankFixTotal > state.bankFixQuestions.length
      ? `Mostrando ${formatNumber(state.bankFixQuestions.length)} de ${formatNumber(state.bankFixTotal)} questões. Use os filtros para reduzir a lista.`
      : `${formatNumber(state.bankFixTotal)} questão(ões) encontrada(s).`;
    renderBankFixSummary();
    renderBankFixTable();
  } catch (error) {
    if (requestId !== state.bankFixRequestId) return;
    $('#bankFixCount').textContent = 'Falha ao carregar';
    $('#bankFixTable').innerHTML = emptyStateHtml({ title: 'Não foi possível abrir o banco', text: error.message });
    toast(error.message || 'Falha ao carregar o banco para correção.', 'error');
  }
}

function bankFixTaskLabel(item) {
  const trail = trailLabel(item.trilha);
  const task = item.tarefa ? `Tarefa ${item.tarefa}` : 'Tarefa sem número';
  const lesson = item.aula || 'Sem aula';
  const content = item.conteudo || item.descricao || 'Conteúdo não informado';
  return `${trail} • ${task} • ${lesson} • ${content}${item.estudado ? ' • estudado' : ''}`;
}

function updateBankFixModalLessons(layer, options, selected = '') {
  const select = $('#bankFixEditLesson', layer);
  const lessons = options?.lessons || [];
  select.innerHTML = ['<option value="">Sem aula</option>', ...lessons.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)].join('');
  select.value = lessons.includes(selected) ? selected : '';
}

function updateBankFixModalTasks(layer, tasks, selected = '') {
  const select = $('#bankFixEditTask', layer);
  select.innerHTML = [
    '<option value="">Sem vínculo exato — usar matéria, aula e assunto</option>',
    ...(tasks || []).map((item) => `<option value="${escapeHtml(item.task_id)}">${escapeHtml(bankFixTaskLabel(item))}</option>`),
  ].join('');
  if ((tasks || []).some((item) => item.task_id === selected)) select.value = selected;
}

async function openBankFixQuestion(uid) {
  const questionUid = String(uid || '').trim();
  if (!questionUid) return;
  try {
    const result = await bridge.call('get_question', questionUid);
    if (!result?.ok || !result.question) throw new Error(result?.error || 'Questão não encontrada.');
    const question = result.question;
    const currentMatter = question.materia || '';
    const currentLesson = question.aula_planilha || '';
    const currentTaskId = question.classificacao_planilha?.contexto_task_id || question.contexto_importacao_estudos?.task_id || '';
    const options = await bridge.call('get_bank_classification_options', currentMatter, currentLesson);
    const subjects = options.subjects || [];
    const statement = String(question.enunciado || '').trim();
    const preview = statement.length > 520 ? `${statement.slice(0, 520)}…` : statement;
    openModal({
      title: question.codigo_origem || 'Corrigir questão',
      eyebrow: 'Correção de classificação do banco',
      body: `<div class="bank-fix-modal">
        <div class="bank-fix-question-preview"><strong>${escapeHtml(question.codigo_origem || 'Sem código')}</strong><span>${escapeHtml([question.banca, question.ano].filter(Boolean).join(' • ') || 'Origem não informada')}</span><p>${escapeHtml(preview || 'Enunciado não informado.')}</p></div>
        <div class="form-grid bank-fix-classification-grid">
          <div class="form-field"><label for="bankFixEditMatter">Matéria correta</label><select id="bankFixEditMatter">${subjects.map((item) => `<option value="${escapeHtml(item)}" ${item === currentMatter ? 'selected' : ''}>${escapeHtml(item)}</option>`).join('')}</select><small class="field-help">Altera a matéria gravada no banco e usada nos filtros/cobertura.</small></div>
          <div class="form-field"><label for="bankFixEditLesson">Aula correta</label><select id="bankFixEditLesson"></select><small class="field-help">Use a aula da planilha quando ela for conhecida.</small></div>
          <div class="form-field form-field--wide"><label for="bankFixEditTask">Conteúdo/tarefa correta da planilha</label><select id="bankFixEditTask"></select><small class="field-help">Recomendado quando a mesma aula possui várias partes. O vínculo exato impede que a questão seja contada no conteúdo errado.</small></div>
        </div>
        <div class="viz-callout bank-fix-note"><strong>O UID e o histórico de estudo serão preservados.</strong><span>A correção muda a classificação da mesma questão; não cria uma cópia.</span></div>
      </div>`,
      footer: `<button class="button button--danger-ghost" type="button" id="bankFixModalDelete">Excluir questão</button><span class="modal-footer-spacer"></span><button class="button button--secondary" type="button" data-modal-close>Cancelar</button><button class="button button--secondary" type="button" id="bankFixFullEditor">Editor completo</button><button class="button button--primary" type="button" id="bankFixSaveClassification">Salvar classificação</button>`,
      onOpen: (layer) => {
        updateBankFixModalLessons(layer, options, currentLesson);
        updateBankFixModalTasks(layer, options.tasks || [], currentTaskId);
        const matterSelect = $('#bankFixEditMatter', layer);
        const lessonSelect = $('#bankFixEditLesson', layer);
        const taskSelect = $('#bankFixEditTask', layer);

        matterSelect.addEventListener('change', async () => {
          const refreshed = await bridge.call('get_bank_classification_options', matterSelect.value, '');
          updateBankFixModalLessons(layer, refreshed, '');
          updateBankFixModalTasks(layer, [], '');
        });
        lessonSelect.addEventListener('change', async () => {
          const refreshed = await bridge.call('get_bank_classification_options', matterSelect.value, lessonSelect.value);
          updateBankFixModalTasks(layer, refreshed.tasks || [], '');
        });
        taskSelect.addEventListener('change', () => {
          const task = (options.tasks || []).find((item) => item.task_id === taskSelect.value);
          if (task?.materia) matterSelect.value = task.materia;
          if (task?.aula) lessonSelect.value = task.aula;
        });

        $('#bankFixSaveClassification', layer).addEventListener('click', async (event) => {
          const button = event.currentTarget;
          setBusy(button, true, 'Salvando classificação');
          try {
            const saved = await bridge.call('update_question_classification', questionUid, {
              materia: matterSelect.value,
              aula: lessonSelect.value,
              task_id: taskSelect.value,
            });
            if (!saved?.ok) throw new Error(saved?.error || 'Não foi possível salvar a classificação.');
            closeModal();
            const assigned = saved.coverage_assignment;
            const detail = assigned
              ? ` Agora ela é contabilizada em ${assigned.materia || matterSelect.value}${assigned.aula ? ` • ${assigned.aula}` : ''}.`
              : ' A matéria e a aula foram atualizadas no banco.';
            toast(`Classificação corrigida.${detail}`, 'success', 7000);
            await Promise.allSettled([loadBankFix(), loadCoverage({ sync: false }), refreshBootstrap()]);
          } catch (error) {
            toast(error.message || 'Falha ao corrigir a classificação.', 'error', 8000);
            setBusy(button, false);
          }
        });
        $('#bankFixFullEditor', layer).addEventListener('click', async () => {
          closeModal();
          await openHistoryQuestion(questionUid);
        });
        $('#bankFixModalDelete', layer).addEventListener('click', async () => {
          if (!window.confirm(`Excluir definitivamente a questão ${question.codigo_origem || ''}?\n\nEla será removida do banco e deixará de contar na cobertura dos estudos.`)) return;
          const deleted = await bridge.call('delete_question', questionUid);
          if (!deleted?.ok) return toast(deleted?.error || 'Não foi possível excluir a questão.', 'error');
          closeModal();
          toast('Questão excluída do banco. A cobertura foi recalculada.', 'success');
          await Promise.allSettled([loadBankFix(), loadCoverage({ sync: false }), refreshBootstrap()]);
        });
      },
    });
  } catch (error) {
    toast(error.message || 'Não foi possível abrir a questão.', 'error');
  }
}

async function deleteBankFixQuestion(uid, code = '') {
  if (!uid) return;
  if (!window.confirm(`Excluir definitivamente a questão ${code || ''}?\n\nEla será removida do banco e deixará de contar na matéria/aula atual.`)) return;
  const result = await bridge.call('delete_question', uid);
  if (!result?.ok) return toast(result?.error || 'Não foi possível excluir a questão.', 'error');
  toast('Questão excluída. Banco e cobertura atualizados.', 'success');
  await Promise.allSettled([loadBankFix(), loadCoverage({ sync: false }), refreshBootstrap()]);
}

function bindBankFixRows(container) {
  $$('tr[data-question-uid]', container).forEach((row) => {
    const uid = row.dataset.questionUid;
    const open = () => openBankFixQuestion(uid);
    row.addEventListener('click', (event) => {
      if (!event.target.closest('button, a, input, select')) open();
    });
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
    });
  });
  $$('[data-bank-fix-correct]', container).forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    openBankFixQuestion(button.dataset.bankFixCorrect);
  }));
  $$('[data-bank-fix-editor]', container).forEach((button) => button.addEventListener('click', async (event) => {
    event.stopPropagation();
    await openHistoryQuestion(button.dataset.bankFixEditor);
  }));
  $$('[data-bank-fix-delete]', container).forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    deleteBankFixQuestion(button.dataset.bankFixDelete, button.dataset.questionCode || '');
  }));
}

function normalizeTableColumn(column) {
  if (Array.isArray(column)) return { label: column[0], key: column[1], type: column[2] || 'auto' };
  return { type: 'auto', ...column };
}

function tableDisplayValue(column, value) {
  const type = column.type === 'auto'
    ? (column.key.includes('date') || column.key.includes('_at') ? 'date' : 'text')
    : column.type;
  if (column.format) return column.format(value);
  if (type === 'date') return formatDate(value);
  if (type === 'number') return formatNumber(numberOrZero(value));
  return textOrMissing(value, column.fallback || 'Não encontrado');
}

function tableSortValue(column, value) {
  const type = column.type === 'auto'
    ? (column.key.includes('date') || column.key.includes('_at') ? 'date' : 'text')
    : column.type;
  if (type === 'number') return String(numberOrZero(value));
  if (type === 'date') {
    const timestamp = value ? new Date(value).valueOf() : 0;
    return String(Number.isFinite(timestamp) ? timestamp : 0);
  }
  return String(value ?? '').trim();
}

function tableHtml(columns, items, options = {}) {
  const normalized = columns.map(normalizeTableColumn);
  const tableId = options.id || `table-${Math.random().toString(36).slice(2)}`;
  const rowUidKey = options.rowUidKey || '';
  const rowDataKey = options.rowDataKey || '';
  const rowDataAttribute = String(options.rowDataAttribute || 'row-id').replace(/[^a-z0-9_-]/gi, '');
  const emptyText = options.emptyText || 'Nenhum registro encontrado.';
  const rows = (items || []).map((item) => {
    const uid = rowUidKey ? String(item[rowUidKey] || '') : '';
    const rowDataValue = rowDataKey ? String(item[rowDataKey] || '') : '';
    const cells = normalized.map((column) => {
      const value = item[column.key];
      const display = tableDisplayValue(column, value);
      const content = column.render ? column.render(value, item, display) : escapeHtml(display);
      return `<td class="${escapeHtml(column.className || '')}" data-column-key="${escapeHtml(column.key)}" data-label="${escapeHtml(column.label)}" data-sort-value="${escapeHtml(tableSortValue(column, value))}" title="${escapeHtml(String(display))}">${content}</td>`;
    }).join('');
    const attributes = [];
    if (uid) attributes.push(`data-question-uid="${escapeHtml(uid)}"`, 'class="table-row--question"', 'tabindex="0"', 'title="Abrir esta questão no banco"');
    if (rowDataValue) attributes.push(`data-${rowDataAttribute}="${escapeHtml(rowDataValue)}"`);
    const rowCanInteract = options.rowInteractive
      && rowDataValue
      && !uid
      && (typeof options.rowInteractiveWhen !== 'function' || options.rowInteractiveWhen(item));
    if (rowCanInteract) {
      attributes.push(
        'tabindex="0"',
        'class="table-row--interactive"',
        `title="${escapeHtml(options.rowInteractiveTitle || 'Clique para abrir')}"`,
        'aria-label="Abrir importação de PDF para este conteúdo estudado"',
      );
    }
    return `<tr ${attributes.join(' ')}>${cells}</tr>`;
  }).join('');
  return `<div class="data-table-wrap ${escapeHtml(options.wrapClass || '')}"><table class="data-table data-table--responsive data-table--managed ${escapeHtml(options.tableClass || '')}" data-table-id="${escapeHtml(tableId)}"><thead><tr>${normalized.map((column) => `<th class="${escapeHtml(column.className || '')}" data-column-key="${escapeHtml(column.key)}" draggable="true" scope="col"><button type="button" class="table-sort-button" title="Clique para ordenar; arraste para mover; use a borda para redimensionar">${escapeHtml(column.label)} <span aria-hidden="true">↕</span></button><span class="column-resizer" aria-hidden="true"></span></th>`).join('')}</tr></thead><tbody>${rows || `<tr><td colspan="${normalized.length}">${escapeHtml(emptyText)}</td></tr>`}</tbody></table></div>`;
}

function tablePreferenceKey(table) {
  return `qf-table-${table.dataset.tableId || 'generic'}`;
}

function saveTablePreference(table) {
  const headers = $$('thead th[data-column-key]', table);
  const activeSort = headers.find((header) => header.hasAttribute('aria-sort'));
  const preference = {
    order: headers.map((header) => header.dataset.columnKey),
    widths: Object.fromEntries(headers.map((header) => [header.dataset.columnKey, Math.round(header.getBoundingClientRect().width)])),
    sort: activeSort ? {
      key: activeSort.dataset.columnKey,
      direction: activeSort.getAttribute('aria-sort') === 'descending' ? 'descending' : 'ascending',
    } : null,
  };
  localStorage.setItem(tablePreferenceKey(table), JSON.stringify(preference));
}

function moveTableColumn(table, sourceKey, targetKey) {
  const headerRow = $('thead tr', table);
  const rows = $$('tr', table);
  const headers = $$('th[data-column-key]', headerRow);
  const from = headers.findIndex((header) => header.dataset.columnKey === sourceKey);
  const to = headers.findIndex((header) => header.dataset.columnKey === targetKey);
  if (from < 0 || to < 0 || from === to) return;
  rows.forEach((row) => {
    const cells = [...row.children];
    const moving = cells[from];
    const target = cells[to];
    if (!moving || !target) return;
    row.insertBefore(moving, from < to ? target.nextSibling : target);
  });
}

function restoreTablePreference(table) {
  const preference = readJsonPreference(tablePreferenceKey(table), {});
  if (Array.isArray(preference.order)) {
    preference.order.forEach((key, targetIndex) => {
      const current = $$('thead th[data-column-key]', table);
      const sourceIndex = current.findIndex((header) => header.dataset.columnKey === key);
      if (sourceIndex >= 0 && sourceIndex !== targetIndex) {
        const targetKey = current[targetIndex]?.dataset.columnKey;
        if (targetKey) moveTableColumn(table, key, targetKey);
      }
    });
  }
  const widths = preference.widths || {};
  $$('thead th[data-column-key]', table).forEach((header) => {
    const width = Number(widths[header.dataset.columnKey]);
    if (width > 48) {
      header.style.width = `${width}px`;
      header.style.minWidth = `${width}px`;
    }
  });
}

function applyManagedTableSort(table, key, direction = 'ascending', persist = true) {
  const header = $(`thead th[data-column-key="${CSS.escape(key)}"]`, table);
  if (!header) return;
  const normalizedDirection = direction === 'descending' ? 'descending' : 'ascending';
  $$('thead th', table).forEach((item) => {
    item.removeAttribute('aria-sort');
    const icon = $('.table-sort-button span', item);
    if (icon) icon.textContent = '↕';
  });
  header.setAttribute('aria-sort', normalizedDirection);
  const icon = $('.table-sort-button span', header);
  if (icon) icon.textContent = normalizedDirection === 'ascending' ? '↑' : '↓';
  const index = [...header.parentElement.children].indexOf(header);
  const rows = $$('tbody tr', table).filter((row) => row.children.length > 1);
  rows.sort((left, right) => {
    const a = left.children[index]?.dataset.sortValue ?? '';
    const b = right.children[index]?.dataset.sortValue ?? '';
    const numericA = Number(a);
    const numericB = Number(b);
    const comparison = Number.isFinite(numericA) && Number.isFinite(numericB)
      ? numericA - numericB
      : a.localeCompare(b, 'pt-BR', { numeric: true, sensitivity: 'base' });
    return normalizedDirection === 'ascending' ? comparison : -comparison;
  });
  const body = $('tbody', table);
  rows.forEach((row) => body.append(row));
  if (persist) saveTablePreference(table);
}

function enhanceManagedTable(table) {
  if (!table || table.dataset.enhanced === '1') return;
  table.dataset.enhanced = '1';
  const wrap = table.closest('.data-table-wrap');
  if (wrap && wrap.dataset.horizontalEnhanced !== '1') {
    wrap.dataset.horizontalEnhanced = '1';
    wrap.tabIndex = wrap.tabIndex >= 0 ? wrap.tabIndex : 0;
    wrap.title = wrap.title || 'Use a barra horizontal ou Shift + roda do mouse para visualizar todas as colunas';
    wrap.addEventListener('wheel', (event) => {
      if (!event.shiftKey || wrap.scrollWidth <= wrap.clientWidth) return;
      event.preventDefault();
      wrap.scrollLeft += event.deltaY || event.deltaX;
    }, { passive: false });
  }
  restoreTablePreference(table);
  let draggedKey = '';
  $$('thead th[data-column-key]', table).forEach((header) => {
    const key = header.dataset.columnKey;
    const sortButton = $('.table-sort-button', header);
    sortButton?.addEventListener('click', () => {
      const nextDirection = header.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
      applyManagedTableSort(table, key, nextDirection, true);
    });
    header.addEventListener('dragstart', (event) => {
      draggedKey = key;
      event.dataTransfer.setData('text/qf-table-column', key);
      event.dataTransfer.effectAllowed = 'move';
      header.classList.add('is-dragging');
    });
    header.addEventListener('dragend', () => { header.classList.remove('is-dragging'); draggedKey = ''; });
    header.addEventListener('dragover', (event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; });
    header.addEventListener('drop', (event) => {
      event.preventDefault();
      const source = event.dataTransfer.getData('text/qf-table-column') || draggedKey;
      if (source && source !== key) { moveTableColumn(table, source, key); saveTablePreference(table); }
    });
    const resizer = $('.column-resizer', header);
    resizer?.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = header.getBoundingClientRect().width;
      const move = (moveEvent) => {
        const width = Math.max(64, Math.round(startWidth + moveEvent.clientX - startX));
        header.style.width = `${width}px`;
        header.style.minWidth = `${width}px`;
      };
      const up = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
        saveTablePreference(table);
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', up, { once: true });
    });
  });
  const preference = readJsonPreference(tablePreferenceKey(table), {});
  if (preference.sort?.key) {
    applyManagedTableSort(table, preference.sort.key, preference.sort.direction, false);
  }
}

function enhanceManagedTables(root = document) {
  $$('.data-table--managed', root).forEach(enhanceManagedTable);
}

const appearanceFields = [
  { key: 'ui_theme', label: 'Tema', type: 'select', options: [['system', 'Sistema'], ['light', 'Claro'], ['dark', 'Escuro']] },
  { key: 'ui_density', label: 'Densidade', type: 'select', options: [['compact', 'Compacta'], ['comfortable', 'Confortável'], ['spacious', 'Ampla']] },
  { key: 'ui_scale', label: 'Escala inicial', type: 'number', min: 0.8, max: 1.45, step: 0.05 },
];
const processingFields = [
  { key: 'dpi', label: 'Resolução OCR (DPI)', type: 'number', min: 120, max: 400 },
  { key: 'languages', label: 'Idiomas do OCR', type: 'text' },
  { key: 'tesseract_cmd', label: 'Executável do Tesseract', type: 'text' },
  { key: 'deep_analysis_dpi', label: 'DPI da análise apurada', type: 'number', min: 260, max: 400 },
];

function renderSettings() {
  renderSettingsForm($('#appearanceSettings'), appearanceFields);
  renderSettingsForm($('#processingSettings'), processingFields);
  renderNetworkSettings(state.config || {});
  renderCloudSyncSettings(state.config || {});
  loadNetworkSettings().catch((error) => console.warn('Rede e proxy:', error));
  loadCloudSyncSettings().catch((error) => console.warn('Cloud Sync:', error));
}

function renderSettingsForm(form, fields) {
  form.innerHTML = fields.map((field) => {
    const value = state.config[field.key] ?? '';
    if (field.type === 'select') return `<div class="form-field"><label for="setting-${field.key}">${escapeHtml(field.label)}</label><select id="setting-${field.key}" name="${field.key}">${field.options.map(([key, label]) => `<option value="${key}" ${String(value) === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></div>`;
    return `<div class="form-field"><label for="setting-${field.key}">${escapeHtml(field.label)}</label><input id="setting-${field.key}" name="${field.key}" type="${field.type}" value="${escapeHtml(value)}" ${field.min != null ? `min="${field.min}"` : ''} ${field.max != null ? `max="${field.max}"` : ''} ${field.step != null ? `step="${field.step}"` : ''}></div>`;
  }).join('');
}

function renderNetworkSettings(settings = {}) {
  const setValue = (selector, value) => {
    const node = $(selector);
    if (node && document.activeElement !== node) node.value = value ?? '';
  };
  setValue('#networkMode', settings.network_mode || 'auto');
  setValue('#networkProxyHost', settings.network_proxy_host || '');
  setValue('#networkProxyPort', settings.network_proxy_port || '');
  setValue('#networkPacUrl', settings.network_pac_url || '');
  setValue('#networkProxyBypass', settings.network_proxy_bypass || 'localhost;127.0.0.1;::1;<local>');
  setValue('#networkProxyAuth', settings.network_proxy_auth || 'none');
  setValue('#networkProxyUsername', settings.network_proxy_username || '');
  const hint = $('#networkPasswordHint');
  if (hint) hint.textContent = settings.network_proxy_password_configured
    ? 'Senha protegida pelo Windows (DPAPI). Deixe o campo vazio para mantê-la.'
    : 'Nenhuma senha armazenada.';
  updateNetworkFieldVisibility();
  const detected = settings.network_system_detected;
  if (detected) renderDetectedNetwork(detected);
}

function updateNetworkFieldVisibility() {
  const mode = $('#networkMode')?.value || 'auto';
  const auth = $('#networkProxyAuth')?.value || 'none';
  $$('.network-manual-field').forEach((node) => { node.hidden = mode !== 'manual'; });
  $$('.network-pac-field').forEach((node) => { node.hidden = mode !== 'pac'; });
  $$('.network-auth-field').forEach((node) => { node.hidden = auth !== 'basic'; });
}

function renderDetectedNetwork(detected = {}, effective = null) {
  const box = $('#networkDetected');
  if (!box) return;
  const parts = [];
  if (detected.source) parts.push(`Origem: ${detected.source}`);
  if (detected.https_proxy) parts.push(`HTTPS: ${detected.https_proxy}`);
  else if (detected.http_proxy) parts.push(`HTTP: ${detected.http_proxy}`);
  if (detected.pac_url) parts.push(`PAC: ${detected.pac_url}`);
  if (detected.auto_detect) parts.push('WPAD/autodetecção ativa');
  if (effective?.detail) parts.push(`Efetivo: ${effective.detail}`);
  box.textContent = parts.length ? parts.join(' • ') : 'Nenhum proxy explícito foi detectado no Windows/ambiente.';
}

function collectNetworkSettings() {
  return {
    network_mode: $('#networkMode')?.value || 'auto',
    network_proxy_host: $('#networkProxyHost')?.value?.trim() || '',
    network_proxy_port: $('#networkProxyPort')?.value?.trim() || '',
    network_pac_url: $('#networkPacUrl')?.value?.trim() || '',
    network_proxy_bypass: $('#networkProxyBypass')?.value?.trim() || 'localhost;127.0.0.1;::1;<local>',
    network_proxy_auth: $('#networkProxyAuth')?.value || 'none',
    network_proxy_username: $('#networkProxyUsername')?.value?.trim() || '',
    network_proxy_password: $('#networkProxyPassword')?.value || '',
  };
}

function courseCatalogTypeLabel(kind) {
  return ({ equal:'Igual', updated:'Estrutura atualizada', new:'Aula nova', archived:'Removida / arquivada', uncertain:'Correspondência incerta' })[kind] || kind || '—';
}

function courseCatalogTypeClass(kind) {
  return ({ equal:'is-equal', updated:'is-updated', new:'is-new', archived:'is-archived', uncertain:'is-uncertain' })[kind] || '';
}

function renderCourseCatalogSettings(data = {}) {
  state.courseCatalogSettings = data || {};
  const input = $('#courseCatalogUrl');
  if (input && document.activeElement !== input) input.value = data.url || input.value || '';
  $('#courseCatalogSourceTitle').textContent = data.source_title || 'Planilha configurada';
  $('#courseCatalogTrailRange').textContent = data.trail_range || 'Faixa de trilhas não identificada';
  $('#courseCatalogLastSync').textContent = data.last_sync ? formatDate(data.last_sync) : 'Ainda não registrada';
  $('#courseCatalogVersion').textContent = `Catálogo: ${data.catalog_version || 'snapshot legado'}`;
  $('#courseCatalogSheets').textContent = (data.sheets || []).join(' + ') || 'Não identificadas';
  $('#courseCatalogLessonCount').textContent = `${formatNumber(data.lesson_count || 0)} aulas/tarefas de referência`;
  const pill = $('#courseCatalogStatusPill');
  if (pill) { pill.textContent = 'Sincronizada'; pill.className = 'status-pill is-success'; }
  const status = $('#courseCatalogStatusText');
  if (status) status.textContent = 'A fonte atual permanece ativa até uma nova planilha passar pelo dry-run e pela mesclagem segura.';
}

async function loadCourseCatalogSettings() {
  try {
    const result = await bridge.call('get_course_catalog_settings');
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível carregar a planilha atual.');
    renderCourseCatalogSettings(result);
  } catch (error) {
    const pill = $('#courseCatalogStatusPill');
    if (pill) { pill.textContent = 'Não verificado'; pill.className = 'status-pill'; }
    if ($('#courseCatalogStatusText')) $('#courseCatalogStatusText').textContent = error.message || 'Falha ao carregar a fonte atual.';
  }
}

function courseCatalogPreservationHtml() {
  return `<div class="catalog-preservation-list">
    <strong>PROGRESSO PESSOAL</strong>
    <span>✓ Aulas estudadas e concluídas serão preservadas</span>
    <span>✓ Questões, acertos, erros e tempo de resposta serão preservados</span>
    <span>✓ FSRS, Knowledge Tracing, IRT e learner model serão preservados</span>
    <span>✓ Histórico do Mobile e decisões adaptativas serão preservados</span>
    <span>✓ Campos vazios da nova planilha NÃO apagarão dados existentes</span>
  </div>`;
}

function showCourseCatalogPreflight(preflight = {}, { allowApply = false, url = '' } = {}) {
  return new Promise((resolve) => {
    const counts = preflight.counts || {};
    const diffs = Array.isArray(preflight.diffs) ? preflight.diffs : [];
    const uncertain = diffs.filter((item) => item.change_type === 'uncertain');
    const summary = `
      <div class="catalog-preflight-summary">
        <div><span>Correspondentes</span><strong>${formatNumber(counts.equal || 0)}</strong></div>
        <div><span>Atualizadas</span><strong>${formatNumber(counts.updated || 0)}</strong></div>
        <div><span>Novas</span><strong>+ ${formatNumber(counts.new || 0)}</strong></div>
        <div><span>Arquivadas</span><strong>${formatNumber(counts.archived || 0)}</strong></div>
        <div><span>Conflitos</span><strong>${formatNumber(counts.uncertain || 0)}</strong></div>
      </div>`;
    const rows = diffs.length ? diffs.map((item, index) => {
      const candidates = Array.isArray(item.candidates) ? item.candidates : [];
      const resolution = item.change_type === 'uncertain' ? `<select class="catalog-resolution" data-lesson-key="${escapeHtml(item.lesson_key || '')}">
        <option value="">Escolha uma decisão…</option>
        ${candidates.map((candidate) => `<option value="same|${escapeHtml(candidate.lesson_key || '')}">É a mesma aula: ${escapeHtml(candidate.task_no || candidate.lesson || candidate.title || candidate.lesson_key)}</option>`).join('')}
        <option value="new">É uma aula nova</option>
        <option value="ignore">Ignorar por enquanto</option>
      </select>` : escapeHtml(item.action || '—');
      return `<div class="catalog-diff-row ${courseCatalogTypeClass(item.change_type)}" data-kind="${escapeHtml(item.change_type || '')}">
        <span><b>${escapeHtml(courseCatalogTypeLabel(item.change_type))}</b></span>
        <span>${escapeHtml(item.trail || '—')}</span>
        <span>${escapeHtml(item.lesson || '—')}<small>${escapeHtml(item.subject || '')}</small></span>
        <span>${escapeHtml(item.previous_title || item.current_title || '—')} ${item.previous_title && item.current_title && item.previous_title !== item.current_title ? `→ ${escapeHtml(item.current_title)}` : ''}</span>
        <span>${resolution}</span>
      </div>`;
    }).join('') : '<p class="field-help">Nenhuma diferença estrutural encontrada.</p>';

    openModal({
      title: 'NOVA PLANILHA DETECTADA',
      eyebrow: 'Estudos e Trilhas · dry-run',
      body: `<div class="catalog-preflight-body">
        <div class="catalog-source-compare"><span>Planilha atual<strong>${escapeHtml(state.courseCatalogSettings?.trail_range || 'Fonte atual')}</strong></span><span>Nova planilha<strong>${escapeHtml((preflight.source || {}).title || url || 'Nova fonte')}</strong><small>${escapeHtml((preflight.sheets || []).filter(Boolean).join(' + ') || 'Abas detectadas automaticamente')}</small></span></div>
        ${summary}
        ${courseCatalogPreservationHtml()}
        <div class="catalog-diff-toolbar"><label>Ver alterações <select id="catalogDiffFilter"><option value="all">Todas</option><option value="new">Somente novas</option><option value="updated">Somente alteradas</option><option value="archived">Somente removidas</option><option value="uncertain">Somente conflitos</option></select></label></div>
        <div class="catalog-diff-table"><div class="catalog-diff-head"><span>TIPO</span><span>TRILHA</span><span>AULA</span><span>SITUAÇÃO</span><span>AÇÃO</span></div>${rows}</div>
        <p class="catalog-preflight-message">${escapeHtml(preflight.message || '')}</p>
      </div>`,
      footer: `${allowApply ? '<button class="button button--primary" type="button" id="confirmCourseCatalogMerge">Mesclar e usar nova planilha</button>' : ''}<button class="button button--secondary" type="button" id="closeCourseCatalogPreflight">${allowApply ? 'Cancelar' : 'Fechar'}</button>`,
      onOpen: (layer) => {
        let settled = false;
        const finish = (value) => { if (settled) return; settled = true; closeModal(); resolve(value); };
        $('#closeCourseCatalogPreflight', layer)?.addEventListener('click', () => finish(null));
        const filter = $('#catalogDiffFilter', layer);
        filter?.addEventListener('change', () => {
          $$('.catalog-diff-row', layer).forEach((row) => { row.hidden = filter.value !== 'all' && row.dataset.kind !== filter.value; });
        });
        const applyButton = $('#confirmCourseCatalogMerge', layer);
        const validate = () => {
          if (!applyButton) return;
          const unresolved = $$('.catalog-resolution', layer).some((select) => !select.value || select.value === 'ignore');
          applyButton.disabled = unresolved;
          applyButton.title = unresolved ? 'Resolva todas as correspondências incertas antes de mesclar.' : '';
        };
        $$('.catalog-resolution', layer).forEach((select) => select.addEventListener('change', validate));
        validate();
        applyButton?.addEventListener('click', () => {
          const resolutions = {};
          $$('.catalog-resolution', layer).forEach((select) => {
            const key = select.dataset.lessonKey || '';
            if (!key || !select.value || select.value === 'ignore') return;
            if (select.value === 'new') resolutions[key] = { action: 'new' };
            else if (select.value.startsWith('same|')) resolutions[key] = { action: 'same', old_key: select.value.slice(5) };
          });
          finish({ apply: true, resolutions });
        });
      },
    });
  });
}

function showCourseCatalogMergeResult(result = {}) {
  const summary = result.summary || {};
  const backup = result.backup || {};
  openModal({
    title: result.noop ? 'PLANILHA JÁ ESTAVA ATUALIZADA' : 'MESCLAGEM CONCLUÍDA',
    eyebrow: 'Estudos e Trilhas',
    body: `<div class="catalog-merge-result">
      <div class="catalog-preflight-summary">
        <div><span>Aulas preservadas</span><strong>${formatNumber(summary.progress_preserved || 0)}</strong></div>
        <div><span>Atualizadas</span><strong>${formatNumber(summary.updated || 0)}</strong></div>
        <div><span>Novas</span><strong>${formatNumber(summary.new || 0)}</strong></div>
        <div><span>Arquivadas</span><strong>${formatNumber(summary.archived || 0)}</strong></div>
      </div>
      <div class="catalog-preservation-list"><strong>VALIDAÇÃO</strong><span>✓ Campos pessoais sobrescritos por vazio: ${formatNumber(summary.personal_fields_overwritten_by_blank || 0)}</span><span>✓ quick_check: ${escapeHtml(result.quick_check || 'ok')}</span><span>✓ Foreign keys: ${formatNumber(result.foreign_key_violations || 0)}</span><span>✓ FSRS preservados: ${summary.fsrs_rows_preserved == null ? 'verificado no relatório' : formatNumber(Math.max(0, summary.fsrs_rows_preserved))}</span><span>✓ Knowledge Tracing preservado: ${summary.knowledge_tracing_rows_preserved == null ? 'verificado no relatório' : formatNumber(Math.max(0, summary.knowledge_tracing_rows_preserved))}</span></div>
      ${backup.path ? `<p class="field-help"><strong>Backup:</strong> ${escapeHtml(backup.path)}<br><strong>SHA-256:</strong> ${escapeHtml(backup.sha256 || '')}</p>` : ''}
      <p>A nova planilha agora é a fonte ativa. O Mobile continua recebendo apenas o estado consolidado do QuestFlow.</p>
    </div>`,
    footer: '<button class="button button--primary" type="button" data-modal-close>Fechar</button>',
  });
}

async function runCourseCatalogPreflight({ apply = false } = {}) {
  const input = $('#courseCatalogUrl');
  const url = String(input?.value || '').trim();
  if (!url) { toast('Informe o link da nova planilha.', 'warning'); input?.focus(); return; }
  const button = apply ? $('#updateCourseCatalog') : $('#testCourseCatalog');
  setBusy(button, true, apply ? 'Analisando e preparando mesclagem' : 'Testando planilha');
  const pill = $('#courseCatalogStatusPill');
  if (pill) { pill.textContent = 'Analisando…'; pill.className = 'status-pill'; }
  try {
    const result = await bridge.call('preflight_course_catalog', url);
    if (!result?.ok) throw new Error(result?.error || 'A planilha não passou na análise.');
    const decision = await showCourseCatalogPreflight(result.preflight || {}, { allowApply: apply, url });
    if (!apply || !decision?.apply) {
      if (pill) { pill.textContent = result.ready ? 'Pronta para mesclar' : 'Revisão necessária'; pill.className = `status-pill ${result.ready ? 'is-success' : 'is-warning'}`; }
      return;
    }
    setBusy(button, true, 'Mesclando planilha com segurança');
    if ($('#courseCatalogStatusText')) $('#courseCatalogStatusText').textContent = 'Criando backup e mesclando o catálogo. Não feche o QuestFlow.';
    const merged = await bridge.call('apply_course_catalog', url, decision.resolutions || {});
    if (!merged?.ok) throw new Error(merged?.error || 'Não foi possível aplicar a nova planilha.');
    await Promise.allSettled([loadCourseCatalogSettings(), refreshBootstrap({ background: true }), loadCoverage({ sync: false })]);
    showCourseCatalogMergeResult(merged);
    toast(merged.message || 'Planilha atualizada com progresso preservado.', 'success', 9000);
  } catch (error) {
    if (pill) { pill.textContent = 'Falha — fonte antiga mantida'; pill.className = 'status-pill is-danger'; }
    if ($('#courseCatalogStatusText')) $('#courseCatalogStatusText').textContent = `A fonte atual não foi alterada: ${error.message}`;
    toast(error.message || 'Falha ao atualizar a planilha.', 'error', 10000);
  } finally {
    setBusy(button, false);
  }
}

async function loadNetworkSettings() {
  const result = await bridge.call('get_network_settings');
  if (!result?.ok) return;
  state.config = { ...state.config, ...(result.settings || {}) };
  renderNetworkSettings(result.settings || {});
}

async function detectNetworkProxy() {
  const button = $('#detectNetworkProxy');
  button?.classList.add('is-loading');
  try {
    const result = await bridge.call('detect_network_proxy');
    if (!result.ok) throw new Error(result.error || 'Falha ao detectar o proxy.');
    renderDetectedNetwork(result.detected || {}, result.effective || null);
    const pill = $('#networkStatusPill');
    if (pill) {
      pill.textContent = result.effective?.enabled ? 'Proxy detectado' : 'Conexão direta';
      pill.dataset.tone = 'success';
    }
    toast(result.effective?.enabled ? 'Proxy corporativo detectado.' : 'Nenhum proxy necessário/detectado.', 'success');
  } catch (error) {
    toast(error.message || 'Falha ao detectar o proxy.', 'error');
  } finally {
    button?.classList.remove('is-loading');
  }
}

function renderNetworkTests(result) {
  const container = $('#networkTestResults');
  if (!container) return;
  const tests = result.tests || [];
  container.innerHTML = tests.map((item) => `
    <div class="network-test-item ${item.ok ? 'is-ok' : 'is-error'}">
      <span class="network-test-icon">${item.ok ? '✓' : '!'}</span>
      <div><strong>${escapeHtml(item.name || 'Teste')}</strong><small>${escapeHtml(item.detail || '')}${item.elapsed_ms != null ? ` • ${escapeHtml(item.elapsed_ms)} ms` : ''}</small></div>
    </div>
  `).join('');
  const pill = $('#networkStatusPill');
  if (pill) {
    pill.textContent = result.ok ? 'Rede pronta' : 'Requer atenção';
    pill.dataset.tone = result.ok ? 'success' : 'danger';
  }
  if (result.proxy) renderDetectedNetwork(result.settings?.network_system_detected || {}, result.proxy);
}

async function testNetworkConnection() {
  const button = $('#testNetworkConnection');
  button?.classList.add('is-loading');
  const container = $('#networkTestResults');
  if (container) container.innerHTML = emptyStateHtml({ text: 'Testando DNS, proxy, TLS, Telegram e Google…', compact: true });
  try {
    const result = await bridge.call('test_network_connection');
    renderNetworkTests(result || {});
    toast(result.ok ? 'Rede e proxy funcionando.' : 'Há itens de rede que precisam de atenção.', result.ok ? 'success' : 'warning', 6500);
  } catch (error) {
    if (container) container.innerHTML = `<div class="network-test-item is-error"><span class="network-test-icon">!</span><div><strong>Falha no diagnóstico</strong><small>${escapeHtml(error.message || String(error))}</small></div></div>`;
    toast(error.message || 'Falha no teste de rede.', 'error');
  } finally {
    button?.classList.remove('is-loading');
  }
}

async function saveNetworkSettings() {
  const button = $('#saveNetworkSettings');
  button?.classList.add('is-loading');
  try {
    const payload = collectNetworkSettings();
    const result = await bridge.call('save_network_settings', payload);
    if (!result.ok) throw new Error(result.error || 'Falha ao salvar a rede.');
    state.config = { ...state.config, ...(result.config || result.settings || payload) };
    if ($('#networkProxyPassword')) $('#networkProxyPassword').value = '';
    renderNetworkSettings(result.settings || state.config);
    toast('Configuração de Rede e Proxy salva.', 'success');
  } catch (error) {
    toast(error.message || 'Falha ao salvar a rede.', 'error');
  } finally {
    button?.classList.remove('is-loading');
  }
}


function renderAiProviderSettings(settings = {}) {
  const active = settings.active_provider || 'local';
  const select = $('#aiActiveProvider'); if (select) select.value = active;
  const models = settings.models || {};
  if ($('#aiOpenaiModel')) $('#aiOpenaiModel').value = models.openai || '';
  if ($('#aiGeminiModel')) $('#aiGeminiModel').value = models.gemini || 'gemini-3.6-flash';
  if ($('#aiAnthropicModel')) $('#aiAnthropicModel').value = models.anthropic || '';
  const configured = settings.keys_configured || {};
  [['openai','#aiOpenaiHint'],['gemini','#aiGeminiHint'],['anthropic','#aiAnthropicHint']].forEach(([pid,sel])=>{ const el=$(sel); if(el) el.textContent=configured[pid]?'Chave protegida e configurada.':'Nenhuma chave armazenada.'; });
  const pricing=settings.pricing||{};
  const costFields={openai:['#aiOpenaiInputCost','#aiOpenaiOutputCost'],gemini:['#aiGeminiInputCost','#aiGeminiOutputCost'],anthropic:['#aiAnthropicInputCost','#aiAnthropicOutputCost']};
  Object.entries(costFields).forEach(([pid,[inp,out]])=>{if($(inp)) $(inp).value=pricing[pid]?.input_per_million||0;if($(out)) $(out).value=pricing[pid]?.output_per_million||0;});
  const meta=(settings.providers||[]).find(p=>p.id===active);
  const label=meta?.label || active;
  if ($('#aiProviderStatusPill')) $('#aiProviderStatusPill').textContent=label;
  if ($('#tutorActiveProvider')) $('#tutorActiveProvider').textContent=label;
  if ($('#tutorProviderHint')) $('#tutorProviderHint').textContent=active==='local'?'RAG local ativo. Marcar esta opção não envia dados para terceiros.':`Ao gerar orientação, o QuestFlow usa ${label} e mantém RAG/auditoria local.`;
}

async function loadAiProviderSettings() {
  try { const result=await bridge.call('get_ai_provider_settings'); if(result?.ok){ state.aiProviderSettings=result.settings||{}; renderAiProviderSettings(result.settings||{}); } } catch (_) {}
}

async function saveAiProviderSettings() {
  const button=$('#saveAiProviderSettings'); setBusy(button,true,'Salvando provedores');
  try {
    const payload={active_provider:$('#aiActiveProvider')?.value||'local',openai_model:$('#aiOpenaiModel')?.value?.trim()||'',gemini_model:$('#aiGeminiModel')?.value?.trim()||'',anthropic_model:$('#aiAnthropicModel')?.value?.trim()||'',openai_api_key:$('#aiOpenaiKey')?.value||'',gemini_api_key:$('#aiGeminiKey')?.value||'',anthropic_api_key:$('#aiAnthropicKey')?.value||'',openai_input_cost:Number($('#aiOpenaiInputCost')?.value||0),openai_output_cost:Number($('#aiOpenaiOutputCost')?.value||0),gemini_input_cost:Number($('#aiGeminiInputCost')?.value||0),gemini_output_cost:Number($('#aiGeminiOutputCost')?.value||0),anthropic_input_cost:Number($('#aiAnthropicInputCost')?.value||0),anthropic_output_cost:Number($('#aiAnthropicOutputCost')?.value||0)};
    const result=await bridge.call('save_ai_provider_settings',payload); if(!result.ok) throw new Error(result.error||'Falha ao salvar provedores.');
    ['#aiOpenaiKey','#aiGeminiKey','#aiAnthropicKey'].forEach(sel=>{if($(sel)) $(sel).value='';}); renderAiProviderSettings(result.settings||{}); toast('Provedores de IA salvos com segurança.','success');
  } catch(error){ toast(error.message,'error',8000); } finally { setBusy(button,false); }
}

async function testAiProvider() {
  const button=$('#testAiProvider'); setBusy(button,true,'Testando IA');
  try { const provider=$('#aiActiveProvider')?.value||'local'; const result=await bridge.call('test_ai_provider',provider); if(!result.ok) throw new Error(result.error||'Falha no teste.'); toast(`${result.provider||'IA'}: ${result.detail||'conexão OK'}`,'success',8000); }
  catch(error){toast(error.message,'error',9000);} finally {setBusy(button,false);}
}


function renderAiPrivacySettings(settings={}) {
  const mode=settings.mode||'balanced'; if($('#aiPrivacyMode')) $('#aiPrivacyMode').value=mode;
  const map={share_taxonomy:'#aiShareTaxonomy',share_statement:'#aiShareStatement',share_alternatives:'#aiShareAlternatives',share_official_answer:'#aiShareAnswer',share_rag:'#aiShareRag',share_binary_media:'#aiShareBinaryMedia',share_learner_summary:'#aiShareLearner',share_user_prompt:'#aiShareUserPrompt',share_personal_notes:'#aiShareNotes'};
  Object.entries(map).forEach(([key,sel])=>{if($(sel)) {$(sel).checked=Boolean(settings[key]); $(sel).disabled=mode!=='custom';}});
  if($('#aiPrivacyStatusPill')) $('#aiPrivacyStatusPill').textContent=mode==='private'?'Privado':(mode==='custom'?'Personalizado':'Equilibrado');
}
async function loadAiPrivacySettings(){try{const r=await bridge.call('get_ai_privacy_settings');if(r?.ok){state.aiPrivacySettings=r.settings||{};renderAiPrivacySettings(r.settings||{});}}catch(_){}}
async function saveAiPrivacySettings(){const b=$('#saveAiPrivacySettings');setBusy(b,true,'Salvando privacidade');try{const payload={mode:$('#aiPrivacyMode')?.value||'balanced',share_taxonomy:Boolean($('#aiShareTaxonomy')?.checked),share_statement:Boolean($('#aiShareStatement')?.checked),share_alternatives:Boolean($('#aiShareAlternatives')?.checked),share_official_answer:Boolean($('#aiShareAnswer')?.checked),share_rag:Boolean($('#aiShareRag')?.checked),share_binary_media:Boolean($('#aiShareBinaryMedia')?.checked),share_learner_summary:Boolean($('#aiShareLearner')?.checked),share_user_prompt:Boolean($('#aiShareUserPrompt')?.checked),share_personal_notes:Boolean($('#aiShareNotes')?.checked),confirm_before_external:true};const r=await bridge.call('save_ai_privacy_settings',payload);if(!r.ok)throw new Error(r.error||'Falha ao salvar privacidade.');state.aiPrivacySettings=r.settings||{};renderAiPrivacySettings(r.settings||{});toast('Centro de Privacidade salvo.','success');await loadTutorPrivacyPreview();}catch(e){toast(e.message,'error');}finally{setBusy(b,false);}}

function renderAiTelemetry(t={}){const target=$('#aiTelemetryBody');if(!target)return;const items=Array.isArray(t.items)?t.items:[];const money=Number(t.estimated_cost_usd||0);target.innerHTML=`<div class="ai-telemetry-summary"><div><span>Chamadas</span><strong>${formatNumber(t.calls||0)}</strong></div><div><span>Entrada</span><strong>${formatNumber(t.input_tokens||0)} tok</strong></div><div><span>Saída</span><strong>${formatNumber(t.output_tokens||0)} tok</strong></div><div><span>Latência média</span><strong>${Math.round(Number(t.avg_latency_ms||0))} ms</strong></div><div><span>Custo estimado</span><strong>${money?`US$ ${money.toFixed(4)}`:'não configurado'}</strong></div></div>${items.length?`<div class="ai-telemetry-list">${items.map(x=>`<div class="ai-telemetry-row"><div><strong>${escapeHtml(x.provider||'')}</strong><small>${escapeHtml(x.model||'')}</small></div><span>${x.calls||0} chamadas · ${Number(x.success_rate||0).toFixed(0)}%</span><span>${Math.round(Number(x.avg_latency_ms||0))} ms</span><span>${formatNumber((x.input_tokens||0)+(x.output_tokens||0))} tok</span><span>${x.prompt_injection_flags||0} alerta(s)</span></div>`).join('')}</div>`:`<div class="network-note">A telemetria começa a aparecer depois das primeiras chamadas REST de IA. ${escapeHtml(t.cost_note||'')}</div>`}`;}
async function loadAiTelemetry(){try{const r=await bridge.call('get_ai_telemetry',30);if(r?.ok)renderAiTelemetry(r.telemetry||{});}catch(_){}}

async function loadTutorPrivacyPreview(){const target=$('#tutorPrivacyPreview');if(!target)return;const external=Boolean($('#tutorOnlineAi')?.checked);if(!external){target.innerHTML='<small>Modo local: nenhum conteúdo é enviado a terceiros.</small>';return;}if(!state.tutorSelectedUid){target.innerHTML='<small>Selecione uma questão para visualizar o que será enviado.</small>';return;}try{const mode=$('input[name="tutorMode"]:checked')?.value||'professor';const prompt=$('#tutorUserPrompt')?.value||'';const r=await bridge.call('get_ai_privacy_preview',state.tutorSelectedUid,mode,prompt);if(!r?.ok)throw new Error(r?.error||'Falha');const p=r.preview||{};const shared=(p.fields||[]).filter(x=>x.shared).map(x=>x.field);const blocked=(p.fields||[]).filter(x=>!x.shared).map(x=>x.field);target.innerHTML=`<strong>Prévia de privacidade · ${escapeHtml(p.mode||'')}</strong><small>Enviado: ${escapeHtml(shared.join(', ')||'nada')}.</small><small>Não enviado: ${escapeHtml(blocked.join(', ')||'nenhum campo')}.</small>${r.security?.sources_with_signals?`<small>⚠ ${r.security.sources_with_signals} fonte(s) com sinais de prompt injection serão sanitizadas.</small>`:''}`;}catch(_){target.innerHTML='<small>Não foi possível montar a prévia; o modo local continua disponível.</small>';}}

function renderUpdateMonitorStatus(status = {}) {
  state.updateMonitorStatus = status || {};
  const days = Array.isArray(status.days) && status.days.length >= 2 ? status.days : [1, 15];
  if ($('#updateMonitorEnabled')) $('#updateMonitorEnabled').checked = status.enabled !== false;
  if ($('#updateMonitorDay1') && document.activeElement !== $('#updateMonitorDay1')) $('#updateMonitorDay1').value = days[0];
  if ($('#updateMonitorDay2') && document.activeElement !== $('#updateMonitorDay2')) $('#updateMonitorDay2').value = days[1];
  const pill = $('#updateMonitorStatusPill');
  if (pill) {
    pill.textContent = status.enabled === false ? 'Desativado' : (status.due ? 'Verificação disponível' : (status.last_success_at ? 'Em dia' : 'Aguardando'));
    pill.dataset.tone = status.due ? 'warning' : (status.enabled === false ? '' : (status.last_success_at ? 'success' : ''));
  }
  const text = $('#updateMonitorStatusText');
  if (text) {
    const parts = [`Agenda: dias ${days[0]} e ${days[1]}`];
    if (status.last_success_at) parts.push(`última verificação concluída: ${formatDate(status.last_success_at)}`);
    else if (status.last_check_at) parts.push(`última tentativa: ${formatDate(status.last_check_at)}`);
    if (status.snoozed && status.snooze_until) parts.push(`adiado até ${formatDate(status.snooze_until)}`);
    if (status.last_summary?.offline_or_blocked) parts.push('última tentativa sem acesso externo; o banco permaneceu intacto');
    parts.push('a checagem de rede só começa após sua confirmação');
    text.textContent = parts.join(' • ');
  }
}

async function loadUpdateMonitorStatus({ promptIfDue = false } = {}) {
  try {
    const status = await bridge.call('get_update_monitor_status');
    renderUpdateMonitorStatus(status || {});
    if (promptIfDue && status?.due && state.updateMonitorPromptCycle !== status.cycle) {
      state.updateMonitorPromptCycle = status.cycle || `cycle-${Date.now()}`;
      showScheduledUpdateMonitorPrompt(status);
    }
    return status;
  } catch (_) { return null; }
}

function updateMonitorReportHtml(result = {}) {
  const summary = result.summary || {};
  const items = result.items || [];
  const stateOf = (item) => !item.ok ? 'error' : (item.changed ? 'changed' : (item.baseline ? 'baseline' : 'ok'));
  const labelOf = (item) => !item.ok ? 'Falhou' : (item.changed ? 'Mudou' : (item.baseline ? 'Linha de base' : 'Sem mudança'));
  return `<div class="update-monitor-report">
    <div class="update-monitor-summary">
      <div><span>Fontes acessadas</span><strong>${Number(summary.successes || 0)}</strong></div>
      <div><span>Mudanças</span><strong>${Number(summary.changed || 0)}</strong></div>
      <div><span>Novas linhas-base</span><strong>${Number(summary.baseline || 0)}</strong></div>
      <div><span>Falhas</span><strong>${Number(summary.failures || 0)}</strong></div>
    </div>
    <p>${escapeHtml(result.message || 'Verificação concluída.')}</p>
    <div class="update-monitor-list">${items.map((item) => {
      const status = stateOf(item);
      const dot = status === 'error' ? 'error' : (status === 'changed' ? 'warning' : 'ok');
      return `<article class="update-monitor-item" data-state="${status}"><span class="status-dot status-dot--${dot}"></span><div><strong>${escapeHtml(item.name || item.id || 'Fonte')}</strong><small>${escapeHtml(item.group || '')} • ${escapeHtml(labelOf(item))}${item.title ? ` • ${escapeHtml(item.title)}` : ''}</small>${item.error ? `<small>${escapeHtml(item.error)}</small>` : (item.changed && item.preview ? `<small>${escapeHtml(item.preview)}</small>` : '')}</div></article>`;
    }).join('')}</div>
  </div>`;
}

function showUpdateMonitorResult(result = {}) {
  openModal({
    title: result.summary?.offline_or_blocked ? 'Verificação adiada' : 'Relatório de atualizações',
    eyebrow: 'APIs de IA · Turso · plataformas de concursos',
    body: updateMonitorReportHtml(result),
    footer: '<button class="button button--primary" type="button" data-modal-close>Concluir</button>',
  });
}

async function runUpdateMonitorNow({ scheduled = false } = {}) {
  const button = $('#runUpdateMonitorNow');
  if (button) setBusy(button, true, 'Verificando fontes oficiais');
  try {
    const started = await bridge.call('start_update_monitor_check');
    if (!started?.ok) throw new Error(started?.error || 'Não foi possível iniciar a verificação.');
    toast('Verificação iniciada em segundo plano. Você pode continuar usando o QuestFlow.', 'info', 6500);
    const result = await monitorTask(started.task_id, (task) => {
      if (button && task?.message) button.title = `${task.message} ${Math.round(Number(task.progress || 0) * 100)}%`;
    }, { timeoutMs: 180000, intervalMs: 650 });
    await loadUpdateMonitorStatus();
    showUpdateMonitorResult(result || {});
    if (result?.summary?.offline_or_blocked) toast('Sem internet/acesso externo. Nada foi alterado no banco e a verificação continuará pendente.', 'warning', 9000);
    else toast('Monitor quinzenal concluído sem bloquear o banco.', 'success', 6500);
    return result;
  } catch (error) {
    toast(error.message || 'A verificação não pôde ser concluída. O banco local não foi afetado.', 'warning', 9000);
    if (scheduled) await loadUpdateMonitorStatus();
    return null;
  } finally {
    if (button) setBusy(button, false);
  }
}

async function saveUpdateMonitorSettings() {
  const button = $('#saveUpdateMonitorSettings');
  setBusy(button, true, 'Salvando monitor');
  try {
    const day1 = Number($('#updateMonitorDay1')?.value || 1);
    const day2 = Number($('#updateMonitorDay2')?.value || 15);
    if (![day1, day2].every((x) => Number.isInteger(x) && x >= 1 && x <= 28) || day1 === day2) {
      throw new Error('Escolha dois dias diferentes, entre 1 e 28.');
    }
    const status = await bridge.call('save_update_monitor_settings', { enabled: Boolean($('#updateMonitorEnabled')?.checked), days: [day1, day2] });
    if (status?.ok === false) throw new Error(status.error || 'Falha ao salvar o monitor.');
    renderUpdateMonitorStatus(status || {});
    toast('Monitor quinzenal salvo.', 'success');
  } catch (error) { toast(error.message, 'error', 7000); }
  finally { setBusy(button, false); }
}

function showUpdateMonitorHistory() {
  const status = state.updateMonitorStatus || {};
  const history = [...(status.history || [])].reverse();
  const body = history.length
    ? `<div class="update-monitor-list">${history.map((item) => `<article class="update-monitor-item"><span class="status-dot status-dot--${item.offline_or_blocked ? 'warning' : 'ok'}"></span><div><strong>${escapeHtml(item.event === 'check' ? 'Verificação' : item.event === 'snoozed' ? 'Adiado' : item.event === 'skipped' ? 'Ciclo ignorado' : item.event || 'Evento')}</strong><small>${escapeHtml(formatDate(item.at))}${item.changed != null ? ` • mudanças: ${Number(item.changed || 0)} • sucessos: ${Number(item.successes || 0)} • falhas: ${Number(item.failures || 0)}` : ''}</small></div></article>`).join('')}</div>`
    : '<p>Ainda não há histórico do monitor.</p>';
  openModal({ title: 'Histórico do monitor', eyebrow: 'Somente metadados locais', body, footer: '<button class="button button--primary" data-modal-close>Fechar</button>' });
}

function showScheduledUpdateMonitorPrompt(status = {}) {
  const days = status.days || [1, 15];
  openModal({
    title: 'Verificação quinzenal disponível',
    eyebrow: 'Monitor de tecnologia do QuestFlow',
    body: `<div class="stack"><p>Chegou a janela programada para verificar mudanças nas <strong>APIs de IA, Turso e plataformas de concursos</strong>.</p><div class="network-note"><strong>Seguro para trabalhar:</strong> a consulta só acessa a internet se você escolher “Verificar agora”, roda fora da thread da interface e não abre nem grava o SQLite. Se não houver internet, o QuestFlow apenas adia a verificação.</div><p class="field-help">Agenda atual: dias ${escapeHtml(days[0])} e ${escapeHtml(days[1])} de cada mês.</p></div>`,
    footer: '<button class="button" type="button" id="skipUpdateMonitorCycle">Pular esta quinzena</button><button class="button button--secondary" type="button" id="snoozeUpdateMonitor">Adiar 24h</button><button class="button button--primary" type="button" id="confirmUpdateMonitorNow">Verificar agora</button>',
    onOpen: (layer) => {
      $('#skipUpdateMonitorCycle', layer)?.addEventListener('click', async () => { await bridge.call('defer_update_monitor', 'skip'); closeModal(); await loadUpdateMonitorStatus(); toast('Esta janela quinzenal foi ignorada. O próximo lembrete seguirá a agenda.', 'info'); });
      $('#snoozeUpdateMonitor', layer)?.addEventListener('click', async () => { await bridge.call('defer_update_monitor', 'snooze'); closeModal(); await loadUpdateMonitorStatus(); toast('Verificação adiada por 24 horas.', 'info'); });
      $('#confirmUpdateMonitorNow', layer)?.addEventListener('click', async () => { closeModal(); await runUpdateMonitorNow({ scheduled: true }); });
    },
  });
}

function startUpdateMonitorWatch() {
  const loop = async () => {
    if (!document.hidden) await loadUpdateMonitorStatus({ promptIfDue: true }).catch(() => {});
    window.setTimeout(loop, document.hidden ? 60 * 60 * 1000 : 20 * 60 * 1000);
  };
  window.setTimeout(loop, 1800);
}


function runtimeStateLabel(value='') {
  const map={healthy:'Saudável',offline:'Offline normal',degraded:'Degradado',suspect:'Suspeito',recovering:'Recuperando',failed:'Falha',disabled:'Desativado',initializing:'Inicializando',attention:'Atenção',offline_normal:'Offline normal'};
  return map[String(value||'').toLowerCase()] || textOrMissing(value,'Desconhecido');
}

function renderRuntimeWatchdog(data={}) {
  const watchdog=data.watchdog||{}; const compatibility=data.compatibility||{}; const rateLimits=data.rate_limits||[]; const services=watchdog.services||[];
  const config=state.config||{};
  const set=(sel,val)=>{const el=$(sel); if(el) el.value=val ?? '';}; const check=(sel,val)=>{const el=$(sel); if(el) el.checked=Boolean(val);};
  check('#watchdogEnabled', config.watchdog_enabled !== false);
  check('#watchdogAutoRecover', config.watchdog_auto_recover !== false);
  set('#watchdogInterval', config.watchdog_interval_seconds || watchdog.interval_seconds || 5);
  set('#watchdogTaskStall', config.watchdog_task_stall_seconds || 240);
  set('#runtimeIoConcurrency', config.runtime_io_max_concurrency || 4);
  set('#runtimeTaskHistory', config.runtime_task_history_limit || 160);
  set('#aiRateLimit', config.ai_rate_limit_per_minute || 30);
  set('#cloudRateLimit', config.cloud_rate_limit_per_minute || 120);
  const pill=$('#runtimeWatchdogStatusPill');
  if(pill){pill.textContent=`${runtimeStateLabel(watchdog.overall)} · ${Math.round(Number(watchdog.score||0))}%`; pill.className=`status-pill ${['failed','degraded'].includes(watchdog.overall)?'status-pill--warning':''}`;}
  const summary=$('#runtimeWatchdogSummary');
  if(summary){
    summary.innerHTML=`<div class="runtime-health-overview"><div class="runtime-health-score">${Math.round(Number(watchdog.score||0))}%</div><div class="runtime-health-copy"><strong>${escapeHtml(runtimeStateLabel(watchdog.overall))}</strong><span>${watchdog.auto_recover?'Autorrecuperação segura ativa':'Somente monitoramento'} · ${services.length} serviço(s) supervisionado(s)</span></div></div>
      <div class="runtime-health-grid">${services.map(s=>{const detail=s.detail||{}; const hints=[]; if(detail.heartbeat_age_seconds!=null) hints.push(`heartbeat ${Number(detail.heartbeat_age_seconds).toFixed(1)}s`); if(detail.latency_ms!=null) hints.push(`latência ${Number(detail.latency_ms).toFixed(1)}ms`); if(detail.pending!=null) hints.push(`${formatNumber(detail.pending)} pendente(s)`); if(detail.active!=null) hints.push(`${formatNumber(detail.active)} tarefa(s) ativa(s)`); if(detail.last_error) hints.push(detail.last_error); return `<article class="runtime-health-card" data-state="${escapeHtml(s.status||'initializing')}"><div class="runtime-health-card__head"><strong>${escapeHtml(s.label||s.name)}</strong><span class="runtime-health-state">${escapeHtml(runtimeStateLabel(s.status))}</span></div><small>${escapeHtml(hints.filter(Boolean).join(' · ')||'Sem alertas recentes.')}</small>${s.recoverable?`<button class="button" type="button" data-runtime-restart="${escapeHtml(s.name)}">Reiniciar serviço</button>`:''}</article>`;}).join('')}</div>`;
  }
  const compat=$('#runtimeCompatibilityBody');
  if(compat){
    const py=compatibility.python||{}, sq=compatibility.sqlite||{}, pf=compatibility.platform||{};
    const dbService=services.find(s=>s.name==='sqlite')||{}; const schemas=dbService.detail?.schema_versions||{}; const schemaText=Object.entries(schemas).map(([k,v])=>`${k} v${v}`).join(' · ');
    compat.innerHTML=`<div class="runtime-compatibility-row"><strong>QuestFlow</strong><span>${escapeHtml(compatibility.app_version||state.app?.version||'')}</span></div><div class="runtime-compatibility-row"><strong>Python</strong><span>${escapeHtml(py.version||'')} · matriz ${escapeHtml(py.validated_range||'')}</span></div><div class="runtime-compatibility-row"><strong>SQLite</strong><span>${escapeHtml(sq.version||'')} · mínimo ${escapeHtml(sq.minimum||'')}</span></div>${schemaText?`<div class="runtime-compatibility-row"><strong>Schemas do banco</strong><span>${escapeHtml(schemaText)}</span></div>`:''}<div class="runtime-compatibility-row"><strong>Sistema</strong><span>${escapeHtml(`${pf.system||''} ${pf.release||''} · ${pf.bits||''} bits`)}</span></div>${(compatibility.warnings||[]).map(w=>`<div class="network-note">${escapeHtml(w)}</div>`).join('')}${rateLimits.length?`<div class="runtime-compatibility-row"><strong>Rate limiters ativos</strong><span>${rateLimits.map(x=>`${escapeHtml(x.key)} ${formatNumber(x.rate_per_minute)}/min`).join(' · ')}</span></div>`:''}`;
  }
  const history=$('#runtimeWatchdogHistory');
  if(history){const items=watchdog.history||[]; history.innerHTML=items.length?items.slice().reverse().map(h=>`<div class="runtime-history-row"><span>${escapeHtml(formatDate(h.at))}</span><strong>${escapeHtml(h.service||'supervisor')}</strong><code>${escapeHtml(`${h.event||''}${h.status?` · ${h.status}`:''}`)}</code></div>`).join(''):'<p class="empty-state">Nenhum incidente registrado nesta sessão.</p>';}
}

async function loadRuntimeWatchdogStatus(){
  try{const r=await bridge.call('get_runtime_watchdog_status'); if(r?.ok){state.runtimeWatchdog=r; renderRuntimeWatchdog(r);}}
  catch(e){const pill=$('#runtimeWatchdogStatusPill'); if(pill) pill.textContent='Indisponível';}
}

async function saveRuntimeWatchdogSettings(){
  const b=$('#saveRuntimeWatchdogSettings'); setBusy(b,true,'Salvando Watchdog');
  try{
    const payload={enabled:Boolean($('#watchdogEnabled')?.checked),auto_recover:Boolean($('#watchdogAutoRecover')?.checked),interval_seconds:Number($('#watchdogInterval')?.value||5),task_stall_seconds:Number($('#watchdogTaskStall')?.value||240),io_max_concurrency:Number($('#runtimeIoConcurrency')?.value||4),task_history_limit:Number($('#runtimeTaskHistory')?.value||160),ai_rate_limit_per_minute:Number($('#aiRateLimit')?.value||30),cloud_rate_limit_per_minute:Number($('#cloudRateLimit')?.value||120)};
    const r=await bridge.call('save_runtime_watchdog_settings',payload); if(!r?.ok) throw new Error(r?.error||'Falha ao salvar Watchdog.'); state.config={...state.config,watchdog_enabled:payload.enabled,watchdog_auto_recover:payload.auto_recover,watchdog_interval_seconds:payload.interval_seconds,watchdog_task_stall_seconds:payload.task_stall_seconds,runtime_io_max_concurrency:payload.io_max_concurrency,runtime_task_history_limit:payload.task_history_limit,ai_rate_limit_per_minute:payload.ai_rate_limit_per_minute,cloud_rate_limit_per_minute:payload.cloud_rate_limit_per_minute}; renderRuntimeWatchdog(r); toast('Watchdog e limites salvos.','success');
  }catch(e){toast(e.message,'error');} finally{setBusy(b,false);}
}

async function runRuntimeWatchdogCheck(){const b=$('#runRuntimeWatchdogCheck');setBusy(b,true,'Verificando');try{const r=await bridge.call('run_runtime_watchdog_check');if(!r?.ok)throw new Error(r?.error||'Falha na verificação.');await loadRuntimeWatchdogStatus();toast('Saúde do runtime verificada.','success');}catch(e){toast(e.message,'error');}finally{setBusy(b,false);}}

async function restartRuntimeService(name){try{const r=await bridge.call('restart_runtime_service',name);if(!r?.ok)throw new Error(r?.error||'Não foi possível reiniciar o serviço.');toast('Recuperação solicitada com segurança.','success');setTimeout(loadRuntimeWatchdogStatus,700);}catch(e){toast(e.message,'error');}}

function renderCloudSyncSettings(settings = {}, status = null) {
  const set = (selector, value) => { const node = $(selector); if (node && document.activeElement !== node) node.value = value ?? ''; };
  const check = (selector, value) => { const node = $(selector); if (node) node.checked = Boolean(value); };
  check('#cloudSyncEnabled', settings.cloud_sync_enabled);
  const enabledToggle = $('#cloudSyncEnabled');
  const activationCompleted = Boolean(settings.cloud_sync_activation_completed);
  if (enabledToggle) {
    enabledToggle.disabled = Boolean(settings.cloud_sync_safe_activation_required) && !activationCompleted;
    enabledToggle.title = enabledToggle.disabled ? 'Conclua a Ativação segura antes de liberar o automático.' : '';
  }
  set('#cloudTursoUrl', settings.cloud_turso_url || '');
  set('#cloudDeviceName', settings.cloud_device_name || '');
  set('#cloudSyncInterval', settings.cloud_sync_interval_seconds || 30);
  check('#cloudSyncOnStart', settings.cloud_sync_on_start !== false);
  check('#cloudSyncOnShutdown', settings.cloud_sync_on_shutdown !== false);
  check('#mobileLanEnabled', settings.mobile_lan_enabled);
  const tokenHint = $('#cloudTokenHint');
  if (tokenHint) tokenHint.textContent = settings.cloud_turso_token_configured
    ? 'Token protegido pelo Windows (DPAPI). Deixe vazio para mantê-lo.'
    : 'Nenhum token Turso armazenado neste computador.';
  const activationBox = $('#cloudActivationSummary');
  if (activationBox) {
    const activation = status?.activation || {};
    const completed = Boolean(settings.cloud_sync_activation_completed || activation.completed);
    activationBox.className = `cloud-activation-inline ${completed ? 'is-active' : 'is-pending'}`;
    activationBox.innerHTML = completed
      ? `<strong>✓ Ativação segura concluída</strong><span>Sincronização automática liberada${activation.completed_at ? ` · ${escapeHtml(formatDate(activation.completed_at))}` : ''}.</span>`
      : `<strong>Proteção da primeira sincronização</strong><span>Antes da primeira escrita, o QuestFlow valida SQLite, Turso, IDs/hashes, fila, conflitos e cria um backup local.</span>`;
  }
  renderCloudSyncStatus(status || {});
}

function renderCloudSyncStatus(status = {}) {
  const pill = $('#cloudSyncStatusPill');
  const text = $('#cloudSyncStatusText');
  const stateLabel = { synced: 'Sincronizado', pending: 'Pendente', ready: 'Pronto', error: 'Erro', warning: 'Atenção', disabled: 'Desativado', activation_required: 'Aguardando ativação', database_busy: 'Banco ocupado', database_unavailable: 'Banco indisponível' }[status.state] || (status.enabled ? 'Pronto' : 'Desativado');
  if (pill) { pill.textContent = stateLabel; pill.dataset.tone = status.state === 'error' ? 'danger' : (status.state === 'synced' ? 'success' : ''); }
  if (text) {
    const parts = [];
    if (status.device_name) parts.push(`Dispositivo: ${status.device_name}`);
    if (status.generation) parts.push(`Geração: ${status.generation}`);
    parts.push(`Pendentes: ${status.pending || 0}`);
    if (status.conflicts) parts.push(`Conflitos registrados: ${status.conflicts}`);
    if (status.last_sync_at) parts.push(`Última sincronização: ${formatDate(status.last_sync_at)}`);
    if (status.last_error) parts.push(`Último erro: ${status.last_error}`);
    text.textContent = parts.join(' • ') || 'A sincronização ainda não foi executada.';
  }
}

function collectCloudSyncSettings() {
  return {
    cloud_sync_enabled: Boolean($('#cloudSyncEnabled')?.checked),
    cloud_turso_url: $('#cloudTursoUrl')?.value?.trim() || '',
    cloud_turso_token: $('#cloudTursoToken')?.value || '',
    cloud_device_name: $('#cloudDeviceName')?.value?.trim() || '',
    cloud_sync_interval_seconds: Number($('#cloudSyncInterval')?.value || 30),
    cloud_sync_on_start: Boolean($('#cloudSyncOnStart')?.checked),
    cloud_sync_on_shutdown: Boolean($('#cloudSyncOnShutdown')?.checked),
    mobile_lan_enabled: Boolean($('#mobileLanEnabled')?.checked),
  };
}

async function loadCloudSyncSettings() {
  const result = await bridge.call('get_cloud_sync_settings');
  if (!result?.ok) return;
  state.config = { ...state.config, ...(result.settings || {}) };
  renderCloudSyncSettings(result.settings || {}, result.status || {});
  try {
    const mobile = await bridge.call('get_mobile_access');
    const box = $('#mobileAccessText');
    const apiUrls = Array.isArray(mobile?.api_urls) ? mobile.api_urls : [];
    if (box) {
      box.textContent = mobile?.enabled && apiUrls.length
        ? `Pronto para o celular: ${apiUrls[0]}${apiUrls.length > 1 ? ` • alternativas: ${apiUrls.slice(1).join(' • ')}` : ''}`
        : 'Acesso local desativado ou aguardando reinício do QuestFlow.';
    }
    const localPill = $('#mobileLocalStatusPill');
    if (localPill) {
      localPill.textContent = mobile?.enabled && apiUrls.length ? 'Pronto' : (result.settings?.mobile_lan_enabled ? 'Reinicie o Studio' : 'Desativado');
      localPill.dataset.tone = mobile?.enabled && apiUrls.length ? 'success' : (result.settings?.mobile_lan_enabled ? 'warning' : '');
    }
  } catch (_) {}
}

function renderMobileCloudBridgeSettings(settings = {}, status = null) {
  const set = (selector, value) => { const node = $(selector); if (node && document.activeElement !== node) node.value = value ?? ''; };
  const check = (selector, value) => { const node = $(selector); if (node) node.checked = Boolean(value); };
  check('#mobileCloudBridgeEnabled', settings.mobile_cloud_bridge_enabled);
  set('#mobileCloudBridgeUrl', settings.mobile_cloud_bridge_url || '');
  set('#mobileCloudBridgeInterval', settings.mobile_cloud_bridge_interval_seconds || 30);
  set('#mobileCloudBridgePackSize', settings.mobile_cloud_bridge_pack_size || 40);
  const hint = $('#mobileCloudBridgeKeyHint');
  if (hint) hint.textContent = settings.mobile_cloud_bridge_key_configured
    ? 'Chave protegida pelo Windows (DPAPI). Deixe o campo vazio para mantê-la.'
    : 'Nenhuma chave do Gateway protegida neste computador.';
  renderMobileCloudBridgeStatus(status || {});
}

function renderMobileCloudBridgeStatus(status = {}) {
  const pill = $('#mobileCloudBridgeStatusPill');
  const text = $('#mobileCloudBridgeStatusText');
  const label = { ready: 'Pronto', disabled: 'Desativado', needs_key: 'Falta chave', error: 'Erro' }[status.state] || (status.mobile_cloud_bridge_enabled ? 'Configurando' : 'Desativado');
  if (pill) {
    pill.textContent = label;
    pill.dataset.tone = status.state === 'ready' ? 'success' : status.state === 'error' ? 'danger' : status.state === 'needs_key' ? 'warning' : '';
  }
  if (text) {
    const parts = [];
    if (status.mobile_cloud_bridge_url) parts.push(`Gateway: ${status.mobile_cloud_bridge_url}`);
    parts.push(`Pacote offline: ${formatNumber(status.published_questions || 0)} questões publicadas`);
    parts.push(`Respostas aguardando no Gateway: ${formatNumber(status.pending_remote_events || 0)}`);
    if (status.last_sync_at) parts.push(`Última troca: ${formatDate(status.last_sync_at)}`);
    if (status.last_error) parts.push(`Último erro: ${status.last_error}`);
    text.textContent = parts.join(' • ') || 'Cloud Bridge ainda não configurado. O modo LAN continua funcionando normalmente.';
  }
}

function collectMobileCloudBridgeSettings() {
  return {
    mobile_cloud_bridge_enabled: Boolean($('#mobileCloudBridgeEnabled')?.checked),
    mobile_cloud_bridge_url: $('#mobileCloudBridgeUrl')?.value?.trim() || '',
    mobile_cloud_bridge_key: $('#mobileCloudBridgeKey')?.value || '',
    mobile_cloud_bridge_interval_seconds: Number($('#mobileCloudBridgeInterval')?.value || 30),
    mobile_cloud_bridge_pack_size: Number($('#mobileCloudBridgePackSize')?.value || 40),
  };
}

async function loadMobileCloudBridgeSettings() {
  const result = await bridge.call('get_mobile_cloud_bridge_settings');
  if (!result?.ok) return result;
  state.config = { ...state.config, ...(result.settings || {}) };
  renderMobileCloudBridgeSettings(result.settings || {}, result.status || {});
  return result;
}

async function saveMobileCloudBridgeSettings() {
  const button = $('#saveMobileCloudBridgeSettings');
  setBusy(button, true, 'Salvando');
  try {
    const payload = collectMobileCloudBridgeSettings();
    const result = await bridge.call('save_mobile_cloud_bridge_settings', payload);
    if (!result?.ok) throw new Error(result?.error || 'Falha ao salvar o Mobile Cloud Bridge.');
    state.config = { ...state.config, ...(result.settings || {}) };
    const key = $('#mobileCloudBridgeKey'); if (key) key.value = '';
    renderMobileCloudBridgeSettings(result.settings || {}, result.status || {});
    toast(payload.mobile_cloud_bridge_enabled ? 'Mobile Cloud Bridge salvo. O Studio publicará apenas projeções seguras do Mobile.' : 'Mobile Cloud Bridge desativado.', 'success', 7000);
    await loadMobileFoundation();
  } catch (error) { toast(error.message || 'Falha ao salvar Mobile Cloud Bridge.', 'error'); }
  finally { setBusy(button, false); }
}

async function testMobileCloudBridge() {
  const button = $('#testMobileCloudBridge'); setBusy(button, true, 'Testando');
  try {
    const result = await bridge.call('test_mobile_cloud_bridge');
    if (!result?.ok) throw new Error(result?.error || 'Gateway indisponível.');
    renderMobileCloudBridgeStatus(result.status || {});
    toast('Gateway respondeu corretamente.', 'success');
  } catch (error) { toast(error.message || 'Não foi possível acessar o Gateway.', 'error'); }
  finally { setBusy(button, false); }
}

async function syncMobileCloudBridgeNow() {
  const button = $('#syncMobileCloudBridgeNow'); setBusy(button, true, 'Sincronizando');
  try {
    const result = await bridge.call('sync_mobile_cloud_bridge_now');
    if (!result?.ok) throw new Error(result?.publish?.error || result?.drain?.error || result?.error || 'Falha no Mobile Cloud Bridge.');
    renderMobileCloudBridgeStatus(result.status || {});
    toast('Projeções publicadas e respostas do Mobile recebidas.', 'success');
    await loadMobileFoundation();
  } catch (error) { toast(error.message || 'Falha ao sincronizar Mobile Cloud Bridge.', 'error'); }
  finally { setBusy(button, false); }
}

function renderMobileFoundationStatus(status = {}) {
  const pill = $('#mobileFoundationStatusPill');
  if (pill) {
    pill.textContent = status?.ok ? 'Fundação pronta' : 'Indisponível';
    pill.dataset.tone = status?.ok ? 'success' : 'danger';
  }
  const metrics = $('#mobileFoundationMetrics');
  if (metrics) {
    const shortId = (value) => {
      const text = String(value || '—');
      return text.length > 20 ? `${text.slice(0, 8)}…${text.slice(-6)}` : text;
    };
    const cards = [
      ['Mobile', '0.10.0 Study Session'],
      ['Aparelhos conectados', formatNumber(status.active_devices || 0)],
      ['Aparelhos desconectados', formatNumber(status.disconnected_devices || 0)],
      ['Eventos de estudo', formatNumber(status.learning_events || 0)],
      ['Tempo de resposta', status.active_timing_quality_gate ? 'Protegido' : 'Verificar'],
      ['Modo principal', status.cloud_bridge?.enabled ? 'LAN + Cloud opcional' : 'Studio local + offline'],
    ];
    metrics.innerHTML = cards.map(([label, value]) => `<div class="mobile-foundation-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');
  }
  const list = $('#mobileDeviceList');
  if (list) {
    const devices = Array.isArray(status.devices) ? status.devices : [];
    if (!devices.length) {
      list.innerHTML = '<p class="muted">Nenhum aparelho conectado ou salvo na lista.</p>';
    } else {
      const activeDevices = devices.filter((device) => String(device.status || '') === 'active');
      const disconnectedDevices = devices.filter((device) => String(device.status || '') !== 'active');
      const deviceCard = (device, active) => {
        const lastSeen = device.last_seen_at ? formatDate(device.last_seen_at) : '—';
        const statusText = active ? 'Conectado' : 'Desconectado';
        const action = active
          ? `<button class="button button--secondary button--compact" type="button" data-mobile-disconnect="${escapeHtml(device.device_id || '')}">Desconectar</button>`
          : `<div class="button-row"><span class="status-pill">Desconectado</span><button class="button button--secondary button--compact" type="button" data-mobile-forget="${escapeHtml(device.device_id || '')}">Remover da lista</button></div>`;
        const hint = active
          ? 'Este aparelho está autorizado a sincronizar com o QuestFlow.'
          : 'Para voltar a usar este aparelho, gere um novo QR e conecte novamente. O mesmo registro será reativado.';
        return `<div class="mobile-device-item"><div class="mobile-device-item__copy"><strong>${escapeHtml(device.name || 'QuestFlow Mobile')} · ${escapeHtml(String(device.platform || '').toUpperCase())}</strong><small>${escapeHtml(statusText)} · ${escapeHtml(device.app_version || '')} · último contato: ${escapeHtml(lastSeen)}${device.push_registered ? ' · push registrado' : ''}</small><small>${escapeHtml(hint)}</small><small>ID: ${escapeHtml(device.device_id || '')}</small></div>${action}</div>`;
      };
      const section = (title, items, active) => items.length
        ? `<div class="mobile-device-group"><h4>${escapeHtml(title)} <span class="status-pill">${formatNumber(items.length)}</span></h4>${items.map((device) => deviceCard(device, active)).join('')}</div>`
        : '';
      list.innerHTML = `${section('Conectados', activeDevices, true)}${section('Desconectados', disconnectedDevices, false)}`;

      $$('[data-mobile-disconnect]', list).forEach((button) => button.addEventListener('click', async () => {
        const deviceId = button.dataset.mobileDisconnect || '';
        if (!deviceId) return;
        if (!window.confirm('Desconectar este aparelho? A sessão será encerrada, mas o histórico de estudo será preservado.')) return;
        setBusy(button, true, 'Desconectando');
        try {
          const result = await bridge.call('disconnect_mobile_device', deviceId);
          if (!result?.ok) throw new Error(result?.error || 'Não foi possível desconectar o aparelho.');
          toast('Aparelho desconectado. Para voltar, conecte-o novamente usando um novo QR.', 'success');
          await loadMobileFoundation();
        } catch (error) { toast(error.message || 'Falha ao desconectar aparelho.', 'error'); }
        finally { setBusy(button, false); }
      }));

      $$('[data-mobile-forget]', list).forEach((button) => button.addEventListener('click', async () => {
        const deviceId = button.dataset.mobileForget || '';
        if (!deviceId) return;
        if (!window.confirm('Remover este aparelho da lista? O histórico de respostas e métricas será preservado.')) return;
        setBusy(button, true, 'Removendo');
        try {
          const result = await bridge.call('forget_mobile_device', deviceId);
          if (!result?.ok) throw new Error(result?.error || 'Não foi possível remover o aparelho da lista.');
          toast('Aparelho removido da lista. O histórico de estudo foi preservado.', 'success');
          await loadMobileFoundation();
        } catch (error) { toast(error.message || 'Falha ao remover aparelho da lista.', 'error'); }
        finally { setBusy(button, false); }
      }));
    }
  }

}

async function loadMobileFoundation() {
  const status = await bridge.call('get_mobile_foundation_status');
  renderMobileFoundationStatus(status || {});
  return status;
}

async function createMobilePairing() {
  const button = $('#createMobilePairing');
  setBusy(button, true, 'Gerando');
  try {
    const result = await bridge.call('create_mobile_pairing');
    if (!result?.ok || !result?.pairing) throw new Error(result?.error || 'Não foi possível criar o pareamento.');
    const pairing = result.pairing;
    state.mobilePairing = pairing;
    const card = $('#mobilePairingCard');
    const qr = $('#mobilePairingQr');
    const token = $('#mobilePairingToken');
    const expiry = $('#mobilePairingExpiry');
    const server = $('#mobilePairingServer');
    if (card) card.hidden = false;
    if (token) token.textContent = pairing.pairing_token || '';
    if (server) {
      const cloud = pairing.cloud_base_url ? ` • Cloud Bridge: ${pairing.cloud_base_url}` : '';
      server.textContent = pairing.api_base_url
        ? `API local: ${pairing.api_base_url}${cloud}`
        : `A API local ainda não está acessível pela rede.${cloud}`;
    }
    if (expiry) expiry.textContent = `Expira em até ${Math.round(Number(pairing.expires_in_seconds || 300) / 60)} min · ${pairing.expires_at ? formatDate(pairing.expires_at) : ''} · uso único.`;
    if (qr) {
      if (pairing.qr_data_uri) { qr.src = pairing.qr_data_uri; qr.hidden = false; }
      else { qr.removeAttribute('src'); qr.hidden = true; }
    }
    toast(pairing.api_base_url ? `Pareamento criado. Leia o QR pelo QuestFlow Mobile ${currentMobileRelease()}.` : 'Pareamento criado, mas a API local ainda não está acessível. Ative o acesso pelo celular e reinicie o Studio antes do primeiro pareamento.', pairing.api_base_url ? 'success' : 'warning', 9000);
    await loadMobileFoundation();
  } catch (error) { toast(error.message || 'Falha ao criar pareamento.', 'error'); }
  finally { setBusy(button, false); }
}

async function copyMobilePairing() {
  const value = state.mobilePairing?.pairing_uri || state.mobilePairing?.pairing_token || $('#mobilePairingToken')?.textContent || '';
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    toast('Código de pareamento copiado.', 'success');
  } catch (_) {
    const token = $('#mobilePairingToken');
    if (token) {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(token);
      selection?.removeAllRanges(); selection?.addRange(range);
    }
    toast('Selecione e copie o código exibido.', 'warning');
  }
}

async function saveMobileLanSettings() {
  const button = $('#saveMobileLanSettings');
  if (button) setBusy(button, true, 'Salvando');
  try {
    const payload = {
      cloud_sync_enabled: Boolean(state.config?.cloud_sync_enabled),
      cloud_turso_url: String(state.config?.cloud_turso_url || ''),
      cloud_turso_token: '',
      cloud_device_name: String(state.config?.cloud_device_name || ''),
      cloud_sync_interval_seconds: Number(state.config?.cloud_sync_interval_seconds || 30),
      cloud_sync_on_start: Boolean(state.config?.cloud_sync_on_start),
      cloud_sync_on_shutdown: Boolean(state.config?.cloud_sync_on_shutdown),
      mobile_lan_enabled: Boolean($('#mobileLanEnabled')?.checked),
    };
    const result = await bridge.call('save_cloud_sync_settings', payload);
    if (!result?.ok) throw new Error(result?.error || 'Não foi possível salvar o acesso do Mobile.');
    state.config = { ...state.config, ...(result.settings || payload) };
    renderCloudSyncSettings(result.settings || state.config, result.status || {});
    await loadCloudSyncSettings();
    toast(payload.mobile_lan_enabled ? 'Acesso local do Mobile salvo. Reinicie o Studio se o status pedir.' : 'Acesso local do Mobile desativado.', 'success', 7000);
  } catch (error) {
    toast(error.message || 'Falha ao salvar o acesso do Mobile.', 'error', 8000);
  } finally { if (button) setBusy(button, false); }
}

async function saveCloudSyncSettings() {
  const button = $('#saveCloudSyncSettings');
  button?.classList.add('is-loading');
  try {
    const payload = collectCloudSyncSettings();
    const result = await bridge.call('save_cloud_sync_settings', payload);
    if (!result.ok) throw new Error(result.error || 'Falha ao salvar Cloud Sync.');
    if ($('#cloudTursoToken')) $('#cloudTursoToken').value = '';
    state.config = { ...state.config, ...(result.settings || payload) };
    renderCloudSyncSettings(result.settings || state.config, result.status || {});
    toast(result.activation_required ? 'Configuração salva. Agora execute a Ativação segura antes da primeira sincronização.' : 'Configuração do Cloud Sync salva.', result.activation_required ? 'warning' : 'success', 8000);
  } catch (error) { toast(error.message || 'Falha ao salvar Cloud Sync.', 'error'); }
  finally { button?.classList.remove('is-loading'); }
}

function cloudActivationStep(ok, title, detail = '') {
  const tone = ok === true ? 'success' : ok === false ? 'danger' : 'warning';
  const icon = ok === true ? '✓' : ok === false ? '!' : '…';
  return `<div class="cloud-activation-step cloud-activation-step--${tone}"><span>${icon}</span><div><strong>${escapeHtml(title)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div></div>`;
}

function renderCloudActivationPreview(preview = {}) {
  const config = preview.configuration || {};
  const remote = preview.remote || {};
  const questions = preview.questions || {};
  const dry = preview.dry_run || {};
  const guard = preview.recovery_guard || {};
  const groups = Array.isArray(dry.groups) ? dry.groups : [];
  const comparisonDetail = remote.reachable
    ? `${formatNumber(questions.local_count || 0)} local · ${formatNumber(questions.remote_count || 0)} Turso · ${formatNumber(questions.different_count || 0)} mesmo ID com conteúdo diferente · ${formatNumber(questions.local_only_count || 0)} somente local · ${formatNumber(questions.remote_only_count || 0)} somente nuvem`
    : 'A comparação será executada após conectar ao Turso.';
  return `<div class="cloud-activation-wizard">
    <div class="notice"><strong>Nenhuma escrita no Turso nesta etapa.</strong><span>O preflight apenas lê a nuvem e registra checkpoints locais de diagnóstico.</span></div>
    ${cloudActivationStep(Boolean(preview.local_healthy), 'SQLite local', `quick_check: ${preview.quick_check || '—'} · FK: ${formatNumber(preview.foreign_key_violations || 0)}`)}
    ${guard.active ? cloudActivationStep(true, 'Proteção pós-recuperação', 'RECOVERY_GUARD ativo. A Ativação segura arquivará esta proteção somente depois de validar o backup local; o automático continuará bloqueado até fila = 0 e conflitos = 0.') : ''}
    ${cloudActivationStep(Boolean(config.complete), 'Configuração e credencial', config.complete ? 'URL e token presentes.' : 'Informe URL e token e salve a configuração.')}
    ${cloudActivationStep(Boolean(remote.reachable), 'Conexão com Turso', remote.reachable ? `Conectado${remote.elapsed_ms != null ? ` · ${remote.elapsed_ms} ms` : ''} · ${formatNumber(remote.event_count || 0)} evento(s) remotos` : (preview.error || preview.message || 'Não verificado.'))}
    ${cloudActivationStep(remote.reachable ? true : null, 'Comparação de questões por ID + hash', comparisonDetail)}
    ${cloudActivationStep(dry.event_ids_unique !== false && !Number(dry.predicted_conflict_count || 0), 'Dry-run da fila', `${formatNumber(dry.pending || 0)} alteração(ões) · ${formatNumber(dry.predicted_conflict_count || 0)} conflito(s) previsto(s) · event_id ${dry.event_ids_unique === false ? 'duplicado' : 'idempotente'}`)}
    <div class="cloud-activation-groups">${groups.length ? groups.map((g) => `<span class="sync-queue-chip"><strong>${formatNumber(g.count || 0)}</strong> ${escapeHtml(g.label || g.table_name || 'Dados')} · ${escapeHtml(g.namespace || 'system')} · ${escapeHtml(g.kind || 'canonical')}</span>`).join('') : '<span class="muted">Nenhuma alteração local pendente no dry-run.</span>'}</div>
    ${cloudActivationStep(true, 'Backup antes da primeira escrita', 'Será criado e validado automaticamente imediatamente antes da sincronização inicial.')}
  </div>`;
}

async function openCloudSafeActivation() {
  const button = $('#safeActivateCloudSync');
  setBusy(button, true, 'Validando');
  try {
    // Save URL/token first, but do not enable automatic sync.
    const payload = { ...collectCloudSyncSettings(), cloud_sync_enabled: false };
    const saved = await bridge.call('save_cloud_sync_settings', payload);
    if (!saved?.ok) throw new Error(saved?.error || 'Não foi possível salvar a configuração do Turso.');
    if ($('#cloudTursoToken')) $('#cloudTursoToken').value = '';
    const result = await bridge.call('get_cloud_sync_activation_preview');
    const preview = result?.preview || {};
    const canActivate = Boolean(preview.ok) && !Boolean(preview.blocking_conflicts);
    const source = preview.recommended_source === 'this_device' ? 'this_device' : 'merge';
    const sourceLabel = preview.resume_available
      ? `Retomar primeira sincronização${Number(preview.resume_pending || 0) ? ` · ${formatNumber(preview.resume_pending)} pendentes` : ''}`
      : (source === 'this_device' ? 'Usar este computador como origem' : 'Mesclar com a nuvem');
    openModal({
      title: 'Ativação segura do Cloud Sync',
      eyebrow: 'Turso · primeira sincronização protegida',
      body: `${renderCloudActivationPreview(preview)}${preview.resume_available ? '<div class="notice notice--warning"><strong>Sincronização anterior ficou incompleta, mas está segura para retomada.</strong><span>O QuestFlow continuará da fila existente sem semear novamente os mesmos registros.</span></div>' : ''}${preview.blocking_conflicts ? '<div class="notice notice--danger"><strong>Ativação bloqueada.</strong><span>Há uma alteração remota ainda não confirmada para o mesmo registro de uma alteração local. Nenhuma escrita foi feita.</span></div>' : ''}${preview.requires_difference_confirmation ? '<div class="notice notice--warning"><strong>Bancos diferentes.</strong><span>A mesclagem preservará o backup local e exige confirmação humana antes da primeira escrita.</span></div>' : ''}`,
      footer: `<button class="button button--secondary" data-modal-close>Cancelar</button>${canActivate ? `<button class="button button--primary" id="confirmCloudSafeActivation">${escapeHtml(sourceLabel)}</button>` : ''}`,
      onOpen: () => $('#confirmCloudSafeActivation')?.addEventListener('click', async (event) => {
        const confirmButton = event.currentTarget;
        let confirmed = false;
        if (preview.requires_difference_confirmation) {
          confirmed = window.confirm('Existem diferenças entre o banco local e o Turso. O QuestFlow criará um backup validado antes da mesclagem. Deseja continuar?');
          if (!confirmed) return;
        }
        setBusy(confirmButton, true, preview.resume_available ? 'Retomando sincronização' : 'Sincronizando com proteção');
        try {
          let activated = null;
          for (let slice = 0; slice < 20; slice += 1) {
            activated = await bridge.call('activate_cloud_sync_safely', source, confirmed);
            if (!activated?.ok) throw new Error(activated?.error || 'A ativação segura não foi concluída.');
            if (activated?.completed || activated?.activation?.completed) break;
            const pending = Number(activated?.pending ?? activated?.status?.pending ?? 0);
            confirmButton.textContent = pending > 0
              ? `Sincronizando · ${formatNumber(pending)} restante(s)`
              : 'Confirmando sincronização';
            await new Promise((resolve) => setTimeout(resolve, 250));
          }
          if (!(activated?.completed || activated?.activation?.completed)) {
            const pending = Number(activated?.pending ?? activated?.status?.pending ?? 0);
            const before = Number(activated?.pending_before ?? pending);
            const pushed = Number(activated?.pushed ?? activated?.sync?.pushed ?? Math.max(0, before - pending));
            if (pushed > 0 || pending < before) {
              toast(`Sincronização avançou: ${formatNumber(Math.max(pushed, before - pending))} alteração(ões) enviada(s); ${formatNumber(pending)} ainda aguardam.`, 'warning', 12000);
            } else {
              toast(`Nenhuma alteração foi enviada neste ciclo. A fila continua em ${formatNumber(pending)}. Abra o diagnóstico antes de repetir.`, 'error', 12000);
            }
            setBusy(confirmButton, false);
            confirmButton.textContent = 'Retomar primeira sincronização';
            return;
          }
          closeModal();
          const backup = activated.backup?.path ? ` Backup: ${activated.backup.path}` : '';
          toast(`Cloud Sync ativado com segurança.${backup}`, 'success', 10000);
          await Promise.all([loadCloudSyncSettings(), loadDatabaseHealth({ quiet: true })]);
        } catch (error) {
          toast(error.message || 'Falha na ativação segura. O automático permaneceu desativado.', 'error', 12000);
          setBusy(confirmButton, false);
        }
      }),
    });
  } catch (error) { toast(error.message || 'Não foi possível iniciar a ativação segura.', 'error', 10000); }
  finally { setBusy(button, false); }
}

async function testCloudSync() {
  const result = await bridge.call('test_cloud_sync_connection');
  if (result.ok) toast(`Turso conectado${result.result?.elapsed_ms != null ? ` em ${result.result.elapsed_ms} ms` : ''}.`, 'success');
  else toast(result.error || 'Falha ao conectar ao Turso.', 'error', 8000);
  if (result.status) renderCloudSyncStatus(result.status);
}

async function prepareCloudSync(source) {
  const result = await bridge.call('prepare_cloud_sync', source);
  if (result.ok) toast(`Turso preparado. ${result.result?.seeded || 0} registro(s) colocados na fila inicial.`, 'success', 8000);
  else toast(result.error || 'Falha ao preparar o Turso.', 'error', 9000);
  if (result.status) renderCloudSyncStatus(result.status);
}

async function syncCloudNow({ refreshHealth = true } = {}) {
  const button = $('#databaseSyncNow') || $('#syncCloudNow');
  if (button) setBusy(button, true);
  try {
    const result = await bridge.call('sync_cloud_now');
    const pending = Number(result?.pending ?? result?.status?.pending ?? 0);
    if (result?.activation_required) {
      toast('Antes da primeira sincronização, conclua a Ativação segura.', 'warning', 8000);
      await openCloudSafeActivation();
    } else if (result.ok) {
      const repaired = Number(result.repaired || 0);
      toast(`Sincronização concluída: ${result.pushed || 0} enviados, ${result.pulled || 0} recebidos${repaired ? ` · ${repaired} evento(s) antigo(s) retirados da fila ativa` : ''}.`, 'success', 8000);
    } else if (result?.error) {
      toast(`Sincronização não concluída: ${result.error}`, 'error', 10000);
    } else if (pending) {
      toast(`A sincronização não avançou: ainda há ${formatNumber(pending)} evento(s) pendente(s). Abra os detalhes para identificar o motivo.`, 'warning', 9000);
    } else {
      toast('A sincronização não pôde ser confirmada. Os dados locais foram preservados.', 'warning', 8000);
    }
    if (result.status) renderCloudSyncStatus(result.status);
    if (refreshHealth) await loadDatabaseHealth({ quiet: true });
    return result;
  } finally { if (button) setBusy(button, false); }
}

async function resetStudyCycle() {
  const trigger = $('#resetStudyCycle');
  openModal({
    title: 'Reiniciar estudos do zero',
    eyebrow: 'Ação irreversível no histórico ativo',
    body: `
      <div class="reset-confirm-grid">
        ${identityPicture('empty-state-art')}
        <p>O banco de questões será preservado, mas o progresso de estudo será zerado para que todas as questões elegíveis voltem a ser tratadas como não estudadas.</p>
        <div class="reset-confirm-summary">
          <div><strong>Será zerado</strong><span>Envios, respostas, acertos, erros, FSRS/repetição espaçada, prioridades adaptativas, XP, sequências e ciclos.</span></div>
          <div><strong>Será preservado</strong><span>Questões, classificações, aprovações, imagens, configurações, proxy e correções pendentes.</span></div>
        </div>
        <p>Um backup automático do banco será criado antes da operação.</p>
        <label class="reset-confirm-input" for="resetStudyConfirm">
          <span>Digite <strong>REINICIAR</strong> para confirmar</span>
          <input id="resetStudyConfirm" type="text" autocomplete="off" spellcheck="false" placeholder="REINICIAR">
        </label>
      </div>`,
    footer: `
      <button class="button button--secondary" type="button" data-modal-close>Cancelar</button>
      <button class="button button--danger" type="button" id="confirmResetStudy" disabled>Reiniciar agora</button>`,
    onOpen: (layer) => {
      const input = $('#resetStudyConfirm', layer);
      const confirm = $('#confirmResetStudy', layer);
      const update = () => { confirm.disabled = String(input.value || '').trim().toUpperCase() !== 'REINICIAR'; };
      input.addEventListener('input', update);
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !confirm.disabled) confirm.click();
      });
      confirm.addEventListener('click', async () => {
        if (confirm.disabled) return;
        setBusy(confirm, true, 'Reiniciando ciclo de estudos');
        if (trigger) trigger.disabled = true;
        try {
          const result = await bridge.call('flow_action', 'reset');
          if (!result.ok) throw new Error(result.error || 'Não foi possível reiniciar os estudos.');
          closeModal();
          const backup = result.backup_path ? ` Backup: ${result.backup_path}` : '';
          toast(`Ciclo reiniciado. Todas as questões elegíveis voltaram ao estado inicial.${backup}`, 'success', 9000);
          state.eventCursor = 0;
          await Promise.allSettled([refreshBootstrap(), loadDashboard(), loadFlow(), loadCoverage()]);
        } catch (error) {
          toast(error.message || 'Falha ao reiniciar os estudos.', 'error', 9000);
          setBusy(confirm, false);
        } finally {
          if (trigger) trigger.disabled = false;
        }
      });
    },
  });
}

async function saveSettings() {
  const payload = {};
  [...appearanceFields, ...processingFields].forEach((field) => {
    const input = $(`#setting-${field.key}`);
    payload[field.key] = field.type === 'number' ? Number(input.value) : input.value;
  });
  const result = await bridge.call('save_settings', payload);
  if (result.ok) {
    state.config = { ...state.config, ...payload };
    document.documentElement.dataset.density = payload.ui_density || 'comfortable';
    applyTheme(payload.ui_theme || state.theme);
    applyZoom(Number(payload.ui_scale || state.zoom));
    toast('Configurações salvas.', 'success');
  } else toast(result.error || 'Falha ao salvar.', 'error');
}

async function exportData(kind) {
  const result = await bridge.call('export_data', kind, Boolean(state.config.approved_only_export));
  if (result.ok) toast(`Arquivo salvo em ${result.path}`, 'success', 7000);
  else if (!result.cancelled) toast(result.error || 'Falha na exportação.', 'error');
}

function applyBootstrap(data) {
  state.bootstrap = data;
  state.config = data.config || state.config || {};
  state.taxonomy = data.taxonomy || state.taxonomy || { materias: [] };
  if (data.dashboard_preview && Object.keys(data.dashboard_preview).length) {
    state.dashboardPreview = data.dashboard_preview;
  }
  $('#appVersion').textContent = `Versão ${data.app?.version || ''}`;
  const pending = data.stats?.pending ?? data.stats?.pendente;
  if (pending != null) {
    $('#pendingBadge').hidden = !pending;
    $('#pendingBadge').textContent = pending;
  }
  if (data.pending_reviews != null) {
    $('#correctionsBadge').hidden = !data.pending_reviews;
    $('#correctionsBadge').textContent = data.pending_reviews || 0;
  }
  document.documentElement.dataset.density = state.config.ui_density || 'comfortable';
}

async function refreshBootstrap({ background = true } = {}) {
  if (!background) {
    const data = await bridge.call('bootstrap');
    applyBootstrap(data);
    return data;
  }
  const started = await bridge.call('start_bootstrap_load');
  if (!started.ok) throw new Error(started.error || 'Não foi possível atualizar os dados iniciais.');
  const data = await monitorTask(started.task_id, () => {}, { timeoutMs: 90000, intervalMs: 400 });
  applyBootstrap(data);
  return data;
}

async function pollFlowEvents() {
  try {
    const result = await bridge.call('poll_events', state.eventCursor);
    state.eventCursor = result.cursor || state.eventCursor;
    (result.items || []).forEach((item) => {
      if (item.event === 'error') toast(item.message || 'Erro no fluxo Telegram.', 'error');
      if (item.event === 'cycle_done') toast('Ciclo do Telegram concluído.', 'success');
    });
  } catch (_) { /* bridge may be closing */ }
  if (!document.hidden) setTimeout(pollFlowEvents, 2500);
  else setTimeout(pollFlowEvents, 6000);
}


function percentText(value) { return `${Math.round(Number(value || 0) * 100)}%`; }

function renderTodayPanel(today = {}) {
  state.todayDashboard = today || {};
  const target = $('#todayPanel');
  if (!target) return;
  const project = today.project || null;
  if (!project) {
    target.innerHTML = emptyStateHtml({title:'Defina seu concurso-alvo',text:'Crie um Projeto de Concurso e registre o edital para o QuestFlow priorizar o estudo com contexto real.',compact:true,button:'<button class="button button--primary" id="createProjectFromToday" type="button">Criar projeto de concurso</button>'});
    $('#createProjectFromToday')?.addEventListener('click',()=>navigate('examproject'));
    return;
  }
  const coverage=today.coverage||{};
  const tasks=Array.isArray(today.tasks)?today.tasks:[];
  target.innerHTML=`<div class="today-summary">
    <div class="today-project"><span>Projeto ativo</span><strong>${escapeHtml(project.name||'Concurso')}</strong><small>${escapeHtml(project.board||'Banca não informada')} · ${today.days_to_exam==null?'data não informada':`${escapeHtml(today.days_to_exam)} dia(s) para a prova`}</small></div>
    <div class="today-kpis"><div><strong>${formatNumber(today.due_reviews||0)}</strong><span>revisões vencidas</span></div><div><strong>${percentText(coverage.weighted_coverage??coverage.coverage_rate)}</strong><span>cobertura do edital</span></div><div><strong>${percentText(coverage.mastery_rate)}</strong><span>itens dominados</span></div><div><strong>${formatNumber(today.estimated_minutes||0)} min</strong><span>plano estimado</span></div></div>
  </div>
  <div class="today-task-list">${tasks.length?tasks.map((task,index)=>`<button class="today-task" type="button" data-today-route="${escapeHtml(task.route||'recommend')}"><span class="today-task__number">${index+1}</span><span><strong>${escapeHtml(task.title||'Ação')}</strong><small>${escapeHtml(task.detail||'')}</small></span><b>${formatNumber(task.minutes||0)} min</b></button>`).join(''):'<p class="success-note">Nenhuma pendência crítica. Use o Recomendador para continuar avançando o edital.</p>'}</div>
  <div class="today-footer"><span>${escapeHtml(today.message||'')}</span><button class="button button--ghost button--compact" type="button" id="openActiveProject">Ver projeto e edital</button></div>`;
  $$('[data-today-route]',target).forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.todayRoute||'recommend')));
  $('#openActiveProject')?.addEventListener('click',()=>navigate('examproject'));
}

async function loadTodayDashboard() {
  const target=$('#todayPanel');
  if(target) target.innerHTML='<div class="skeleton" style="height:8rem"></div>';
  try {
    const result=await bridge.call('get_today_dashboard',state.examProjectId||'');
    if(!result.ok) throw new Error(result.error||'Não foi possível montar o plano de hoje.');
    renderTodayPanel(result.today||{});
    const badge=$('#examProjectBadge');
    const attention=Number(result.today?.critical_gaps?.length||0);
    if(badge){badge.hidden=!attention;badge.textContent=attention>9?'9+':String(attention||'');}
  } catch(error) {
    if(target) target.innerHTML=emptyStateHtml({title:'Plano diário indisponível',text:error.message,compact:true});
  }
}

function editalVersionDiff(version={}) {
  try { return JSON.parse(version.change_summary_json||'{}'); } catch(_) { return {}; }
}

function fillExamProjectForm(project={}) {
  $('#examProjectName').value=project.name||''; $('#examProjectAgency').value=project.agency||'';
  $('#examProjectRole').value=project.role||''; $('#examProjectBoard').value=project.board||'';
  $('#examProjectDate').value=project.exam_date||''; $('#examProjectStatus').value=project.status||'planejamento';
  $('#examProjectNotes').value=project.notes||'';
}

function renderExamProjectDashboard(data={}) {
  state.examProjectDashboard=data; const project=data.project||null; state.examProjectId=project?.id||null;
  const select=$('#examProjectSelect');
  if(select){select.innerHTML='<option value="">Novo projeto</option>'+((data.projects||[]).map(p=>`<option value="${escapeHtml(p.id)}">${p.active?'★ ':''}${escapeHtml(p.name)}${p.version_count?` · ${p.version_count} versão(ões)`:''}</option>`).join('')); select.value=project?.id||'';}
  if(project) fillExamProjectForm(project);
  const c=data.coverage||{}; const currency=data.currency||{};
  const metrics=$('#examProjectMetrics'); if(metrics) metrics.innerHTML=[['Dias até a prova',data.days_to_exam==null?'—':data.days_to_exam,project?.exam_date||'Data não informada'],['Cobertura',percentText(c.weighted_coverage??c.coverage_rate),`${formatNumber(c.covered||0)}/${formatNumber(c.items||0)} itens com questões`],['Domínio',percentText(c.weighted_mastery??c.mastery_rate),`${formatNumber(c.mastered||0)} itens consolidados`],['Atualidade',formatNumber(currency.attention||0),currency.attention?'questões exigem atenção':'sem alertas temporais']].map(([a,b,d])=>`<article class="metric-card"><span>${escapeHtml(a)}</span><strong>${escapeHtml(b)}</strong><small>${escapeHtml(d)}</small></article>`).join('');
  const coverage=$('#examCoveragePanel');
  if(coverage) coverage.innerHTML=!project?emptyStateHtml({title:'Nenhum projeto ativo',text:'Crie um projeto e registre a primeira versão do edital.',compact:true}):!(data.version)?emptyStateHtml({title:'Registre o edital',text:'Cole o conteúdo programático para calcular cobertura e prioridades.',compact:true}):`<div class="coverage-overview"><div><strong>${percentText(c.coverage_rate)}</strong><span>itens cobertos</span></div><div><strong>${percentText(c.study_rate)}</strong><span>itens estudados</span></div><div><strong>${percentText(c.mastery_rate)}</strong><span>itens dominados</span></div></div><div class="edital-items-table"><div class="edital-items-head"><span>Conteúdo</span><span>Questões</span><span>Desempenho</span><span>Prioridade</span></div>${(data.items||[]).slice(0,80).map(item=>`<div class="edital-item-row"><span><strong>${escapeHtml(item.subject||'')}</strong><small>${escapeHtml(item.topic||item.subtopic||'')}</small></span><span>${formatNumber(item.linked_questions||0)}${item.restricted_questions?` <small>(${item.restricted_questions} restrita)</small>`:''}</span><span>${item.mastery==null?(item.accuracy==null?'sem dados':percentText(item.accuracy)):percentText(item.mastery)}<small>${formatNumber(item.attempts||0)} tentativas</small></span><span><b class="priority-pill ${Number(item.priority||0)>=70?'is-critical':Number(item.priority||0)>=45?'is-medium':'is-low'}">${Number(item.priority||0).toFixed(0)}</b></span></div>`).join('')}</div>`;
  const versions=$('#editalVersionsPanel');
  if(versions) versions.innerHTML=(data.versions||[]).length?(data.versions||[]).map(v=>{const diff=editalVersionDiff(v);const cnt=diff.counts||{};return `<article class="version-row"><div><strong>v${v.version_no} · ${escapeHtml(v.label||'Edital')}</strong><small>${escapeHtml(v.published_at||'data não informada')}</small></div><span>+${formatNumber(cnt.added||0)} · −${formatNumber(cnt.removed||0)} · Δ${formatNumber(cnt.changed||0)}</span></article>`}).join(''):'<p class="field-help">Nenhuma versão registrada.</p>';
  const cp=$('#questionCurrencyPanel');
  if(cp){const counts=currency.counts||{};const attention=currency.items||[];cp.innerHTML=`<div class="currency-chips">${Object.entries(counts).filter(([,n])=>Number(n)>0).map(([key,n])=>`<span><b>${formatNumber(n)}</b>${escapeHtml((currency.labels||{})[key]||key)}</span>`).join('')}</div>${attention.length?`<div class="currency-list">${attention.map(item=>`<article><div><strong>${escapeHtml(item.source_code||'Questão')}</strong><small>${escapeHtml(item.subject||'')} · ${escapeHtml(item.primary_topic||'')}</small><p>${escapeHtml(item.reason||'Revisão temporal necessária.')}</p></div><select data-currency-uid="${escapeHtml(item.question_uid)}"><option value="potencialmente_desatualizada" ${item.status==='potencialmente_desatualizada'?'selected':''}>Potencialmente desatualizada</option><option value="vigente" ${item.status==='vigente'?'selected':''}>Vigente</option><option value="desatualizada" ${item.status==='desatualizada'?'selected':''}>Desatualizada</option><option value="anulada" ${item.status==='anulada'?'selected':''}>Anulada</option><option value="controversa" ${item.status==='controversa'?'selected':''}>Controversa</option><option value="historica" ${item.status==='historica'?'selected':''}>Histórica</option></select></article>`).join('')}</div>`:'<p class="success-note">Nenhuma questão exige revisão temporal no momento.</p>'}`; $$('[data-currency-uid]',cp).forEach(sel=>sel.addEventListener('change',()=>changeQuestionCurrency(sel.dataset.currencyUid,sel.value)));}
}

async function loadExamProjectPage(projectId='') {
  try { const result=await bridge.call('get_exam_project_dashboard',projectId||''); if(!result.ok) throw new Error(result.error||'Falha ao carregar projeto.'); renderExamProjectDashboard(result.dashboard||{}); }
  catch(error){toast(error.message,'error');}
}

async function saveExamProject() {
  const existing=$('#examProjectSelect')?.value||'';
  const payload={id:existing||undefined,name:$('#examProjectName')?.value||'',agency:$('#examProjectAgency')?.value||'',role:$('#examProjectRole')?.value||'',board:$('#examProjectBoard')?.value||'',exam_date:$('#examProjectDate')?.value||'',status:$('#examProjectStatus')?.value||'planejamento',notes:$('#examProjectNotes')?.value||'',active:Boolean(state.examProjectDashboard?.project?.active||!state.examProjectDashboard?.project)};
  const result=await bridge.call('save_exam_project',payload); if(!result.ok){toast(result.error||'Não foi possível salvar o projeto.','error');return;} renderExamProjectDashboard(result.dashboard||{}); toast('Projeto de concurso salvo.','success'); await loadTodayDashboard();
}
async function activateExamProject(){const id=$('#examProjectSelect')?.value||state.examProjectId||'';if(!id){toast('Salve o projeto antes de ativá-lo.','warning');return;}const r=await bridge.call('set_active_exam_project',id);if(!r.ok){toast(r.error||'Falha ao ativar projeto.','error');return;}renderExamProjectDashboard(r.dashboard||{});renderTodayPanel(r.today||{});toast('Projeto ativo atualizado no Learning Engine.','success');}
async function previewEditalParsing(){const r=await bridge.call('parse_edital_text',$('#editalText')?.value||'');const t=$('#editalParsePreview');if(!r.ok){toast(r.error||'Falha ao interpretar edital.','error');return;}if(t)t.innerHTML=`<div class="edital-preview-head"><strong>${formatNumber(r.count||0)} item(ns) reconhecido(s)</strong><span>Revise antes de registrar.</span></div>${(r.items||[]).slice(0,30).map(i=>`<div><b>${escapeHtml(i.subject||'Conteúdo geral')}</b><span>${escapeHtml(i.topic||'')}</span><small>peso ${Number(i.weight||1).toFixed(1)}</small></div>`).join('')}`;}
async function saveEditalVersion(){const id=state.examProjectId||$('#examProjectSelect')?.value||'';if(!id){toast('Crie e salve o projeto antes de registrar o edital.','warning');return;}const text=$('#editalText')?.value||'';if(!text.trim()){toast('Cole o conteúdo programático do edital.','warning');return;}const r=await bridge.call('add_edital_version',id,{label:$('#editalVersionLabel')?.value||'',published_at:$('#editalPublishedAt')?.value||'',effective_from:$('#editalPublishedAt')?.value||'',source_url:$('#editalSourceUrl')?.value||'',content_text:text});if(!r.ok){toast(r.error||'Falha ao registrar versão.','error');return;}renderExamProjectDashboard(r.dashboard||{});renderTodayPanel(r.today||{});toast('Nova versão do edital registrada; cobertura e diff recalculados.','success');}
async function relinkExamProject(){const id=state.examProjectId||'';if(!id){toast('Selecione um projeto.','warning');return;}const r=await bridge.call('relink_exam_project',id);if(!r.ok){toast(r.error||'Falha no remapeamento.','error');return;}renderExamProjectDashboard(r.dashboard||{});toast(`${formatNumber(r.result?.linked||0)} vínculo(s) automático(s) recalculado(s).`,'success');}
async function scanProjectCurrency(){const r=await bridge.call('scan_question_currency',state.examProjectId||'');if(!r.ok){toast(r.error||'Falha na verificação temporal.','error');return;}toast(`${formatNumber(r.result?.flagged||0)} questão(ões) sinalizada(s) para revisão temporal.`,'success');await loadExamProjectPage(state.examProjectId||'');}
async function changeQuestionCurrency(uid,status){const r=await bridge.call('set_question_currency',uid,status,'Decisão humana na tela Projeto e edital',state.examProjectDashboard?.project?.exam_date||'');if(!r.ok){toast(r.error||'Falha ao atualizar estado.','error');return;}toast('Estado temporal atualizado.','success');await loadExamProjectPage(state.examProjectId||'');}

function bindEvents() {
  $('#mainNav').addEventListener('click', (event) => {
    const button = event.target.closest('[data-route]');
    if (button) navigate(button.dataset.route);
  });
  $('#sidebarToggle').addEventListener('click', () => setSidebarCollapsed(!state.sidebarCollapsed));
  $('#themeToggle').addEventListener('click', () => applyTheme(state.theme === 'dark' ? 'light' : 'dark'));
  $('#fullscreenToggle').addEventListener('click', toggleFullscreen);
  $('#closeQuestFlow')?.addEventListener('click', requestSafeClose);
  document.addEventListener('fullscreenchange', updateFullscreenButton);
  $('#zoomOut').addEventListener('click', () => applyZoom(state.zoom - 0.05));
  $('#zoomIn').addEventListener('click', () => applyZoom(state.zoom + 0.05));
  $('#classicUiButton').addEventListener('click', async () => {
    const result = await bridge.call('launch_classic');
    if (!result.ok) toast(result.error || 'Não foi possível abrir a interface clássica.', 'error');
  });
  $('#globalSearch').addEventListener('keydown', async (event) => {
    if (event.key === 'Enter') {
      await navigate('review');
      $('#questionSearch').value = event.currentTarget.value;
      await loadQuestions();
    }
  });
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('#globalSearch').focus(); }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && state.route === 'review') { event.preventDefault(); saveCurrentQuestion(false); }
  });

  $('#refreshDashboard').addEventListener('click', () => Promise.all([loadDashboard({ force: true }), loadTodayDashboard()]));
  $('#refreshToday')?.addEventListener('click', loadTodayDashboard);
  $('#examProjectSelect')?.addEventListener('change', async (event)=>{const id=event.target.value||''; if(!id){state.examProjectId=null;state.examProjectDashboard={project:null,projects:state.examProjectDashboard?.projects||[]};fillExamProjectForm({});return;} await loadExamProjectPage(id);});
  $('#saveExamProject')?.addEventListener('click', saveExamProject);
  $('#activateExamProject')?.addEventListener('click', activateExamProject);
  $('#previewEditalParsing')?.addEventListener('click', previewEditalParsing);
  $('#saveEditalVersion')?.addEventListener('click', saveEditalVersion);
  $('#relinkExamProject')?.addEventListener('click', relinkExamProject);
  $('#scanProjectCurrency')?.addEventListener('click', scanProjectCurrency);
  $('#refreshVisualAnalytics')?.addEventListener('click', () => loadDashboard({ force: true }));
  $('#visualAnalyticsPanel')?.addEventListener('click', handleLearnerModelAction);
  $('#rebuildLearnerModel')?.addEventListener('click', rebuildLearnerModel);
  $('#refreshCuration')?.addEventListener('click', refreshBankIntelligenceDerived);
  $('#closeCurationQueue')?.addEventListener('click', () => { const panel=$('#curationQueuePanel'); if(panel) panel.hidden=true; });
  $('#refreshStage5')?.addEventListener('click', () => loadStage5Page(state.stage5SelectedUid || ''));
  $('#stage5SeedQuestion')?.addEventListener('change', async (event) => { state.stage5SelectedUid = event.target.value || null; await loadStage5Page(state.stage5SelectedUid || ''); });
  $('#generateControlledQuestion')?.addEventListener('click', generateStage5Draft);
  $('#saveLegislationVersion')?.addEventListener('click', saveLegislationVersion);
  $('#resolveLegislationVersion')?.addEventListener('click', resolveLegislationVersion);
  $('#runGoldRegression')?.addEventListener('click', runGoldRegression);
  $('#refreshTutor')?.addEventListener('click', () => loadTutorPage(state.tutorSelectedUid || ''));
  $('#refreshRecommendations')?.addEventListener('click', loadRecommendationPage);
  $('#recommendationMode')?.addEventListener('change', loadRecommendationPage);
  $('#startAdaptiveSimulation')?.addEventListener('click', startAdaptiveSimulation);
  $('#resumeAdaptiveSimulation')?.addEventListener('click', (event) => resumeAdaptiveSimulation(event.currentTarget.dataset.sessionId || ''));
  $('#abandonAdaptiveSimulation')?.addEventListener('click', abandonAdaptiveSimulation);
  $('#generateTutorAnswer')?.addEventListener('click', generateTutorAnswer);
  $$('[data-tutor-quick-prompt]').forEach((button) => button.addEventListener('click', () => {
    const field = $('#tutorUserPrompt');
    if (!field || button.disabled) return;
    field.value = button.dataset.tutorQuickPrompt || '';
    field.focus();
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }));
  $('#refreshTutorDiagnosis')?.addEventListener('click', refreshTutorDiagnosis);
  $('#openAiSettings')?.addEventListener('click', () => navigate('settings'));
  $('#saveAiProviderSettings')?.addEventListener('click', saveAiProviderSettings);
  $('#testAiProvider')?.addEventListener('click', testAiProvider);
  $('#saveAiPrivacySettings')?.addEventListener('click', saveAiPrivacySettings);
  $('#aiPrivacyMode')?.addEventListener('change', async ()=>{const mode=$('#aiPrivacyMode')?.value||'balanced'; if(mode==='private') renderAiPrivacySettings({mode:'private'}); else if(mode==='balanced') renderAiPrivacySettings({mode:'balanced',share_taxonomy:true,share_statement:true,share_alternatives:true,share_official_answer:true,share_rag:true,share_binary_media:false,share_user_prompt:true}); else {const r=await bridge.call('get_ai_privacy_settings').catch(()=>null);renderAiPrivacySettings({...((r||{}).settings||{}),mode:'custom'});}});
  $('#tutorOnlineAi')?.addEventListener('change', loadTutorPrivacyPreview);
  $$('input[name="tutorMode"]').forEach(el=>el.addEventListener('change',()=>{updateTutorModeUi();loadTutorPrivacyPreview();}));
  $('#tutorUserPrompt')?.addEventListener('change', loadTutorPrivacyPreview);
  $('#tutorRepresentation')?.addEventListener('change', ()=>{state.tutorScaffoldSessionId=null;state.tutorScaffoldLevel=null;});
  $('#saveUpdateMonitorSettings')?.addEventListener('click', saveUpdateMonitorSettings);
  $('#runUpdateMonitorNow')?.addEventListener('click', () => runUpdateMonitorNow({ scheduled: false }));
  $('#showUpdateMonitorHistory')?.addEventListener('click', showUpdateMonitorHistory);
  $('#saveRuntimeWatchdogSettings')?.addEventListener('click', saveRuntimeWatchdogSettings);
  $('#runRuntimeWatchdogCheck')?.addEventListener('click', runRuntimeWatchdogCheck);
  $('#refreshRuntimeWatchdog')?.addEventListener('click', loadRuntimeWatchdogStatus);
  $('#runtimeWatchdogSummary')?.addEventListener('click', (event)=>{const button=event.target.closest('[data-runtime-restart]'); if(button) restartRuntimeService(button.dataset.runtimeRestart||'');});
  $('#rebuildSemanticIndex')?.addEventListener('click', rebuildSemanticIndex);
  $('#refreshDatabaseHealth')?.addEventListener('click', () => loadDatabaseHealth({ quiet: false }));
  $('#chooseImportFiles').addEventListener('click', chooseImportFiles);
  $('#dropZone').addEventListener('click', (event) => { if (event.target.id !== 'chooseImportFiles') chooseImportFiles(); });
  $('#dropZone').addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') chooseImportFiles(); });
  $('#startImport').addEventListener('click', startImport);

  $('#questionSearch').addEventListener('input', debounce(loadQuestions, 300));
  $('#questionStatus').addEventListener('change', loadQuestions);
  $('#refreshBankFix')?.addEventListener('click', loadBankFix);
  $('#bankFixSearch')?.addEventListener('input', debounce(loadBankFix, 280));
  $('#bankFixStatus')?.addEventListener('change', loadBankFix);
  $('#bankFixMatter')?.addEventListener('change', async () => {
    if ($('#bankFixLesson')) $('#bankFixLesson').value = '';
    await loadBankFix();
  });
  $('#bankFixLesson')?.addEventListener('change', loadBankFix);
  $('#clearBankFixFilters')?.addEventListener('click', async () => {
    if ($('#bankFixSearch')) $('#bankFixSearch').value = '';
    if ($('#bankFixMatter')) $('#bankFixMatter').value = '';
    if ($('#bankFixLesson')) $('#bankFixLesson').value = '';
    if ($('#bankFixStatus')) $('#bankFixStatus').value = 'todos';
    await loadBankFix();
  });
  $('#createQuestion').addEventListener('click', createQuestion);
  $('#deleteQuestion').addEventListener('click', deleteQuestion);
  $('#annulQuestion').addEventListener('click', annulQuestion);
  $('#rereadQuestion').addEventListener('click', rereadQuestion);
  $('#reviewPreview').addEventListener('click', showTelegramPreview);
  $('#openGroundingBenchmark')?.addEventListener('click', openGroundingBenchmark);
  $('#openRetrievalCalibration')?.addEventListener('click', openRetrievalCalibration);
  $('#openRetrievalObservability')?.addEventListener('click', openRetrievalObservability);
  $('#openRetrievalQualityGate')?.addEventListener('click', openRetrievalQualityGate);
  $('#refreshQuestionIntelligence')?.addEventListener('click', () => loadQuestionIntelligence(state.currentUid, { scanDuplicates: true }));
  $('#showAiBrief')?.addEventListener('click', showAiCommentaryBrief);
  $('#showKnowledgeGraph')?.addEventListener('click', showKnowledgeGraph);
  $('#showHybridEvidence')?.addEventListener('click', showHybridEvidence);
  $('#openTutorForQuestion')?.addEventListener('click', openCurrentQuestionInTutor);
  $('#assistCommentaryAi')?.addEventListener('click', assistCommentaryWithAi);
  $('#researchGoogleCommentary')?.addEventListener('click', researchCommentaryOnGoogle);
  $('#toggleQuestionHeader')?.addEventListener('click', () => applyQuestionHeaderCollapsed(!state.questionHeaderCollapsed));
  $('#collapseQuestionList').addEventListener('click', () => {
    state.questionListCollapsed = !state.questionListCollapsed;
    $('#reviewShell').classList.toggle('is-list-collapsed', state.questionListCollapsed);
    $('#collapseQuestionList').textContent = state.questionListCollapsed ? '⇥' : '⇤';
  });
  $('#questionForm').addEventListener('submit', (event) => { event.preventDefault(); saveCurrentQuestion(false); });
  $('#approveQuestion').addEventListener('click', () => saveCurrentQuestion(true));
  $('#discardChanges').addEventListener('click', () => state.originalQuestion && renderQuestionEditor(structuredClone(state.originalQuestion), state.currentImage));
  $('#addAlternative').addEventListener('click', addAlternative);
  $('#attachImage').addEventListener('click', attachImage);
  $('#removeImage').addEventListener('click', removeImage);
  $('#statementInput').addEventListener('input', (event) => { autoResize(event.target); markDirty(); });
  $('#explanationInput').addEventListener('input', (event) => { autoResize(event.target); markDirty(); });

  $('#refreshFlow').addEventListener('click', loadFlow);
  $('#sendCycleNow').addEventListener('click', (event) => flowAction('send_now', event.currentTarget));
  $('#flowStart').addEventListener('click', (event) => flowAction('start', event.currentTarget));
  $('#flowPause').addEventListener('click', (event) => flowAction('pause', event.currentTarget));
  $('#flowResume').addEventListener('click', (event) => flowAction('resume', event.currentTarget));
  $('#flowStop').addEventListener('click', (event) => flowAction('stop', event.currentTarget));
  $('#telegramQuestionsPause')?.addEventListener('click', (event) => flowAction('pause_questions', event.currentTarget));
  $('#telegramQuestionsResume')?.addEventListener('click', (event) => flowAction('resume_questions', event.currentTarget));
  $('#retryFailures').addEventListener('click', (event) => flowAction('retry_all', event.currentTarget));
  $('#optimizeFsrs')?.addEventListener('click', (event) => flowAction('optimize_fsrs', event.currentTarget));
  $('#saveFlowSettings').addEventListener('click', saveFlowSettings);
  $('#saveTelegramSettings').addEventListener('click', saveTelegramSettings);
  $('#testTelegramConnection').addEventListener('click', testTelegramConnection);

  $('#refreshCorrections').addEventListener('click', loadCorrections);
  $('#refreshCoverage').addEventListener('click', () => loadCoverage({ sync: false }));
  $('#syncCoverage')?.addEventListener('click', () => loadCoverage({ sync: true }));
  $('#addTrailGuide')?.addEventListener('click', addTrailGuidePdfs);
  $('#coverageSearch').addEventListener('input', debounce(renderCoverage, 180));
  $('#coverageStatus').addEventListener('change', renderCoverage);
  $('#saveSettings').addEventListener('click', saveSettings);
  $('#testCourseCatalog')?.addEventListener('click', () => runCourseCatalogPreflight({ apply: false }));
  $('#updateCourseCatalog')?.addEventListener('click', () => runCourseCatalogPreflight({ apply: true }));
  $('#resetStudyCycle')?.addEventListener('click', resetStudyCycle);
  $('#networkMode')?.addEventListener('change', updateNetworkFieldVisibility);
  $('#networkProxyAuth')?.addEventListener('change', updateNetworkFieldVisibility);
  $('#detectNetworkProxy')?.addEventListener('click', detectNetworkProxy);
  $('#testNetworkConnection')?.addEventListener('click', testNetworkConnection);
  $('#saveNetworkSettings')?.addEventListener('click', saveNetworkSettings);
  $('#saveCloudSyncSettings')?.addEventListener('click', saveCloudSyncSettings);
  $('#testCloudSync')?.addEventListener('click', testCloudSync);
  $('#safeActivateCloudSync')?.addEventListener('click', openCloudSafeActivation);
  $('#syncCloudNow')?.addEventListener('click', syncCloudNow);
  $('#saveMobileCloudBridgeSettings')?.addEventListener('click', saveMobileCloudBridgeSettings);
  $('#testMobileCloudBridge')?.addEventListener('click', testMobileCloudBridge);
  $('#syncMobileCloudBridgeNow')?.addEventListener('click', syncMobileCloudBridgeNow);
  $('#createMobilePairing')?.addEventListener('click', createMobilePairing);
  $('#createMobilePairingTop')?.addEventListener('click', createMobilePairing);
  $('#saveMobileLanSettings')?.addEventListener('click', saveMobileLanSettings);
  $('#refreshMobilePage')?.addEventListener('click', async () => { await Promise.all([loadCloudSyncSettings(), loadMobileFoundation(), loadMobileCloudBridgeSettings()]); toast('Status do Mobile atualizado.', 'success'); });
  $('#refreshMobileFoundation')?.addEventListener('click', loadMobileFoundation);
  $('#copyMobilePairing')?.addEventListener('click', copyMobilePairing);
  $$('[data-export]').forEach((button) => button.addEventListener('click', () => exportData(button.dataset.export)));
  $('#importDatabase').addEventListener('click', async () => {
    const result = await bridge.call('import_database');
    if (result.ok) { toast('Banco importado.', 'success'); await refreshBootstrap(); }
    else if (!result.cancelled) toast(result.error || 'Falha na importação.', 'error');
  });
  setupRichTextTools();
  const systemTheme = window.matchMedia?.('(prefers-color-scheme: dark)');
  systemTheme?.addEventListener?.('change', () => {
    if (state.theme === 'system') updateThemeIdentity();
  });
  window.addEventListener('beforeunload', (event) => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
}

async function init() {
  applyTheme(state.theme);
  applyZoom(state.zoom);
  applyQuestionHeaderCollapsed(state.questionHeaderCollapsed, false);
  const storedSidebar = localStorage.getItem('qf-sidebar-collapsed');
  setSidebarCollapsed(storedSidebar === '1' || (storedSidebar == null && window.innerWidth < 1180), false);
  setSystemStatus('Preparando interface…', 'loading');
  virtualList = new VirtualQuestionList($('#questionViewport'), $('#questionSpacer'), $('#questionRows'));
  virtualList.onSelect = selectQuestion;
  renderQuestionTableHeader();
  updateFullscreenButton();
  bindEvents();
  installDomRuntime();
  // Let WebView paint the complete shell before crossing the Python bridge.
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  try {
    await bridge.init();
    const shell = await bridge.call('bootstrap_shell');
    applyBootstrap(shell);
    bridge.startHeartbeat();
    const route = location.hash.slice(1);
    // Navigation renders skeletons immediately and all expensive dashboard work
    // is executed by a Python worker polled with short, non-blocking calls.
    await navigate(routes[route] ? route : 'dashboard');
    const healthLoop = async () => {
      if (state.route === 'dashboard' && state.startupReady && !document.hidden) {
        await loadDatabaseHealth({ quiet: true }).catch(() => {});
      }
      window.setTimeout(healthLoop, document.hidden ? 180000 : 60000);
    };
    window.setTimeout(healthLoop, 60000);
    loadAiProviderSettings().catch(() => {});
    loadAiPrivacySettings().catch(() => {});
    loadAiTelemetry().catch(() => {});
    loadUpdateMonitorStatus().catch(() => {});
    startUpdateMonitorWatch();
    // Complete taxonomy/configuration loading without delaying the first paint.
    refreshBootstrap({ background: true }).catch((error) => {
      console.warn('Atualização de metadados adiada:', error);
    });
    startStudyGuideWatch();
    pollFlowEvents();
  } catch (error) {
    setSystemStatus('Falha na inicialização', 'error');
    toast(error.message, 'error', 0);
  }
}

document.addEventListener('DOMContentLoaded', init);
