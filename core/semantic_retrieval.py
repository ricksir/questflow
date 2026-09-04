from __future__ import annotations

"""Busca híbrida, assinatura semântica local e grafo de conhecimento do QuestFlow.

A implementação é deliberadamente dependency-free e offline-first. Ela usa uma
representação vetorial por hashing (unigramas + bigramas + expansões conceituais)
como fallback local e combina esse sinal com busca lexical/BM25-like e metadados.
A interface foi desenhada para permitir trocar o vetor local por embeddings de um
provedor externo no futuro sem alterar o banco ou a UI.
"""

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
import unicodedata
from typing import Any, Iterable

SEMANTIC_VERSION = "qf-semantic-1"
VECTOR_DIMS = 256

_STOPWORDS = {
    "a", "ao", "aos", "as", "de", "da", "das", "do", "dos", "e", "em", "na", "nas", "no", "nos",
    "o", "os", "ou", "para", "por", "que", "se", "um", "uma", "uns", "umas", "com", "como", "quanto",
    "sobre", "ser", "sao", "sua", "seu", "suas", "seus", "esta", "este", "essa", "esse", "isto", "isso",
    "à", "às", "é", "não", "nos termos", "assinale", "alternativa", "correta", "incorreta", "item", "itens",
}

# Expansões pequenas e conservadoras para aproximar termos recorrentes de concursos.
# Não pretendem substituir embeddings neurais; apenas melhoram o fallback offline.
_CONCEPT_ALIASES = {
    "constituição": ("constitucional", "cf", "constituicao"),
    "ctn": ("codigo tributario nacional", "tributario"),
    "crédito tributário": ("credito tributario", "obrigacao tributaria"),
    "licitação": ("licitacao", "contratacao publica"),
    "administração pública": ("administracao publica", "direito administrativo"),
    "cebraspe": ("cespe", "certo errado"),
    "certo errado": ("cebraspe", "cespe"),
    "fgv": ("fundacao getulio vargas",),
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9§ºª]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(value: Any) -> list[str]:
    text = normalize_text(value)
    tokens = [token for token in text.split() if len(token) >= 2 and token not in _STOPWORDS]
    return tokens


def _expand_concepts(text: str) -> list[str]:
    norm = normalize_text(text)
    expanded: list[str] = []
    for concept, aliases in _CONCEPT_ALIASES.items():
        concept_norm = normalize_text(concept)
        if concept_norm and concept_norm in norm:
            expanded.append(concept_norm.replace(" ", "_"))
            expanded.extend(normalize_text(alias).replace(" ", "_") for alias in aliases)
        else:
            for alias in aliases:
                alias_norm = normalize_text(alias)
                if alias_norm and alias_norm in norm:
                    expanded.append(concept_norm.replace(" ", "_"))
                    break
    return [item for item in expanded if item]


def _bucket(feature: str, dims: int = VECTOR_DIMS) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    integer = int.from_bytes(digest, "big", signed=False)
    index = integer % dims
    sign = -1.0 if (integer >> 8) & 1 else 1.0
    return index, sign


def hashed_embedding(value: Any, *, dims: int = VECTOR_DIMS) -> list[float]:
    """Vetorização local determinística, adequada para fallback offline."""
    text = clean_text(value)
    tokens = tokenize(text)
    features: list[tuple[str, float]] = [(token, 1.0) for token in tokens]
    features.extend((f"{a}_{b}", 1.25) for a, b in zip(tokens, tokens[1:]))
    features.extend((feature, 1.45) for feature in _expand_concepts(text))
    vector = [0.0] * dims
    counts = Counter(feature for feature, _ in features)
    weights = {feature: weight for feature, weight in features}
    for feature, count in counts.items():
        index, sign = _bucket(feature, dims)
        vector[index] += sign * (1.0 + math.log1p(count)) * weights.get(feature, 1.0)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 7) for value in vector]


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    a = list(left)
    b = list(right)
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def lexical_score(query: Any, document: Any) -> float:
    """BM25-like normalizado para reranking local, sem corpus global."""
    q = tokenize(query)
    d = tokenize(document)
    if not q or not d:
        return 0.0
    counts = Counter(d)
    dl = max(1, len(d))
    score = 0.0
    k1, b = 1.35, 0.72
    avgdl = 120.0
    for token in set(q):
        tf = counts.get(token, 0)
        if not tf:
            continue
        denom = tf + k1 * (1.0 - b + b * dl / avgdl)
        score += (tf * (k1 + 1.0)) / max(0.001, denom)
    return min(1.0, score / max(1.0, len(set(q)) * 1.25))


