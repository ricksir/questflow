from __future__ import annotations

import json
import math
import re
import shutil
import unicodedata
import urllib.request

from .network import network_urlopen
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


DEFAULT_SPREADSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1lT6I_8fgNiBSt7wlfGH7eXfubkupbAsH03gkxJ7jBd4/edit?usp=sharing"
)

_STOPWORDS = {
    "A", "O", "AS", "OS", "DE", "DA", "DO", "DAS", "DOS", "E", "EM",
    "NO", "NA", "NOS", "NAS", "UM", "UMA", "PARA", "POR", "COM", "SEM",
    "AO", "AOS", "ATE", "APOS", "ENTRE", "SOBRE", "QUE", "SE", "SER",
    "ESTA", "ESTAO", "FOI", "SAO", "COMO", "OU", "SEU", "SUA", "SEUS",
    "SUAS", "TODO", "TODA", "TODOS", "TODAS", "PARTE", "TEORIA", "AULA",
    "PDF", "REVISAO", "RESOLUCAO", "QUESTAO", "QUESTOES", "TOPICO", "FINAL",
    "INICIO", "INCLUSIVE", "EXCLUSIVE", "ESTUDO", "CONTEUDO", "COMPLETA",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ascii_upper(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", _clean(value))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return normalized.upper()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Z0-9]{2,}", _ascii_upper(value))
        if token not in _STOPWORDS
    }


def _lesson_from_text(text: str) -> str:
    match = re.search(r"\bAula\s+(\d{1,2})(?:\s*[-–]\s*(II))?\b", text, re.I)
    if not match:
        return ""
    suffix = "-II" if match.group(2) else ""
    return f"Aula {int(match.group(1)):02d}{suffix}"


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    if not letters:
        return 0
    number = 0
    for char in letters.group(0):
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def _xlsx_sheet_rows(path: str | Path) -> dict[str, list[list[Any]]]:
    """Read ordinary Google/Excel worksheets with the Python standard library.

    This intentionally avoids macros, formulas and formatting. It only needs the
    displayed text in MAPA_AF and CICLO_REG to build the QuestFlow taxonomy.
    """
    source = Path(path)
    with zipfile.ZipFile(source, "r") as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for item in root.findall("x:si", namespace):
                parts = [node.text or "" for node in item.findall(".//x:t", namespace)]
                shared_strings.append("".join(parts))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        main_ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        rel_map = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall("r:Relationship", rel_ns)
        }
        sheets: dict[str, str] = {}
        relation_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        for sheet in workbook.findall("x:sheets/x:sheet", main_ns):
            target = rel_map.get(sheet.attrib.get(relation_key, ""), "")
            if target:
                if target.startswith("/"):
                    target = target.lstrip("/")
                elif not target.startswith("xl/"):
                    target = "xl/" + target
                sheets[sheet.attrib["name"]] = target

        output: dict[str, list[list[Any]]] = {}
        for name, target in sheets.items():
            if target not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(target))
            rows: list[list[Any]] = []
            for row_element in root.findall("x:sheetData/x:row", main_ns):
                values: dict[int, Any] = {}
                for cell in row_element.findall("x:c", main_ns):
                    ref = cell.attrib.get("r", "A1")
                    index = _column_index(ref)
                    cell_type = cell.attrib.get("t", "")
                    value_element = cell.find("x:v", main_ns)
                    inline = cell.find("x:is", main_ns)
                    value: Any = ""
                    if cell_type == "inlineStr" and inline is not None:
                        value = "".join(
                            node.text or "" for node in inline.findall(".//x:t", main_ns)
                        )
                    elif value_element is not None:
                        raw = value_element.text or ""
                        if cell_type == "s":
                            try:
                                value = shared_strings[int(raw)]
                            except (ValueError, IndexError):
                                value = raw
                        elif cell_type == "b":
                            value = raw == "1"
                        else:
                            try:
                                value = int(raw) if re.fullmatch(r"-?\d+", raw) else float(raw)
                            except ValueError:
                                value = raw
                    values[index] = value
                if values:
                    row = [""] * (max(values) + 1)
                    for index, value in values.items():
                        row[index] = value
                    rows.append(row)
                else:
                    rows.append([])
            output[name] = rows
        return output


