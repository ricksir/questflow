from __future__ import annotations

import html
import concurrent.futures
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from difflib import SequenceMatcher
from typing import Callable, Iterable

from .google_browser import GoogleBrowserError, run_visible_google_ai_search, read_visible_page
from .network import network_urlopen


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    score: float = 0.0
    provider: str = ""

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
            "provider": self.provider,
        }


class WebEnrichmentError(RuntimeError):
    pass


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "QuestFlowStudio/4.0.0"
)

_SEARCH_DIRECTIVE = (
    "qual é o gabarito e a justificativa desta questão? "
    "Responda somente com o gabarito e a explicação diretamente relacionada à questão, sem repetir enunciado, metadados ou menus."
)
_COMMENTARY_MIN_CONFIDENCE = 0.62
# Abaixo deste valor a extração ainda pode ser aproveitada quando a própria consulta
# está ancorada na questão (código/enunciado) e o texto é substantivo. A confiança
# passa a ser um sinal para revisão humana, não uma guilhotina que apaga a resposta.
_COMMENTARY_ACCEPT_CONFIDENCE = 0.28
_MIN_LINKS_PER_STAGE = 5
_MAX_LINKS_PER_STAGE = 10

_STOP_WORDS = {
    "para", "como", "uma", "mais", "sobre", "pela", "pelo", "deve", "sera",
    "será", "assinale", "questao", "questão", "item", "correta", "incorreta",
    "dos", "das", "que", "com", "sem", "nos", "nas", "seu", "sua", "aos",
    "das", "este", "esta", "isso", "cada", "qual", "quando", "onde", "entre",
}


def _strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _html_to_lines(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(
        r"<(?:br|hr)\s*/?>|</(?:p|div|li|h[1-6]|tr|td|section|article|button|label)>",
        "\n",
        value,
        flags=re.I,
    )
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _normalize(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9áéíóúâêôãõç ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _statement_similarity(left: str, right: str) -> float:
    left_n = _normalize(left)
    right_n = _normalize(right)
    if not left_n or not right_n:
        return 0.0
    sequence = SequenceMatcher(None, left_n[:900], right_n[:4000]).ratio()
    left_words = [word for word in left_n.split() if len(word) >= 4 and word not in _STOP_WORDS]
    right_words = set(right_n.split())
    overlap = sum(1 for word in left_words if word in right_words) / max(1, min(len(left_words), 45))
    phrase = 1.0 if left_n[:120] in right_n else 0.0
    return min(1.0, sequence * 0.38 + overlap * 0.47 + phrase * 0.15)


def _request_text(url: str, *, timeout: int = 18, max_bytes: int = 1_800_000) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with network_urlopen(request, timeout=timeout) as response:
        raw = response.read(max_bytes)
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def _meaningful_words(statement: str, limit: int = 18) -> list[str]:
    words = [
        word for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", statement)
        if word.lower() not in _STOP_WORDS
    ]
    output: list[str] = []
    for word in words:
        if word.lower() not in {item.lower() for item in output}:
            output.append(word)
        if len(output) >= limit:
            break
    return output


def _usable_question_code(question: dict) -> str:
    code = str(question.get("codigo_origem", "") or question.get("id", "")).strip().upper()
    match = re.fullmatch(r"Q\d{4,12}", code)
    return match.group(0) if match else ""


def build_code_search_queries(question: dict) -> list[str]:
    """Primeira etapa: código isolado seguido apenas da pergunta orientadora."""
    code = _usable_question_code(question)
    if not code:
        return []
    return [f'"{code}" {_SEARCH_DIRECTIVE}']

def build_statement_search_queries(question: dict) -> list[str]:
    """Segunda etapa: somente o enunciado e a pergunta orientadora.

    O código, a banca e o ano não entram na consulta. Esses dados são usados apenas
    para validar as páginas abertas pelo programa.
    """
    statement = re.sub(r"\s+", " ", str(question.get("enunciado", "")).strip())
    if not statement:
        return []
    statement = statement.rstrip(" ,.;:")
    exact = statement[:360].strip()
    queries: list[str] = []
    if exact:
        queries.append(f'"{exact}" {_SEARCH_DIRECTIVE}')
    words = _meaningful_words(statement, 28)
    if words:
        broad = " ".join(words)
        query = f'{broad} {_SEARCH_DIRECTIVE}'
        if query not in queries:
            queries.append(query)
    return queries[:2]

def build_search_query(question: dict) -> str:
    code_queries = build_code_search_queries(question)
    if code_queries:
        return code_queries[0]
    statement_queries = build_statement_search_queries(question)
    return statement_queries[0] if statement_queries else ""


def build_search_queries(question: dict) -> list[str]:
    """Expõe a ordem real da pesquisa sem criar consultas combinadas.

    1. código isolado;
    2. enunciado isolado, usado somente como fallback.
    """
    return [*build_code_search_queries(question), *build_statement_search_queries(question)]

def _unwrap_result_url(url: str) -> str:
    url = html.unescape(url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("uddg", "url", "u", "q"):
        candidate = query.get(key, [""])[0]
        if candidate.startswith(("http://", "https://")):
            return urllib.parse.unquote(candidate)
    if url.startswith("/url?"):
        candidate = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        if candidate.startswith(("http://", "https://")):
            return urllib.parse.unquote(candidate)
    return url


def _parse_google_html(page: str) -> list[SearchResult]:
    """Extrai resultados das variações HTML simples do Google."""
    results: list[SearchResult] = []
    seen: set[str] = set()
    patterns = [
        r'<a[^>]+href="(/url\?q=[^"]+)"[^>]*>\s*<h3[^>]*>(.*?)</h3>',
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>\s*<h3[^>]*>(.*?)</h3>',
        r'<a[^>]+href="(/url\?[^\"]*?(?:q|url)=https?%3A%2F%2F[^\"]+)"[^>]*>(.*?)</a>',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, page, flags=re.I | re.S):
            url = _unwrap_result_url(match.group(1))
            if not url.startswith(("http://", "https://")):
                continue
            host = urllib.parse.urlparse(url).netloc.lower()
            canonical = url.split("#", 1)[0].rstrip("/")
            if "google." in host or canonical in seen:
                continue
            title = _strip_html(match.group(2))
            if not title:
                continue
            seen.add(canonical)
            block = page[match.start(): min(len(page), match.end() + 2600)]
            snippet_match = re.search(
                r'<div[^>]+class="[^"]*(?:VwiC3b|IsZvec|aCOpRe|kb0PBd)[^"]*"[^>]*>(.*?)</div>',
                block,
                flags=re.I | re.S,
            )
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=_strip_html(snippet_match.group(1)) if snippet_match else "",
                provider="Google",
            ))
    return results

def _parse_duckduckgo_html(page: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    anchors = list(re.finditer(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        page,
        flags=re.I | re.S,
    ))
    for index, match in enumerate(anchors):
        end = anchors[index + 1].start() if index + 1 < len(anchors) else min(len(page), match.end() + 5000)
        block = page[match.start():end]
        snippet_match = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>', block, flags=re.I | re.S)
        results.append(SearchResult(
            title=_strip_html(match.group(2)),
            url=_unwrap_result_url(match.group(1)),
            snippet=_strip_html(snippet_match.group(1)) if snippet_match else "",
            provider="DuckDuckGo",
        ))
    return results


def _parse_duckduckgo_lite(page: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    anchors = list(re.finditer(
        r'<a[^>]+(?:class=["\']result-link["\']|rel=["\']nofollow["\'])[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        page,
        flags=re.I | re.S,
    ))
    snippets = [_strip_html(item) for item in re.findall(
        r'<td[^>]+class=["\']result-snippet["\'][^>]*>(.*?)</td>', page, flags=re.I | re.S
    )]
    for index, match in enumerate(anchors):
        title = _strip_html(match.group(2))
        url = _unwrap_result_url(match.group(1))
        if title and url.startswith(("http://", "https://")):
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippets[index] if index < len(snippets) else "",
                provider="DuckDuckGo Lite",
            ))
    return results


def _parse_bing_html(page: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', page, flags=re.I | re.S):
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        if not link:
            continue
        snippet = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        title = _strip_html(link.group(2))
        url = _unwrap_result_url(link.group(1))
        if title and url:
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=_strip_html(snippet.group(1)) if snippet else "",
                provider="Bing",
            ))
    return results