def taxonomy_terms(question: dict) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    fields = (
        ("materia", question.get("materia")),
        ("assunto", question.get("assunto")),
        ("aula", question.get("aula_planilha")),
        ("banca", question.get("banca")),
        ("orgao", question.get("orgao")),
    )
    for kind, value in fields:
        if clean_text(value):
            values.append((kind, clean_text(value)))
    for value in question.get("assuntos", []) if isinstance(question.get("assuntos"), list) else []:
        if clean_text(value):
            values.append(("topico", clean_text(value)))
    refs = question.get("referencias_legais", [])
    if isinstance(refs, str):
        refs = [part.strip() for part in refs.split("|")]
    for value in refs if isinstance(refs, list) else []:
        if clean_text(value):
            values.append(("referencia_legal", clean_text(value)))
    tags = question.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split("|")]
    for value in tags if isinstance(tags, list) else []:
        if clean_text(value):
            values.append(("tag", clean_text(value)))
    seen: set[tuple[str, str]] = set()
    output: list[tuple[str, str]] = []
    for kind, label in values:
        key = (kind, normalize_text(label))
        if key not in seen and key[1]:
            seen.add(key)
            output.append((kind, label))
    return output


def question_document(question: dict) -> str:
    parts = [
        clean_text(question.get("materia")), clean_text(question.get("assunto")),
        " ".join(clean_text(x) for x in (question.get("assuntos") or []) if clean_text(x)) if isinstance(question.get("assuntos"), list) else "",
        clean_text(question.get("enunciado")), clean_text(question.get("explicacao")),
        clean_text(question.get("banca")), clean_text(question.get("orgao")),
        " ".join(label for _, label in taxonomy_terms(question)),
    ]
    return "\n".join(part for part in parts if part)


def taxonomy_overlap(left: dict, right: dict) -> float:
    a = {f"{kind}:{normalize_text(label)}" for kind, label in taxonomy_terms(left)}
    b = {f"{kind}:{normalize_text(label)}" for kind, label in taxonomy_terms(right)}
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def semantic_duplicate_score(left: dict, right: dict, *, lexical_similarity: float = 0.0) -> dict:
    left_doc = question_document(left)
    right_doc = question_document(right)
    vector = cosine_similarity(hashed_embedding(left_doc), hashed_embedding(right_doc))
    tax = taxonomy_overlap(left, right)
    exact_meta = 0.0
    if clean_text(left.get("banca")) and normalize_text(left.get("banca")) == normalize_text(right.get("banca")):
        exact_meta += 0.04
    if left.get("ano") and str(left.get("ano")) == str(right.get("ano")):
        exact_meta += 0.03
    score = min(1.0, lexical_similarity * 0.32 + vector * 0.50 + tax * 0.11 + exact_meta)
    return {
        "score": round(score, 4),
        "lexical": round(float(lexical_similarity), 4),
        "vector": round(vector, 4),
        "taxonomy": round(tax, 4),
        "version": SEMANTIC_VERSION,
        "method": "hybrid_local_hashing",
    }


def hybrid_retrieval_score(
    query: str,
    content: str,
    *,
    metadata_text: str = "",
    subject_match: bool = False,
    query_vector: Iterable[float] | None = None,
    content_vector: Iterable[float] | None = None,
) -> dict:
    lexical = lexical_score(query, content)
    q_vector = list(query_vector) if query_vector is not None else hashed_embedding(query)
    d_vector = list(content_vector) if content_vector is not None else hashed_embedding(content)
    semantic = cosine_similarity(q_vector, d_vector)
    metadata = lexical_score(query, metadata_text) if metadata_text else 0.0
    boost = 0.07 if subject_match else 0.0
    final = min(1.0, lexical * 0.34 + semantic * 0.48 + metadata * 0.11 + boost)
    return {
        "score": round(final, 4), "lexical": round(lexical, 4), "semantic": round(semantic, 4),
        "metadata": round(metadata, 4), "subject_boost": round(boost, 4), "version": SEMANTIC_VERSION,
    }


def chunk_text(text: str, *, max_chars: int = 1300, overlap: int = 180) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
        else:
            start = 0
            while start < len(paragraph):
                end = min(len(paragraph), start + max_chars)
                chunks.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(start + 1, end - overlap)
            current = ""
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 20]


def graph_for_question(question: dict) -> dict:
    terms = taxonomy_terms(question)
    nodes = []
    for kind, label in terms:
        node_id = hashlib.sha1(f"{kind}:{normalize_text(label)}".encode("utf-8")).hexdigest()[:24]
        nodes.append({"id": node_id, "type": kind, "label": label, "normalized": normalize_text(label)})
    edges = []
    subject = next((node for node in nodes if node["type"] == "materia"), None)
    topic = next((node for node in nodes if node["type"] == "assunto"), None)
    for node in nodes:
        if subject and node["id"] != subject["id"] and node["type"] in {"assunto", "topico", "aula"}:
            edges.append({"source": subject["id"], "target": node["id"], "relation": "contem"})
        if topic and node["id"] != topic["id"] and node["type"] in {"topico", "referencia_legal", "tag"}:
            edges.append({"source": topic["id"], "target": node["id"], "relation": "relaciona"})
    return {"version": SEMANTIC_VERSION, "nodes": nodes, "edges": edges}


__all__ = [
    "SEMANTIC_VERSION", "VECTOR_DIMS", "chunk_text", "clean_text", "cosine_similarity", "graph_for_question",
    "hashed_embedding", "hybrid_retrieval_score", "lexical_score", "normalize_text", "question_document",
    "semantic_duplicate_score", "taxonomy_overlap", "taxonomy_terms", "tokenize",
]
