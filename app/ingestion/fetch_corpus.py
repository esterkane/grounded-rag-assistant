"""Fetch the document corpus from public Elastic GitHub repositories.

This implements the fetch step specified in ``docs/CORPUS.md``: it shallow-clones
the source repos, selects on-topic Markdown files, and writes each into
``data/sample_corpus/`` (namespaced by repo) with git-derived front-matter that
the Phase 1 loaders expect (``title``, ``source_url``, ``version``,
``last_updated``).

It is intentionally dependency-free (standard library + the ``git`` binary only)
so it can run on the host or a CI runner without the application's Python deps or
Elasticsearch. Run it via ``make corpus`` before ``make ingest``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# --- Configuration --------------------------------------------------------

DEFAULT_CORPUS_DIR = Path("data/sample_corpus")
DEFAULT_MIN_DOCS = 15
DEFAULT_MAX_DOCS = 40
# A file must reach this topic score to be selected. A single path keyword
# (weighted x3) clears it; an isolated body mention does not.
DEFAULT_MIN_SCORE = 2
# Skip stubs/redirects that carry no real content to retrieve.
MIN_BODY_CHARS = 200

# Topic filter from docs/CORPUS.md: search, vector, hybrid, RRF, embeddings,
# semantic, RAG / AI-search. Word-bounded so "rag" does not match "storage".
TOPIC_RE = re.compile(
    r"\b(?:search|vector|hybrid|rrf|embeddings?|semantic|rag|ai[-\s]?search)\b",
    re.IGNORECASE,
)
H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RepoSource:
    """A source repository to fetch corpus documents from."""

    org: str
    repo: str
    ref: str = "main"

    @property
    def slug(self) -> str:
        return self.repo

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.org}/{self.repo}.git"


# Primary + secondary sources, per docs/CORPUS.md.
SOURCE_REPOS: tuple[RepoSource, ...] = (
    RepoSource("elastic", "elasticsearch-labs"),
    RepoSource("elastic", "docs-content"),
)


@dataclass(frozen=True)
class FrontMatter:
    title: str
    source_url: str
    version: str
    last_updated: str


class FetchError(RuntimeError):
    """Raised when the corpus cannot be fetched cleanly (e.g. GitHub is down)."""


# --- Git helpers ----------------------------------------------------------


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def clone_or_update(repo: RepoSource, work_dir: Path) -> Path:
    """Shallow-clone ``repo`` into ``work_dir``, or update an existing clone.

    Raises ``FetchError`` (non-zero exit upstream) if GitHub is unreachable.
    """
    dest = work_dir / repo.repo
    if (dest / ".git").is_dir():
        fetch = _run_git(["fetch", "--depth", "1", "origin", repo.ref], cwd=dest)
        if fetch.returncode != 0:
            raise FetchError(f"git fetch failed for {repo.clone_url}: {fetch.stderr.strip()}")
        reset = _run_git(["reset", "--hard", f"origin/{repo.ref}"], cwd=dest)
        if reset.returncode != 0:
            raise FetchError(f"git reset failed for {repo.clone_url}: {reset.stderr.strip()}")
        return dest

    work_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    clone = _run_git(
        ["clone", "--depth", "1", "--branch", repo.ref, repo.clone_url, str(dest)]
    )
    if clone.returncode != 0:
        raise FetchError(f"git clone failed for {repo.clone_url}: {clone.stderr.strip()}")
    return dest


def git_last_commit_date(repo_dir: Path, rel_path: str) -> str:
    """Return the file's last commit date (``%cs``), or ``unknown``.

    On a ``--depth 1`` clone git only holds the tip commit, so this resolves to
    the tip commit date for every file — see docs/CORPUS.md.
    """
    result = _run_git(["log", "-1", "--format=%cs", "--", rel_path], cwd=repo_dir)
    date = result.stdout.strip()
    if result.returncode != 0 or not date:
        return "unknown"
    return date


# --- Selection & front-matter derivation ----------------------------------


def split_existing_front_matter(text: str) -> tuple[str | None, str]:
    """Split a leading ``---`` front-matter block from the body, if present."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[4:end], text[end + 4 :].lstrip()
    return None, text