def _parse_bing_rss(page: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    try:
        root = ET.fromstring(page)
    except ET.ParseError:
        return results
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        snippet = _strip_html(item.findtext("description") or "")
        if title and url.startswith(("http://", "https://")):
            results.append(SearchResult(title=title, url=url, snippet=snippet, provider="Bing RSS"))
    return results


def search_web(query: str, *, timeout: int = 10, max_results: int = 12) -> list[SearchResult]:
    """Fallback HTTP usando somente o Google.

    A pesquisa principal da versão 3.0.7 usa um navegador visível e lê a página
    já renderizada. Esta função existe apenas como contingência quando o navegador
    local não puder ser iniciado.
    """
    if not query.strip():
        return []
    endpoint = "https://www.google.com/search?" + urllib.parse.urlencode({
        "q": query,
        "num": max(10, max_results),
        "hl": "pt-BR",
        "filter": "0",
        "gbv": "1",
    })
    try:
        page = _request_text(endpoint, timeout=timeout)
    except Exception as error:
        raise WebEnrichmentError(f"Google indisponível: {error}") from error
    return _parse_google_html(page)[:max(1, min(max_results, 50))]

def score_results(question: dict, results: Iterable[SearchResult]) -> list[SearchResult]:
    statement = str(question.get("enunciado", ""))
    code = _normalize(str(question.get("codigo_origem", "")))
    board = _normalize(str(question.get("banca", "")))
    agency = _normalize(str(question.get("orgao", "")))
    year = _normalize(str(question.get("ano", "") or ""))
    scored: list[SearchResult] = []
    for result in results:
        haystack_raw = f"{result.title} {result.snippet} {result.url}"
        haystack = _normalize(haystack_raw)
        similarity = _statement_similarity(statement, haystack_raw)
        code_bonus = 0.42 if code and re.search(rf"\b{re.escape(code)}\b", haystack) else 0.0
        board_bonus = 0.07 if board and board in haystack else 0.0
        agency_bonus = 0.04 if agency and agency in haystack else 0.0
        year_bonus = 0.03 if year and year in haystack else 0.0
        result.score = round(min(1.0, similarity * 0.72 + code_bonus + board_bonus + agency_bonus + year_bonus), 4)
        scored.append(result)
    return sorted(scored, key=lambda item: item.score, reverse=True)


def _extract_answer(text: str, raw_html: str = "") -> str:
    upper = text.upper()
    patterns = [
        r"(?:GABARITO(?:\s+OFICIAL(?:\s+DA\s+BANCA)?)?|RESPOSTA(?:\s+CORRETA)?|ALTERNATIVA\s+CORRETA)\s*[:\-–]?\s*(?:LETRA\s*)?([A-E])\b",
        r"(?:GABARITO(?:\s+OFICIAL(?:\s+DA\s+BANCA)?)?|RESPOSTA)\s*[:\-–]?\s*(CERTO|CORRETO|VERDADEIRO|ERRADO|INCORRETO|FALSO)\b",
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, upper)
        if match:
            value = match.group(1)
            return value if index == 0 else ("C" if value in {"CERTO", "CORRETO", "VERDADEIRO"} else "E")

    # Muitos bancos mantêm o gabarito em JSON ou atributos HTML, mesmo quando o
    # texto visível esconde a letra até o usuário responder.
    html_upper = html.unescape(raw_html or "").upper()
    hidden_patterns = [
        r'"(?:CORRECT[_-]?ANSWER|RIGHT[_-]?ANSWER|ANSWER|GABARITO)"\s*:\s*"(?:LETRA\s*)?([A-E])"',
        r'(?:DATA-(?:CORRECT-)?ANSWER|DATA-GABARITO|CORRECT-OPTION)\s*=\s*["\'](?:LETRA\s*)?([A-E])["\']',
        r'"(?:CORRECT[_-]?ANSWER|RIGHT[_-]?ANSWER|GABARITO)"\s*:\s*"(CERTO|CORRETO|VERDADEIRO|ERRADO|INCORRETO|FALSO)"',
    ]
    for index, pattern in enumerate(hidden_patterns):
        match = re.search(pattern, html_upper, re.I)
        if match:
            value = match.group(1).upper()
            return value if index < 2 else ("C" if value in {"CERTO", "CORRETO", "VERDADEIRO"} else "E")
    return ""

def _semantic_line(value: str) -> str:
    """Remove marcadores visuais do Modo IA sem apagar letras das alternativas."""
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = re.sub(r"^[#>*•·▪▫◦‣⁃✓✔✗✘❌✅📋📝📌📍📚📖🔎💡⚠️ℹ️\-–—]+\s*", "", value)
    value = re.sub(r"^\d+[.)]\s+(?=[A-Za-zÀ-ÿ])", "", value)
    value = value.strip(" *_`~")
    return value.strip()


def _extract_alternatives(text: str) -> list[dict]:
    raw_lines = [line for line in text.splitlines() if str(line).strip()]
    lines = [_semantic_line(line) for line in raw_lines]
    lines = [line for line in lines if line]
    alternatives: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        inline = re.match(
            r"^(?:Alternativa\s+)?\(?([A-E])\)?\s*[).;:\-–—]\s*(.+)$",
            line,
            re.I,
        )
        if inline:
            alternatives.append({"chave": inline.group(1).upper(), "texto": inline.group(2).strip()})
            index += 1
            continue
        standalone = re.fullmatch(r"(?:Alternativa\s+)?\(?([A-E])\)?", line, re.I)
        if standalone and index + 1 < len(lines):
            key = standalone.group(1).upper()
            pieces: list[str] = []
            cursor = index + 1
            while cursor < len(lines):
                next_line = lines[cursor]
                if re.fullmatch(r"(?:Alternativa\s+)?\(?[A-E]\)?", next_line, re.I):
                    break
                if re.match(r"^(?:Alternativa\s+)?\(?[A-E]\)?\s*[).;:\-–—]\s*", next_line, re.I):
                    break
                if re.search(
                    r"^(?:GABARITO|RESPOSTA|JUSTIFICATIVA|EXPLICAÇÃO|RESOLUÇÃO|COMENTÁRIOS?|PRÓXIMAS QUESTÕES)",
                    next_line,
                    re.I,
                ):
                    break
                pieces.append(next_line)
                cursor += 1
            if pieces:
                alternatives.append({"chave": key, "texto": " ".join(pieces).strip()})
                index = cursor
                continue
        index += 1
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in alternatives:
        key = item["chave"]
        if key in seen or not item["texto"]:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:12]


def _extract_justification(text: str) -> str:
    """Extrai comentário/justificativa quando a página o disponibiliza."""
    lines = [_semantic_line(line) for line in text.splitlines() if str(line).strip()]
    lines = [line for line in lines if line]
    start_patterns = (
        r"^(?:JUSTIFICATIVA|COMENTÁRIO(?:\s+DO\s+PROFESSOR)?|GABARITO\s+COMENTADO|EXPLICAÇÃO|RESOLUÇÃO)\s*[:\-–]?\s*(.*)$",
        r"^(?:COMENTÁRIOS?\s+DA\s+QUESTÃO|FUNDAMENTAÇÃO)\s*[:\-–]?\s*(.*)$",
    )
    stop = re.compile(r"^(?:PRÓXIMAS QUESTÕES|AULAS|ESTATÍSTICAS|CADERNOS|CRIAR ANOTAÇÕES|NOTIFICAR ERRO|OUTRAS QUESTÕES|ALTERNATIVAS)$", re.I)
    for index, line in enumerate(lines):
        remainder = ""
        matched = False
        for pattern in start_patterns:
            match = re.match(pattern, line, re.I)
            if match:
                remainder = match.group(1).strip()
                matched = True
                break
        if not matched:
            continue
        pieces = [remainder] if remainder else []
        for following in lines[index + 1:index + 18]:
            if stop.match(following):
                break
            if re.match(r"^(?:A|B|C|D|E)\s*[).:-]", following, re.I):
                break
            pieces.append(following)
            if len(" ".join(pieces)) >= 2500:
                break
        value = re.sub(r"\s+", " ", " ".join(pieces)).strip()
        if len(value) >= 25:
            return value[:4000]
    return ""


_COMMENTARY_NOISE_RE = re.compile(
    r"^(?:Informações(?: da Questão| Gerais)?|Enunciado(?: da Questão)?|Texto da questão|Alternativas|"
    r"Banca\s*:|Ano\s*:|Órgão\s*:|Prova\s*:|Cargo\s*:|Área\s*:|Especialidade\s*:|Turno\s*:|Matéria\s*:|Assunto\s*:|"
    r"Fontes|Saiba mais|Mostrar mais|Compartilhar|Feedback|Mais resultados|Resultados da Web|Pesquisas relacionadas|"
    r"As pessoas também perguntam|Perguntas relacionadas|Próximas questões|Estatísticas|Cadernos|Criar anotações|Notificar erro)\b",
    re.I,
)


