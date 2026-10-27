"""
Additive schema migrations for databases that already hold documents.

`Base.metadata.create_all` happily creates new *tables*, but it will never add
a *column* to a table that already exists. A deployment that has been running
since before the Studio shipped would therefore start and then fail on the
first query touching `documents.origin`.

Everything here is additive and idempotent: add a column if it is missing, do
nothing otherwise. No column is ever dropped or retyped, so running an older
build against a migrated database still works.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> {column: SQL type and default}
ADDITIONS: dict[str, dict[str, str]] = {
    "documents": {
        "layout_json": "TEXT",
        "structured_html": "TEXT",
        "ocr_engine": "VARCHAR",
        "ocr_confidence": "FLOAT",
        "origin": "VARCHAR DEFAULT 'uploaded'",
        "template_id": "VARCHAR",
        "source_html": "TEXT",
        "version": "VARCHAR DEFAULT '1.0'",
        "revision_of": "VARCHAR",
        "created_by": "VARCHAR",
        "folder_id": "VARCHAR",
        "deleted_at": "DATETIME",
        "deleted_by": "VARCHAR",
        "deleted_from_folder_id": "VARCHAR",
    },
    "signatures": {
        "designation": "VARCHAR",
        # Placement as a fraction of the page. NULL means "let the automatic
        # layout decide", which is what every existing signature wants.
        "page_number": "INTEGER",
        "x_pct": "FLOAT",
        "y_pct": "FLOAT",
        "width_pct": "FLOAT",
        "placed_by": "VARCHAR",
        "placed_at": "DATETIME",
    },
    "users": {
        "department": "VARCHAR",
        "department_id": "VARCHAR REFERENCES departments(id)",
        "job_title": "VARCHAR",
        # Which quality team this person belongs to. Nullable: an
        # administrator, or somebody who only ever appears on a CFT, belongs to
        # no single team and must not be forced into one.
        "quality_team_id": "VARCHAR",
        "account_type": "VARCHAR DEFAULT 'employee'",
        # Existing users keep the ability to approve and, deliberately, do NOT
        # gain the ability to sign. Signature authority is granted, never
        # inherited by a migration.
        "can_approve": "BOOLEAN DEFAULT 1",
        "can_sign": "BOOLEAN DEFAULT 0",
    },
    "approval_steps": {
        # A step now says whether one of its named people decides for it or
        # whether all of them must. Existing steps - including approvals part
        # way through - default to "any", which is how they behaved when the
        # people on them were asked to approve. A migration must never change
        # what somebody already agreed to.
        "approval_mode": "VARCHAR DEFAULT 'any'",
        # QMS: which box of the client's process flow this step implements, so
        # the engine can recognise the CFT joint review (B6) and the final
        # decision (B7) without matching on a step's display name.
        "qms_stage": "VARCHAR",
    },
    # QMS. These tables are created complete by create_all on a new database;
    # the entries below only matter to an installation that predates a column
    # being added to an already-shipped QMS table.
    "records": {
        "approval_overrides": "TEXT",
        "reverify_count": "INTEGER DEFAULT 0",
        "cft_objection": "TEXT",
        "nok_summary": "TEXT",
        "nok_flagged_at": "DATETIME",
        "nok_flagged_to": "VARCHAR",
        "nok_cleared_at": "DATETIME",
        "cft_target_date": "DATETIME",
        "storage_folder_id": "VARCHAR",
        "storage_path": "VARCHAR",
        "stored_at": "DATETIME",
        "stored_by": "VARCHAR",
    },
    "formats": {
        "cft_target_days": "INTEGER DEFAULT 3",
        # An ordered approval route, as JSON. NULL means "use the four steps
        # the process document specifies", which is what every template
        # created before this existed wants.
        "approval_route": "TEXT",
        # The form's shape - header, tables, checklists, signatures - as JSON.
        # NULL means the template is drawn as a plain list of its fields, which
        # is how every template created before the designer existed behaves.
        "layout": "TEXT",
        "work_instruction_ref": "VARCHAR",
        "work_instruction": "TEXT",
        "storage_path": "VARCHAR",
        "blank_file_path": "VARCHAR",
        "blank_mime_type": "VARCHAR",
        "blank_file_size": "INTEGER",
    },
    "notifications": {
        "read_at": "DATETIME",
    },
    # Where a field sits on a designed form: the builder's field_name, or
    # field_name:row:column for a table cell. NULL on fields from before the
    # designer, which are matched by id or label as they always were.
    "format_fields": {
        "layout_key": "VARCHAR",
    },
    "record_field_values": {
        "layout_key": "VARCHAR",
    },
}


def apply_migrations(engine: Engine) -> list[str]:
    """Add any missing columns and remove stale unique constraints that block My Folder uploads."""
    applied: list[str] = []
    inspector = inspect(engine)

    try:
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        logger.warning(f"Could not inspect the database, skipping migrations: {exc}")
        return applied

    for table, columns in ADDITIONS.items():
        if table not in existing_tables:
            continue  # create_all will build it complete

        have = {c["name"] for c in inspector.get_columns(table)}

        for column, ddl in columns.items():
            if column in have:
                continue
            statement = f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                applied.append(f"{table}.{column}")
                logger.info(f"Schema migration: added {table}.{column}")
            except Exception as exc:
                # A parallel worker may have won the race. Anything else is
                # worth seeing in the log but is not worth refusing to start.
                logger.warning(f"Schema migration skipped for {table}.{column}: {exc}")

    if "documents" in existing_tables:
        try:
            indexes = inspector.get_indexes("documents")
            for index in indexes:
                columns = index.get("column_names") or []
                name = index.get("name")
                if columns == ["file_hash"] and index.get("unique"):
                    with engine.begin() as conn:
                        conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
                    applied.append(f"documents.file_hash_unique_index_removed")
                    logger.info(f"Schema migration: dropped unique index {name} on documents.file_hash")
        except Exception as exc:
            logger.warning(f"Could not reconcile file_hash index on documents: {exc}")

    return applied
