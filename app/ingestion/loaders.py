"""Corpus loaders: discover files and turn them into ``Document`` objects.

Markdown carries front-matter (``title``, ``source_url``, ``version``,
``last_updated``) written by ``fetch_corpus.py``. PDFs are read with ``pypdf``
(imported lazily so the rest of ingestion does not require it).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.chunking import make_doc_id
from app.ingestion.models import Document

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_FM_KEYS = {"title", "source_url", "version", "last_updated"}


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` front-matter block from the body.

    A minimal parser for ``key: value`` lines (the four keys we write). No YAML
    dependency. Returns (metadata, body); metadata is empty if no block is present.
    """
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in _FM_KEYS and value:
            meta[key] = value
    return meta, text[m.end() :]


def _derive_title(body: str, fallback: str) -> str:
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else fallback


def load_markdown(path: Path, corpus_root: Path) -> Document:
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_front_matter(raw)
    source_path = str(path.relative_to(corpus_root))
    title = meta.get("title") or _derive_title(body, path.stem)
    return Document(
        doc_id=make_doc_id(source_path),
        source_path=source_path,
        title=title,
        content=body,
        kind="markdown",
        source_url=meta.get("source_url", ""),
        version=meta.get("version", "unknown"),
        last_updated=meta.get("last_updated"),
    )


def load_pdf(path: Path, corpus_root: Path) -> Document:
    from pypdf import PdfReader  # lazy: only PDFs need this

    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    source_path = str(path.relative_to(corpus_root))
    info = reader.metadata or {}
    title = (info.title if getattr(info, "title", None) else None) or path.stem
    return Document(
        doc_id=make_doc_id(source_path),
        source_path=source_path,
        title=title,
        content=text,
        kind="pdf",
        source_url="",
        version="unknown",
        last_updated=None,
    )


def discover(path: Path):
    """Yield (file_path, kind) for supported files under ``path``."""
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        suffix = file.suffix.lower()
        if suffix == ".md":
            yield file, "markdown"
        elif suffix == ".pdf":
            yield file, "pdf"


def load_document(path: Path, kind: str, corpus_root: Path) -> Document:
    if kind == "markdown":
        return load_markdown(path, corpus_root)
    if kind == "pdf":
        return load_pdf(path, corpus_root)
    raise ValueError(f"unsupported document kind: {kind}")
