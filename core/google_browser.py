from __future__ import annotations

import atexit
import os
import re
import shutil
import threading
import time
import urllib.parse

from .network import NetworkManager
from pathlib import Path
from typing import Callable


class GoogleBrowserError(RuntimeError):
    pass


_SESSION_LOCK = threading.RLock()
_SESSION: dict[str, object] = {"driver": None, "browser": "", "profile": ""}


def _driver_alive(driver) -> bool:
    if driver is None:
        return False
    try:
        _ = driver.current_url
        _ = driver.window_handles
        return True
    except Exception:
        return False


def close_google_browser_session() -> None:
    """Encerra a sessão persistente usada pelo Modo IA."""
    with _SESSION_LOCK:
        driver = _SESSION.get("driver")
        _SESSION.update({"driver": None, "browser": "", "profile": ""})
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


atexit.register(close_google_browser_session)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_google_url(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return False
    return host.endswith("google.com") or ".google." in host or host.endswith("google.com.br")


def _collect_organic_links(driver, limit: int = 10) -> list[dict]:
    from selenium.webdriver.common.by import By

    links: list[dict] = []
    seen: set[str] = set()
    for anchor in driver.find_elements(By.CSS_SELECTOR, "a"):
        try:
            href = str(anchor.get_attribute("href") or "").strip()
            if not href.startswith(("http://", "https://")) or _is_google_url(href):
                continue
            canonical = href.split("#", 1)[0].rstrip("/")
            if canonical in seen:
                continue
            text = _clean(anchor.text)
            if not text:
                try:
                    text = _clean(anchor.find_element(By.CSS_SELECTOR, "h3").text)
                except Exception:
                    continue
            if len(text) < 4:
                continue
            seen.add(canonical)
            links.append({"title": text[:300], "url": href, "snippet": "", "provider": "Google"})
            if len(links) >= limit:
                break
        except Exception:
            continue
    return links


def _accept_google_consent(driver) -> None:
    from selenium.webdriver.common.by import By

    candidates = (
        "Aceitar tudo",
        "Concordo",
        "I agree",
        "Accept all",
    )
    for label in candidates:
        try:
            buttons = driver.find_elements(By.XPATH, f"//button[contains(normalize-space(.), {label!r})]")
            if buttons:
                buttons[0].click()
                time.sleep(1)
                return
        except Exception:
            continue


def _page_body_text(driver) -> str:
    try:
        return str(driver.find_element("tag name", "body").text or "")
    except Exception:
        return ""


def _expand_google_answer(driver, *, max_clicks: int = 4) -> dict:
    """Expande a resposta/visão geral do Google antes de ler a página.

    O Google costuma recolher a parte inferior da resposta em um controle chamado
    "Mostrar mais". O controle pode ser um ``button``, um elemento com
    ``role=button`` ou um ``div`` clicável. A função tenta as variações visíveis,
    aguarda o texto crescer e repete enquanto houver outro expansor.
    """
    try:
        from selenium.webdriver.common.by import By
    except Exception:
        class By:
            XPATH = "xpath"

    labels = (
        "Mostrar mais",
        "Ver mais",
        "Mostrar tudo",
        "Mais detalhes",
        "Show more",
        "See more",
    )
    clicked_labels: list[str] = []
    errors: list[str] = []
    previous_text = _page_body_text(driver)

    for _ in range(max(1, max_clicks)):
        candidate = None
        candidate_label = ""
        for label in labels:
            literal = label.replace("'", "\\'")
            xpaths = (
                f"//button[normalize-space(.)='{literal}']",
                f"//*[@role='button' and normalize-space(.)='{literal}']",
                f"//*[self::div or self::span or self::a][normalize-space(.)='{literal}']",
                f"//button[contains(normalize-space(.), '{literal}')]",
                f"//*[@role='button' and contains(normalize-space(.), '{literal}')]",
            )
            for xpath in xpaths:
                try:
                    for element in driver.find_elements(By.XPATH, xpath):
                        if not element.is_displayed():
                            continue
                        candidate = element
                        candidate_label = label
                        break
                except Exception:
                    continue
                if candidate is not None:
                    break
            if candidate is not None:
                break

        if candidate is None:
            break

        before_length = len(previous_text)
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                candidate,
            )
            time.sleep(0.35)
            try:
                candidate.click()
            except Exception:
                driver.execute_script("arguments[0].click();", candidate)
            clicked_labels.append(candidate_label)
        except Exception as error:
            errors.append(f"{candidate_label}: {error}")
            break

        deadline = time.time() + 5.0
        expanded_text = previous_text
        while time.time() < deadline:
            time.sleep(0.45)
            expanded_text = _page_body_text(driver)
            if len(expanded_text) >= before_length + 120:
                break
            # O botão pode mudar para "Mostrar menos" mesmo quando o ganho textual
            # é pequeno; nesse caso, a expansão também foi concluída.
            if "mostrar menos" in expanded_text.lower() or "show less" in expanded_text.lower():
                break
        previous_text = expanded_text
        # Assim que os campos desejados aparecerem, não clica em outros controles
        # "Mostrar mais" pertencentes a resultados ou perguntas relacionadas.
        if re.search(r"\bGabarito\b", previous_text, re.I) and re.search(
            r"\b(?:Justificativa|Explicação|Resolução|Comentário)\b", previous_text, re.I
        ):
            break

    return {
        "expanded": bool(clicked_labels),
        "click_count": len(clicked_labels),
        "labels": clicked_labels,
        "errors": errors,
        "text": previous_text,
    }