def _cell(row: list[Any], index: int) -> str:
    return _clean(row[index] if index < len(row) else "")


def _raw_cell(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else ""


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        try:
            return float(value) if math.isfinite(float(value)) else default
        except Exception:
            return default
    text = _clean(value).replace("%", "").replace(" ", "")
    if not text:
        return default
    # Brazilian spreadsheets commonly use comma as decimal separator.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        parsed = float(text)
        return parsed if math.isfinite(parsed) else default
    except ValueError:
        return default


def _integer(value: Any) -> int:
    return max(0, int(round(_number(value, 0.0))))


def _duration_minutes(value: Any) -> int:
    """Return a Google/Excel duration as minutes.

    XLSX exports usually store ``1:30`` as a fraction of a day (0.0625),
    while pasted/imported snapshots may contain the displayed string. Supporting
    both formats keeps the study marker reliable without depending on cell styles.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = _number(value, 0.0)
        if numeric <= 0:
            return 0
        # Excel time/duration serials are fractions of one day. Values below 2
        # cover ordinary study sessions and also durations longer than 24h.
        if numeric < 2:
            return max(0, int(round(numeric * 24 * 60)))
        return max(0, int(round(numeric * 60)))
    text = _clean(value).lower()
    match = re.fullmatch(r"(\d{1,3})\s*:\s*(\d{1,2})", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?", text)
    if match and (match.group(1) or match.group(2)):
        return int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    return max(0, int(round(_number(value, 0.0) * 60)))


def _duration_label(minutes: int) -> str:
    minutes = max(0, int(minutes or 0))
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h{remainder:02d}"
    if hours:
        return f"{hours}h"
    return f"{remainder}min" if remainder else ""


def _performance_percent(value: Any, questions: int = 0, hits: int = 0) -> float:
    numeric = _number(value, -1.0)
    if numeric >= 0:
        # Percentage-formatted XLSX cells are often stored as 0.8462.
        if 0 <= numeric <= 1:
            numeric *= 100
        return round(max(0.0, min(100.0, numeric)), 2)
    if questions > 0:
        return round(max(0.0, min(100.0, hits * 100.0 / questions)), 2)
    return 0.0


def _question_goal_from_description(description: str) -> int:
    normalized = _ascii_upper(description)
    patterns = [
        r"(?:RESOLUCAO|RESOLVER|RESOLVA|RESOLUCAO\s+DE)\s+(?:DE\s+)?(\d{1,4})\s+QUEST",
        r"(?:E\s+)?RESOLUCAO\s+DE\s+(\d{1,4})\s+QUEST",
        r"(\d{1,4})\s+QUESTOES?\s+(?:DO|DA|DE)\s+PDF",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return max(0, int(match.group(1)))
    return 0



def _find_sheet(sheets: dict[str, list[list[Any]]], candidates: tuple[str, ...]) -> tuple[str, list[list[Any]]]:
    by_normalized = {_ascii_upper(name): (name, rows) for name, rows in sheets.items()}
    for candidate in candidates:
        found = by_normalized.get(_ascii_upper(candidate))
        if found:
            return found
    return "", []


def _detect_ciclo_columns(ciclo_rows: list[list[Any]]) -> dict[str, int]:
    """Learn the CICLO layout from its visible headers instead of fixed letters.

    The supplied trail guides explain the semantic fields while the Google Sheet
    may rename/reorder columns over time. Header detection keeps the coverage
    logic stable if that happens.
    """
    defaults = {
        "trail": 0, "date": 1, "task": 2, "subject": 3, "planned_time": 4,
        "effective_time": 5, "description": 7, "questions": 8, "hits": 9,
        "performance": 10,
    }
    for row in ciclo_rows[:80]:
        normalized = [_ascii_upper(value) for value in row]
        if "DISCIPLINA" not in normalized or not any(value in {"TAREFA", "TAREFAS"} for value in normalized):
            continue
        result = dict(defaults)
        for index, value in enumerate(normalized):
            if value == "TRILHA":
                result["trail"] = index
            elif value == "DATA":
                result["date"] = index
            elif value == "TAREFA":
                result["task"] = index
            elif value == "DISCIPLINA":
                result["subject"] = index
            elif value == "CH":
                result["planned_time"] = index
            elif "CH" in value and "EFETIVA" in value:
                result["effective_time"] = index
            elif value in {"TAREFAS", "TITULO DA TAREFA", "TÍTULO DA TAREFA", "DESCRICAO", "DESCRIÇÃO"}:
                result["description"] = index
            elif ("QUEST" in value and "FEIT" in value) or value in {"QTD EXE", "QTD EXERCICIOS", "QTD EXERCÍCIOS"}:
                result["questions"] = index
            elif "ACERTO" in value:
                result["hits"] = index
            elif value in {"DESEMPENHO", "DES (%)", "DES %"}:
                result["performance"] = index
        return result
    return defaults


def _identifier(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric) and numeric.is_integer():
            return str(int(numeric))
    text = _clean(value)
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text

def _canonical_materias(mapa_rows: list[list[Any]], ciclo_rows: list[list[Any]], ciclo_columns: dict[str, int] | None = None) -> list[str]:
    materias: list[str] = []
    # The main subject list is in column B of MAPA_AF, approximately rows 11-36.
    for row in mapa_rows[10:36]:
        value = _cell(row, 1).upper()
        if value and value not in {"GUIA", "TOTAL PDFS"}:
            materias.append(re.sub(r"\s+", " ", value).strip())

    aliases = {
        "RACIOCÍNIO LÓGICO MATEMÁTICO": "RACIOCÍNIO-LÓGICO MATEMÁTICO",
        "CONTABILIDADE (SILVIO SANDE)": "CONTABILIDADE GERAL E AVANÇADA",
    }
    subject_index = int((ciclo_columns or {}).get("subject", 3))
    for row in ciclo_rows:
        value = _cell(row, subject_index).upper()
        value = aliases.get(value, value)
        if value and value not in {"DISCIPLINA", "LIMPE OS ERROS", "ORIENTAÇÕES DE ESTUDO"}:
            materias.append(value)

    unique: list[str] = []
    for item in materias:
        if item and item not in unique:
            unique.append(item)
    return unique


def _default_aliases(materias: list[str]) -> dict[str, str]:
    aliases = {_ascii_upper(item): item for item in materias}
    aliases.update(
        {
            "AUDITORIA CONTABIL": "AUDITORIA",
            "CONTABILIDADE": "CONTABILIDADE GERAL E AVANÇADA",
            "CONTABILIDADE GERAL": "CONTABILIDADE GERAL E AVANÇADA",
            "CONTABILIDADE AVANCADA": "CONTABILIDADE GERAL E AVANÇADA",
            "CONTABILIDADE SILVIO SANDE": "CONTABILIDADE GERAL E AVANÇADA",
            "LINGUA PORTUGUESA": "PORTUGUÊS",
            "RACIOCINIO LOGICO": "RACIOCÍNIO-LÓGICO MATEMÁTICO",
            "RACIOCINIO LOGICO MATEMATICO": "RACIOCÍNIO-LÓGICO MATEMÁTICO",
            "LINGUA INGLESA": "INGLÊS",
            "ECONOMIA": "ECONOMIA E FINANÇAS PÚBLICAS",
        }
    )
    return aliases


def _default_manual_rules() -> dict[str, list[dict[str, Any]]]:
    return {
        "FLUÊNCIA EM DADOS": [
            {
                "aula": "Aula 06",
                "assunto": "SISTEMAS DE SUPORTE À DECISÃO, DATA WAREHOUSE, BUSINESS INTELLIGENCE E ETL",
                "padroes": [
                    "data warehouse",
                    "datawarehouse",
                    "business intelligence",
                    "etl",
                    "extract transform load",
                    "extração, transformação e carga",
                    "data mart",
                    "olap",
                    "oltp",
                    "staging area",
                    "integração de dados",
                ],
            },
        ],
        "AUDITORIA": [
            {
                "aula": "Aula 00",
                "assunto": "CONCEITOS, OBJETO, OBJETIVO, ORIGEM E ASPECTOS GERAIS DA AUDITORIA",
                "padroes": [
                    "conceitos, objeto, objetivo e aspectos gerais",
                    "origem, evolução e desenvolvimento",
                    "princípios éticos",
                    "código de ética",
                    "normas de auditoria",
                    "objetivos do auditor",
                    "julgamento profissional",
                    "ceticismo profissional",
                ],
            },
            {
                "aula": "Aulas 01-02",
                "assunto": "AUDITORIA INTERNA, AUDITORIA EXTERNA, CONTROLE INTERNO E GOVERNANÇA",
                "padroes": [
                    "auditoria interna e externa",
                    "funções e diferenças",
                    "auditoria interna contábil",
                    "normas internacionais de auditoria interna",
                    "controle interno",
                    "governança corporativa",
                    "três linhas",
                    "modelo das três linhas",
                ],
            },
            {
                "aula": "Aula 03",
                "assunto": "EVIDÊNCIAS, PROCEDIMENTOS, TESTES E DOCUMENTAÇÃO DE AUDITORIA",
                "padroes": [
                    "evidência de auditoria",
                    "evidências de auditoria",
                    "procedimentos de auditoria",
                    "testes de auditoria",
                    "testes de observância",
                    "testes substantivos",
                    "circularização",
                    "confirmações externas",
                    "papéis de trabalho",
                    "documentação de auditoria",
                ],
            },
            {
                "aula": "Aula 04",
                "assunto": "AMOSTRAGEM, CONTROLE DE QUALIDADE E PERÍCIA",
                "padroes": [
                    "amostragem",
                    "revisão externa de qualidade",
                    "revisão de qualidade",
                    "controle de qualidade",
                    "monitoramento, supervisão",
                    "perícia contábil",
                ],
            },
            {
                "aula": "Aula 05",
                "assunto": "FRAUDE, ERRO, RISCO, DISTORÇÃO E MATERIALIDADE",
                "padroes": [
                    "fraude e erro",
                    "fraudes",
                    "risco de auditoria",
                    "distorção relevante",
                    "distorções",
                    "materialidade",
                ],
            },
            {
                "aula": "Aula 06",
                "assunto": "RELATÓRIO, PARECER E OPINIÃO DO AUDITOR",
                "padroes": [
                    "relatório de auditoria",
                    "parecer de auditoria",
                    "opinião modificada",
                    "opinião do auditor",
                    "opinião com ressalva",
                    "opinião adversa",
                    "abstenção de opinião",
                    "documentos e relatórios",
                ],
            },
            {
                "aula": "Aula 12",
                "assunto": "PROCEDIMENTOS DE AUDITORIA EM ÁREAS ESPECÍFICAS",
                "padroes": [
                    "procedimentos de auditoria em áreas específicas",
                    "ativo circulante",
                    "saldo credor",
                    "aquisições de mercadorias",
                    "depreciação",
                    "fornecedores a pagar",
                    "áreas específicas",
                ],
            },
            {
                "aula": "",
                "assunto": "ESTRUTURA CONCEITUAL E TRABALHOS DE ASSEGURAÇÃO",
                "padroes": [
                    "estrutura conceitual de trabalhos de asseguração",
                    "trabalho de asseguração diferente de auditoria e revisão",
                    "nbc to 3000",
                    "trabalhos de asseguração",
                ],
            },
        ]
    }


def build_taxonomy_from_xlsx(
    xlsx_path: str | Path,
    source_url: str = DEFAULT_SPREADSHEET_URL,
) -> dict[str, Any]:
    sheets = _xlsx_sheet_rows(xlsx_path)
    mapa_name, mapa_rows = _find_sheet(sheets, ("MAPA_AF", "MAPA_AT", "MAPA"))
    ciclo_name, ciclo_rows = _find_sheet(sheets, ("CICLO_REG", "CICLO"))
    if not mapa_rows or not ciclo_rows:
        raise ValueError("A planilha precisa conter uma aba de MAPA (MAPA_AF/MAPA_AT/MAPA) e uma aba de CICLO (CICLO_REG/CICLO).")

    ciclo_columns = _detect_ciclo_columns(ciclo_rows)
    materias = _canonical_materias(mapa_rows, ciclo_rows, ciclo_columns)
    aliases = _default_aliases(materias)
    current_trail = ""
    tasks: list[dict[str, Any]] = []
    discipline_aliases = {
        "RACIOCÍNIO LÓGICO MATEMÁTICO": "RACIOCÍNIO-LÓGICO MATEMÁTICO",
        "CONTABILIDADE (SILVIO SANDE)": "CONTABILIDADE GERAL E AVANÇADA",
    }
    for row_number, row in enumerate(ciclo_rows, start=1):
        first = _cell(row, ciclo_columns["trail"])
        if re.fullmatch(r"TRILHA\s+\d+", first, re.I):
            current_trail = first.upper()
        matter_raw = _cell(row, ciclo_columns["subject"]).upper()
        matter = discipline_aliases.get(matter_raw, matter_raw)
        description = _cell(row, ciclo_columns["description"])
        if (
            not matter
            or not description
            or matter in {"DISCIPLINA", "LIMPE OS ERROS", "ORIENTAÇÕES DE ESTUDO"}
        ):
            continue
        task_type = "teoria"
        normalized_description = _ascii_upper(description)
        if "RESOLUCAO" in normalized_description or "RESOLVER" in normalized_description:
            task_type = "questoes"
        if "REVISAO" in normalized_description and task_type == "questoes":
            task_type = "revisao_questoes"
        elif "REVISAO" in normalized_description:
            task_type = "revisao"
        segments = [
            _clean(item)
            for item in re.findall(r'[“\"]([^”\"]{2,160})[”\"]', description)
        ]
        planned_minutes = _duration_minutes(_raw_cell(row, ciclo_columns["planned_time"]))
        effective_minutes = _duration_minutes(_raw_cell(row, ciclo_columns["effective_time"]))
        questions_done = _integer(_raw_cell(row, ciclo_columns["questions"]))
        correct_answers = _integer(_raw_cell(row, ciclo_columns["hits"]))
        performance = _performance_percent(_raw_cell(row, ciclo_columns["performance"]), questions_done, correct_answers)
        task_date = _cell(row, ciclo_columns["date"])
        task_number = _identifier(_raw_cell(row, ciclo_columns["task"]))
        explicit_goal = questions_done if questions_done > 0 else _question_goal_from_description(description)
        study_evidence: list[str] = []
        if task_date:
            study_evidence.append("data")
        if effective_minutes > 0:
            study_evidence.append("ch_efetiva")
        if questions_done > 0:
            study_evidence.append("questoes_feitas")
        if correct_answers > 0:
            study_evidence.append("acertos")
        studied = bool(effective_minutes > 0 or questions_done > 0 or correct_answers > 0 or task_date)
        tasks.append(
            {
                "row": row_number,
                "trilha": current_trail,
                "tarefa": task_number,
                "data": task_date,
                "materia": matter,
                "aula": _lesson_from_text(description),
                "tipo": task_type,
                "descricao": description,
                "segmentos": segments,
                "ch_planejada_min": planned_minutes,
                "ch_planejada": _duration_label(planned_minutes),
                "ch_efetiva_min": effective_minutes,
                "ch_efetiva": _duration_label(effective_minutes),
                "questoes_feitas": questions_done,
                "acertos": correct_answers,
                "desempenho": performance,
                "meta_questoes": explicit_goal,
                "meta_origem": "questoes_feitas" if questions_done > 0 else ("descricao" if explicit_goal > 0 else ""),
                "estudado": studied,
                "evidencias_estudo": study_evidence,
            }
        )

    match = re.search(r"/d/([A-Za-z0-9_-]+)", source_url)
    spreadsheet_id = match.group(1) if match else ""
    known_title = (
        "Trilhas00a18_AFRFB_Planilha de Controle"
        if spreadsheet_id == "1lT6I_8fgNiBSt7wlfGH7eXfubkupbAsH03gkxJ7jBd4"
        else Path(xlsx_path).stem
    )
    return {
        "schema": "questflow.taxonomy.v1",
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": {
            "title": known_title,
            "spreadsheet_id": spreadsheet_id,
            "url": source_url,
            "sheets": [mapa_name, ciclo_name],
            "instructions_sheet": next((name for name in sheets if _ascii_upper(name) in {"INSTRUCOES", "INSTRUÇÕES"}), ""),
        },
        "materias": materias,
        "aliases": aliases,
        "regras_manuais": _default_manual_rules(),
        "tarefas_referencia": tasks,
        "spreadsheet_logic": {
            "mapa_sheet": mapa_name,
            "ciclo_sheet": ciclo_name,
            "ciclo_columns": ciclo_columns,
            "study_evidence": ["DATA", "CH EFETIVA", "TOT QUEST FEITAS", "TOT ACERTOS"],
            "performance_inputs": ["TOT QUEST FEITAS", "TOT ACERTOS"],
        },
    }


def save_taxonomy(taxonomy: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def download_public_spreadsheet(
    spreadsheet_url: str,
    destination: str | Path,
    timeout: int = 45,
) -> Path:
    match = re.search(r"/d/([A-Za-z0-9_-]+)", spreadsheet_url)
    if not match:
        raise ValueError("Link de Google Sheets inválido.")
    export_url = (
        f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=xlsx"
    )
    request = urllib.request.Request(
        export_url,
        headers={"User-Agent": "QuestFlow-PDF-Importer/1.1"},
    )
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    with network_urlopen(request, timeout=timeout) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if output.stat().st_size < 1000:
        raise RuntimeError("O Google Sheets retornou um arquivo vazio ou inválido.")
    return output


class SpreadsheetTaxonomy:
    def __init__(self, payload: dict[str, Any], path: str | Path | None = None):
        self.payload = payload
        self.path = Path(path) if path else None
        self.materias = [str(item) for item in payload.get("materias", [])]
        self.aliases = {
            _ascii_upper(str(key)): str(value)
            for key, value in payload.get("aliases", {}).items()
        }
        self.manual_rules = payload.get("regras_manuais", {})
        self.tasks = payload.get("tarefas_referencia", [])
        self.tasks_by_matter: dict[str, list[dict[str, Any]]] = {}
        for task in self.tasks:
            matter = str(task.get("materia", ""))
            if matter:
                self.tasks_by_matter.setdefault(matter, []).append(task)

    @classmethod
    def load(cls, path: str | Path) -> "SpreadsheetTaxonomy":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("schema") != "questflow.taxonomy.v1":
            raise ValueError("Arquivo de taxonomia incompatível.")
        return cls(payload, source)

    @property
    def source_name(self) -> str:
        source = self.payload.get("source", {})
        return str(source.get("title") or source.get("url") or "Taxonomia local")

    def canonical_matter(self, raw_value: str) -> str:
        normalized = _ascii_upper(raw_value)
        if normalized in self.aliases:
            return self.aliases[normalized]
        # Prefer the longest alias so 'CONTABILIDADE PÚBLICA' wins over CONTABILIDADE.
        for alias in sorted(self.aliases, key=len, reverse=True):
            if alias and (normalized.startswith(alias) or f" {alias} " in f" {normalized} "):
                return self.aliases[alias]
        return _clean(raw_value).upper()

    @staticmethod
    def _source_topics(raw_category: str) -> list[str]:
        category = _clean(raw_category)
        if ">" in category:
            first, rest = category.split(">", 1)
        else:
            first, rest = "", category
        parts = [
            _clean(part)
            for part in re.split(r"\s*,\s*", rest)
            if _clean(part)
        ]
        if parts and first and _ascii_upper(parts[0]) == _ascii_upper(first):
            parts = parts[1:]
        unique: list[str] = []
        for part in parts:
            if _ascii_upper(part) not in {_ascii_upper(item) for item in unique}:
                unique.append(part)
        return unique

    def _manual_match(self, matter: str, text: str) -> dict[str, Any] | None:
        normalized = _ascii_upper(text)
        best: tuple[int, dict[str, Any]] | None = None
        for rule in self.manual_rules.get(matter, []):
            hits = sum(
                1
                for pattern in rule.get("padroes", [])
                if _ascii_upper(str(pattern)) in normalized
            )
            if hits and (best is None or hits > best[0]):
                best = (hits, rule)
        if not best:
            return None
        rule = best[1]
        return {
            "aula": str(rule.get("aula", "")),
            "assunto": str(rule.get("assunto", "")),
            "confidence": min(0.99, 0.90 + 0.03 * (best[0] - 1)),
            "method": "regra_manual",
            "reference": "",
        }

    def _task_match(self, matter: str, category: str, statement: str) -> dict[str, Any] | None:
        source_tokens = _tokens(category)
        statement_tokens = _tokens(statement[:1200])
        if not source_tokens and not statement_tokens:
            return None
        best_score = 0.0
        best_task: dict[str, Any] | None = None
        for task in self.tasks_by_matter.get(matter, []):
            if task.get("tipo") not in {"teoria", "questoes"}:
                continue
            reference_text = " ".join(
                [str(task.get("descricao", "")), *[str(x) for x in task.get("segmentos", [])]]
            )
            reference_tokens = _tokens(reference_text)
            if not reference_tokens:
                continue
            category_overlap = len(source_tokens & reference_tokens) / max(1, len(source_tokens))
            statement_overlap = len(statement_tokens & reference_tokens) / max(1, len(reference_tokens))
            score = 0.78 * category_overlap + 0.22 * min(1.0, statement_overlap * 3)
            if score > best_score:
                best_score = score
                best_task = task
        if not best_task or best_score < 0.12:
            return None
        segments = [str(item) for item in best_task.get("segmentos", []) if str(item).strip()]
        subject = " até ".join(segments[:2]) if segments else ""
        return {
            "aula": str(best_task.get("aula", "")),
            "assunto": subject,
            "confidence": round(min(0.89, 0.55 + best_score * 0.40), 2),
            "method": "similaridade_trilha",
            "reference": str(best_task.get("descricao", "")),
        }

    def classify(
        self,
        raw_category: str,
        statement: str = "",
        current_matter: str = "",
        current_topics: list[str] | None = None,
    ) -> dict[str, Any]:
        category = _clean(raw_category)
        category_head = category.split(">", 1)[0].strip() if ">" in category else current_matter
        matter = self.canonical_matter(category_head or current_matter)
        source_topics = self._source_topics(category)
        if not source_topics:
            source_topics = [str(item) for item in (current_topics or []) if str(item).strip()]

        combined = " | ".join([category, *source_topics, statement[:1000]])
        match = self._manual_match(matter, combined)
        if match is None:
            match = self._task_match(matter, category, statement)

        primary_source = source_topics[0] if source_topics else ""
        if match:
            subject = match.get("assunto") or primary_source
            lesson = match.get("aula", "")
            confidence = float(match.get("confidence", 0.0))
            method = str(match.get("method", ""))
            reference = str(match.get("reference", ""))
        else:
            subject = primary_source
            lesson = ""
            confidence = 0.62 if matter and subject else 0.35
            method = "categoria_origem"
            reference = ""

        if not subject and source_topics:
            subject = source_topics[0]
        subject = _clean(subject).upper()
        additional_topics = [
            _clean(item)
            for item in source_topics
            if _clean(item) and _ascii_upper(item) != _ascii_upper(subject)
        ]
        path = [item for item in [matter, lesson, subject] if item]
        status = "classificado" if matter and subject and confidence >= 0.60 else "revisar"
        return {
            "materia": matter,
            "aula": lesson,
            "assunto": subject,
            "assuntos": [subject, *additional_topics] if subject else additional_topics,
            "trilha": path,
            "status": status,
            "confianca": round(confidence, 2),
            "metodo": method,
            "referencia": reference,
            "categoria_origem": category,
            "assuntos_origem": source_topics,
            "fonte_taxonomia": self.source_name,
        }

    def apply_to_question(self, question: dict[str, Any]) -> dict[str, Any]:
        ocr = question.get("ocr", {})
        raw_category = str(ocr.get("categoria_bruta", ""))
        original_matter = str(question.get("materia", ""))
        original_topics = [str(item) for item in question.get("assuntos", [])]
        result = self.classify(
            raw_category=raw_category,
            statement=str(question.get("enunciado", "")),
            current_matter=original_matter,
            current_topics=original_topics,
        )
        question["materia_origem"] = original_matter
        question["assuntos_origem"] = original_topics
        question["materia"] = result["materia"] or original_matter
        question["aula_planilha"] = result["aula"]
        question["assunto"] = result["assunto"]
        question["assuntos"] = result["assuntos"]
        question["trilha_assuntos"] = result["trilha"]
        question["classificacao_planilha"] = {
            "status": result["status"],
            "confianca": result["confianca"],
            "metodo": result["metodo"],
            "referencia": result["referencia"],
            "fonte": result["fonte_taxonomia"],
            "categoria_origem": result["categoria_origem"],
            "assuntos_origem": result["assuntos_origem"],
        }
        return question
