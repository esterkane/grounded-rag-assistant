"""Unit tests for the corpus fetch filtering and front-matter (no network)."""

from app.ingestion.fetch_corpus import _derive_title, _front_matter, _is_topical
from app.ingestion.loaders import parse_front_matter


def test_topic_filter_selects_relevant_markdown():
    assert _is_topical("notebooks/search/hybrid-search.md")
    assert _is_topical("reference/vector-search.md")


def test_topic_filter_rejects_offtopic_and_excluded():
    assert not _is_topical("docs/installation-guide.md")  # no topic keyword
    assert not _is_topical("notebooks/search/setup.py")  # not markdown
    assert not _is_topical("tests/search/test_things.md")  # excluded segment
    assert not _is_topical("CONTRIBUTING.md")  # excluded name


def test_derive_title_prefers_first_h1():
    assert _derive_title("# Real Title\n\nbody", "fallback") == "Real Title"
    assert _derive_title("no heading here", "fallback") == "fallback"


def test_front_matter_round_trips():
    fm = _front_matter("My Doc", "https://github.com/x/y/blob/main/z.md", "main", "2025-05-01")
    meta, body = parse_front_matter(fm + "# Heading\n\ncontent")
    assert meta["title"] == "My Doc"
    assert meta["source_url"].endswith("z.md")
    assert meta["version"] == "main"
    assert meta["last_updated"] == "2025-05-01"
    assert body.startswith("# Heading")
