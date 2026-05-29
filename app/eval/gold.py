"""Gold evaluation set loading.

The gold set lives in ``data/gold/queries.jsonl`` (one JSON object per line).
Each item identifies the documents that should answer a query by their stable
``source_path`` (the per-document identifier in the corpus), whether the query
is answerable from the corpus, and a free-text note.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GoldQuery:
    query: str
    # Stable document identifiers (chunk.source_path) expected to be relevant.
    relevant_doc_ids: list[str] = field(default_factory=list)
    expected_answerable: bool = True
    notes: str = ""


def load_gold(path: str | Path) -> list[GoldQuery]:
    """Load and validate the gold set from a JSONL file."""
    gold: list[GoldQuery] = []
    for line_no, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if "query" not in data:
            raise ValueError(f"{path}:{line_no}: missing required field 'query'")
        gold.append(
            GoldQuery(
                query=data["query"],
                relevant_doc_ids=list(data.get("relevant_doc_ids", [])),
                expected_answerable=bool(data.get("expected_answerable", True)),
                notes=str(data.get("notes", "")),
            )
        )
    return gold