def topic_score(rel_path: str, body: str) -> int:
    """Score topical relevance. Path keywords weigh more than body mentions."""
    path_hits = len(TOPIC_RE.findall(rel_path))
    body_hits = len(TOPIC_RE.findall(body))
    return path_hits * 3 + min(body_hits, 10)


def extract_title(body: str, fallback: str) -> str:
    match = H1_RE.search(body)
    title = match.group(1) if match else fallback
    return " ".join(title.split()).strip('"').strip()


def derive_front_matter(repo: RepoSource, repo_dir: Path, rel_path: str) -> FrontMatter:
    """Derive front-matter for one file from git + content (docs/CORPUS.md mapping)."""
    text = (repo_dir / rel_path).read_text(encoding="utf-8", errors="replace")
    _, body = split_existing_front_matter(text)
    fallback_title = Path(rel_path).stem.replace("-", " ").replace("_", " ").title()
    return FrontMatter(
        title=extract_title(body, fallback_title),
        source_url=f"https://github.com/{repo.org}/{repo.repo}/blob/{repo.ref}/{rel_path}",
        version=repo.ref,
        last_updated=git_last_commit_date(repo_dir, rel_path),
    )


def render_document(front_matter: FrontMatter, body: str) -> str:
    """Render a corpus file: normalized front-matter block + body."""
    header = "\n".join(
        [
            "---",
            f"title: {front_matter.title}",
            f"source_url: {front_matter.source_url}",
            f"version: {front_matter.version}",
            f"last_updated: {front_matter.last_updated}",
            "---",
            "",
            "",
        ]
    )
    return header + body.strip() + "\n"


@dataclass(frozen=True)
class Candidate:
    repo: RepoSource
    repo_dir: Path
    rel_path: str
    score: int


def select_files(repo: RepoSource, repo_dir: Path, min_score: int) -> tuple[list[Candidate], int]:
    """Return on-topic candidates from ``repo_dir`` and the count skipped."""
    candidates: list[Candidate] = []
    skipped = 0
    for path in sorted(repo_dir.rglob("*.md")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(repo_dir).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue
        _, body = split_existing_front_matter(text)
        if len(body.strip()) < MIN_BODY_CHARS:
            skipped += 1
            continue
        score = topic_score(rel_path, body)
        if score < min_score:
            skipped += 1
            continue
        candidates.append(Candidate(repo, repo_dir, rel_path, score))
    return candidates, skipped


# --- Orchestration --------------------------------------------------------


@dataclass(frozen=True)
class FetchSummary:
    repos: list[str]
    matched: int
    selected: int
    skipped: int
    per_repo_selected: dict[str, int]


def fetch_corpus(
    repos: tuple[RepoSource, ...] = SOURCE_REPOS,
    *,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    work_dir: Path | None = None,
    max_docs: int = DEFAULT_MAX_DOCS,
    min_docs: int = DEFAULT_MIN_DOCS,
    min_score: int = DEFAULT_MIN_SCORE,
) -> FetchSummary:
    """Fetch, select, and install the corpus. Atomic: nothing is written into
    ``corpus_dir`` unless every clone succeeds and at least one file is selected.
    """
    if work_dir is None:
        work_dir = Path(tempfile.gettempdir()) / "grounded-rag-corpus"

    repo_index = {repo: i for i, repo in enumerate(repos)}
    all_candidates: list[Candidate] = []
    skipped_total = 0
    for repo in repos:
        repo_dir = clone_or_update(repo, work_dir)
        candidates, skipped = select_files(repo, repo_dir, min_score)
        all_candidates.extend(candidates)
        skipped_total += skipped

    # Highest score first; deterministic tie-break by source order then path.
    all_candidates.sort(key=lambda c: (-c.score, repo_index[c.repo], c.rel_path))
    chosen = all_candidates[:max_docs]
    if not chosen:
        raise FetchError(
            "no on-topic documents selected from any source repo — refusing to "
            "install an empty corpus"
        )

    # Stage everything before touching corpus_dir so a mid-run failure cannot
    # leave a half-populated corpus behind.
    with tempfile.TemporaryDirectory(prefix="corpus-stage-") as stage_root_str:
        stage_root = Path(stage_root_str)
        for cand in chosen:
            front_matter = derive_front_matter(cand.repo, cand.repo_dir, cand.rel_path)
            _, body = split_existing_front_matter(
                (cand.repo_dir / cand.rel_path).read_text(encoding="utf-8", errors="replace")
            )
            out_path = stage_root / cand.repo.slug / cand.rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(render_document(front_matter, body), encoding="utf-8")

        corpus_dir.mkdir(parents=True, exist_ok=True)
        for repo in repos:
            staged_repo = stage_root / repo.slug
            if not staged_repo.exists():
                continue
            target = corpus_dir / repo.slug
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(staged_repo), str(target))

    per_repo: dict[str, int] = {}
    for cand in chosen:
        per_repo[cand.repo.slug] = per_repo.get(cand.repo.slug, 0) + 1

    return FetchSummary(
        repos=[f"{r.org}/{r.repo}@{r.ref}" for r in repos],
        matched=len(all_candidates),
        selected=len(chosen),
        skipped=skipped_total,
        per_repo_selected=per_repo,
    )