def _captcha_markers(text: str) -> bool:
    lower = str(text or "").lower()
    return any(
        marker in lower
        for marker in (
            "tráfego incomum",
            "trafego incomum",
            "unusual traffic",
            "não sou um robô",
            "nao sou um robo",
            "not a robot",
            "recaptcha",
            "confirme que você não é um robô",
            "confirme que voce nao e um robo",
        )
    )


def _captcha_present(driver) -> bool:
    try:
        current_url = str(driver.current_url or "").lower()
    except Exception:
        current_url = ""
    if "/sorry/" in current_url or "google.com/sorry" in current_url or "google.com.br/sorry" in current_url:
        return True
    body_text = _page_body_text(driver)
    if _captcha_markers(body_text):
        return True
    try:
        from selenium.webdriver.common.by import By

        selectors = (
            "iframe[src*='recaptcha']",
            "iframe[title*='recaptcha']",
            "iframe[title*='challenge']",
            "form#captcha-form",
            "div.g-recaptcha",
        )
        for selector in selectors:
            try:
                if driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _wait_for_manual_captcha(
    driver,
    *,
    timeout_seconds: int = 900,
    poll_seconds: float = 1.0,
    sleep_func=time.sleep,
    time_func=time.time,
) -> dict:
    """Mantém o navegador aberto enquanto o usuário resolve a verificação do Google.

    A função não tenta contornar ou automatizar o CAPTCHA. Ela apenas aguarda a
    intervenção humana e continua quando o Google redireciona de volta aos
    resultados. Se o navegador for fechado, retorna imediatamente com erro.
    """
    started = time_func()
    detected = _captcha_present(driver)
    if not detected:
        return {
            "detected": False,
            "resolved": True,
            "timed_out": False,
            "waited_seconds": 0,
            "browser_closed": False,
        }

    browser_closed = False
    while time_func() - started < max(15, int(timeout_seconds)):
        try:
            if not _captcha_present(driver):
                # Aguarda um pouco para a página de resultados terminar de renderizar.
                sleep_func(1.2)
                return {
                    "detected": True,
                    "resolved": True,
                    "timed_out": False,
                    "waited_seconds": round(time_func() - started, 1),
                    "browser_closed": False,
                }
        except Exception:
            browser_closed = True
            break
        sleep_func(max(0.25, float(poll_seconds)))

    return {
        "detected": True,
        "resolved": False,
        "timed_out": not browser_closed,
        "waited_seconds": round(time_func() - started, 1),
        "browser_closed": browser_closed,
    }

