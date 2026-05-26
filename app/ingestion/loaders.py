from pathlib import Path

from pypdf import PdfReader

from app.ingestion.models import SourceDocument


def load_documents(path: Path) -> tuple[list[SourceDocument], list[str]]:
    paths = [path] if path.is_file() else sorted(path.rglob("*"))
    documents: list[SourceDocument] = []
    failures: list[str] = []

    for source_path in paths:
        if not source_path.is_file() or source_path.suffix.lower() not in {".md", ".pdf"}:
            continue
        try:
            documents.append(load_document(source_path))
        except Exception as exc:
            failures.append(f"{source_path}: {exc}")

    return documents, failures


def load_document(path: Path) -> SourceDocument:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return load_markdown(path)
    if suffix == ".pdf":
        return load_pdf(path)
    raise ValueError(f"unsupported document type: {path.suffix}")


def load_markdown(path: Path) -> SourceDocument:
    text = path.read_text(encoding="utf-8")
    metadata, content = parse_front_matter(text)
    return SourceDocument(
        source_path=path.as_posix(),
        content=content.strip(),
        title=require_metadata(metadata, "title", path),
        source_url=require_metadata(metadata, "source_url", path),
        version=require_metadata(metadata, "version", path),
        last_updated=require_metadata(metadata, "last_updated", path),
        permissions=parse_permissions(metadata.get("permissions")),
    )


def load_pdf(path: Path) -> SourceDocument:
    reader = PdfReader(str(path))
    content = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not content:
        raise ValueError("no extractable PDF text")
    return SourceDocument(
        source_path=path.as_posix(),
        content=content,
        title=path.stem.replace("-", " ").title(),
        source_url=path.as_uri(),
        version="unknown",
        last_updated="unknown",
    )


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("front matter is missing closing ---")

    raw_metadata = text[4:end].strip()
    content = text[end + 4 :].lstrip()
    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid front matter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, content


def require_metadata(metadata: dict[str, str], key: str, path: Path) -> str:
    value = metadata.get(key)
    if not value:
        raise ValueError(f"{path} missing required front matter key: {key}")
    return value


def parse_permissions(raw_permissions: str | None) -> list[str]:
    if not raw_permissions:
        return ["public"]
    value = raw_permissions.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    roles = [role.strip().strip('"').strip("'") for role in value.split(",")]
    return [role for role in roles if role] or ["public"]