def _clean_commentary_fragment(value: str) -> tuple[str, int]:
    """Remove UI/metadados do Google sem reescrever o conteúdo substantivo."""
    kept: list[str] = []
    removed = 0
    for raw in str(value or "").splitlines():
        line = _semantic_line(raw)
        if not line:
            continue
        if _COMMENTARY_NOISE_RE.match(line):
            removed += 1
            continue
        if re.match(r"^(?:A|B|C|D|E)\s*[).:\-–—]\s+", line, re.I):
            removed += 1
            continue
        if re.fullmatch(r"(?:A|B|C|D|E|CERTO|ERRADO|CORRETO|INCORRETO)", line, re.I):
            removed += 1
            continue
        kept.append(line)
    text = re.sub(r"\s+", " ", " ".join(kept)).strip()
    # Marcadores que pertencem ao campo, não à fundamentação.
    text = re.sub(
        r"^(?:Gabarito(?: oficial)?|Resposta(?: correta)?|Alternativa correta)\s*[:\-–—]?\s*"
        r"(?:letra\s*)?(?:[A-E]|Certo|Errado|Correto|Incorreto)\b\s*[.\-–—:]*\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    return text[:4200], removed


def _commentary_quality(text: str, question: dict, *, method: str, removed_noise: int = 0) -> float:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) < 25:
        return 0.0
    statement = str(question.get("enunciado") or "")
    q_words = set(word.casefold() for word in _meaningful_words(statement, 24))
    t_words = set(word.casefold() for word in _meaningful_words(clean, 60))
    overlap = len(q_words & t_words) / max(1, min(len(q_words), 18))
    explanatory = bool(re.search(
        r"\b(porque|pois|portanto|assim|logo|decorre|significa|consiste|ocorre|razão|fundament|"
        r"corret[ao]|incorret[ao]|verdadeir[ao]|fals[ao]|de acordo|nos termos|conforme|uma vez que)\b",
        clean,
        re.I,
    ))
    base = 0.48
    if method.startswith("heading"):
        base = 0.80
    elif method.startswith("answer_context"):
        base = 0.68
    elif method.startswith("semantic_sentence"):
        base = 0.56
    length_bonus = min(0.08, max(0.0, (len(clean) - 60) / 1800.0))
    score = base + min(0.08, overlap * 0.12) + (0.05 if explanatory else 0.0) + length_bonus
    if removed_noise >= 4:
        score -= min(0.10, removed_noise * 0.01)
    if _COMMENTARY_NOISE_RE.search(clean):
        score -= 0.12
    return round(max(0.0, min(1.0, score)), 4)


def _commentary_is_substantive(value: str) -> bool:
    """Distingue explicação útil de rótulos/metadados curtos sem impor estilo textual."""
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(clean) < 24:
        return False
    if _COMMENTARY_NOISE_RE.fullmatch(clean):
        return False
    words = re.findall(r"[A-Za-zÀ-ÿ]{3,}", clean)
    return len(words) >= 5


def _extract_focused_commentary(block: str, question: dict, answer: str = "") -> dict:
    """Extrai a justificativa e *preserva* uma resposta real mesmo com confiança baixa.

    A 6.8.0 original tratava a confiança como filtro binário. Isso fazia uma
    justificativa verdadeira desaparecer quando o Google mudava a forma de redigir.
    Aqui, confiança volta a ser um indicador: se a seção é explicitamente uma
    explicação ou está imediatamente ligada ao gabarito, o texto limpo é retornado.
    """
    explicit = _section_after_heading(
        block,
        r"Justificativa|Explicação|Resolução|Gabarito comentado|Fundamentação|Comentário(?: do professor)?",
        (
            "Enunciado", "Enunciado da Questão", "Alternativas", "Gabarito", "Resposta", "Informações da Questão",
            "Informações Gerais", "Fontes", "Saiba mais", "Mais resultados", "Pesquisas relacionadas", "Feedback",
        ),
    ) or _extract_justification(block)
    if explicit:
        clean, removed = _clean_commentary_fragment(explicit)
        confidence = _commentary_quality(clean, question, method="heading_explicit", removed_noise=removed)
        if _commentary_is_substantive(clean):
            return {"text": clean, "confidence": confidence, "method": "heading_explicit", "noise_removed": removed}

    lines = [_semantic_line(x) for x in str(block or "").splitlines() if str(x).strip()]
    lines = [x for x in lines if x]
    answer_marker = re.compile(
        r"^(?:Gabarito(?: oficial)?|Resposta(?: correta)?|Alternativa correta)\s*[:\-–—]?\s*"
        r"(?:letra\s*)?(?:[A-E]|Certo|Errado|Correto|Incorreto)\b",
        re.I,
    )
    natural_answer_marker = re.compile(
        r"^(?:A\s+)?(?:resposta|alternativa)\s+correta\s+(?:é|e)\s+(?:a\s+)?(?:alternativa\s+)?[A-E]\b",
        re.I,
    )
    for idx, line in enumerate(lines):
        match = answer_marker.search(line) or natural_answer_marker.search(line)
        if not match:
            continue
        pieces: list[str] = []
        removed = 0
        # Importante: o Google costuma devolver "Gabarito: C. Isso porque..." na
        # MESMA linha. O Hotfix 2 ignorava esse sufixo e depois dizia não ter achado.
        inline = line[match.end():].lstrip(" .:;-–—")
        if inline:
            pieces.append(inline)
        for following in lines[idx + 1:idx + 12]:
            if re.match(r"^(?:Enunciado|Alternativas|Informações|Fontes|Saiba mais|Mais resultados|Pesquisas relacionadas|Feedback)\b", following, re.I):
                if pieces:
                    break
                removed += 1
                continue
            if re.match(r"^(?:A|B|C|D|E)\s*[).:\-–—]\s+", following, re.I):
                removed += 1
                continue
            if _COMMENTARY_NOISE_RE.match(following):
                removed += 1
                continue
            pieces.append(following)
            if len(" ".join(pieces)) >= 2200:
                break
        clean, extra_removed = _clean_commentary_fragment("\n".join(pieces))
        removed += extra_removed
        confidence = _commentary_quality(clean, question, method="answer_context", removed_noise=removed)
        if _commentary_is_substantive(clean):
            return {"text": clean, "confidence": confidence, "method": "answer_context", "noise_removed": removed}

    # Último recurso controlado: poucas sentenças explicativas, nunca o bloco integral.
    compact = re.sub(r"\s+", " ", str(block or "")).strip()
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])", compact)
    meaningful = {w.casefold() for w in _meaningful_words(str(question.get("enunciado") or ""), 24)}
    chosen: list[str] = []
    for sentence in sentences:
        candidate, removed = _clean_commentary_fragment(sentence)
        if removed or len(candidate) < 35 or _COMMENTARY_NOISE_RE.match(candidate):
            continue
        words = {w.casefold() for w in _meaningful_words(candidate, 40)}
        overlap = len(words & meaningful)
        explanatory = bool(re.search(
            r"\b(porque|pois|portanto|assim|decorre|consiste|significa|correta|incorreta|verdadeira|falsa|"
            r"de acordo|nos termos|conforme|uma vez que|isso porque|desse modo|dessa forma)\b",
            candidate,
            re.I,
        ))
        if explanatory and (overlap >= 1 or not meaningful):
            chosen.append(candidate)
        if len(chosen) >= 5:
            break
    clean = " ".join(chosen).strip()
    confidence = _commentary_quality(clean, question, method="semantic_sentence", removed_noise=0)
    if _commentary_is_substantive(clean) and confidence >= _COMMENTARY_ACCEPT_CONFIDENCE:
        return {"text": clean[:3400], "confidence": confidence, "method": "semantic_sentence", "noise_removed": 0}
    return {"text": "", "confidence": confidence, "method": "none", "noise_removed": 0}


def _extract_metadata(text: str, code: str = "", raw_html: str = "") -> dict:
    metadata: dict = {}
    year = re.search(r"\bAno\s*:\s*((?:19|20)\d{2})\b", text, re.I)
    if not year:
        year = re.search(r"\b(?:19|20)\d{2}\b", text)
    if year:
        metadata["ano"] = int(year.group(1) if year.lastindex else year.group(0))
    for field, label in (("banca", "Banca"), ("orgao", "Órgão"), ("prova", "Prova")):
        match = re.search(
            rf"\b{label}\s*:\s*(.*?)(?=\s+(?:Ano|Banca|Órgão|Prova)\s*:|\||\n|$)",
            text,
            re.I,
        )
        if match:
            metadata[field] = re.sub(r"\s+", " ", match.group(1)).strip(" |-")
    subject_match = re.search(rf"\b{re.escape(code)}\s+([^\n|]+)", text, re.I) if code else None
    if subject_match:
        subject = subject_match.group(1).strip()
        subject = re.split(r"\b(?:Ano|Banca|Órgão|Prova)\s*:", subject, maxsplit=1, flags=re.I)[0].strip()
        if 2 <= len(subject) <= 120:
            metadata["materia_web"] = subject
    answer = _extract_answer(text, raw_html)
    if answer:
        metadata["gabarito"] = answer
    justification = _extract_justification(text)
    if justification:
        metadata["justificativa"] = justification
    return metadata

def _isolate_question_blocks(text: str, code: str, original_statement: str = "") -> list[str]:
    if not code:
        phrase = re.sub(r"\s+", " ", str(original_statement or "")).strip()[:120]
        if phrase:
            match = re.search(re.escape(phrase), re.sub(r"\s+", " ", text), re.I)
            if match:
                compact = re.sub(r"\s+", " ", text)
                return [compact[max(0, match.start() - 700): min(len(compact), match.end() + 12_000)]]
        return [text]
    matches = list(re.finditer(rf"\b{re.escape(code)}\b", text, re.I))
    if not matches:
        return [text]
    all_codes = list(re.finditer(r"\bQ\d{5,10}\b", text, re.I))
    blocks: list[str] = []
    for match in matches:
        start = max(0, match.start() - 600)
        end = min(len(text), match.end() + 18_000)
        for other in all_codes:
            if other.start() > match.end() + 20:
                end = min(end, other.start())
                break
        blocks.append(text[start:end])
    return blocks or [text]