def _build_driver(profile_dir: str | Path | None = None):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
    except Exception as error:
        raise GoogleBrowserError(
            "O componente Selenium não está instalado. Execute novamente INSTALAR_E_DIAGNOSTICAR.bat."
        ) from error

    common_args = [
        "--start-maximized",
        "--lang=pt-BR",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-component-update",
        "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    errors: list[str] = []

    chrome_options = ChromeOptions()
    chrome_options.page_load_strategy = "eager"
    chrome_options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    })
    for arg in common_args:
        chrome_options.add_argument(arg)

    # A janela Selenium é o contexto que realmente acessa a Internet. Diferente
    # do Chrome principal do QuestFlow (que fala apenas com 127.0.0.1), ela
    # herda/recebe a política corporativa de proxy centralizada.
    network_manager = NetworkManager()
    for arg in network_manager.chrome_arguments("https://www.google.com/"):
        chrome_options.add_argument(arg)
    chrome_binary = os.environ.get("QUESTFLOW_CHROME_BINARY")
    if not chrome_binary:
        try:
            from desktop_runtime import browser_candidates

            candidates = browser_candidates()
            chrome_binary = str(candidates[0]) if candidates else ""
        except Exception:
            chrome_binary = ""
    if chrome_binary:
        chrome_options.binary_location = chrome_binary

    if profile_dir:
        Path(profile_dir).mkdir(parents=True, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    try:
        # Selenium Manager pode precisar baixar/localizar o driver. Repasse o
        # proxy efetivo sem alterar permanentemente o ambiente do processo.
        proxy_env = network_manager.environment("https://googlechromelabs.github.io/")
        previous_env = {key: os.environ.get(key) for key in proxy_env}
        os.environ.update(proxy_env)
        if proxy_env.get("HTTPS_PROXY"):
            os.environ["SE_PROXY"] = proxy_env["HTTPS_PROXY"]
            previous_env.setdefault("SE_PROXY", None)
        try:
            driver = webdriver.Chrome(options=chrome_options)
        finally:
            for key, previous in previous_env.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
        driver.set_page_load_timeout(24)
        driver.set_script_timeout(20)
        return driver, "Google Chrome"
    except Exception as error:
        errors.append(f"Chrome: {error}")

    raise GoogleBrowserError(
        "Não foi possível abrir o Google Chrome para a pesquisa visível. " + (errors[0] if errors else "Chrome indisponível.")
    )



def _acquire_driver(profile_dir: str | Path | None = None, *, reuse_session: bool = True):
    profile_key = str(Path(profile_dir).resolve()) if profile_dir else ""
    if not reuse_session:
        driver, browser = _build_driver(profile_dir)
        return driver, browser, False
    with _SESSION_LOCK:
        driver = _SESSION.get("driver")
        if _driver_alive(driver) and str(_SESSION.get("profile", "")) == profile_key:
            try:
                # Fecha abas extras deixadas por uma navegação interrompida.
                handles = list(driver.window_handles)
                if handles:
                    for handle in handles[1:]:
                        try:
                            driver.switch_to.window(handle)
                            driver.close()
                        except Exception:
                            pass
                    driver.switch_to.window(handles[0])
            except Exception:
                pass
            return driver, str(_SESSION.get("browser", "")), True
        close_google_browser_session()
        driver, browser = _build_driver(profile_dir)
        _SESSION.update({"driver": driver, "browser": browser, "profile": profile_key})
        return driver, browser, False


def _visible_ai_answer_snapshot(driver, query: str = "") -> dict:
    """Captura o bloco mais provável da resposta, evitando menus e resultados laterais.

    O Modo IA altera classes e atributos com frequência. Em vez de depender de uma
    classe específica, o JavaScript pontua blocos visíveis pelo código da questão e
    por títulos semânticos como Enunciado, Gabarito e Justificativa.
    """
    terms = [item.lower() for item in re.findall(r"Q\d{4,12}|[A-Za-zÀ-ÿ]{5,}", query)[:12]]
    script = r"""
        const terms = arguments[0] || [];
        const labels = [
          'informações gerais','informações da questão','enunciado','alternativas',
          'gabarito','justificativa','explicação','resolução','banca','ano','órgão'
        ];
        const visible = (el) => {
          const s = window.getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return s && s.display !== 'none' && s.visibility !== 'hidden' && r.width > 180 && r.height > 40;
        };
        const primarySelectors = [
          'main','[role="main"]','article','section','[data-attrid]','[data-hveid]',
          '[jsname]','div[role="region"]'
        ].join(',');
        const seen = new Set();
        const candidates = [];
        const evaluateNodes = (nodes) => {
          for (const el of nodes) {
            if (!visible(el)) continue;
            const text = (el.innerText || '').trim();
            if (text.length < 80 || text.length > 30000) continue;
            const normalized = text.toLowerCase();
            let labelHits = 0;
            for (const label of labels) if (normalized.includes(label)) labelHits++;
            let termHits = 0;
            for (const term of terms) if (term && normalized.includes(term)) termHits++;
            const explicitAnswer = normalized.includes('gabarito') && (
              normalized.includes('explicação') || normalized.includes('explicacao') ||
              normalized.includes('justificativa') || normalized.includes('resolução') || normalized.includes('resolucao')
            );
            if (!explicitAnswer && labelHits < 2 && termHits < 1) continue;
            const signature = text.slice(0, 220) + '|' + text.length;
            if (seen.has(signature)) continue;
            seen.add(signature);
            const childPenalty = Math.min(2.5, el.children.length / 25);
            const sizePenalty = Math.max(0, (text.length - 5000) / 5000);
            // Hotfix 4: o layout atual do Modo IA exibe um bloco compacto
            // "Gabarito: ... / Explicação: ..." que pode não repetir nenhum termo
            // da consulta. Esse bloco deve vencer contêineres grandes com menus/cards.
            const compactAnswerBonus = explicitAnswer ? (18 + Math.max(0, 5 - text.length / 900)) : 0;
            const score = compactAnswerBonus + termHits * 5 + labelHits * 2.4 - childPenalty - sizePenalty;
            candidates.push({text, score, length:text.length, labelHits, termHits, explicitAnswer});
          }
        };
        evaluateNodes(Array.from(document.querySelectorAll(primarySelectors)));
        // Hotfix 6: o Modo IA atual costuma renderizar a resposta em um DIV compacto
        // dentro de um contêiner grande. Mesmo que o <main> já tenha virado candidato,
        // varremos também os blocos que possuam explicitamente Gabarito +
        // Explicação/Justificativa/Resolução. Assim o bloco pequeno entra na disputa
        // e vence pelo bônus de resposta compacta, em vez de o coletor ficar com a
        // página inteira ou com cards laterais.
        const explicitNodes = Array.from(document.querySelectorAll('div,section,article')).filter(el => {
          if (!visible(el)) return false;
          const text = (el.innerText || '').trim();
          if (text.length < 70 || text.length > 16000) return false;
          const normalized = text.toLowerCase();
          return normalized.includes('gabarito') && (
            normalized.includes('explicação') || normalized.includes('explicacao') ||
            normalized.includes('justificativa') || normalized.includes('resolução') ||
            normalized.includes('resolucao') || normalized.includes('fundamentação') ||
            normalized.includes('fundamentacao')
          );
        }).slice(0, 900);
        evaluateNodes(explicitNodes);
        // Fallback mais caro: só quando ainda não apareceu nenhum candidato útil.
        if (candidates.length === 0) {
          const codeTerm = terms.find(term => /^q\d{4,12}$/i.test(term));
          const fallbackNodes = Array.from(document.querySelectorAll('div')).filter(el => {
            const text = (el.innerText || '').toLowerCase();
            return codeTerm ? text.includes(codeTerm) : labels.some(label => text.includes(label));
          }).slice(0, 500);
          evaluateNodes(fallbackNodes);
        }
        candidates.sort((a,b) => b.score - a.score || b.labelHits - a.labelHits || a.length - b.length);
        return candidates.slice(0, 8);
    """
    try:
        candidates = driver.execute_script(script, terms) or []
    except Exception:
        candidates = []
    if candidates:
        best = candidates[0]
        return {
            "text": str(best.get("text", "")),
            "method": "semantic_dom_block",
            "score": float(best.get("score", 0) or 0),
            "candidate_count": len(candidates),
        }
    body = _page_body_text(driver)
    return {"text": body, "method": "body_fallback", "score": 0.0, "candidate_count": 0}


def _scroll_ai_page(driver, *, steps: int = 5) -> None:
    """Força o carregamento de trechos lazy-loaded sem esperar imagens externas."""
    try:
        height = int(driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);") or 0)
        if height <= 0:
            return
        for index in range(1, max(2, steps) + 1):
            driver.execute_script("window.scrollTo(0, arguments[0]);", int(height * index / max(2, steps)))
            time.sleep(0.18)
        driver.execute_script("window.scrollTo(0, 0);")
    except Exception:
        pass



def _click_ai_mode_tab(driver) -> bool:
    """Tenta ativar o Modo IA pela interface da Pesquisa Google."""
    try:
        from selenium.webdriver.common.by import By
    except Exception:
        return False
    labels = ("Modo IA", "AI Mode")
    for label in labels:
        literal = label.replace("'", "\\'")
        xpaths = (
            f"//a[normalize-space(.)='{literal}']",
            f"//button[normalize-space(.)='{literal}']",
            f"//*[@role='tab' and normalize-space(.)='{literal}']",
            f"//*[contains(normalize-space(.), '{literal}') and (@role='tab' or self::a or self::button)]",
        )
        for xpath in xpaths:
            try:
                for element in driver.find_elements(By.XPATH, xpath):
                    if not element.is_displayed():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                    try:
                        element.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", element)
                    time.sleep(1.2)
                    return True
            except Exception:
                continue
    return False


def _find_ai_query_box(driver):
    """Localiza o campo de pergunta do Modo IA sem depender de um único seletor."""
    try:
        from selenium.webdriver.common.by import By
    except Exception:
        return None
    selectors = (
        "textarea[placeholder*='Pergunte']",
        "textarea[aria-label*='Pergunte']",
        "input[placeholder*='Pergunte']",
        "input[aria-label*='Pergunte']",
        "textarea",
        "input[name='q']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
    )
    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                if element.is_displayed() and element.is_enabled():
                    return element
        except Exception:
            continue
    return None


def _submit_ai_query(driver, query: str) -> bool:
    try:
        from selenium.webdriver.common.keys import Keys
    except Exception:
        return False
    box = _find_ai_query_box(driver)
    if box is None:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", box)
        box.click()
        try:
            box.clear()
        except Exception:
            pass
        # Contenteditable nem sempre respeita clear().
        try:
            box.send_keys(Keys.CONTROL, "a")
            box.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
        box.send_keys(query)
        box.send_keys(Keys.ENTER)
        return True
    except Exception:
        return False


def _ai_mode_active(driver) -> bool:
    try:
        url = str(driver.current_url or "").lower()
    except Exception:
        url = ""
    body = _page_body_text(driver).lower()
    return (
        "/ai" in url
        or "udm=50" in url
        or "modo ia" in body
        or "ai mode" in body
        or "pergunte o que quiser" in body
    )


def _wait_for_ai_answer(
    driver,
    query: str,
    *,
    wait_seconds: int = 75,
    sleep_func=time.sleep,
    time_func=time.time,
) -> dict:
    """Aguarda o bloco semântico da resposta e encerra cedo quando ele é útil.

    Desde a 6.8.0 a pergunta orientadora pede uma resposta curta (gabarito +
    justificativa) e explicitamente manda não repetir código/enunciado/metadados.
    A lógica antiga ainda exigia que o código Qxxxx aparecesse *na resposta*, o
    que transformava respostas boas e concisas em falso ``timeout``.
    """
    started = time_func()
    deadline = started + max(10, int(wait_seconds))
    previous = ""
    stable_cycles = 0
    best_snapshot = {"text": "", "method": "body_fallback", "score": 0.0, "candidate_count": 0}
    attempts = 0
    ready_reason = "timeout"
    first_answer_signal_at = 0.0
    last_content_change_at = started
    query_lower = str(query or "").casefold()
    focused_request = (
        "gabarito" in query_lower
        and any(term in query_lower for term in ("justificativa", "explicação", "explicacao"))
    )
    while time_func() < deadline:
        attempts += 1
        if _captcha_present(driver):
            return {
                "text": _page_body_text(driver), "stable": False, "captcha": True,
                "capture_method": "captcha", "captured_chars": 0,
                "attempts": attempts, "elapsed_seconds": round(time_func() - started, 2),
                "ready_reason": "captcha",
            }
        snapshot = _visible_ai_answer_snapshot(driver, query)
        current = str(snapshot.get("text", ""))
        if len(current) > len(str(best_snapshot.get("text", ""))) or float(snapshot.get("score", 0)) > float(best_snapshot.get("score", 0)):
            best_snapshot = snapshot
        lower = current.lower()
        loading = any(marker in lower for marker in (
            "gerando", "pesquisando", "analisando", "criando resposta", "thinking", "searching",
        ))
        section_hits = sum(1 for marker in (
            "informações gerais", "informações da questão", "enunciado", "alternativas",
            "gabarito", "justificativa", "explicação", "resolução",
        ) if marker in lower)
        code_terms = [term.lower() for term in re.findall(r"Q\d{4,12}", query)]
        code_context = not code_terms or any(term in lower for term in code_terms)
        answer_signal = bool(re.search(
            r"(?im)\b(?:gabarito|resposta(?:\s+correta)?|alternativa\s+correta)\b",
            current,
        ))
        explanation_signal = any(marker in lower for marker in (
            "justificativa", "explicação", "explicacao", "resolução", "resolucao",
            "fundamentação", "fundamentacao",
        ))
        # Fluxo legado: respostas longas que repetem os dados da questão.
        complete = code_context and section_hits >= 4 and len(current) >= 420
        useful = code_context and section_hits >= 2 and len(current) >= 280
        # Fluxo 6.8.x: resposta deliberadamente curta. Aqui o código NÃO precisa
        # ser ecoado pelo Google, pois ele já está na consulta. O que importa é
        # haver gabarito e justificativa, com texto estável e sem indicador de carga.
        focused_complete = focused_request and answer_signal and explanation_signal and len(current) >= 95
        focused_useful = focused_request and (answer_signal or explanation_signal) and len(current) >= 120
        now = time_func()
        has_answer_signal = bool(focused_complete or focused_useful or complete or useful)
        if has_answer_signal and not first_answer_signal_at:
            first_answer_signal_at = now
        if current != previous:
            last_content_change_at = now
        if current and current == previous and has_answer_signal:
            stable_cycles += 1
        else:
            stable_cycles = 0
        # Não basta a página repetir o mesmo texto em dois polls muito próximos:
        # o Modo IA pode pausar durante o streaming e continuar alguns instantes depois.
        # Exigimos uma janela real sem mudanças antes de capturar a resposta final.
        quiet_seconds = max(0.0, now - last_content_change_at)
        answer_age_seconds = max(0.0, now - first_answer_signal_at) if first_answer_signal_at else 0.0
        focused_settled = quiet_seconds >= 4.0 and answer_age_seconds >= 5.0
        verbose_settled = quiet_seconds >= 3.0 and answer_age_seconds >= 4.0
        if focused_complete and stable_cycles >= 4 and focused_settled and not loading:
            ready_reason = "focused_answer_stable"
            best_snapshot = snapshot
            break
        if focused_useful and stable_cycles >= 5 and focused_settled and not loading:
            ready_reason = "focused_text_stable"
            best_snapshot = snapshot
            break
        # Compatibilidade com o formato antigo/verboso do Modo IA.
        if complete and stable_cycles >= 4 and verbose_settled and not loading:
            ready_reason = "complete_sections_stable"
            best_snapshot = snapshot
            break
        if useful and stable_cycles >= 6 and verbose_settled and not loading:
            ready_reason = "useful_text_stable"
            best_snapshot = snapshot
            break
        previous = current
        if attempts in {4, 10, 20, 40}:
            _scroll_ai_page(driver, steps=3)
        sleep_func(0.60)
    best_text = str(best_snapshot.get("text", "")) or previous
    return {
        "text": best_text,
        "stable": ready_reason != "timeout",
        "captcha": False,
        "capture_method": str(best_snapshot.get("method", "body_fallback")),
        "captured_chars": len(best_text),
        "candidate_count": int(best_snapshot.get("candidate_count", 0) or 0),
        "attempts": attempts,
        "elapsed_seconds": round(time_func() - started, 2),
        "ready_reason": ready_reason,
    }


def run_visible_google_ai_search(
    query: str,
    *,
    profile_dir: str | Path | None = None,
    wait_seconds: int = 75,
    captcha_wait_seconds: int = 900,
    reuse_session: bool = True,
) -> dict:
    """Abre somente o Modo IA do Google e lê a resposta renderizada.

    Nenhum resultado orgânico é aberto. A função acessa ``google.com/ai``; caso o
    campo do Modo IA não esteja disponível nessa rota, usa a busca comum apenas
    para clicar na aba ``Modo IA`` e só então envia a pergunta.
    """
    query = _clean(query)
    if not query:
        raise GoogleBrowserError("A consulta do Google está vazia.")

    started_at = time.time()
    driver, browser_name, browser_reused = _acquire_driver(profile_dir, reuse_session=reuse_session)
    ai_entry_url = "https://www.google.com/ai?hl=pt-BR"
    fallback_url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "pt-BR"})
    try:
        driver.get(ai_entry_url)
        _accept_google_consent(driver)
        captcha_wait = _wait_for_manual_captcha(driver, timeout_seconds=captcha_wait_seconds)
        if captcha_wait.get("detected") and not captcha_wait.get("resolved"):
            return {
                "query": query,
                "search_url": str(getattr(driver, "current_url", ai_entry_url) or ai_entry_url),
                "browser": browser_name,
                "search_text": _page_body_text(driver),
                "search_html": str(getattr(driver, "page_source", "") or ""),
                "results": [],
                "opened_pages": [],
                "blocked": True,
                "ai_mode_activated": False,
                "ai_answer_stable": False,
                "captcha_detected": True,
                "captcha_resolved": False,
                "captcha_timed_out": bool(captcha_wait.get("timed_out")),
                "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
                "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
                "google_answer_expanded": False,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }

        submitted = _submit_ai_query(driver, query)
        if not submitted:
            driver.get(fallback_url)
            _accept_google_consent(driver)
            captcha_wait = _wait_for_manual_captcha(driver, timeout_seconds=captcha_wait_seconds)
            if captcha_wait.get("detected") and not captcha_wait.get("resolved"):
                return {
                    "query": query,
                    "search_url": str(getattr(driver, "current_url", fallback_url) or fallback_url),
                    "browser": browser_name,
                    "search_text": _page_body_text(driver),
                    "search_html": str(getattr(driver, "page_source", "") or ""),
                    "results": [], "opened_pages": [], "blocked": True,
                    "ai_mode_activated": False, "ai_answer_stable": False,
                    "captcha_detected": True, "captcha_resolved": False,
                    "captcha_timed_out": bool(captcha_wait.get("timed_out")),
                    "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
                    "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
                    "google_answer_expanded": False, "google_expand_clicks": 0,
                    "google_expand_labels": [], "google_expand_errors": [],
                }
            if not _click_ai_mode_tab(driver):
                raise GoogleBrowserError(
                    "O Modo IA não apareceu na conta/região atual do Google. Faça login no perfil do navegador e tente novamente."
                )
            time.sleep(1.0)
            # A aba pode preservar a consulta ou abrir o campo vazio.
            if not any(term.lower() in _page_body_text(driver).lower() for term in re.findall(r"Q\d{4,12}", query)):
                _submit_ai_query(driver, query)

        answer_wait = _wait_for_ai_answer(driver, query, wait_seconds=wait_seconds)
        if answer_wait.get("captcha"):
            captcha_wait = _wait_for_manual_captcha(driver, timeout_seconds=captcha_wait_seconds)
            if captcha_wait.get("resolved"):
                answer_wait = _wait_for_ai_answer(driver, query, wait_seconds=wait_seconds)

        expansion = _expand_google_answer(driver, max_clicks=6)
        body_text = str(expansion.get("text") or answer_wait.get("text") or _page_body_text(driver))
        # Uma segunda espera captura texto que só aparece depois da expansão.
        post = _wait_for_ai_answer(driver, query, wait_seconds=max(30, wait_seconds // 2))
        if len(str(post.get("text", ""))) > len(body_text) or str(post.get("ready_reason", "")).startswith("focused_"):
            body_text = str(post.get("text", ""))
        # Recaptura final: depois de a resposta parecer pronta, concede uma pequena
        # janela para o DOM aplicar o último lote de texto. Isso evita o caso em que
        # o usuário já vê a explicação completa na tela, mas o Selenium ficou com o
        # snapshot imediatamente anterior.
        time.sleep(2.2)
        final_snapshot = _visible_ai_answer_snapshot(driver, query)
        final_text = str(final_snapshot.get("text", ""))
        if final_text and (
            len(final_text) >= len(body_text)
            or ("gabarito" in final_text.lower() and any(x in final_text.lower() for x in ("explicação", "explicacao", "justificativa", "resolução", "resolucao")))
        ):
            body_text = final_text
        try:
            page_html = str(driver.page_source or "")
            current_url = str(driver.current_url or ai_entry_url)
        except Exception:
            page_html = ""
            current_url = ai_entry_url
        blocked = _captcha_present(driver) or _captcha_markers(body_text)
        return {
            "query": query,
            "search_url": current_url,
            "browser": browser_name,
            "search_text": body_text,
            "search_html": page_html,
            "results": [],
            "opened_pages": [],
            "blocked": blocked,
            "ai_mode_activated": _ai_mode_active(driver),
            "ai_answer_stable": bool(answer_wait.get("stable") or post.get("stable")),
            "captcha_detected": bool(captcha_wait.get("detected")),
            "captcha_resolved": bool(captcha_wait.get("resolved")),
            "captcha_timed_out": bool(captcha_wait.get("timed_out")),
            "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
            "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
            "google_answer_expanded": bool(expansion.get("expanded")),
            "browser_reused": browser_reused,
            "load_seconds": round(time.time() - started_at, 2),
            "capture_method": str(final_snapshot.get("method") or post.get("capture_method") or answer_wait.get("capture_method") or "body_fallback"),
            "captured_chars": len(body_text),
            "capture_attempts": int(answer_wait.get("attempts", 0) or 0) + int(post.get("attempts", 0) or 0),
            "answer_ready_reason": str(post.get("ready_reason") or answer_wait.get("ready_reason") or ""),
            "google_expand_clicks": int(expansion.get("click_count", 0) or 0),
            "google_expand_labels": list(expansion.get("labels", [])),
            "google_expand_errors": list(expansion.get("errors", [])),
        }
    except Exception:
        # Sessões quebradas são descartadas para a próxima consulta reconstruir o navegador.
        if reuse_session:
            close_google_browser_session()
        raise
    finally:
        if not reuse_session:
            try:
                driver.quit()
            except Exception:
                pass


def run_visible_google_search(
    query: str,
    *,
    profile_dir: str | Path | None = None,
    wait_seconds: int = 12,
    max_links: int = 5,
    need_open_links: Callable[[str, str], bool] | None = None,
    captcha_wait_seconds: int = 900,
) -> dict:
    """Abre uma pesquisa Google visível e lê a página já renderizada.

    A função captura o texto da página de resultados (inclusive blocos carregados por
    JavaScript, quando visíveis). Só abre links orgânicos quando o callback informa
    que os dados da própria página de pesquisa não foram suficientes.
    """
    query = _clean(query)
    if not query:
        raise GoogleBrowserError("A consulta do Google está vazia.")

    driver, browser_name = _build_driver(profile_dir)
    search_url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "pt-BR"})
    opened_pages: list[dict] = []
    try:
        driver.get(search_url)
        _accept_google_consent(driver)
        captcha_wait = _wait_for_manual_captcha(
            driver,
            timeout_seconds=captcha_wait_seconds,
        )
        if captcha_wait.get("detected") and not captcha_wait.get("resolved"):
            return {
                "query": query,
                "search_url": search_url,
                "browser": browser_name,
                "search_text": _page_body_text(driver),
                "search_html": str(getattr(driver, "page_source", "") or ""),
                "results": [],
                "opened_pages": [],
                "blocked": True,
                "captcha_detected": True,
                "captcha_resolved": False,
                "captcha_timed_out": bool(captcha_wait.get("timed_out")),
                "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
                "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
                "google_answer_expanded": False,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }
        deadline = time.time() + max(5, wait_seconds)
        body_text = ""
        page_html = ""
        while time.time() < deadline:
            try:
                body_text = _page_body_text(driver)
                page_html = str(driver.page_source or "")
            except Exception:
                time.sleep(0.5)
                continue
            # Aguarda a página realmente renderizar. Não encerra apenas porque o
            # cabeçalho "Informações" apareceu: os dados inferiores podem estar
            # escondidos atrás do botão "Mostrar mais".
            if len(body_text) > 350:
                break
            time.sleep(0.7)

        expansion = _expand_google_answer(driver)
        if expansion.get("text"):
            body_text = str(expansion["text"])
        try:
            page_html = str(driver.page_source or "")
        except Exception:
            page_html = page_html or ""

        # Depois da expansão, aguarda o DOM estabilizar para capturar enunciado,
        # gabarito e justificativa que aparecem abaixo do botão.
        stable_length = len(body_text)
        stable_cycles = 0
        final_deadline = time.time() + 4.0
        while time.time() < final_deadline:
            time.sleep(0.45)
            refreshed = _page_body_text(driver)
            if len(refreshed) == stable_length:
                stable_cycles += 1
            else:
                body_text = refreshed
                stable_length = len(refreshed)
                stable_cycles = 0
            if stable_cycles >= 2:
                break
        try:
            page_html = str(driver.page_source or "")
        except Exception:
            pass

        blocked = _captcha_present(driver) or _captcha_markers(body_text)
        links = _collect_organic_links(driver, max(10, max_links))
        should_open = bool(need_open_links(body_text, page_html)) if need_open_links else False

        if should_open:
            original_handle = driver.current_window_handle
            for result in links[: max(1, max_links)]:
                page_data = {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "text": "",
                    "html": "",
                    "opened": False,
                    "error": "",
                }
                try:
                    driver.execute_script("window.open(arguments[0], '_blank');", result["url"])
                    driver.switch_to.window(driver.window_handles[-1])
                    time.sleep(2.5)
                    page_data["text"] = str(driver.find_element("tag name", "body").text or "")
                    page_data["html"] = str(driver.page_source or "")
                    page_data["opened"] = bool(page_data["text"] or page_data["html"])
                except Exception as error:
                    page_data["error"] = str(error)
                finally:
                    opened_pages.append(page_data)
                    try:
                        if driver.current_window_handle != original_handle:
                            driver.close()
                        driver.switch_to.window(original_handle)
                    except Exception:
                        pass

        return {
            "query": query,
            "search_url": search_url,
            "browser": browser_name,
            "search_text": body_text,
            "search_html": page_html,
            "results": links,
            "opened_pages": opened_pages,
            "blocked": blocked,
            "captcha_detected": bool(captcha_wait.get("detected")),
            "captcha_resolved": bool(captcha_wait.get("resolved")),
            "captcha_timed_out": bool(captcha_wait.get("timed_out")),
            "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
            "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
            "google_answer_expanded": bool(expansion.get("expanded")),
            "google_expand_clicks": int(expansion.get("click_count", 0) or 0),
            "google_expand_labels": list(expansion.get("labels", [])),
            "google_expand_errors": list(expansion.get("errors", [])),
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def read_visible_page(
    url: str,
    *,
    profile_dir: str | Path | None = None,
    wait_seconds: int = 10,
    captcha_wait_seconds: int = 900,
) -> dict:
    """Abre uma página no Google Chrome visível e devolve o texto e o HTML renderizados."""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise GoogleBrowserError("O endereço selecionado é inválido.")
    driver, browser_name = _build_driver(profile_dir)
    try:
        driver.get(url)
        _accept_google_consent(driver)
        captcha_wait = _wait_for_manual_captcha(
            driver,
            timeout_seconds=captcha_wait_seconds,
        )
        if captcha_wait.get("detected") and not captcha_wait.get("resolved"):
            return {
                "url": str(getattr(driver, "current_url", url) or url),
                "browser": browser_name,
                "text": _page_body_text(driver),
                "html": str(getattr(driver, "page_source", "") or ""),
                "opened": False,
                "blocked": True,
                "captcha_detected": True,
                "captcha_resolved": False,
                "captcha_timed_out": bool(captcha_wait.get("timed_out")),
                "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
                "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
                "google_answer_expanded": False,
                "google_expand_clicks": 0,
                "google_expand_labels": [],
                "google_expand_errors": [],
            }
        expansion = {"expanded": False, "click_count": 0, "labels": [], "errors": [], "text": ""}
        if _is_google_url(url):
            time.sleep(1.0)
            expansion = _expand_google_answer(driver)
        deadline = time.time() + max(4, wait_seconds)
        body_text = ""
        page_html = ""
        previous_length = -1
        stable_cycles = 0
        while time.time() < deadline:
            try:
                body_text = str(driver.find_element("tag name", "body").text or "")
                page_html = str(driver.page_source or "")
            except Exception:
                time.sleep(0.5)
                continue
            current_length = len(body_text)
            if current_length > 200 and current_length == previous_length:
                stable_cycles += 1
            else:
                stable_cycles = 0
            if stable_cycles >= 2:
                break
            previous_length = current_length
            time.sleep(0.7)
        return {
            "url": str(driver.current_url or url),
            "browser": browser_name,
            "text": body_text,
            "html": page_html,
            "opened": bool(body_text or page_html),
            "blocked": _captcha_present(driver) or _captcha_markers(body_text),
            "captcha_detected": bool(captcha_wait.get("detected")),
            "captcha_resolved": bool(captcha_wait.get("resolved")),
            "captcha_timed_out": bool(captcha_wait.get("timed_out")),
            "captcha_waited_seconds": captcha_wait.get("waited_seconds", 0),
            "captcha_browser_closed": bool(captcha_wait.get("browser_closed")),
            "google_answer_expanded": bool(expansion.get("expanded")),
            "google_expand_clicks": int(expansion.get("click_count", 0) or 0),
            "google_expand_labels": list(expansion.get("labels", [])),
            "google_expand_errors": list(expansion.get("errors", [])),
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass
