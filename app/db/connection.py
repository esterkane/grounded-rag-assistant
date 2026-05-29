"""PostgreSQL connection helpers.

Importable and free of FastAPI coupling, consistent with the retrieval/generation
layering. Repository functions take an open connection so they are easy to test
and compose; this module is the single place that knows how to open one from
:class:`~app.config.Settings`.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from app.config import Settings, get_settings


def connect(settings: Settings | None = None) -> psycopg.Connection:
    """Open a new PostgreSQL connection with dict rows.

    Caller owns the connection (use it as a context manager). Rows are returned
    as dicts so repository code can map them to Pydantic models by name.
    """
    settings = settings or get_settings()
    return psycopg.connect(settings.postgres_dsn, row_factory=dict_row)