def _extract_statement(block: str, alternatives: list[dict], original_statement: str) -> str:
    # Em páginas de bancos, o enunciado fica entre os metadados e "Alternativas".
    marker = re.search(r"\bAlternativas\b", block, re.I)
    prefix = block[:marker.start()] if marker else block
    lines = [line.strip() for line in prefix.splitlines() if line.strip()]
    filtered: list[str] = []
    for line in lines:
        if re.search(r"^(?:Próximas questões|Com base no mesmo assunto|Ano:|Banca:|Órgão:|Prova:|Q\d+\s+[^.]+)$", line, re.I):
            continue
        if re.search(r"^(?:Responder|Questões de Concurso|Gabarito Comentado|Aulas|Comentários|Estatísticas)$", line, re.I):
            continue
        filtered.append(line)
    candidate = " ".join(filtered[-8:]).strip()
    # Para páginas de material didático com a questão em uma só linha.
    if alternatives:
        first_alt = alternatives[0]["texto"]
        position = candidate.lower().find(first_alt[:30].lower()) if first_alt else -1
        if position > 0:
            candidate = candidate[:position].strip()
    if original_statement and _statement_similarity(original_statement, candidate) < 0.35:
        # Use uma janela do texto que mais se aproxima do enunciado existente.
        normalized_original = _normalize(original_statement)
        first_words = " ".join(normalized_original.split()[:10])
        match = re.search(re.escape(first_words), _normalize(block), re.I) if first_words else None
        if match:
            candidate = original_statement
    return re.sub(r"\s+", " ", candidate).strip()


def _normalized_board_tokens(value: str) -> set[str]:
    normalized = _normalize(value).upper()
    aliases = {
        "CESPE": "CEBRASPE",
        "CESPE CEBRASPE": "CEBRASPE",
        "CESPE/CEBRASPE": "CEBRASPE",
        "CEBRASPE CESPE": "CEBRASPE",
    }
    compact = re.sub(r"[^A-Z0-9]+", " ", normalized).strip()
    canonical = aliases.get(compact, compact)
    tokens = {item for item in canonical.split() if len(item) >= 2}
    if "CESPE" in tokens or "CEBRASPE" in tokens:
        tokens.update({"CESPE", "CEBRASPE"})
    return tokens


def _board_confirmed(expected: str, candidate_text: str, extracted: str = "") -> bool:
    expected_tokens = _normalized_board_tokens(expected)
    if not expected_tokens:
        return False
    candidate_tokens = _normalized_board_tokens(f"{extracted} {candidate_text}")
    return bool(expected_tokens & candidate_tokens)


def _year_confirmed(expected, candidate_text: str, extracted=None) -> bool:
    try:
        expected_year = int(expected)
    except (TypeError, ValueError):
        return False
    if extracted not in (None, ""):
        try:
            if int(extracted) == expected_year:
                return True
        except (TypeError, ValueError):
            pass
    return bool(re.search(rf"\b{expected_year}\b", candidate_text))


def parse_candidate_question(
    raw_html: str,
    question: dict,
    *,
    url: str = "",
    provider: str = "",
    source_kind: str = "page",
) -> dict:
    text = _html_to_lines(raw_html)
    code = _usable_question_code(question)
    original_statement = str(question.get("enunciado", "")).strip()
    expected_board = str(question.get("banca", "")).strip()
    expected_year = question.get("ano")
    best: dict = {}
    for block in _isolate_question_blocks(text, code, original_statement):
        alternatives = _extract_alternatives(block)
        statement = _extract_statement(block, alternatives, original_statement)
        similarity = _statement_similarity(original_statement, block)
        exact_code = bool(code and re.search(rf"\b{re.escape(code)}\b", block, re.I))
        metadata = _extract_metadata(block, code, raw_html if source_kind == "page" else "")
        board_match = _board_confirmed(expected_board, block, str(metadata.get("banca", "")))
        year_match = _year_confirmed(expected_year, block, metadata.get("ano"))
        metadata_confirmed = bool(board_match and year_match)
        statement_confirmed = similarity >= (0.48 if exact_code else 0.82)
        page_opened = source_kind == "page"
        verified = bool(page_opened and metadata_confirmed and statement_confirmed)
        answer_on_page = bool(page_opened and metadata.get("gabarito"))
        justification_on_page = bool(page_opened and metadata.get("justificativa"))
        score = (
            similarity * 0.54
            + (0.20 if exact_code else 0.0)
            + (0.10 if board_match else 0.0)
            + (0.08 if year_match else 0.0)
            + (0.04 if answer_on_page else 0.0)
            + (0.04 if justification_on_page else 0.0)
        )
        candidate = {
            "url": url,
            "provider": provider,
            "source_kind": source_kind,
            "page_opened": page_opened,
            "exact_code": exact_code,
            "statement_similarity": round(similarity, 4),
            "statement_confirmed": statement_confirmed,
            "board_match": board_match,
            "year_match": year_match,
            "metadata_confirmed": metadata_confirmed,
            "answer_on_page": answer_on_page,
            "justification_on_page": justification_on_page,
            "verified": verified,
            "score": round(min(1.0, score), 4),
            "statement": statement,
            "alternatives": alternatives,
            **metadata,
        }
        if not best or candidate["score"] > best.get("score", 0):
            best = candidate
    return best

def _fetch_candidate_html(url: str, *, timeout: int = 12) -> str:
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        return _request_text(url, timeout=timeout, max_bytes=1_200_000)
    except Exception:
        return ""


def _candidate_to_structured(candidate: dict) -> dict:
    structured: dict = {}
    mapping = {
        "ano": "ano", "banca": "banca", "orgao": "orgao", "prova": "prova",
        "cargo": "cargo", "area": "area", "especialidade": "especialidade", "turno": "turno",
        "materia_web": "materia", "assunto_web": "assunto",
        "gabarito": "gabarito", "statement": "enunciado", "alternatives": "alternativas",
        "justificativa": "explicacao",
    }
    for source, target in mapping.items():
        value = candidate.get(source)
        if value not in (None, "", []):
            structured[target] = value
    if structured.get("alternativas"):
        structured["tipo"] = "certo_errado" if {
            item.get("chave") for item in structured["alternativas"]
        } == {"C", "E"} else "multipla_escolha"
    return structured

def _search_stage(
    question: dict,
    queries: list[str],
    *,
    stage: str,
    max_results: int,
) -> dict:
    merged: dict[str, SearchResult] = {}
    errors: list[str] = []
    executed_queries: list[str] = []
    for query in queries:
        executed_queries.append(query)
        try:
            found = search_web(query, timeout=11, max_results=max(max_results, _MAX_LINKS_PER_STAGE))
        except Exception as error:
            errors.append(f"{stage}: {error}")
            continue
        for result in found:
            current = merged.get(result.url)
            if current is None or len(result.snippet) > len(current.snippet):
                merged[result.url] = result
        if len(merged) >= max(_MIN_LINKS_PER_STAGE, max_results):
            break

    results = score_results(question, merged.values())[:max(1, min(max(max_results, _MAX_LINKS_PER_STAGE), 40))]
    candidates: list[dict] = []
    attempted_links: list[dict] = []
    verified_found = False
    target_limit = min(_MAX_LINKS_PER_STAGE, len(results))
    for index, result in enumerate(results[:target_limit]):
        raw = _fetch_candidate_html(result.url, timeout=15)
        attempt = {
            "position": index + 1,
            "url": result.url,
            "provider": result.provider,
            "opened": bool(raw),
            "verified": False,
            "answer_found": False,
            "justification_found": False,
        }
        if raw:
            candidate = parse_candidate_question(
                raw,
                question,
                url=result.url,
                provider=result.provider,
                source_kind="page",
            )
            if candidate:
                candidate["search_stage"] = stage
                candidates.append(candidate)
                attempt.update({
                    "verified": bool(candidate.get("verified")),
                    "answer_found": bool(candidate.get("answer_on_page")),
                    "justification_found": bool(candidate.get("justification_on_page")),
                    "board_confirmed": bool(candidate.get("board_match")),
                    "year_confirmed": bool(candidate.get("year_match")),
                    "statement_similarity": float(candidate.get("statement_similarity", 0) or 0),
                })
                verified_found = verified_found or bool(candidate.get("verified"))
        attempted_links.append(attempt)

        # Sempre abre pelo menos cinco links quando disponíveis. Se ainda não houve
        # confirmação, continua até dez antes de recorrer ao enunciado.
        if index + 1 >= _MIN_LINKS_PER_STAGE and verified_found:
            break

    # Snippets são exibidos para diagnóstico, mas nunca confirmam nem fornecem gabarito.
    for result in results:
        snippet_candidate = parse_candidate_question(
            f"<div>{html.escape(result.title)}</div><div>{html.escape(result.snippet)}</div>",
            question,
            url=result.url,
            provider=result.provider,
            source_kind="snippet",
        )
        if snippet_candidate:
            snippet_candidate["search_stage"] = stage
            candidates.append(snippet_candidate)
    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    verified = [item for item in candidates if item.get("verified")]
    return {
        "stage": stage,
        "queries": executed_queries,
        "results": results,
        "candidates": candidates,
        "verified_candidates": verified,
        "attempted_links": attempted_links,
        "errors": errors,
    }

