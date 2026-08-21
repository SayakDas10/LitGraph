from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pymupdf
import requests

DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
REFERENCE_HEADING = re.compile(r"(?:^|\n)\s*(?:references|bibliography|works cited)\s*(?:\n|$)", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return b"%PDF-" in stream.read(1024)
    except OSError:
        return False


def valid_attachment(stream, extension: str) -> bool:
    """Check common container signatures; restore the upload stream position."""
    position = stream.tell()
    header = stream.read(8)
    stream.seek(position)
    if extension == "pdf":
        position = stream.tell()
        stream.seek(0)
        pdf_header = stream.read(1024)
        stream.seek(position)
        return b"%PDF-" in pdf_header
    if extension in {"docx", "pptx"}:
        return header.startswith(b"PK\x03\x04")
    if extension == "ppt":
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension in {"txt", "md"}:
        return b"\x00" not in header
    return False


def extract_pdf(path: Path) -> tuple[str, str]:
    """Extract text and a conservative local title, always closing the document."""
    with pymupdf.open(path) as document:
        page_texts = [page.get_text("text") for page in document]
        metadata_title = (document.metadata or {}).get("title", "").strip()
    text = "\n".join(page_texts)
    title = metadata_title if _plausible_title(metadata_title) else _title_from_first_page(page_texts[0] if page_texts else "")
    return text, title or path.stem


def _plausible_title(title: str) -> bool:
    return len(title) >= 8 and not title.isnumeric() and not title.lower().endswith(".pdf")


def _title_from_first_page(text: str) -> str:
    candidates = []
    for line in text.splitlines()[:30]:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if 12 <= len(cleaned) <= 240 and len(WORD_PATTERN.findall(cleaned)) >= 3:
            if not re.match(r"^(abstract|doi|arxiv|copyright|proceedings)\b", cleaned, re.IGNORECASE):
                candidates.append(cleaned)
    return max(candidates[:8], key=len, default="")


def resolve_online_title(text: str, fallback: str, timeout: float = 5) -> tuple[str, str]:
    """Resolve metadata by DOI only; never transmit arbitrary first-page text."""
    doi_match = DOI_PATTERN.search(text[:20_000])
    if not doi_match:
        return fallback, "local"
    doi = doi_match.group(0).rstrip(".,;)")
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "title"}, timeout=timeout,
        )
        response.raise_for_status()
        title = response.json().get("title", "").strip()
        return (title, "semantic-scholar-doi") if _plausible_title(title) else (fallback, "local")
    except (requests.RequestException, ValueError, AttributeError):
        return fallback, "local"


def paper_record(path: str, absolute_path: Path, previous: dict[str, Any] | None, online: bool) -> dict[str, Any]:
    stat = absolute_path.stat()
    text, title = extract_pdf(absolute_path)
    source = "local"
    if online:
        title, source = resolve_online_title(text, title)
    return {
        "path": path, "uuid": previous["uuid"] if previous else uuid.uuid4().hex,
        "mtime": stat.st_mtime, "size": stat.st_size, "title": title,
        "manual_title": previous.get("manual_title", 0) if previous else 0,
        "status": previous.get("status", "none") if previous else "none",
        "text": text, "metadata_source": source,
    }


def build_edges(papers: list[dict[str, Any]], affected_paths: set[str] | None = None) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for source in papers:
        source_text = source.get("text", "")
        reference_start, reference_text = _reference_section(source_text)
        if not reference_text:
            continue
        for target in papers:
            if source["path"] == target["path"]:
                continue
            if affected_paths is not None and source["path"] not in affected_paths and target["path"] not in affected_paths:
                continue
            match = _title_match(reference_text, target["title"])
            if not match:
                continue
            entry = _reference_entry(reference_text, match.start(), match.end())
            marker, marker_method = _citation_marker(entry)
            contexts = _citation_contexts(source_text[:reference_start], marker)
            confidence = 0.72 + (0.18 if marker else 0) + (0.05 if contexts else 0)
            edges.append({
                "source": source["path"], "target": target["path"], "marker": marker,
                "contexts": json.dumps(contexts, ensure_ascii=False),
                "bibliography": re.sub(r"\s+", " ", entry).strip()[:1000],
                "confidence": min(confidence, 0.95), "method": f"normalized-title+{marker_method}",
            })
    return edges


def _reference_section(text: str) -> tuple[int, str]:
    matches = list(REFERENCE_HEADING.finditer(text))
    return (matches[-1].end(), text[matches[-1].end():]) if matches else (len(text), "")


def _title_match(reference_text: str, title: str) -> re.Match[str] | None:
    # Retain stop words: removing them makes the regex require surrounding
    # content words to be adjacent (for example, "robust memory" would not
    # match "robust in memory"). Punctuation remains deliberately flexible.
    tokens = WORD_PATTERN.findall(title.lower())
    if len(tokens) < 3:
        return None
    selected = tokens[: min(10, len(tokens))]
    return re.search(r"\b" + r"[\s\W_]+".join(map(re.escape, selected)) + r"\b", reference_text, re.IGNORECASE)


def _reference_entry(reference_text: str, start: int, end: int) -> str:
    numbered_start = list(re.finditer(r"(?:^|\n)\s*(?:\[\d+\]|\d+[.)])\s+", reference_text[:start]))
    entry_start = numbered_start[-1].start() if numbered_start else max(0, start - 250)
    next_numbered = re.search(r"\n\s*(?:\[\d+\]|\d+[.)])\s+", reference_text[end:])
    entry_end = end + next_numbered.start() if next_numbered else min(len(reference_text), end + 350)
    return reference_text[entry_start:entry_end]


def _citation_marker(entry: str) -> tuple[str, str]:
    numeric = re.search(r"^\s*(?:\[(\d+)\]|(\d+)[.)])", entry)
    if numeric:
        return numeric.group(1) or numeric.group(2), "numeric-marker"
    year = YEAR_PATTERN.search(entry)
    surname = re.search(r"\b([A-Z][A-Za-z'’-]{2,})\b", entry)
    if year and surname:
        return f"{surname.group(1)} {year.group(0)}", "author-year-marker"
    return "", "unmarked"


def _citation_contexts(body: str, marker: str) -> list[str]:
    if not marker:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", body))
    if marker.isdigit():
        number = re.escape(marker)
        pattern = re.compile(rf"\[[^\]]*(?<!\d){number}(?!\d)[^\]]*\]")
    else:
        surname, year = marker.rsplit(" ", 1)
        pattern = re.compile(rf"\b{re.escape(surname)}\b[^.!?]{{0,80}}\b{re.escape(year)}\b", re.IGNORECASE)
    return [sentence.strip() for sentence in sentences if pattern.search(sentence)][:10]
