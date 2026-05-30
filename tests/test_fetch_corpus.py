"""Tests for the corpus fetch script (docs/CORPUS.md).

The front-matter derivation tests run against a real but tiny local git repo
("fake git history"), so they exercise the actual ``git log`` path without any
network. The full live-network fetch is a separate, explicitly-marked test that
is skipped unless ``RUN_LIVE_CORPUS_FETCH`` is set.
"""

import os
from pathlib import Path

import pytest

from app.ingestion.fetch_corpus import (
    FrontMatter,
    RepoSource,
    corpus_fetch_date,
    derive_front_matter,
    extract_title,
    fetch_corpus,
    render_document,
    split_existing_front_matter,
    topic_score,
)
from app.ingestion.loaders import load_markdown


def test_derive_front_matter_stamps_the_fetch_date(tmp_path: Path) -> None:
    repo = RepoSource("elastic", "elasticsearch-labs", ref="main")
    (tmp_path / "notebooks").mkdir()
    (tmp_path / "notebooks/hybrid-search.md").write_text(
        "# Hybrid Search with RRF\n\nReciprocal rank fusion combines BM25 and kNN.\n",
        encoding="utf-8",
    )

    fetched_at = "2026-05-30"
    fm = derive_front_matter(repo, tmp_path, "notebooks/hybrid-search.md", fetched_at)

    assert fm.title == "Hybrid Search with RRF"
    assert fm.source_url == (
        "https://github.com/elastic/elasticsearch-labs/blob/main/notebooks/hybrid-search.md"
    )
    assert fm.version == "main"
    # last_updated is the corpus snapshot date, not a per-file commit date.
    assert fm.last_updated == fetched_at


def test_one_fetch_shares_a_single_last_updated_across_files(tmp_path: Path) -> None:
    repo = RepoSource("elastic", "elasticsearch-labs", ref="main")
    (tmp_path / "a.md").write_text("# Vector Search\n\nDense kNN retrieval.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Semantic Search\n\nEmbeddings recall.\n", encoding="utf-8")

    fetched_at = corpus_fetch_date()
    fm_a = derive_front_matter(repo, tmp_path, "a.md", fetched_at)
    fm_b = derive_front_matter(repo, tmp_path, "b.md", fetched_at)

    # Every file from the same fetch carries the same snapshot stamp.
    assert fm_a.last_updated == fm_b.last_updated == fetched_at
    # corpus_fetch_date() is an ISO date (YYYY-MM-DD).
    assert len(fetched_at) == 10 and fetched_at.count("-") == 2


def test_rendered_document_roundtrips_through_the_loader(tmp_path: Path) -> None:
    # No git here: render the derived front-matter and confirm the Phase 1 loader
    # accepts it (required keys present, body preserved). Runs everywhere.
    fm = FrontMatter(
        title="Vector Search",
        source_url="https://github.com/elastic/elasticsearch-labs/blob/main/vector-search.md",
        version="main",
        last_updated="2025-01-02",
    )
    body = "# Vector Search\n\nDense vector kNN retrieval in Elasticsearch.\n"

    out = tmp_path / "out.md"
    out.write_text(render_document(fm, body), encoding="utf-8")

    doc = load_markdown(out)
    assert doc.title == "Vector Search"
    assert doc.source_url.endswith("/blob/main/vector-search.md")
    assert doc.version == "main"
    assert doc.last_updated == "2025-01-02"
    assert doc.permissions == ["public"]
    assert "Dense vector kNN" in doc.content


def test_existing_front_matter_is_stripped_before_h1_lookup() -> None:
    text = "---\nmapped_pages:\n  - /old/url\n---\n\n# Semantic Search\n\nBody.\n"
    fm_block, body = split_existing_front_matter(text)
    assert fm_block is not None
    assert body.startswith("# Semantic Search")
    assert extract_title(body, "fallback") == "Semantic Search"


def test_title_falls_back_to_filename_when_no_h1() -> None:
    assert extract_title("No heading here, just prose.\n", "rrf retrieval") == "rrf retrieval"


def test_topic_score_weights_path_and_ignores_unrelated_words() -> None:
    assert topic_score("guides/hybrid-search.md", "About hybrid search and vectors") > 0
    # "storage"/"average" must not trip the word-bounded "rag"/"search" filter.
    assert topic_score("ops/storage.md", "Average storage configuration guide.") == 0


@pytest.mark.live_network
@pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_CORPUS_FETCH"),
    reason="live GitHub fetch; set RUN_LIVE_CORPUS_FETCH=1 to run",
)
def test_full_fetch_against_github(tmp_path: Path) -> None:
    summary = fetch_corpus(
        corpus_dir=tmp_path / "corpus",
        work_dir=tmp_path / "clones",
        max_docs=20,
    )
    assert summary.selected > 0
    written = list((tmp_path / "corpus").rglob("*.md"))
    assert written
    # Every written file must carry valid front-matter the loader accepts.
    for path in written:
        doc = load_markdown(path)
        assert doc.title
        assert doc.source_url.startswith("https://github.com/")