def _google_overview_block(page_text: str, code: str = "") -> str:
    """Isola o bloco do Modo IA mesmo quando os títulos possuem ícones/markdown."""
    raw_lines = [line for line in str(page_text or "").splitlines() if str(line).strip()]
    lines = [_semantic_line(line) for line in raw_lines]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    marker_index = None
    headings = re.compile(
        r"^(?:Informações (?:da Questão|Gerais)|Enunciado(?: da Questão)?|Texto da questão|"
        r"Alternativas|Gabarito|Justificativa|Explicação|Resolução)$",
        re.I,
    )
    for index, line in enumerate(lines):
        if headings.search(line):
            marker_index = index
            break
    if marker_index is None and code:
        for index, line in enumerate(lines):
            if re.search(rf"\b{re.escape(code)}\b", line, re.I):
                marker_index = index
                break
    if marker_index is None:
        # Respostas sem título explícito ainda podem ser reconhecidas pela presença
        # conjunta de banca, ano e enunciado.
        for index, line in enumerate(lines):
            window = "\n".join(lines[index:index + 30])
            if re.search(r"\bBanca\s*:", window, re.I) and re.search(r"\bAno\s*:", window, re.I):
                marker_index = index
                break
    if marker_index is None:
        # O Modo IA frequentemente obedece à instrução de não repetir metadados e
        # devolve diretamente "A alternativa correta..."/"Isso porque...". Nessa
        # forma não há código, banca, ano nem título formal, mas a resposta já está
        # no DOM. Reconhecemos o início sem exigir que o Google repita a pergunta.
        direct_answer = re.compile(
            r"\b(?:gabarito|resposta correta|alternativa correta|item (?:está|e) (?:correto|incorreto)|"
            r"afirmativa (?:está|e) (?:correta|incorreta)|isso porque|a justificativa|portanto|pois)\b",
            re.I,
        )
        for index, line in enumerate(lines):
            if direct_answer.search(line):
                marker_index = index
                break
    if marker_index is None:
        return ""

    start = max(0, marker_index - 6)
    stop_markers = re.compile(
        r"^(?:As pessoas também perguntam|Mais resultados|Pesquisas relacionadas|Vídeos|Imagens|"
        r"Resultados da Web|Sobre resultados destacados|Feedback|Perguntas relacionadas)$",
        re.I,
    )
    selected: list[str] = []
    for line in lines[start:start + 220]:
        if selected and stop_markers.match(line):
            break
        selected.append(line)
    return "\n".join(selected)


def _section_after_heading(block: str, heading: str, stops: tuple[str, ...]) -> str:
    lines = [_semantic_line(line) for line in block.splitlines() if str(line).strip()]
    lines = [line for line in lines if line]
    start = None
    heading_re = re.compile(r"^(?:" + heading + r")\s*[:\-–—]?\s*(.*)$", re.I)
    inline_remainder = ""
    for index, line in enumerate(lines):
        match = heading_re.match(line)
        if match:
            start = index + 1
            inline_remainder = match.group(1).strip()
            break
    if start is None:
        return ""
    pieces: list[str] = [inline_remainder] if inline_remainder else []
    stop_re = re.compile(r"^(?:" + "|".join(stops) + r")\s*[:\-–—]?", re.I)
    for line in lines[start:]:
        if stop_re.match(line):
            break
        pieces.append(line)
    return re.sub(r"\s+", " ", " ".join(pieces)).strip()


def parse_google_search_page(page_text: str, page_html: str, question: dict, *, search_url: str) -> dict:
    """Lê a resposta exibida na própria página renderizada do Google."""
    code = _usable_question_code(question)
    block = _google_overview_block(page_text, code)
    if not block:
        return {}

    original_statement = str(question.get("enunciado", "")).strip()
    expected_board = str(question.get("banca", "")).strip()
    expected_year = question.get("ano")
    metadata = _extract_metadata(block, code, page_html)
    answer = _extract_answer(block, page_html)
    focused = _extract_focused_commentary(block, question, answer)
    justification = str(focused.get("text") or "")
    statement = _section_after_heading(
        block,
        r"Enunciado(?: da Questão)?|Texto da questão",
        ("Alternativas", "Gabarito", "Justificativa", "Explicação", "Resolução", "Informações da Questão", "Informações Gerais", "Fontes"),
    )
    alternatives = _extract_alternatives(block)
    similarity = _statement_similarity(original_statement, statement or block)
    exact_code = bool(code and re.search(rf"\b{re.escape(code)}\b", block, re.I))
    board_match = _board_confirmed(expected_board, block, str(metadata.get("banca", "")))
    year_match = _year_confirmed(expected_year, block, metadata.get("ano"))
    metadata_confirmed = bool(board_match and year_match)
    statement_confirmed = bool(similarity >= 0.68 or (exact_code and similarity >= 0.18))
    verified = bool(metadata_confirmed and ((code and exact_code) or (not code and similarity >= 0.72)))
    score = min(
        1.0,
        similarity * 0.38
        + (0.28 if exact_code else 0.0)
        + (0.13 if board_match else 0.0)
        + (0.11 if year_match else 0.0)
        + (0.05 if answer else 0.0)
        + (0.05 if justification else 0.0),
    )
    extra_labels = {
        "cargo": r"Cargo",
        "area": r"Área|Area",
        "especialidade": r"Especialidade",
        "turno": r"Turno",
        "materia_web": r"Matéria|Materia",
        "assunto_web": r"Assunto",
    }
    for field, label in extra_labels.items():
        match = re.search(rf"(?mi)^\s*(?:{label})\s*:\s*(.+?)\s*$", block)
        if match:
            metadata[field] = re.sub(r"\s+", " ", match.group(1)).strip(" |-•")
    cargo_value = str(metadata.get("cargo", ""))
    cargo_area = re.search(r"^(.*?)\s*[–—-]\s*Área\s*:\s*(.+)$", cargo_value, re.I)
    if cargo_area:
        metadata["cargo"] = cargo_area.group(1).strip(" -–—")
        metadata.setdefault("area", cargo_area.group(2).strip(" -–—"))

    candidate = {
        "url": search_url,
        "provider": "Google – página carregada",
        "source_kind": "google_search_page",
        "page_opened": True,
        "exact_code": exact_code,
        "statement_similarity": round(similarity, 4),
        "statement_confirmed": statement_confirmed,
        "board_match": board_match,
        "year_match": year_match,
        "metadata_confirmed": metadata_confirmed,
        "answer_on_page": bool(answer),
        "justification_on_page": bool(justification),
        "explanation_confidence": float(focused.get("confidence", 0) or 0),
        "explanation_method": str(focused.get("method") or "none"),
        "noise_removed": int(focused.get("noise_removed", 0) or 0),
        "verified": verified,
        "score": round(score, 4),
        "statement": statement,
        "alternatives": alternatives,
        "gabarito": answer,
        "justificativa": justification,
        "google_overview_text": block,
        **metadata,
    }
    if answer:
        candidate["gabarito"] = answer
    if justification:
        candidate["justificativa"] = justification
    return candidate


