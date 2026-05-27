"""Build the sample corpus from public Elastic GitHub repositories.

Standard library only (uses ``git`` via subprocess) so it runs without the
project's ML/ES dependencies — ``make corpus`` runs before ``make ingest``.

Strategy (see docs/CORPUS.md): partial-clone each repo (``--depth 1
--filter=blob:none --no-checkout``), list the tree cheaply, select topic-relevant
``.md`` files, lazily fetch only those blobs, and write them under
``data/sample_corpus/<repo>/`` with git-derived front-matter. ``data/sample_corpus``
is gitignored and reproducible — the repo holds this script, not Elastic's content.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.ingestion.loaders import parse_front_matter

# (org, repo). elasticsearch-labs is primary (Apache-2.0); docs-content secondary.
SOURCES = [
    ("elastic", "elasticsearch-labs"),
    ("elastic", "docs-content"),
]

TOPIC_KEYWORDS = (
    "search", "vector", "hybrid", "rrf", "reciprocal", "embedding", "embeddings",
    "semantic", "rag", "knn", "retriev", "rerank", "reranking", "elser", "dense",
    "similarity", "ai-search", "ann",
)

# Path segments / filenames that are never corpus content.
EXCLUDE_SEGMENTS = {
    "node_modules", ".github", "test", "tests", "__tests__", "templates",
    "images", "img", "assets", ".devcontainer",
}
EXCLUDE_NAMES = {
    "changelog.md", "contributing.md", "code_of_conduct.md", "code-of-conduct.md",
    "license.md", "security.md", "support.md",
}

MIN_CHARS = 300


class CorpusFetchError(RuntimeError):
    pass


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CorpusFetchError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _is_topical(path: str) -> bool:
    lower = path.lower()
    if not lower.endswith(".md"):
        return False
    segments = lower.split("/")
    if any(seg in EXCLUDE_SEGMENTS for seg in segments):
        return False
    if segments[-1] in EXCLUDE_NAMES:
        return False
    return any(kw in lower for kw in TOPIC_KEYWORDS)


def _derive_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _front_matter(title: str, source_url: str, version: str, last_updated: str) -> str:
    safe_title = title.replace('"', "'").strip()
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f'source_url: "{source_url}"\n'
        f'version: "{version}"\n'
        f'last_updated: "{last_updated}"\n'
        "---\n\n"
    )


def fetch_repo(org: str, repo: str, out_root: Path, limit: int) -> tuple[int, int]:
    """Fetch one repo into out_root/<repo>. Returns (selected, skipped)."""
    url = f"https://github.com/{org}/{repo}.git"
    tmp = Path(tempfile.mkdtemp(prefix=f"corpus-{repo}-"))
    try:
        _git("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", url, str(tmp))
        branch = _git("-C", str(tmp), "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"
        last_updated = _git("-C", str(tmp), "log", "-1", "--format=%cs").strip()

        all_paths = _git("-C", str(tmp), "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        candidates = sorted(p for p in all_paths if _is_topical(p))[: limit * 3]

        dest_root = out_root / repo
        if dest_root.exists():
            shutil.rmtree(dest_root)  # reproducible: drop stale selection

        selected = 0
        skipped = 0
        for path in candidates:
            if selected >= limit:
                break
            try:
                raw = _git("-C", str(tmp), "show", f"HEAD:{path}")
            except CorpusFetchError:
                skipped += 1
                continue
            _, body = parse_front_matter(raw)
            if len(body.strip()) < MIN_CHARS:
                skipped += 1
                continue
            title = _derive_title(body, Path(path).stem)
            source_url = f"https://github.com/{org}/{repo}/blob/{branch}/{path}"
            dest = dest_root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                _front_matter(title, source_url, branch, last_updated) + body.lstrip(),
                encoding="utf-8",
            )
            selected += 1
        return selected, skipped
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the sample corpus from Elastic repos.")
    parser.add_argument("--out", default="data/sample_corpus", help="Output corpus directory.")
    parser.add_argument("--limit", type=int, default=18, help="Max files per repo.")
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    total = 0
    try:
        for org, repo in SOURCES:
            print(f"Fetching {org}/{repo} ...", flush=True)
            selected, skipped = fetch_repo(org, repo, out_root, args.limit)
            total += selected
            print(f"  selected={selected} skipped={skipped}")
    except CorpusFetchError as exc:
        print(f"ERROR: corpus fetch failed: {exc}", file=sys.stderr)
        print(
            "If you are offline, place a few Markdown docs with front-matter "
            "directly in data/sample_corpus/ (see docs/CORPUS.md).",
            file=sys.stderr,
        )
        return 1

    print(f"Done. {total} documents written to {out_root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
