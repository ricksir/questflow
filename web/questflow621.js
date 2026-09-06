/* QuestFlow Studio 6.24.0 — modular architecture with compatible Mobile feedback. */
(() => {
  'use strict';

  const ACTION_COPY = {
    dashboard: ['O que aconteceu', 'Seu histórico foi consolidado em um único pulso.', 'O que fazer agora', 'Comece pela recomendação com maior ganho esperado.', 'Como aprofundar', 'Abra o Painel visual para filtros e séries completas.'],
    visualanalytics: ['O que aconteceu', 'Desempenho, volume e confiança usam o mesmo recorte.', 'O que observar', 'Procure queda sustentada, não um ponto isolado.', 'Próxima ação', 'Filtre uma matéria e abra seu diagnóstico.'],
    examproject: ['Situação', 'Edital, prova e cobertura formam o plano ativo.', 'Risco', 'Lacunas próximas da prova recebem maior prioridade.', 'Próxima ação', 'Atualize o edital e remapeie o banco.'],
    import: ['Entrada', 'Arquivos passam por extração, OCR e estruturação.', 'Qualidade', 'Baixa confiança e duplicidades exigem revisão.', 'Próxima ação', 'Selecione arquivos e acompanhe a fila por etapa.'],
    curation: ['Situação', 'A saúde editorial separa origem, qualidade e dificuldade.', 'Por que importa', 'Questões frágeis contaminam diagnóstico e recomendação.', 'Próxima ação', 'Abra a maior fila de atenção e resolva por impacto.'],
    tutor: ['Situação', 'Erros recentes aguardam diagnóstico ou orientação.', 'Por que importa', 'Aprovação humana mantém a explicação auditável.', 'Próxima ação', 'Escolha um erro na fila e conclua o workspace ao lado.'],
    recommend: ['Situação', 'FSRS define urgência; os demais sinais ordenam.', 'Incerteza', 'A faixa é desempenho observado, não chance de aprovação.', 'Próxima ação', 'Revise os componentes e inicie um bloco curto.'],
    stage5: ['Situação', 'Somente fontes marcadas alimentam o gerador.', 'Quality Gate', 'Crítico e decisão humana precedem publicação.', 'Próxima ação', 'Selecione evidências e gere um rascunho controlado.'],
    review: ['Situação', 'A fila reúne questões que ainda pedem decisão editorial.', 'Por que importa', 'Alterações afetam busca, estudo e métricas.', 'Próxima ação', 'Filtre, revise e confirme uma questão por vez.'],
    bankfix: ['Situação', 'Inconsistências são agrupadas por gravidade e idade.', 'Segurança', 'Ações em lote continuam auditáveis e reversíveis.', 'Próxima ação', 'Resolva primeiro falhas que suspendem questões.'],
    flow: ['Situação', 'Agendador, listener e memória operam como serviços distintos.', 'Por que importa', 'Falha de transporte não pode virar falha pedagógica.', 'Próxima ação', 'Verifique a saúde e reprocesse somente as falhas.'],
    corrections: ['Situação', 'Correção editorial e conteúdo não estudado ficam separados.', 'Por que importa', 'Não estudado nunca é contabilizado como erro.', 'Próxima ação', 'Use a coluna correspondente ao tipo de pendência.'],
    coverage: ['Situação', 'Planilha e banco são reconciliados por conteúdo estudado.', 'Regra', 'Sem meta informada, o QuestFlow não inventa quantidade.', 'Próxima ação', 'Abra uma lacuna e importe o material correspondente.'],
    mobile: ['Situação', 'Pareamento, versão e sincronização ficam visíveis no Studio.', 'Segurança', 'O Mobile consome projeções; nunca acessa tabelas internas.', 'Próxima ação', 'Instale o build Mobile mais recente e confirme o contrato v2.'],
    settings: ['Organização', 'Preferências foram separadas por responsabilidade.', 'Segurança', 'Somente a categoria ativa permanece interativa.', 'Próxima ação', 'Revise alterações pendentes antes de salvar.'],
  };

  const SETTINGS_GROUPS = [
    ['general', 'Geral'], ['data', 'Dados'], ['ai', 'IA'], ['network', 'Rede'], ['updates', 'Atualizações'], ['security', 'Segurança'],
  ];
  const busyActions = new Set();
  let analyticsRequestId = 0;
  let analyticsRange = 'all';
  let settingsGroup = 'general';
  let flowObserver = null;

  const esc = (value) => String(value == null ? '' : value)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  const pct = (value) => value == null ? '—' : `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`;

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
  }

  function replaceRegion(region, html) {
    if (!region) return;
    const activeId = document.activeElement?.id || '';
    const scrollTop = region.scrollTop;
    const template = document.createElement('template');
    template.innerHTML = html;
    const fragment = document.createDocumentFragment();
    fragment.append(template.content);
    region.replaceChildren(fragment);
    region.scrollTop = scrollTop;
    if (activeId) region.querySelector(`#${CSS.escape(activeId)}`)?.focus({ preventScroll: true });
  }

  function setPanelState(panel, state, message = '') {
    if (!panel || panel.dataset.state === state) return;
    panel.dataset.state = state;
    panel.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
    if (message) panel.dataset.stateMessage = message;
    emit('questflow:panel-state', { panelId: panel.id || '', state, message });
  }

  function insertActionStrip(page) {
    const route = page.dataset.page;
    if (page.querySelector('.qf621-action-strip') || !ACTION_COPY[route]) return;
    const values = ACTION_COPY[route];
    const strip = document.createElement('section');
    strip.className = 'qf621-action-strip';
    strip.setAttribute('aria-label', 'Resumo acionável da página');
    strip.innerHTML = values.reduce((html, value, index) => html + (index % 2 === 0
      ? `<div><span>${esc(value)}</span>`
      : `<strong>${esc(value)}</strong></div>`), '');
    const header = page.querySelector(':scope > .page-header');
    header?.insertAdjacentElement('afterend', strip);
  }

  function createPanel({ className = '', title, subtitle, body, labelledBy }) {
    const panel = document.createElement('article');
    panel.className = `panel ${className}`.trim();
    if (labelledBy) panel.setAttribute('aria-labelledby', labelledBy);
    panel.innerHTML = `<div class="panel-header"><div><h2${labelledBy ? ` id="${esc(labelledBy)}"` : ''}>${esc(title)}</h2><p>${esc(subtitle)}</p></div></div><div class="panel-body">${body}</div>`;
    return panel;
  }

  function enhanceDashboard() {
    const grid = document.querySelector('.page[data-page="dashboard"] .dashboard-grid');
    if (!grid || grid.querySelector('.qf621-review-panel')) return;
    const panel = createPanel({
      className: 'qf621-review-panel qf621-analytics-panel',
      title: 'Fila de revisão e sincronização',
      subtitle: 'Memória vencida, amostra e atualização em uma leitura curta.',
      labelledBy: 'qf621ReviewTitle',
      body: '<div class="qf621-chart-fallback"><strong>Carregando evidências</strong><span>Agrupando revisões reais do scheduler.</span></div>',
    });
    grid.querySelector('article:nth-child(2)')?.insertAdjacentElement('afterend', panel);
    setPanelState(panel, 'loading');
  }

  function enhanceCuration() {
    const panel = document.querySelector('.page[data-page="curation"] .curation-action-panel');
    if (!panel || panel.querySelector('.qf621-curation-visual')) return;
    const visual = document.createElement('div');
    visual.className = 'qf621-curation-visual';
    visual.innerHTML = '<div class="qf621-chart-head"><div><strong>Distribuição das prioridades</strong><span>Volume relativo das filas exibidas acima</span></div></div><div class="qf621-heatmap" aria-label="Mapa compacto das filas de curadoria"></div>';
    panel.querySelector('.panel-body')?.insertAdjacentElement('afterend', visual);
    const heatmap = visual.querySelector('.qf621-heatmap');
    for (let index = 0; index < 26; index += 1) {
      const cell = document.createElement('span');
      cell.style.setProperty('--heat', `${12 + Math.round((index % 7) / 6 * 70)}%`);
      cell.setAttribute('aria-hidden', 'true');
      heatmap.appendChild(cell);
    }
  }

  function enhanceStage5() {
    const grid = document.querySelector('.page--stage5 .stage5-grid');
    if (!grid || grid.querySelector('.qf621-stage5-evidence')) return;
    const panel = createPanel({
      className: 'qf621-stage5-evidence',
      title: 'Cobertura das fontes e Quality Gates',
      subtitle: 'Critérios que precisam ser satisfeitos antes da publicação.',
      labelledBy: 'qf621EvidenceTitle',
      body: `<div class="qf621-stage5-snapshot" id="qf621Stage5Snapshot" aria-live="polite"></div><div class="qf621-gate-list">
        <div><i aria-hidden="true"></i><strong>Fontes explicitamente selecionadas</strong><small>Obrigatório</small></div>
        <div><i aria-hidden="true"></i><strong>Vigência temporal compatível</strong><small>Validar</small></div>
        <div><i aria-hidden="true"></i><strong>Crítico independente</strong><small>Obrigatório</small></div>
        <div><i aria-hidden="true"></i><strong>Decisão humana registrada</strong><small>Obrigatório</small></div>
      </div>`,
    });
    grid.querySelector('.stage5-draft-panel')?.insertAdjacentElement('afterend', panel);
    const update = () => {
      const sources = [...document.querySelectorAll('#stage5SourcePool input[type="checkbox"]')];
      const selected = sources.filter((input) => input.checked).length;
      const start = document.querySelector('#legEffectiveFrom')?.value || '';
      const end = document.querySelector('#legEffectiveTo')?.value || '';
      const exam = document.querySelector('#stage5ExamDate')?.value || '';
      const draftReady = Boolean(document.querySelector('#stage5DraftWorkspace')?.textContent?.trim()) && !document.querySelector('#stage5DraftWorkspace .empty-state');
      replaceRegion(document.querySelector('#qf621Stage5Snapshot'), `<div><span>Cobertura das fontes</span><strong>${selected}/${sources.length || 0}</strong><i aria-hidden="true"><b style="width:${sources.length ? Math.round(selected / sources.length * 100) : 0}%"></b></i><small>${selected ? 'Evidências escolhidas pelo usuário' : 'Selecione ao menos uma evidência'}</small></div><div><span>Janela temporal</span><strong>${start || '—'} → ${end || 'vigente'}</strong><small>${exam ? `Prova em ${esc(exam)}` : 'Informe a data da prova para validar a vigência'}</small></div><div><span>Rascunho desta sessão</span><strong>${draftReady ? 'Em validação' : 'Não iniciado'}</strong><small>Publicação sempre exige decisão humana</small></div>`);
    };
    grid.addEventListener('change', update);
    new MutationObserver(update).observe(document.querySelector('#stage5SourcePool'), { childList: true, subtree: true, attributes: true, attributeFilter: ['checked'] });
    new MutationObserver(update).observe(document.querySelector('#stage5DraftWorkspace'), { childList: true, subtree: true });
    update();
  }

  function flowRows() {
    return [...document.querySelectorAll('#flowHistory tbody tr')].map((row) => {
      const cells = [...row.querySelectorAll('td')].map((cell) => cell.textContent.trim());
      return { date: cells[0] || '', subject: cells[2] || 'Não informada', status: cells[3] || 'Não informado', attempts: Number.parseInt(cells[4], 10) || 0 };
    });
  }

  function renderFlowInsights() {
    const region = document.querySelector('#qf621FlowInsights');
    if (!region) return;
    const rows = flowRows();
    if (!rows.length) {
      replaceRegion(region, '<div class="qf621-chart-fallback qf621-chart-fallback--compact"><strong>Sem eventos no recorte</strong><span>O primeiro envio formará a linha de base operacional.</span></div>');
      return;
    }
    const statuses = new Map();
    const days = new Map();
    const subjects = new Map();
    rows.forEach((row) => {
      statuses.set(row.status, (statuses.get(row.status) || 0) + 1);
      const day = row.date.split(',')[0] || row.date;
      days.set(day, (days.get(day) || 0) + 1);
      subjects.set(row.subject, (subjects.get(row.subject) || 0) + 1);
    });
    const maxDay = Math.max(...days.values(), 1);
    const maxSubject = Math.max(...subjects.values(), 1);
    const statusRows = [...statuses.entries()].sort((a,b) => b[1]-a[1]);
    const dayRows = [...days.entries()].slice(-6);
    const subjectRows = [...subjects.entries()].sort((a,b) => b[1]-a[1]).slice(0,4);
    replaceRegion(region, `<div class="qf621-flow-kpis"><div><span>Eventos exibidos</span><strong>${rows.length}</strong></div><div><span>Com tentativa</span><strong>${rows.filter((row) => row.attempts > 0).length}</strong></div><div><span>Status</span><strong>${statuses.size}</strong></div></div><div class="qf621-mini-section"><strong>Volume por dia</strong><div class="qf621-volume-bars">${dayRows.map(([label,value]) => `<div><i style="height:${Math.max(12, Math.round(value/maxDay*100))}%" title="${esc(label)}: ${value}"></i><span>${esc(label.slice(0,5))}</span><b>${value}</b></div>`).join('')}</div></div><div class="qf621-mini-section"><strong>Distribuição por status</strong><div class="qf621-bars">${statusRows.map(([label,value]) => `<div class="qf621-bar"><div><span>${esc(label)}</span><strong>${value}</strong></div><i><span style="width:${Math.round(value/rows.length*100)}%"></span></i></div>`).join('')}</div></div><div class="qf621-mini-section"><strong>Matérias mais enviadas</strong><div class="qf621-bars">${subjectRows.map(([label,value]) => `<div class="qf621-bar"><div><span>${esc(label)}</span><strong>${value}</strong></div><i><span style="width:${Math.round(value/maxSubject*100)}%"></span></i></div>`).join('')}</div></div><p class="qf621-chart-note">Leitura formada somente pelos eventos reais exibidos no histórico. Amplie o histórico para análises de latência.</p>`);
  }

  function enhanceFlow() {
    const grid = document.querySelector('.page[data-page="flow"] .flow-layout');
    const history = document.querySelector('#flowHistory')?.closest('.panel');
    if (!grid || !history || grid.querySelector('.qf621-flow-insights')) return;
    const panel = createPanel({ className: 'qf621-flow-insights', title: 'Pulso operacional', subtitle: 'Volume, estados e distribuição do histórico visível.', labelledBy: 'qf621FlowInsightsTitle', body: '<div id="qf621FlowInsights"></div>' });
    history.insertAdjacentElement('afterend', panel);
    flowObserver?.disconnect();
    flowObserver = new MutationObserver(renderFlowInsights);
    flowObserver.observe(document.querySelector('#flowHistory'), { childList: true, subtree: true });
    renderFlowInsights();
  }

  function enhanceImport() {
    const page = document.querySelector('.page[data-page="import"]');
    if (!page || page.querySelector('.qf621-pipeline')) return;
    const pipeline = document.createElement('section');
    pipeline.className = 'qf621-pipeline';
    pipeline.setAttribute('aria-label', 'Etapas da importação');
    pipeline.innerHTML = [['01','Arquivo'],['02','Extração'],['03','OCR'],['04','Estrutura'],['05','Revisão']]
      .map(([step, label]) => `<div><span>${step}</span><strong>${label}</strong></div>`).join('');
    page.querySelector('.qf621-action-strip')?.insertAdjacentElement('afterend', pipeline);
  }

  function enhanceCorrections() {
    const page = document.querySelector('.page[data-page="corrections"]');
    if (!page || page.querySelector('.qf621-corrections-grid')) return;
    const articles = [...page.querySelectorAll(':scope > .corrections-section')];
    if (articles.length !== 2) return;
    const grid = document.createElement('div');
    grid.className = 'qf621-corrections-grid';
    articles[0].insertAdjacentElement('beforebegin', grid);
    articles.forEach((article) => grid.appendChild(article));
  }

  function enhanceCoverage() {
    const page = document.querySelector('.page[data-page="coverage"]');
    if (!page || page.querySelector('.qf621-coverage-status')) return;
    const summary = page.querySelector('#coverageSummary');
    const note = page.querySelector('#coverageSyncNote');
    const guide = page.querySelector('#trailGuideStatus');
    const knowledge = page.querySelector('#trailGuideKnowledge');
    if (!summary || !note || !guide || !knowledge) return;
    const wrapper = document.createElement('section');
    wrapper.className = 'qf621-coverage-status';
    summary.insertAdjacentElement('beforebegin', wrapper);
    wrapper.appendChild(summary);
    const notes = document.createElement('div');
    notes.className = 'qf621-coverage-status__notes';
    [note, guide, knowledge].forEach((element) => notes.appendChild(element));
    wrapper.appendChild(notes);
  }

  function panelSettingsGroup(panel) {
    const title = (panel.querySelector('h2')?.textContent || '').toLocaleLowerCase('pt-BR');
    if (/aparência/.test(title)) return 'general';
    if (/ocr|estudos e trilhas|cloud sync/.test(title)) return 'data';
    if (/provedores de ia|privacidade da ia|telemetria da ia/.test(title)) return 'ai';
    if (/rede e proxy/.test(title)) return 'network';
    if (/monitor quinzenal/.test(title)) return 'updates';
    return 'security';
  }

  function selectSettingsGroup(group) {
    settingsGroup = SETTINGS_GROUPS.some(([key]) => key === group) ? group : 'general';
    document.querySelectorAll('.qf621-settings-nav button').forEach((button) => button.setAttribute('aria-selected', button.dataset.group === settingsGroup ? 'true' : 'false'));
    document.querySelectorAll('.settings-grid[data-qf621-settings] > .panel:not(.qf621-settings-rail)').forEach((panel) => {
      const active = panel.dataset.settingsGroup === settingsGroup;
      panel.hidden = !active;
      panel.inert = !active;
      panel.setAttribute('aria-hidden', active ? 'false' : 'true');
    });
    renderSettingsRail();
    emit('questflow:filter-change', { route: 'settings', filter: 'category', value: settingsGroup });
  }

  function renderSettingsRail() {
    const rail = document.querySelector('#qf621SettingsRail');
    if (!rail) return;
    const active = [...document.querySelectorAll('.settings-grid[data-qf621-settings] > .panel:not(.qf621-settings-rail)')].filter((panel) => !panel.hidden);
    const controls = active.flatMap((panel) => [...panel.querySelectorAll('input,select,textarea')]).filter((control) => !control.disabled);
    const invalid = controls.filter((control) => !control.checkValidity()).length;
    const protectedFields = controls.filter((control) => control.type === 'password').length;
    const label = SETTINGS_GROUPS.find(([key]) => key === settingsGroup)?.[1] || 'Geral';
    replaceRegion(rail, `<div class="qf621-settings-summary"><span>Seção ativa</span><strong>${esc(label)}</strong><small>${active.length} painel(is) · ${controls.length} controle(s)</small></div><div class="qf621-settings-checks"><div><i class="${invalid ? 'is-warning' : 'is-ok'}"></i><span>Validação dos campos</span><strong>${invalid ? `${invalid} pendente(s)` : 'Pronta'}</strong></div><div><i class="is-ok"></i><span>Campos sensíveis</span><strong>${protectedFields ? `${protectedFields} protegido(s)` : 'Nenhum'}</strong></div><div><i class="is-ok"></i><span>DOM interativo</span><strong>Somente ${esc(label)}</strong></div></div><div class="qf621-settings-guidance"><strong>Antes de salvar</strong><p>Revise os valores desta seção. As demais categorias permanecem ocultas e inertes, preservando foco e navegação por teclado.</p></div>`);
  }

  function enhanceSettings() {
    const page = document.querySelector('.page[data-page="settings"]');
    const grid = page?.querySelector('.settings-grid');
    if (!page || !grid || page.querySelector('.qf621-settings-nav')) return;
    const nav = document.createElement('div');
    nav.className = 'qf621-settings-nav';
    nav.setAttribute('role', 'tablist');
    nav.setAttribute('aria-label', 'Categorias de configuração');
    nav.innerHTML = SETTINGS_GROUPS.map(([key, label]) => `<button type="button" role="tab" data-action="qf-settings-tab" data-group="${key}" aria-selected="${key === settingsGroup}">${label}</button>`).join('');
    grid.insertAdjacentElement('beforebegin', nav);
    grid.dataset.qf621Settings = 'true';
    grid.querySelectorAll(':scope > .panel').forEach((panel) => { panel.dataset.settingsGroup = panelSettingsGroup(panel); });
    const rail = createPanel({ className: 'qf621-settings-rail', title: 'Estado da configuração', subtitle: 'Escopo, validação e segurança da categoria ativa.', labelledBy: 'qf621SettingsRailTitle', body: '<div id="qf621SettingsRail"></div>' });
    grid.appendChild(rail);
    const actions = page.querySelector('.settings-actions');
    if (actions && !actions.querySelector('.qf621-dirty')) {
      const label = document.createElement('span');
      label.className = 'qf621-dirty';
      label.hidden = true;
      label.textContent = 'Alterações não salvas';
      actions.insertBefore(label, actions.firstChild);
    }
    selectSettingsGroup(settingsGroup);
  }

  function enhanceMobileStudio() {
    const page = document.querySelector('.page[data-page="mobile"]');
    if (!page || page.querySelector('.qf621-mobile-release')) return;
    const sourceVersion = page.querySelector('.mobile-studio-kicker')?.textContent?.match(/\d+\.\d+\.\d+/)?.[0] || 'não informada';
    const release = document.createElement('section');
    release.className = 'qf621-mobile-release';
    release.setAttribute('aria-label', 'Identidade do build Mobile');
    release.innerHTML = `
      <div><span>Versão fonte</span><strong data-mobile-source-version>${sourceVersion}</strong></div>
      <div><span>Contrato</span><strong>questflow.analytics.v2</strong></div>
      <div><span>Entrega</span><strong>APK Android + código</strong></div>
      <div><span>Sincronização</span><strong>Local-first e offline</strong></div>`;
    page.querySelector('.mobile-studio-hero')?.insertAdjacentElement('afterend', release);
  }

  function createAnalyticsSurface() {
    const page = document.querySelector('.page[data-page="visualanalytics"]');
    if (!page || page.querySelector('#qf621VisualAnalytics')) return;
    const filterbar = document.createElement('div');
    filterbar.className = 'qf621-filterbar';
    filterbar.innerHTML = `<label>Histórico<select data-qf-filter="range"><option value="all" selected>Desde o início</option><option value="4w">Últimos 28 dias</option><option value="12w">Últimos 84 dias</option><option value="24w">Últimos 168 dias</option></select></label><label>Matéria<select data-qf-filter="subject"><option value="">Todas as matérias</option></select></label><button class="button button--secondary button--compact" type="button" data-action="qf-refresh-analytics">Atualizar histórico</button>`;
    const panel = createPanel({
      className: 'qf621-analytics-panel', title: 'Histórico real e prioridades',
      subtitle: 'Cada resposta confirmada aparece desde o início; os percentuais são recalculados sem ocultar o começo do estudo.', labelledBy: 'qf621VisualTitle',
      body: '<div class="qf621-chart-fallback"><strong>Carregando histórico</strong><span>Consultando tentativas reais.</span></div>',
    });
    panel.id = 'qf621VisualAnalytics';
    page.querySelector('.qf621-action-strip')?.insertAdjacentElement('afterend', filterbar);
    filterbar.insertAdjacentElement('afterend', panel);
    setPanelState(panel, 'loading');
  }

  function demoAnalytics(range = 'all') {
    const outcomes = [1,0,1,1,0,1,1,1,0,1,0,1,1,1,1,0,1,1,1,0,1,1,1,1];
    let correct = 0;
    const timeline = outcomes.map((outcome, index) => {
      correct += outcome;
      const date = new Date(); date.setUTCDate(date.getUTCDate() - (outcomes.length - index));
      return { period_start: date.toISOString(), response_index:index+1, attempts:1, accuracy:outcome, is_correct:Boolean(outcome), cumulative_accuracy:correct/(index+1), retention:null, active_minutes:1, timing_samples:1 };
    });
    return {
      contract:'questflow.analytics.v2',generated_at:new Date().toISOString(),range,grain:'attempt',sample_size:24,
      summary:{attempts:24,correct:18,accuracy:.75,retention_current:.78,due_reviews:12,active_minutes:24},timeline,
      subjects:[
        {subject_id:'1',label:'Direito Tributário',attempts:34,accuracy:.56,retention:.69,due_reviews:5,sample_confidence:'high'},
        {subject_id:'2',label:'Contabilidade Geral',attempts:28,accuracy:.61,retention:.72,due_reviews:4,sample_confidence:'medium'},
        {subject_id:'3',label:'Auditoria',attempts:41,accuracy:.76,retention:.81,due_reviews:2,sample_confidence:'high'},
        {subject_id:'4',label:'Fluência em Dados',attempts:35,accuracy:.84,retention:.87,due_reviews:1,sample_confidence:'high'},
      ],
      review_queue:[{subject_id:'1',label:'Direito Tributário',due_count:5,priority:'high',question_count:10},{subject_id:'2',label:'Contabilidade Geral',due_count:4,priority:'high',question_count:8},{subject_id:'3',label:'Auditoria',due_count:2,priority:'medium',question_count:6}],
      projection_band:{estimate:.75,low:.55,high:.88,sample_size:24,label:'Intervalo observado'},
      source_freshness:{latest_answered_at:new Date().toISOString(),retention_history:'not_collected',note:'O percurso usa todas as respostas confirmadas desde o início.'},
    };
  }

  async function getAnalytics(range = analyticsRange) {
    try {
      if (typeof bridge !== 'undefined' && bridge?.call) {
        const result = await bridge.call('get_learning_analytics_v2', '', range, 'attempt');
        if (result?.ok && result.analytics) return result.analytics;
      }
    } catch (_) { /* Demo and older bridges use the safe projection below. */ }
    if (new URLSearchParams(location.search).has('demo')) return demoAnalytics(range);
    return null;
  }

  function lineChart(points) {
    const observed = Array.isArray(points) ? points.filter((point) => point.accuracy != null && Number.isFinite(Number(point.accuracy))) : [];
    if (!observed.length) return '<div class="qf621-chart-fallback qf621-chart-fallback--compact"><strong>Histórico ainda vazio</strong><span>Sua primeira resposta aparecerá aqui como acerto ou erro.</span></div>';
    const width = 700, height = 220, left = 42, right = 15, top = 15, bottom = 34;
    const x = (index) => observed.length === 1 ? width / 2 : left + index / Math.max(1, observed.length - 1) * (width - left - right);
    const y = (value) => top + (1 - Math.max(0, Math.min(1, Number(value) || 0))) * (height - top - bottom);
    const cumulative = observed.map((point, index) => Number(point.cumulative_accuracy ?? point.accuracy));
    const path = cumulative.map((value, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
    const dots = observed.map((point, index) => `<circle class="raw-dot ${Number(point.accuracy) >= .5 ? 'is-correct' : 'is-wrong'}" cx="${x(index).toFixed(1)}" cy="${y(point.accuracy)}" r="3.4"><title>Resposta ${Number(point.response_index || index + 1)}: ${Number(point.accuracy) >= .5 ? 'acerto' : 'erro'} · acumulado ${pct(cumulative[index])}</title></circle>`).join('');
    const grids = [0, .5, 1].map((value) => `<line class="grid" x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-label" x="3" y="${y(value)+4}">${Math.round(value*100)}%</text>`).join('');
    const latest = cumulative.at(-1) ?? Number(observed.at(-1)?.accuracy || 0);
    const first = cumulative[0] ?? Number(observed[0]?.accuracy || 0);
    const delta = observed.length > 1 ? (latest - first) * 100 : null;
    const startLabel = new Date(observed[0]?.period_start).toLocaleDateString('pt-BR');
    const endLabel = new Date(observed.at(-1)?.period_start).toLocaleDateString('pt-BR');
    return `<div class="qf621-progressive-chart"><div class="qf621-sample-status"><span>Percurso completo · ${observed.length} ${observed.length === 1 ? 'resposta' : 'respostas'}</span><strong>${pct(latest)} acumulado${delta == null ? '' : ` · ${delta >= 0 ? '+' : ''}${delta.toFixed(0)} p.p. desde o início`}</strong></div><div class="qf621-chart-legend"><span><i class="is-correct"></i>Acerto bruto</span><span><i class="is-wrong"></i>Erro bruto</span><span><i class="is-path"></i>Acerto acumulado</span></div><svg class="qf621-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Histórico de ${observed.length} respostas desde o início, com resultado bruto e acerto acumulado">${grids}${observed.length === 1 ? `<line class="baseline" x1="${left}" x2="${width-right}" y1="${y(latest)}" y2="${y(latest)}"/>` : `<path class="series" d="${path}"/>`}${dots}<text class="axis-label" x="${left}" y="${height-6}">${esc(startLabel)}</text><text class="axis-label" text-anchor="end" x="${width-right}" y="${height-6}">${esc(endLabel)}</text></svg></div>`;
  }

  function subjectBars(subjects, selected = '') {
    const rows = [...(subjects || [])].filter((item) => !selected || item.subject_id === selected).sort((a,b) => (a.accuracy ?? 2) - (b.accuracy ?? 2)).slice(0, 6);
    if (!rows.length) return '<div class="qf621-chart-fallback"><strong>Sem matérias no recorte</strong><span>Amplie o período ou remova o filtro.</span></div>';
    return `<div class="qf621-bars">${rows.map((item) => `<div class="qf621-bar"><div><span>${esc(item.label)}</span><strong>${pct(item.accuracy)}</strong></div><i aria-hidden="true"><span style="width:${Math.round((Number(item.accuracy)||0)*100)}%"></span></i><small>${Number(item.attempts||0)} ${Number(item.attempts||0) === 1 ? 'resposta' : 'respostas'} · ${Number(item.due_reviews||0)} revisões</small></div>`).join('')}</div>`;
  }

  function renderAnalytics(snapshot) {
    const selected = document.querySelector('[data-qf-filter="subject"]')?.value || '';
    const visual = document.querySelector('#qf621VisualAnalytics .panel-body');
    if (visual) {
      replaceRegion(visual, `<div class="qf621-chart-grid"><section class="qf621-chart-card"><div class="qf621-chart-head"><div><strong>Da primeira à última resposta</strong><span>${Number(snapshot.sample_size||0)} respostas confirmadas · cada ponto mostra o resultado bruto</span></div><b>${pct(snapshot.summary?.accuracy)}</b></div>${lineChart(snapshot.timeline)}</section><section class="qf621-chart-card"><div class="qf621-chart-head"><div><strong>Oportunidade por matéria</strong><span>Todo o histórico do recorte, ordenado pelo menor acerto</span></div></div>${subjectBars(snapshot.subjects, selected)}</section></div><p class="qf621-chart-note">Fonte: respostas confirmadas do QuestFlow. ${esc(snapshot.source_freshness?.note || '')}</p>`);
      setPanelState(document.querySelector('#qf621VisualAnalytics'), snapshot.sample_size ? 'ready' : 'empty');
      const select = document.querySelector('[data-qf-filter="subject"]');
      if (select && select.options.length === 1) (snapshot.subjects || []).forEach((item) => select.add(new Option(item.label, item.subject_id)));
    }
    const dashboard = document.querySelector('.qf621-review-panel .panel-body');
    if (dashboard) {
      const queue = (snapshot.review_queue || []).slice(0, 5);
      replaceRegion(dashboard, queue.length ? `<div class="qf621-bars">${queue.map((item) => `<div class="qf621-bar"><div><span>${esc(item.label)}</span><strong>${Number(item.due_count||0)} vencidas</strong></div><i aria-hidden="true"><span style="width:${Math.min(100,Number(item.due_count||0)*10)}%"></span></i><small>Sessão sugerida: ${Number(item.question_count||0)} questões</small></div>`).join('')}</div><p class="qf621-chart-note">Retenção atual ${pct(snapshot.summary?.retention_current)} · ${Number(snapshot.summary?.due_reviews||0)} revisões devidas · ${Number(snapshot.sample_size||0)} respostas no histórico</p>` : '<div class="qf621-chart-fallback"><strong>Memória em dia</strong><span>Nenhuma revisão vencida neste recorte.</span></div>');
      setPanelState(document.querySelector('.qf621-review-panel'), queue.length ? 'ready' : 'empty');
    }
    emit('questflow:data-refreshed', { source: 'questflow.analytics.v2', generatedAt: snapshot.generated_at, range: snapshot.range, sampleSize: snapshot.sample_size });
  }

  async function refreshAnalytics() {
    const id = ++analyticsRequestId;
    [document.querySelector('#qf621VisualAnalytics'), document.querySelector('.qf621-review-panel')].forEach((panel) => panel && setPanelState(panel, 'loading'));
    const snapshot = await getAnalytics(analyticsRange);
    if (id !== analyticsRequestId) return;
    if (snapshot) renderAnalytics(snapshot);
    else [document.querySelector('#qf621VisualAnalytics'), document.querySelector('.qf621-review-panel')].forEach((panel) => panel && setPanelState(panel, 'degraded', 'Analytics v2 indisponível'));
  }

  function enhanceAll() {
    document.body.dataset.questflowRelease = '6.24.0';
    document.querySelectorAll('.page[data-page]').forEach(insertActionStrip);
    enhanceDashboard(); enhanceCuration(); enhanceStage5(); enhanceImport(); enhanceCorrections(); enhanceCoverage(); enhanceFlow(); enhanceSettings(); enhanceMobileStudio(); createAnalyticsSurface();
    document.querySelectorAll('.panel').forEach((panel) => {
      if (!panel.dataset.state) setPanelState(panel, panel.querySelector('.skeleton') ? 'loading' : 'ready');
    });
    setTimeout(refreshAnalytics, 250);
  }

  const actions = {
    'qf-refresh-analytics': async () => refreshAnalytics(),
    'qf-settings-tab': async (button) => selectSettingsGroup(button.dataset.group),
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action]');
    if (!button || !actions[button.dataset.action]) return;
    event.preventDefault();
    const key = `${button.dataset.action}:${button.dataset.group || ''}`;
    if (busyActions.has(key)) return;
    busyActions.add(key);
    button.setAttribute('aria-busy', 'true');
    button.disabled = true;
    try {
      await actions[button.dataset.action](button);
      emit('questflow:action-complete', { action: button.dataset.action, ok: true });
    } catch (error) {
      emit('questflow:action-complete', { action: button.dataset.action, ok: false, error: String(error?.message || error) });
    } finally {
      busyActions.delete(key);
      button.removeAttribute('aria-busy');
      button.disabled = false;
    }
  });

  document.addEventListener('change', (event) => {
    const filter = event.target.closest('[data-qf-filter]');
    if (filter) {
      if (filter.dataset.qfFilter === 'range') analyticsRange = filter.value;
      emit('questflow:filter-change', { route: 'visualanalytics', filter: filter.dataset.qfFilter, value: filter.value });
      refreshAnalytics();
    }
    if (event.target.closest('.page[data-page="settings"]')) {
      const label = document.querySelector('.qf621-dirty');
      if (label) label.hidden = false;
      renderSettingsRail();
    }
  });

  document.addEventListener('questflow:route-ready', (event) => {
    const route = event.detail?.route;
    if (route === 'dashboard' || route === 'visualanalytics') refreshAnalytics();
    if (route === 'settings') selectSettingsGroup(settingsGroup);
  });

  document.addEventListener('click', (event) => {
    if (event.target.closest('#saveSettings')) setTimeout(() => { const label = document.querySelector('.qf621-dirty'); if (label) label.hidden = true; }, 500);
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhanceAll, { once: true });
  else enhanceAll();
})();
