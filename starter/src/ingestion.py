"""Read and normalize source data."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping useful paragraph boundaries."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def load_pdf(path: Path | str, document_id: str, source: str) -> list[DocumentPage]:
    """Load a PDF or JSON corpus page list and return structured page objects."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")

    suffix = file_path.suffix.lower()
    pages: list[DocumentPage] = []

    if suffix == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            page_items = payload.get("pages", [])
        elif isinstance(payload, list):
            page_items = payload
        else:
            raise ValueError(f"Unsupported JSON corpus format in {file_path}")

        for index, item in enumerate(page_items, start=1):
            if not isinstance(item, dict):
                continue
            page_no = int(item.get("page", index))
            text = normalize_text(item.get("text", ""))
            metadata = {k: v for k, v in item.items() if k not in {"page", "text"}}
            pages.append(
                DocumentPage(
                    document_id=document_id,
                    source=source,
                    page=page_no,
                    text=text,
                    metadata=metadata,
                )
            )
        return pages

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        for page_index, page in enumerate(reader.pages, start=1):
            text = normalize_text(page.extract_text() or "")
            pages.append(
                DocumentPage(
                    document_id=document_id,
                    source=source,
                    page=page_index,
                    text=text,
                    metadata={"page_count": len(reader.pages)},
                )
            )
        return pages

    text = normalize_text(file_path.read_text(encoding="utf-8"))
    pages.append(
        DocumentPage(
            document_id=document_id,
            source=source,
            page=1,
            text=text,
            metadata={"file_type": suffix.lstrip(".") or "text"},
        )
    )
    return pages
