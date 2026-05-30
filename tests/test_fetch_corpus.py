"""Tests for the corpus fetch script (docs/CORPUS.md).

The front-matter derivation tests run against a real but tiny local git repo
("fake git history"), so they exercise the actual ``git log`` path without any
network. The full live-network fetch is a separate, explicitly-marked test that
is skipped unless ``RUN_LIVE_CORPUS_FETCH`` is set.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.ingestion.fetch_corpus import (
    FrontMatter,
    RepoSource,
    derive_front_matter,
    extract_title,
    fetch_corpus,
    render_document,
    split_existing_front_matter,
    topic_score,
)
from app.ingestion.loaders import load_markdown

# The git-fixture tests need a real git binary. It is present on the host and on
# CI runners, but not inside the api Docker image (where fetching is never run),
# so skip rather than fail there.
requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")


def _git(args: list[str], cwd: Path, date: str | None = None) -> None:
    env = dict(os.environ)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def _init_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], repo_dir)
    _git(["config", "user.email", "test@example.com"], repo_dir)
    _git(["config", "user.name", "Test"], repo_dir)


@requires_git
def test_derive_front_matter_from_fake_git_history(tmp_path: Path) -> None:
    repo_dir = tmp_path / "elasticsearch-labs"
    _init_repo(repo_dir)
    rel_path = "notebooks/hybrid-search.md"
    target = repo_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Hybrid Search with RRF\n\nReciprocal rank fusion combines BM25 and kNN.\n",
        encoding="utf-8",
    )
    _git(["add", "."], repo_dir)
    _git(["commit", "-q", "-m", "add doc"], repo_dir, date="2024-03-14T12:00:00")

    repo = RepoSource("elastic", "elasticsearch-labs", ref="main")
    fm = derive_front_matter(repo, repo_dir, rel_path)

    assert fm.title == "Hybrid Search with RRF"
    assert fm.source_url == (
        "https://github.com/elastic/elasticsearch-labs/blob/main/notebooks/hybrid-search.md"
    )
    assert fm.version == "main"
    assert fm.last_updated == "2024-03-14"


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
