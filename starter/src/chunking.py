"""Implement fixed-size and structure-aware chunking."""
from __future__ import annotations

import re

from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split text into overlapping windows and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")
    if not page.text.strip():
        return []

    step = size - overlap
    chunks: list[Chunk] = []
    text = page.text
    index = 0
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        part = text[start:end].strip()
        if not part:
            break
        chunk_id = f"{page.document_id}:{page.page}:{index}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=part,
                metadata={**page.metadata, "chunk_strategy": "fixed_size", "chunk_index": index},
            )
        )
        index += 1
        if end >= len(text):
            break
        start += step
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs, split oversized paragraphs, and retain the page metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if not page.text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", page.text.strip()) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    index = 0

    def flush_buffer() -> None:
        nonlocal index
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        if not text:
            return
        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}:{page.page}:{index}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=text,
                metadata={**page.metadata, "chunk_strategy": "by_paragraph", "chunk_index": index},
            )
        )
        index += 1

    for paragraph in paragraphs:
        if len(paragraph) <= max_size:
            if buffer_len + len(paragraph) + 1 <= max_size:
                buffer.append(paragraph)
                buffer_len += len(paragraph) + 1
            else:
                flush_buffer()
                buffer = [paragraph]
                buffer_len = len(paragraph)
        else:
            if buffer:
                flush_buffer()
                buffer = []
                buffer_len = 0
            segments = [paragraph[i : i + max_size] for i in range(0, len(paragraph), max_size)]
            for seg in segments:
                chunks.append(
                    Chunk(
                        chunk_id=f"{page.document_id}:{page.page}:{index}",
                        document_id=page.document_id,
                        source=page.source,
                        page=page.page,
                        text=seg.strip(),
                        metadata={**page.metadata, "chunk_strategy": "by_paragraph", "chunk_index": index},
                    )
                )
                index += 1
    if buffer:
        flush_buffer()
    return chunks
