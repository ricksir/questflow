from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract
from PIL import Image


@dataclass(slots=True)
class MarkdownBundle:
    source_path: str
    cache_key: str
    markdown_path: str
    metadata_path: str
    image_dir: str
    pages: list[str]
    engine: str
    used_ocr: bool

    @property
    def markdown(self) -> str:
        return "\n\n".join(self.pages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "cache_key": self.cache_key,
            "markdown_path": self.markdown_path,
            "metadata_path": self.metadata_path,
            "image_dir": self.image_dir,
            "pages": self.pages,
            "engine": self.engine,
            "used_ocr": self.used_ocr,
        }


def _hash_file(path: Path, *, salt: str = "") -> str:
    digest = hashlib.sha256()
    digest.update(salt.encode("utf-8"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:24]


def _clean_markdown(text: str) -> str:
    text = text.replace("\x00", "").replace("\u00ad", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()



def _pdf_text_probe(path: Path, sample_pages: int = 3) -> tuple[float, int]:
    """Cheap probe used to avoid expensive layout analysis on image-only PDFs."""
    document = pymupdf.open(path)
    try:
        lengths: list[int] = []
        image_count = 0
        for index, page in enumerate(document):
            if index >= max(1, sample_pages):
                break
            lengths.append(len((page.get_text("text") or "").strip()))
            image_count += len(page.get_images(full=True))
        return (sum(lengths) / max(1, len(lengths))), image_count
    finally:
        document.close()


def _fallback_pdf_pages(path: Path) -> list[str]:
    document = pymupdf.open(path)
    try:
        pages = []
        for index, page in enumerate(document):
            text = page.get_text("text") or ""
            pages.append(f"<!-- page:{index + 1} -->\n\n{_clean_markdown(text)}")
        return pages
    finally:
        document.close()


def _ocr_image_to_markdown(path: Path, languages: str) -> list[str]:
    with Image.open(path) as image:
        text = pytesseract.image_to_string(image.convert("RGB"), lang=languages, config="--psm 6")
    return [f"<!-- page:1 -->\n\n{_clean_markdown(text)}"]


def _ocr_pdf_pages(path: Path, languages: str, dpi: int) -> list[str]:
    """Convert an image-only PDF into page-preserving OCR Markdown.

    The page markers are intentionally retained because the question extractor
    uses them to report the original page range and attach visual context.
    """
    document = pymupdf.open(path)
    try:
        pages: list[str] = []
        scale = max(150, min(int(dpi), 400)) / 72
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            text = pytesseract.image_to_string(
                image,
                lang=languages,
                config="--psm 6",
            )
            pages.append(f"<!-- page:{index + 1} -->\n\n{_clean_markdown(text)}")
        return pages or ["<!-- page:1 -->"]
    finally:
        document.close()


def _try_pymupdf4llm(
    path: Path,
    image_dir: Path,
    *,
    languages: str,
    force_ocr: bool,
    dpi: int,
) -> tuple[list[str], str, bool]:
    """Run PyMuPDF4LLM in an isolated process.

    PyMuPDF4LLM 0.3.x can keep the source PDF open briefly on Windows after
    ``to_markdown`` returns. Running the conversion in a short-lived worker
    guarantees that every native handle is released when the worker exits.
    """
    del languages, force_ocr  # kept in the signature for compatibility
    image_dir.mkdir(parents=True, exist_ok=True)
    worker_path = Path(__file__).with_name("markdown_worker.py")
    if not worker_path.exists():
        raise FileNotFoundError(worker_path)

    with tempfile.TemporaryDirectory(prefix="questflow_markdown_worker_") as temp_name:
        result_path = Path(temp_name) / "result.json"
        command = [
            sys.executable,
            str(worker_path),
            "--source",
            str(path),
            "--image-dir",
            str(image_dir),
            "--result",
            str(result_path),
            "--dpi",
            str(max(150, min(int(dpi), 400))),
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                "Falha no processo isolado do PyMuPDF4LLM"
                + (f": {detail}" if detail else "")
            )
        if not result_path.exists():
            raise RuntimeError("O processo isolado não retornou o resultado Markdown.")
        payload = json.loads(result_path.read_text(encoding="utf-8"))

    raw_pages = payload.get("pages", [])
    pages = [
        f"<!-- page:{index + 1} -->\n\n{_clean_markdown(str(page_text))}"
        for index, page_text in enumerate(raw_pages)
    ]
    if not pages:
        pages = ["<!-- page:1 -->"]
    version = str(payload.get("version", "unknown"))
    return pages, f"pymupdf4llm-{version}-isolated", False


def build_markdown_bundle(
    source_path: str | Path,
    cache_dir: str | Path,
    *,
    languages: str = "por+eng",
    force_ocr: bool = False,
    dpi: int = 220,
    refresh: bool = False,
) -> MarkdownBundle:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    key = _hash_file(path, salt=f"{languages}|{force_ocr}|{dpi}|markdown-v2")
    bundle_dir = cache_root / key
    image_dir = bundle_dir / "images"
    markdown_path = bundle_dir / "document.md"
    metadata_path = bundle_dir / "metadata.json"

    if not refresh and markdown_path.exists() and metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            pages = list(metadata.get("pages", []))
            if pages:
                return MarkdownBundle(
                    source_path=str(path),
                    cache_key=key,
                    markdown_path=str(markdown_path),
                    metadata_path=str(metadata_path),
                    image_dir=str(image_dir),
                    pages=[str(item) for item in pages],
                    engine=str(metadata.get("engine", "cache")),
                    used_ocr=bool(metadata.get("used_ocr", False)),
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    bundle_dir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    engine = "fallback"
    used_ocr = False
    pages: list[str]
    if suffix == ".pdf":
        if force_ocr:
            try:
                # Preserve layout images through PyMuPDF4LLM, then use a deterministic
                # Tesseract pass for the Markdown text of difficult/scanned documents.
                try:
                    _try_pymupdf4llm(
                        path,
                        image_dir,
                        languages=languages,
                        force_ocr=False,
                        dpi=dpi,
                    )
                except Exception:
                    pass
                pages = _ocr_pdf_pages(path, languages, dpi)
                engine = "pymupdf4llm-images+tesseract-markdown"
                used_ocr = True
            except Exception:
                pages = _fallback_pdf_pages(path)
                engine = "pymupdf-text-fallback"
                used_ocr = False
        else:
            average_text, sampled_images = _pdf_text_probe(path)
            if (average_text < 180 and sampled_images > 0) or sampled_images > 60:
                # Image-only exports are handled much faster and more accurately by
                # the visual OCR extractor that follows. We still create Markdown
                # immediately, without invoking a costly layout model on every image.
                pages = _fallback_pdf_pages(path)
                engine = "pymupdf-fast-probe-image-heavy-pdf"
                used_ocr = False
            else:
                try:
                    pages, engine, used_ocr = _try_pymupdf4llm(
                        path,
                        image_dir,
                        languages=languages,
                        force_ocr=False,
                        dpi=dpi,
                    )
                except Exception:
                    pages = _fallback_pdf_pages(path)
                    engine = "pymupdf-text-fallback"
                    used_ocr = False
    else:
        pages = _ocr_image_to_markdown(path, languages)
        engine = "tesseract-image-markdown"
        used_ocr = True

    markdown = "\n\n".join(pages)
    markdown_path.write_text(markdown, encoding="utf-8")
    metadata = {
        "source_path": str(path),
        "cache_key": key,
        "pages": pages,
        "engine": engine,
        "used_ocr": used_ocr,
        "image_dir": str(image_dir),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return MarkdownBundle(
        source_path=str(path),
        cache_key=key,
        markdown_path=str(markdown_path),
        metadata_path=str(metadata_path),
        image_dir=str(image_dir),
        pages=pages,
        engine=engine,
        used_ocr=used_ocr,
    )
