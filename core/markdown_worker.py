from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="QuestFlow isolated PyMuPDF4LLM worker")
    parser.add_argument("--source", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--dpi", type=int, default=220)
    args = parser.parse_args()

    source = Path(args.source)
    image_dir = Path(args.image_dir)
    result_path = Path(args.result)
    image_dir.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    import pymupdf4llm

    chunks = pymupdf4llm.to_markdown(
        str(source),
        page_chunks=True,
        write_images=True,
        image_path=str(image_dir),
        image_format="png",
        dpi=max(150, min(int(args.dpi), 400)),
        show_progress=False,
    )

    pages: list[str] = []
    if isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, dict):
                pages.append(str(chunk.get("text", "")))
            else:
                pages.append(str(chunk))
    elif isinstance(chunks, str):
        pages = [chunks]

    payload = {
        "pages": pages,
        "version": str(
            getattr(
                pymupdf4llm,
                "version",
                getattr(pymupdf4llm, "__version__", "unknown"),
            )
        ),
    }
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    # The worker exits immediately after this. Explicit cleanup helps on Windows,
    # while process termination guarantees that any native PDF handles are released.
    del chunks
    gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
