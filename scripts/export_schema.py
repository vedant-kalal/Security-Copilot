#!/usr/bin/env python3
"""
Export the current SQLAlchemy model metadata as plain PostgreSQL DDL to
`database/schema.sql`. This keeps `database/schema.sql` (a convenience
reference for engineers who prefer reading raw SQL over Alembic
migrations) in sync with the real source of truth: the ORM models under
`backend/app/models/` + the Alembic migration in
`backend/migrations/versions/`.

Usage:
    python scripts/export_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app.core.database import Base  # noqa: E402
import app.models  # noqa: E402,F401

OUTPUT_PATH = REPO_ROOT / "database" / "schema.sql"

HEADER = """-- ============================================================================
-- SentinelAI database schema (PostgreSQL + pgvector)
--
-- This file is auto-generated from the SQLAlchemy models in
-- backend/app/models/ via `python scripts/export_schema.py`.
-- The authoritative, versioned source of truth is the Alembic migration
-- at backend/migrations/versions/0001_initial_schema.py — run
-- `alembic upgrade head` to actually provision a database. This file is
-- provided as a convenience reference and for manual `psql` setup.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

"""


def main() -> None:
    dialect = postgresql.dialect()
    lines = [HEADER]

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        lines.append(f"-- Table: {table.name}\n{ddl};\n")
        for index in table.indexes:
            index_ddl = str(CreateIndex(index).compile(dialect=dialect)).strip()
            lines.append(f"{index_ddl};")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