def _parse_repo_arg(value: str) -> RepoSource:
    """Parse ``org/repo`` or ``org/repo@ref`` into a RepoSource."""
    ref = "main"
    spec = value
    if "@" in spec:
        spec, ref = spec.rsplit("@", 1)
    if spec.count("/") != 1 or not all(spec.split("/")):
        raise argparse.ArgumentTypeError(f"expected org/repo[@ref], got: {value!r}")
    org, repo = spec.split("/")
    return RepoSource(org=org, repo=repo, ref=ref)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the document corpus from public Elastic GitHub repos.",
    )
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Where to keep the shallow clones (default: a temp cache, reused across runs).",
    )
    parser.add_argument("--max-docs", type=int, default=DEFAULT_MAX_DOCS)
    parser.add_argument("--min-docs", type=int, default=DEFAULT_MIN_DOCS)
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument(
        "--repo",
        dest="repos",
        action="append",
        type=_parse_repo_arg,
        metavar="ORG/REPO[@REF]",
        help="Override the source repos (repeatable). Defaults to the CORPUS.md set.",
    )
    args = parser.parse_args(argv)

    repos = tuple(args.repos) if args.repos else SOURCE_REPOS
    try:
        summary = fetch_corpus(
            repos,
            corpus_dir=args.corpus_dir,
            work_dir=args.work_dir,
            max_docs=args.max_docs,
            min_docs=args.min_docs,
            min_score=args.min_score,
        )
    except FetchError as exc:
        print(f"corpus fetch failed: {exc}", file=sys.stderr)
        return 1

    per_repo = ", ".join(f"{slug}={n}" for slug, n in sorted(summary.per_repo_selected.items()))
    print("Corpus fetch summary:")
    print(f"  repos fetched : {', '.join(summary.repos)}")
    print(f"  files matched : {summary.matched}")
    print(f"  files selected: {summary.selected} ({per_repo})")
    print(f"  files skipped : {summary.skipped} (off-topic or too small)")
    print(f"  written to    : {args.corpus_dir}")
    if summary.selected < args.min_docs:
        print(
            f"  warning: selected {summary.selected} docs, below the target minimum "
            f"of {args.min_docs} — consider lowering --min-score.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
