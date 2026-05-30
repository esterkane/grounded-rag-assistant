"""Minimal forward-only SQL migration runner.

Applies every ``*.sql`` file in ``app/db/migrations/`` (in lexical order) that has
not been recorded in ``schema_migrations`` yet, each in its own transaction.
Idempotent: re-running applies nothing once everything is recorded.

Run directly: ``python -m app.db.migrate``. Also called best-effort on API
startup so the review UI has its tables.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings
from app.db.connection import connect

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def run_migrations(settings: Settings | None = None) -> list[str]:
    """Apply pending migrations and return the versions newly applied."""
    applied_now: list[str] = []
    with connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_MIGRATIONS)
            cur.execute("SELECT version FROM schema_migrations")
            already = {row["version"] for row in cur.fetchall()}
        conn.commit()

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in already:
                continue
            logger.info("Applying migration %s", version)
            with conn.cursor() as cur:
                cur.execute(path.read_text())
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
            conn.commit()
            applied_now.append(version)

    return applied_now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    applied = run_migrations()
    if applied:
        logger.info("Applied %d migration(s): %s", len(applied), ", ".join(applied))
    else:
        logger.info("No pending migrations.")


if __name__ == "__main__":
    main()