def _google_browser_stage(
    question: dict,
    query: str,
    *,
    stage: str,
    max_results: int,
) -> dict:
    """Executa uma única consulta no Modo IA e não abre resultados externos."""
    if not query:
        return {
            "stage": stage, "queries": [], "results": [], "candidates": [],
            "verified_candidates": [], "attempted_links": [], "errors": [],
        }

    profile = Path(__file__).resolve().parent.parent / "data" / "google_browser_profile"
    browser_data = run_visible_google_ai_search(
        query,
        profile_dir=profile,
        wait_seconds=75,
        captcha_wait_seconds=180,
        reuse_session=True,
    )
    capture_retries = 0
    search_url = str(browser_data.get("search_url", ""))
    search_candidate = parse_google_search_page(
        str(browser_data.get("search_text", "")),
        str(browser_data.get("search_html", "")),
        question,
        search_url=search_url,
    )
    if search_candidate:
        code = _usable_question_code(question)
        query_has_exact_code = bool(code and re.search(rf"\b{re.escape(code)}\b", query, re.I))
        query_code_anchored = bool(stage == "codigo" and query_has_exact_code and browser_data.get("ai_mode_activated"))
        original_statement = re.sub(r"\s+", " ", str(question.get("enunciado") or "")).strip().rstrip(" ,.;:")
        query_without_directive = re.sub(re.escape(_SEARCH_DIRECTIVE), " ", str(query or ""), flags=re.I)
        query_without_directive = re.sub(r"^[\s\"']+|[\s\"']+$", "", query_without_directive).strip()
        query_statement_similarity = _statement_similarity(original_statement, query_without_directive) if original_statement else 0.0
        query_statement_anchored = bool(
            str(stage).startswith("enunciado")
            and browser_data.get("ai_mode_activated")
            and query_statement_similarity >= (0.72 if stage == "enunciado" else 0.52)
        )
        query_anchored = bool(query_code_anchored or query_statement_anchored)
        search_candidate["query_anchored"] = query_anchored
        search_candidate["query_statement_similarity"] = round(query_statement_similarity, 4)
        # Hotfix 4: o contexto da CONSULTA também é uma evidência de vínculo. Se o
        # QuestFlow enviou o código exato ou o próprio enunciado e o Modo IA devolveu
        # um bloco substantivo de gabarito/explicação, não exigimos que o Google
        # repita código, banca e ano dentro da resposta. A diretiva, inclusive, pede
        # explicitamente para não repetir esses metadados.
        if (
            query_anchored
            and str(search_candidate.get("justificativa") or "").strip()
            and _commentary_is_substantive(str(search_candidate.get("justificativa") or ""))
        ):
            search_candidate["verified"] = True
            search_candidate["verification_method"] = (
                "exact_code_query_context" if query_code_anchored else "statement_query_context"
            )
            if query_statement_anchored:
                search_candidate["statement_confirmed"] = True
    first_capture_usable = bool(
        search_candidate
        and search_candidate.get("verified")
        and _commentary_is_substantive(str(search_candidate.get("justificativa") or ""))
    )
    # Só repete a consulta quando a primeira captura realmente não contém uma
    # explicação útil. Antes, qualquer flag de 'unstable' disparava outra navegação
    # completa mesmo quando o texto correto já estava no DOM.
    if (
        not first_capture_usable
        and not bool(browser_data.get("blocked"))
        and (not bool(browser_data.get("ai_answer_stable")) or not str(browser_data.get("search_text") or "").strip())
    ):
        capture_retries = 1
        retry_data = run_visible_google_ai_search(
            query,
            profile_dir=profile,
            wait_seconds=60,
            captcha_wait_seconds=180,
            reuse_session=True,
        )
        retry_url = str(retry_data.get("search_url", ""))
        retry_candidate = parse_google_search_page(
            str(retry_data.get("search_text", "")),
            str(retry_data.get("search_html", "")),
            question,
            search_url=retry_url,
        )
        if retry_candidate:
            code = _usable_question_code(question)
            query_has_exact_code = bool(code and re.search(rf"\b{re.escape(code)}\b", query, re.I))
            query_code_anchored = bool(stage == "codigo" and query_has_exact_code and retry_data.get("ai_mode_activated"))
            original_statement = re.sub(r"\s+", " ", str(question.get("enunciado") or "")).strip().rstrip(" ,.;:")
            query_without_directive = re.sub(re.escape(_SEARCH_DIRECTIVE), " ", str(query or ""), flags=re.I)
            query_without_directive = re.sub(r"^[\s\"']+|[\s\"']+$", "", query_without_directive).strip()
            query_statement_similarity = _statement_similarity(original_statement, query_without_directive) if original_statement else 0.0
            query_statement_anchored = bool(
                str(stage).startswith("enunciado")
                and retry_data.get("ai_mode_activated")
                and query_statement_similarity >= (0.72 if stage == "enunciado" else 0.52)
            )
            query_anchored = bool(query_code_anchored or query_statement_anchored)
            retry_candidate["query_anchored"] = query_anchored
            retry_candidate["query_statement_similarity"] = round(query_statement_similarity, 4)
            if (
                query_anchored
                and str(retry_candidate.get("justificativa") or "").strip()
                and _commentary_is_substantive(str(retry_candidate.get("justificativa") or ""))
            ):
                retry_candidate["verified"] = True
                retry_candidate["verification_method"] = (
                    "exact_code_query_context" if query_code_anchored else "statement_query_context"
                )
                if query_statement_anchored:
                    retry_candidate["statement_confirmed"] = True
        retry_usable = bool(
            retry_candidate
            and retry_candidate.get("verified")
            and _commentary_is_substantive(str(retry_candidate.get("justificativa") or ""))
        )
        if (
            retry_usable
            or bool(retry_data.get("ai_answer_stable"))
            or len(str(retry_data.get("search_text") or "")) > len(str(browser_data.get("search_text") or ""))
        ):
            browser_data = retry_data
            search_url = retry_url
            search_candidate = retry_candidate
    candidates: list[dict] = []
    if search_candidate:
        search_candidate["search_stage"] = stage
        search_candidate["provider"] = "Google Modo IA"
        search_candidate["source_kind"] = "google_ai_page"
        search_candidate["ai_mode_activated"] = bool(browser_data.get("ai_mode_activated"))
        search_candidate["ai_answer_stable"] = bool(browser_data.get("ai_answer_stable"))
        candidates.append(search_candidate)

    results: list[SearchResult] = []
    if search_candidate:
        overview = str(search_candidate.get("google_overview_text", ""))
        results.append(SearchResult(
            title="Resposta exibida no Modo IA do Google",
            url=search_url,
            snippet=re.sub(r"\s+", " ", overview)[:800],
            score=float(search_candidate.get("score", 0) or 0),
            provider="Google Modo IA",
        ))
    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    verified = [item for item in candidates if item.get("verified")]
    errors: list[str] = []
    if not browser_data.get("ai_mode_activated"):
        errors.append("O navegador foi aberto, mas o Modo IA do Google não foi confirmado.")
    if browser_data.get("blocked"):
        if browser_data.get("captcha_browser_closed"):
            errors.append("A janela do Google foi fechada antes da conclusão da verificação de segurança.")
        elif browser_data.get("captcha_timed_out"):
            waited = int(float(browser_data.get("captcha_waited_seconds", 0) or 0))
            errors.append(
                f"A verificação de segurança do Google não foi concluída em {waited // 60 or 1} minuto(s)."
            )
        else:
            errors.append("O Google ainda exibe verificação de tráfego/CAPTCHA no navegador.")
    if not browser_data.get("ai_answer_stable"):
        errors.append("A resposta do Modo IA não ficou estável antes do limite de espera; revise a prévia.")
    for expand_error in browser_data.get("google_expand_errors", []):
        errors.append("Falha ao expandir a resposta do Google: " + str(expand_error))
    return {
        "stage": stage,
        "queries": [query],
        "results": results[:1],
        "candidates": candidates,
        "verified_candidates": verified,
        "attempted_links": [],
        "errors": errors,
        "browser": browser_data.get("browser", ""),
        "google_page_loaded": bool(browser_data.get("search_text")),
        "google_answer_expanded": bool(browser_data.get("google_answer_expanded")),
        "google_expand_clicks": int(browser_data.get("google_expand_clicks", 0) or 0),
        "google_expand_labels": list(browser_data.get("google_expand_labels", [])),
        "ai_mode_activated": bool(browser_data.get("ai_mode_activated")),
        "ai_answer_stable": bool(browser_data.get("ai_answer_stable")),
        "browser_reused": bool(browser_data.get("browser_reused")),
        "google_load_seconds": float(browser_data.get("load_seconds", 0) or 0),
        "capture_method": str(browser_data.get("capture_method", "")),
        "captured_chars": int(browser_data.get("captured_chars", 0) or 0),
        "capture_attempts": int(browser_data.get("capture_attempts", 0) or 0),
        "capture_retries": capture_retries,
        "answer_ready_reason": str(browser_data.get("answer_ready_reason", "")),
        "captcha_detected": bool(browser_data.get("captcha_detected")),
        "captcha_resolved": bool(browser_data.get("captcha_resolved")),
        "captcha_timed_out": bool(browser_data.get("captcha_timed_out")),
        "captcha_waited_seconds": float(browser_data.get("captcha_waited_seconds", 0) or 0),
        "captcha_browser_closed": bool(browser_data.get("captcha_browser_closed")),
    }


