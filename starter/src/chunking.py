"""Implement fixed-size and structure-aware (paragraph) chunking."""
import re

from .models import Chunk, DocumentPage


def _make_chunk(page: DocumentPage, strategy: str, idx: int, text: str) -> Chunk:
    meta = dict(page.metadata)
    meta["strategy"] = strategy
    meta["chunk_index"] = idx
    meta["char_len"] = len(text)
    return Chunk(
        chunk_id=f"{strategy}:{page.document_id}:p{page.page:03d}:c{idx:03d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=meta,
    )


def fixed_size(
    page: DocumentPage, size: int = 500, overlap: int = 50, strategy: str = "A"
) -> list[Chunk]:
    """Split page text into fixed-size character windows with overlap."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError(f"Invalid size={size}, overlap={overlap}")
    text = page.text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    idx = 0
    while start < len(text):
        piece = text[start : start + size].strip()
        if piece:
            chunks.append(_make_chunk(page, strategy, idx, piece))
            idx += 1
        if start + size >= len(text):
            break
        start += step
    return chunks


def _split_long_block(block: str, max_size: int) -> list[str]:
    """Split an oversized paragraph at sentence or word boundaries."""
    if len(block) <= max_size:
        return [block]
    sentences = re.split(r"(?<=[.!?])\s+", block)
    parts: list[str] = []
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        if len(sent) > max_size:
            if buf:
                parts.append(buf)
                buf = ""
            words = sent.split(" ")
            wbuf = ""
            for w in words:
                cand = f"{wbuf} {w}".strip() if wbuf else w
                if len(cand) <= max_size:
                    wbuf = cand
                else:
                    if wbuf:
                        parts.append(wbuf)
                    wbuf = w[:max_size]
            if wbuf:
                parts.append(wbuf)
            continue
        cand = f"{buf} {sent}".strip() if buf else sent
        if len(cand) <= max_size:
            buf = cand
        else:
            if buf:
                parts.append(buf)
            buf = sent
    if buf:
        parts.append(buf)
    return parts


def by_paragraph(
    page: DocumentPage, max_size: int = 800, strategy: str = "B"
) -> list[Chunk]:
    """Group paragraphs up to max_size; split oversized paragraphs cleanly."""
    text = page.text.strip()
    if not text:
        return []

    raw_blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    if len(raw_blocks) == 1 and len(raw_blocks[0]) > max_size:
        # Fallback for PDFs with single-newline paragraph breaks
        raw_blocks = [b.strip() for b in text.split("\n") if b.strip()]

    atomic_blocks: list[str] = []
    for block in raw_blocks:
        atomic_blocks.extend(_split_long_block(block, max_size))

    chunks: list[Chunk] = []
    buf = ""
    idx = 0
    for block in atomic_blocks:
        cand = f"{buf}\n\n{block}".strip() if buf else block
        if len(cand) <= max_size:
            buf = cand
        else:
            if buf:
                chunks.append(_make_chunk(page, strategy, idx, buf))
                idx += 1
            buf = block
    if buf:
        chunks.append(_make_chunk(page, strategy, idx, buf))
    return chunks
