import { studioGet, studioPost } from '../api/studioClient.js';
import type { RouteModule } from './types.js';

type SourceSettings = {
  provider: 'local' | 'api_das_questoes';
  api_das_questoes: {
    base_url: string;
    timeout_seconds: number;
    api_key_configured: boolean;
    documentation: string;
    server_side_only: boolean;
  };
};

let mounted = false;

function panelHtml(): string {
  return `<article class="panel panel--wide" id="questionSourceSettingsPanel">
    <div class="panel-header">
      <div><h2>Fonte do catálogo de questões</h2><p>Escolha o SQLite local ou consulte a APIdasQuestões pelo backend seguro do Studio.</p></div>
      <span class="status-pill" id="questionSourceStatusPill">Carregando…</span>
    </div>
    <div class="panel-body">
      <div class="network-note"><strong>Compatibilidade:</strong> a resposta externa é normalizada para o mesmo modelo QuestFlow. A chave nunca é enviada ao navegador nem ao Mobile; fica protegida pelo Windows.</div>
      <form class="network-settings-grid" id="questionSourceSettings" autocomplete="off">
        <div class="form-field"><label for="questionSourceProvider">Fonte ativa</label><select id="questionSourceProvider"><option value="local">SQLite local</option><option value="api_das_questoes">APIdasQuestões</option></select></div>
        <div class="form-field form-field--wide"><label for="apiDasQuestoesBaseUrl">URL base</label><input id="apiDasQuestoesBaseUrl" type="url" value="https://api.apidasquestoes.com.br/api/v1" spellcheck="false"></div>
        <div class="form-field form-field--wide"><label for="apiDasQuestoesKey">API Key</label><input id="apiDasQuestoesKey" type="password" autocomplete="new-password" placeholder="Deixe vazio para manter a chave protegida"><small class="field-help" id="apiDasQuestoesKeyHint">Ainda não configurada.</small></div>
        <div class="form-field"><label for="apiDasQuestoesTimeout">Timeout (s)</label><input id="apiDasQuestoesTimeout" type="number" min="3" max="120" value="20"></div>
      </form>
      <div class="network-detected" id="questionSourceStatusText">Carregando configuração…</div>
      <div class="network-actions"><button class="button" type="button" id="testQuestionSource">Testar fonte</button><button class="button button--primary" type="button" id="saveQuestionSource">Salvar fonte</button><a class="button button--secondary" href="https://www.apidasquestoes.com.br/documentacao" target="_blank" rel="noopener noreferrer">Documentação oficial</a></div>
    </div>
  </article>`;
}

function element<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Controle ausente: ${id}`);
  return node as T;
}

function setStatus(message: string, ok: boolean | null = null): void {
  element<HTMLElement>('questionSourceStatusText').textContent = message;
  const pill = element<HTMLElement>('questionSourceStatusPill');
  pill.textContent = ok === true ? 'Disponível' : ok === false ? 'Atenção' : 'Configurando';
  pill.dataset.status = ok === true ? 'ready' : ok === false ? 'warning' : 'pending';
}

async function loadSettings(): Promise<void> {
  try {
    const settings = await studioGet<SourceSettings>('question-source');
    element<HTMLSelectElement>('questionSourceProvider').value = settings.provider;
    element<HTMLInputElement>('apiDasQuestoesBaseUrl').value = settings.api_das_questoes.base_url;
    element<HTMLInputElement>('apiDasQuestoesTimeout').value = String(settings.api_das_questoes.timeout_seconds);
    element<HTMLElement>('apiDasQuestoesKeyHint').textContent = settings.api_das_questoes.api_key_configured
      ? 'Chave configurada e protegida. Deixe o campo vazio para mantê-la.'
      : 'Ainda não configurada.';
    setStatus(settings.provider === 'local' ? 'Catálogo local ativo; funciona integralmente offline.' : 'APIdasQuestões ativa para as buscas do Studio.', true);
  } catch (error) {
    setStatus((error as Error).message, false);
  }
}

async function saveSettings(): Promise<void> {
  setStatus('Salvando fonte…');
  try {
    const settings = await studioPost<SourceSettings>('question-source', {
      provider: element<HTMLSelectElement>('questionSourceProvider').value,
      base_url: element<HTMLInputElement>('apiDasQuestoesBaseUrl').value.trim(),
      timeout_seconds: Number(element<HTMLInputElement>('apiDasQuestoesTimeout').value || 20),
      api_key: element<HTMLInputElement>('apiDasQuestoesKey').value.trim(),
    });
    element<HTMLInputElement>('apiDasQuestoesKey').value = '';
    element<HTMLElement>('apiDasQuestoesKeyHint').textContent = settings.api_das_questoes.api_key_configured
      ? 'Chave configurada e protegida. Deixe o campo vazio para mantê-la.'
      : 'Ainda não configurada.';
    setStatus(settings.provider === 'local' ? 'SQLite local ativado.' : 'APIdasQuestões ativada. As próximas buscas do Studio usarão a API.', true);
    document.dispatchEvent(new CustomEvent('questflow:question-source-changed', { detail: { provider: settings.provider } }));
  } catch (error) {
    setStatus((error as Error).message, false);
  }
}

async function testSource(): Promise<void> {
  setStatus('Testando a fonte selecionada…');
  try {
    const result = await studioPost<Record<string, unknown>>('question-source/test', {
      provider: element<HTMLSelectElement>('questionSourceProvider').value,
    });
    setStatus(result.authenticated === false
      ? 'Listas públicas acessíveis. Configure a API Key para consultar questões.'
      : `Fonte disponível${result.total != null ? `; ${String(result.total)} questões encontradas` : ''}.`, true);
  } catch (error) {
    setStatus((error as Error).message, false);
  }
}

const module: RouteModule = {
  async mount({ page }) {
    if (!document.getElementById('questionSourceSettingsPanel')) {
      const grid = page.querySelector<HTMLElement>('.settings-grid');
      const network = page.querySelector<HTMLElement>('.network-panel');
      if (!grid) return;
      if (network) network.insertAdjacentHTML('beforebegin', panelHtml());
      else grid.insertAdjacentHTML('beforeend', panelHtml());
      element<HTMLButtonElement>('saveQuestionSource').addEventListener('click', () => void saveSettings());
      element<HTMLButtonElement>('testQuestionSource').addEventListener('click', () => void testSource());
    }
    if (!mounted) {
      mounted = true;
      await loadSettings();
    }
  },
};

export default module;

