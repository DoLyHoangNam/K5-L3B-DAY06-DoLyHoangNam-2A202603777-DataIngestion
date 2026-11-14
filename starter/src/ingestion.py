"""Read and normalize source data from PDFs and manifest."""
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pypdf

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFC) and whitespace while preserving paragraph breaks."""
    cleaned = unicodedata.normalize("NFC", text or "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    page_numbers: list[int] | None = None,
    page_sections: dict[int, str] | None = None,
    base_metadata: dict[str, Any] | None = None,
) -> list[DocumentPage]:
    """Extract specified physical pages from a PDF, retaining page number and metadata."""
    reader = pypdf.PdfReader(path)
    total = len(reader.pages)
    target_pages = page_numbers if page_numbers is not None else list(range(1, total + 1))

    pages: list[DocumentPage] = []
    for page_no in target_pages:
        if page_no < 1 or page_no > total:
            raise ValueError(f"Page {page_no} out of range (1..{total}) for {path}")
        raw_text = reader.pages[page_no - 1].extract_text() or ""
        text = normalize_text(raw_text)
        meta = dict(base_metadata or {})
        if page_sections and page_no in page_sections:
            meta["section"] = page_sections[page_no]
        meta["char_count"] = len(text)
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_no,
                text=text,
                metadata=meta,
            )
        )
    return pages


def load_corpus_from_manifest(
    manifest_path: Path, project_root: Path
) -> tuple[list[DocumentPage], list[dict[str, Any]]]:
    """Load all manifest-approved content pages and log any empty/short pages."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_pages: list[DocumentPage] = []
    logs: list[dict[str, Any]] = []

    for doc in manifest["documents"]:
        pdf_path = project_root / doc["local_path"]
        page_nums = [p["page"] for p in doc["pages"]]
        page_sections = {p["page"]: p["section"] for p in doc["pages"]}
        base_meta = {"year": doc["year"], "title": doc["title"]}

        loaded = load_pdf(
            path=pdf_path,
            document_id=doc["source_id"],
            source=doc["local_path"],
            page_numbers=page_nums,
            page_sections=page_sections,
            base_metadata=base_meta,
        )
        for p in loaded:
            if not p.text:
                logs.append({"document_id": p.document_id, "page": p.page, "issue": "empty_text"})
            all_pages.append(p)

    return all_pages, logs