def enrich_question(
    question: dict,
    *,
    max_results: int = 12,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict:
    """Pesquisa no Google com Modo IA primário e contingência por fonte pública.

    A contingência só é usada quando o Modo IA não entrega uma justificativa
    verificável. Ela continua partindo do Google e exige correspondência segura
    da questão antes de aceitar qualquer comentário.
    """
    def report(value: float, message: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(float(value), str(message))
            except Exception:
                pass
    code_queries = build_code_search_queries(question)
    statement_queries = build_statement_search_queries(question)
    stages: list[dict] = []
    browser_errors: list[str] = []

    def empty_stage(name: str) -> dict:
        return {
            "stage": name, "queries": [], "results": [], "candidates": [],
            "verified_candidates": [], "attempted_links": [], "errors": [],
        }

    code_stage = empty_stage("codigo")
    if code_queries:
        report(0.38, "Consultando o Google Modo IA pelo código da questão…")
        try:
            code_stage = _google_browser_stage(
                question, code_queries[0], stage="codigo", max_results=max_results
            )
        except Exception as error:
            browser_errors.append(f"Google Modo IA (código): {error}")
            code_stage = empty_stage("codigo")
            code_stage["queries"] = code_queries[:1]
            code_stage["errors"] = [str(error)]
    stages.append(code_stage)
    report(0.50, "Consulta pelo código concluída; verificando correspondência e justificativa…")

    code_verified = list(code_stage.get("verified_candidates", []))

    def has_usable_commentary(stage_data: dict) -> bool:
        return any(
            bool(item.get("verified"))
            and _commentary_is_substantive(str(item.get("justificativa") or ""))
            for item in stage_data.get("candidates", [])
            if isinstance(item, dict)
        )

    # Mesmo com correspondência confirmada pelo código, faz fallback pelo enunciado
    # quando o Google carregou somente metadados/gabarito e não uma explicação limpa.
    need_statement_fallback = not code_verified or not has_usable_commentary(code_stage)

    statement_stage = empty_stage("enunciado")
    if need_statement_fallback and statement_queries:
        report(0.56, "A primeira resposta não trouxe justificativa suficiente; tentando pelo enunciado…")
        for index, statement_query in enumerate(statement_queries[:2]):
            stage_name = "enunciado" if index == 0 else "enunciado_amplo"
            try:
                current_stage = _google_browser_stage(
                    question, statement_query, stage=stage_name, max_results=max_results
                )
            except Exception as error:
                browser_errors.append(f"Google Modo IA ({stage_name}): {error}")
                current_stage = empty_stage(stage_name)
                current_stage["queries"] = [statement_query]
                current_stage["errors"] = [str(error)]
            stages.append(current_stage)
            statement_stage = current_stage
            report(0.64 + index * 0.03, "Consulta pelo enunciado concluída; validando a explicação capturada…")
            if has_usable_commentary(current_stage):
                break

    # Hotfix 2: se o Modo IA não devolveu comentário útil (mudança de layout,
    # resposta curta, indisponibilidade regional ou bloqueio), usa a própria
    # Pesquisa Google para localizar uma página pública correspondente e extrair
    # somente o gabarito comentado/justificativa. Nada é aceito por snippet.
    if not any(has_usable_commentary(item) for item in stages):
        report(0.70, "Modo IA sem explicação utilizável; procurando uma fonte pública correspondente no Google…")
        fallback_queries: list[str] = []
        code = _usable_question_code(question)
        if code:
            fallback_queries.append(f'"{code}"')
        statement = re.sub(r"\s+", " ", str(question.get("enunciado", "") or "")).strip().rstrip(" ,.;:")
        if statement:
            fallback_queries.append(f'"{statement[:300]}"')
        for index, fallback_query in enumerate(fallback_queries[:2]):
            fallback_stage_name = "google_web_codigo" if index == 0 and code else "google_web_enunciado"
            try:
                fallback_stage = _search_stage(
                    question, [fallback_query], stage=fallback_stage_name, max_results=min(6, max_results)
                )
            except Exception as error:
                browser_errors.append(f"Google Web ({fallback_stage_name}): {error}")
                fallback_stage = empty_stage(fallback_stage_name)
                fallback_stage["queries"] = [fallback_query]
                fallback_stage["errors"] = [str(error)]
            stages.append(fallback_stage)
            if has_usable_commentary(fallback_stage):
                report(0.82, "Fonte pública verificada encontrada; isolando somente a justificativa da questão…")
                break

    all_results_by_url: dict[str, SearchResult] = {}
    all_candidates: list[dict] = []
    query_errors: list[str] = browser_errors[:]
    executed_queries: list[str] = []
    attempted_links: list[dict] = []
    for stage_data in stages:
        executed_queries.extend(stage_data.get("queries", []))
        query_errors.extend(stage_data.get("errors", []))
        all_candidates.extend(stage_data.get("candidates", []))
        attempted_links.extend([
            {**item, "stage": stage_data.get("stage", "")}
            for item in stage_data.get("attempted_links", [])
        ])
        for result in stage_data.get("results", []):
            current = all_results_by_url.get(result.url)
            if current is None or result.score > current.score:
                all_results_by_url[result.url] = result

    verified_candidates = [item for item in all_candidates if item.get("verified")]
    verified_candidates.sort(key=lambda item: (
        item.get("search_stage") != "codigo",
        item.get("source_kind") != "google_ai_page",
        -float(item.get("score", 0)),
    ))
    best_candidate = verified_candidates[0] if verified_candidates else (
        max(all_candidates, key=lambda item: item.get("score", 0), default={})
    )

    answer_candidates = [
        item for item in verified_candidates
        if item.get("answer_on_page") and str(item.get("gabarito", "")).upper()
    ]
    answer = ""
    answer_sources: list[dict] = []
    if answer_candidates:
        votes: dict[str, list[dict]] = {}
        for candidate in answer_candidates:
            votes.setdefault(str(candidate.get("gabarito", "")).upper(), []).append(candidate)
        answer, answer_sources = max(
            votes.items(),
            key=lambda item: (
                len({entry.get("url") for entry in item[1]}),
                max(entry.get("score", 0) for entry in item[1]),
            ),
        )

    justification_candidates = [
        item for item in verified_candidates
        if item.get("justification_on_page")
        and _commentary_is_substantive(str(item.get("justificativa", "")))
    ]
    justification = ""
    justification_sources: list[dict] = []
    if justification_candidates:
        justification_candidates.sort(
            key=lambda item: (
                float(item.get("explanation_confidence", 0) or 0),
                float(item.get("score", 0) or 0),
                min(len(str(item.get("justificativa", ""))), 2200),
            ),
            reverse=True,
        )
        justification = str(justification_candidates[0].get("justificativa", "")).strip()
        justification_sources = justification_candidates

    structured = _candidate_to_structured(best_candidate)
    if answer:
        structured["gabarito"] = answer
    if justification:
        structured["explicacao"] = justification

    verified_match = bool(best_candidate.get("verified"))
    exact_code_match = bool(best_candidate.get("exact_code") and verified_match)
    metadata_confirmed = bool(best_candidate.get("metadata_confirmed") and verified_match)
    answer_confirmed = bool(answer and answer_sources)
    justification_confirmed = bool(justification and justification_sources)
    confidence = float(best_candidate.get("score", 0) or 0)
    safe_to_apply = bool(verified_match and metadata_confirmed)
    answer_source_url = str(answer_sources[0].get("url", "")) if answer_sources else ""
    justification_source_url = str(justification_sources[0].get("url", "")) if justification_sources else ""
    verified_source_url = answer_source_url or justification_source_url or (
        str(best_candidate.get("url", "")) if verified_match else ""
    )
    answer_search_stage = str(answer_sources[0].get("search_stage", "")) if answer_sources else ""
    stage_used = (
        str(justification_sources[0].get("search_stage", "")) if justification_sources
        else str(answer_sources[0].get("search_stage", "")) if answer_sources
        else str(best_candidate.get("search_stage", "")) if verified_match
        else ("enunciado" if statement_stage.get("queries") else "codigo")
    )

    return {
        "query": executed_queries[0] if executed_queries else "",
        "queries": executed_queries,
        "code_queries": code_stage.get("queries", []),
        "statement_queries": [
            query for stage_data in stages if str(stage_data.get("stage", "")).startswith("enunciado")
            for query in stage_data.get("queries", [])
        ],
        "search_stages": [
            {
                "stage": item.get("stage"),
                "queries": item.get("queries", []),
                "result_count": len(item.get("results", [])),
                "opened_count": sum(1 for attempt in item.get("attempted_links", []) if attempt.get("opened")),
                "verified_count": len(item.get("verified_candidates", [])),
                "google_page_loaded": bool(item.get("google_page_loaded")),
                "google_answer_expanded": bool(item.get("google_answer_expanded")),
                "google_expand_clicks": int(item.get("google_expand_clicks", 0) or 0),
                "google_expand_labels": list(item.get("google_expand_labels", [])),
                "browser": item.get("browser", ""),
                "captcha_detected": bool(item.get("captcha_detected")),
                "captcha_resolved": bool(item.get("captcha_resolved")),
                "captcha_timed_out": bool(item.get("captcha_timed_out")),
                "captcha_waited_seconds": float(item.get("captcha_waited_seconds", 0) or 0),
                "capture_retries": int(item.get("capture_retries", 0) or 0),
            }
            for item in stages
        ],
        "attempted_links": attempted_links,
        "search_stage_used": stage_used,
        "results": [item.as_dict() for item in sorted(
            all_results_by_url.values(), key=lambda item: item.score, reverse=True
        )[:max(1, min(max_results, 40))]],
        "candidates": all_candidates[:40],
        "best_candidate": best_candidate,
        "structured_question": structured,
        "suggestions": structured,
        "confidence": confidence,
        "exact_code_match": exact_code_match,
        "metadata_confirmed": metadata_confirmed,
        "board_confirmed": bool(best_candidate.get("board_match")),
        "year_confirmed": bool(best_candidate.get("year_match")),
        "verified_match": verified_match,
        "verified_source_url": verified_source_url,
        "answer_source_url": answer_source_url,
        "justification_source_url": justification_source_url,
        "answer_search_stage": answer_search_stage,
        "site_opened": any(
            item.get("source_kind") == "google_ai_page" and item.get("page_opened")
            for item in all_candidates
        ) or any(item.get("opened") for item in attempted_links),
        "google_search_page_read": any(
            item.get("source_kind") == "google_ai_page" for item in all_candidates
        ),
        "google_answer_expanded": any(
            bool(item.get("google_answer_expanded")) for item in stages
        ),
        "google_expand_clicks": sum(
            int(item.get("google_expand_clicks", 0) or 0) for item in stages
        ),
        "captcha_detected": any(bool(item.get("captcha_detected")) for item in stages),
        "captcha_resolved": any(bool(item.get("captcha_detected")) and bool(item.get("captcha_resolved")) for item in stages),
        "captcha_timed_out": any(bool(item.get("captcha_timed_out")) for item in stages),
        "captcha_waited_seconds": sum(float(item.get("captcha_waited_seconds", 0) or 0) for item in stages),
        "answer_confirmed": answer_confirmed,
        "justification_confirmed": justification_confirmed,
        "explanation_confidence": float((justification_sources[0] if justification_sources else best_candidate).get("explanation_confidence", 0) or 0),
        "explanation_method": str((justification_sources[0] if justification_sources else best_candidate).get("explanation_method", "none") or "none"),
        "noise_removed": int((justification_sources[0] if justification_sources else best_candidate).get("noise_removed", 0) or 0),
        "answer_sources": [
            {"url": item.get("url", ""), "provider": item.get("provider", ""), "score": item.get("score", 0)}
            for item in answer_sources
        ],
        "justification_sources": [
            {"url": item.get("url", ""), "provider": item.get("provider", ""), "score": item.get("score", 0)}
            for item in justification_sources
        ],
        "safe_to_apply": safe_to_apply,
        "errors": query_errors,
        "searched": True,
        "search_engine": "Google",
        "search_mode": (
            "google_modo_ia_pagina_renderizada"
            if not str(stage_used).startswith("google_web_")
            else "google_web_fonte_publica_verificada"
        ),
        "ai_mode_activated": any(bool(item.get("ai_mode_activated")) for item in stages),
        "ai_answer_stable": any(bool(item.get("ai_answer_stable")) for item in stages),
    }

def enrichment_from_candidate(candidate: dict, *, query: str = "", question_uid: str = "") -> dict:
    """Transforma uma fonte escolhida pelo usuário em um enriquecimento aplicável."""
    candidate = dict(candidate or {})
    structured = _candidate_to_structured(candidate)
    verified_match = bool(candidate.get("verified"))
    metadata_confirmed = bool(candidate.get("metadata_confirmed"))
    exact_code_match = bool(candidate.get("exact_code") and verified_match)
    safe_to_apply = bool(verified_match and metadata_confirmed)
    source_url = str(candidate.get("url", "")).strip()
    answer = str(structured.get("gabarito", "")).strip()
    explanation = str(structured.get("explicacao", "")).strip()
    return {
        "query": query,
        "queries": [query] if query else [],
        "results": [],
        "candidates": [candidate],
        "best_candidate": candidate,
        "structured_question": structured,
        "suggestions": structured,
        "confidence": float(candidate.get("score", 0) or 0),
        "exact_code_match": exact_code_match,
        "metadata_confirmed": metadata_confirmed,
        "board_confirmed": bool(candidate.get("board_match")),
        "year_confirmed": bool(candidate.get("year_match")),
        "verified_match": verified_match,
        "verified_source_url": source_url if verified_match else "",
        "answer_source_url": source_url if verified_match and answer else "",
        "justification_source_url": source_url if verified_match and explanation else "",
        "answer_confirmed": bool(verified_match and answer),
        "justification_confirmed": bool(verified_match and explanation),
        "safe_to_apply": safe_to_apply,
        "site_opened": bool(candidate.get("page_opened")),
        "google_search_page_read": candidate.get("source_kind") == "google_ai_page",
        "search_stage_used": str(candidate.get("search_stage", "manual")),
        "search_engine": "Google",
        "search_mode": "fonte_selecionada_manualmente",
        "question_uid": question_uid,
        "searched": True,
        "errors": [],
    }


def enrich_selected_url(question: dict, url: str, *, provider: str = "Resultado selecionado") -> dict:
    """Abre uma URL selecionada, confirma a questão e prepara os campos para atualização."""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise WebEnrichmentError("O resultado selecionado não possui um endereço válido.")
    profile = Path(__file__).resolve().parent.parent / "data" / "google_browser_profile"
    page = read_visible_page(url, profile_dir=profile, wait_seconds=12)
    raw_html = str(page.get("html", ""))
    page_text = str(page.get("text", ""))
    candidate: dict = {}
    if "google." in urllib.parse.urlparse(url).netloc.lower():
        candidate = parse_google_search_page(page_text, raw_html, question, search_url=url)
    if not candidate:
        raw = raw_html or f"<pre>{html.escape(page_text)}</pre>"
        candidate = parse_candidate_question(
            raw,
            question,
            url=url,
            provider=provider,
            source_kind="page",
        ) or {}
    if not candidate:
        raise WebEnrichmentError("A página selecionada foi aberta, mas não foi possível reconhecer uma questão nela.")
    candidate["page_opened"] = True
    candidate["provider"] = provider
    candidate.setdefault("search_stage", "manual")
    result = enrichment_from_candidate(candidate, query=url)
    result["opened_page_browser"] = page.get("browser", "")
    return result


def _is_missing(value) -> bool:
    return value in (None, "", 0, [], {})


def apply_safe_suggestions(question: dict, enrichment: dict) -> dict:
    updated = json.loads(json.dumps(question, ensure_ascii=False))
    updated["enriquecimento_web"] = enrichment
    if not enrichment.get("safe_to_apply"):
        return updated

    structured = enrichment.get("structured_question", {}) if isinstance(enrichment.get("structured_question"), dict) else {}
    if not structured and isinstance(enrichment.get("suggestions"), dict):
        structured = enrichment.get("suggestions", {})
    applied: list[str] = []
    for field in ("materia", "assunto", "ano", "banca", "orgao", "prova", "cargo", "area", "especialidade", "turno", "tipo"):
        if _is_missing(updated.get(field)) and not _is_missing(structured.get(field)):
            updated[field] = structured[field]
            applied.append(field)

    candidate_statement = str(structured.get("enunciado", "")).strip()
    current_statement = str(updated.get("enunciado", "")).strip()
    if candidate_statement and (
        not current_statement
        or (len(candidate_statement) > len(current_statement) * 1.08 and _statement_similarity(current_statement, candidate_statement) >= 0.72)
    ):
        updated["enunciado"] = candidate_statement
        applied.append("enunciado")

    if "assunto" in applied:
        topic = str(updated.get("assunto", "")).strip()
        topics = list(updated.get("assuntos", [])) if isinstance(updated.get("assuntos"), list) else []
        if topic and topic not in topics:
            topics.insert(0, topic)
        updated["assuntos"] = topics
        matter = str(updated.get("materia", "")).strip()
        updated["trilha_assuntos"] = [item for item in [matter, topic] if item]

    candidate_alternatives = structured.get("alternativas", [])
    current_alternatives = updated.get("alternativas", [])
    current_complete = isinstance(current_alternatives, list) and len(current_alternatives) >= 2 and all(
        isinstance(item, dict) and str(item.get("texto", "")).strip() for item in current_alternatives
    )
    if isinstance(candidate_alternatives, list) and len(candidate_alternatives) >= 2 and (
        not current_complete or len(candidate_alternatives) > len(current_alternatives)
    ):
        updated["alternativas"] = candidate_alternatives
        applied.append("alternativas")

    answer = str(structured.get("gabarito", "")).strip().upper()
    if answer and _is_missing(updated.get("gabarito")):
        updated["gabarito"] = answer
        applied.append("gabarito")

    explanation = str(structured.get("explicacao", "")).strip()
    if explanation and _is_missing(updated.get("explicacao")):
        updated["explicacao"] = explanation
        applied.append("explicacao")

    alternatives = updated.get("alternativas", []) if isinstance(updated.get("alternativas"), list) else []
    keys = [str(item.get("chave", "")).upper() for item in alternatives if isinstance(item, dict)]
    if alternatives:
        updated["tipo"] = "certo_errado" if set(keys) == {"C", "E"} else "multipla_escolha"
        updated["telegram"] = {
            "modo": "quiz",
            "pergunta": str(updated.get("enunciado", "")),
            "opcoes": [str(item.get("texto", "")) for item in alternatives if isinstance(item, dict)],
            "indice_correto": keys.index(str(updated.get("gabarito", "")).upper()) if str(updated.get("gabarito", "")).upper() in keys else None,
        }

    enrichment["applied_fields"] = applied
    updated["enriquecimento_web"] = enrichment
    return updated

