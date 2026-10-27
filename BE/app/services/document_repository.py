"""Read-only repository view for records that have completed approval and filing.

Folder actions (rename, pin) live here too: a rename rewrites the folder prefix
on the stored records' paths, and a pin is a per-user bookmark on a folder.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import Column, DateTime, String, UniqueConstraint, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..database import Base  # adjust if your declarative Base lives elsewhere
from ..models_qms import Format, QualityTeam, Record, STAGE_STORED, STAGE_CANCELLED
from . import format_service

SEP = " / "
ROOT = "Records"
MAX_FOLDER_NAME_LENGTH = 100
_BAD_NAME_CHARS = set('/\\<>:"|?*')


class FolderValidationError(ValueError):
    """The folder path or the new folder name is not acceptable."""


class FolderConflictError(Exception):
    """A sibling folder with the requested name already exists."""


class RepositoryFolderPin(Base):
    """A folder pinned by one user. Needs a migration to create the table."""

    __tablename__ = "repository_folder_pins"
    __table_args__ = (
        UniqueConstraint("user_id", "folder_path", name="uq_repository_folder_pin"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    # Stored without the "Records" root, e.g. "Teams / Quality Control".
    folder_path = Column(String(1000), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


@dataclass(frozen=True)
class RepositoryFilters:
    """Validated search, folder, date, and pagination criteria for a listing."""

    search: Optional[str] = None
    folder_path: Optional[str] = None
    team_id: Optional[str] = None
    format_id: Optional[str] = None
    filed_date: Optional[date] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    page: int = 1
    page_size: int = 25


@dataclass
class _FolderNode:
    """One folder in the navigation tree with direct and descendant counts."""

    name: str
    path: str
    records_count: int = 0
    total_records: int = 0
    children: dict[str, _FolderNode] = field(default_factory=dict)


class RepositoryFolderTree:
    """Build navigation folders from the stored-record paths."""

    def __init__(self, db: Session, user_id: Optional[str] = None):
        self._db = db
        self._user_id = user_id

    def build(self) -> list[dict]:
        """Build the sidebar tree from all stored records, regardless of filters."""
        rows = (
            self._db.query(Record.storage_path, func.count(Record.id))
            .filter(Record.stage == STAGE_STORED)
            .group_by(Record.storage_path)
            .all()
        )
        root = _FolderNode(name="Records", path="Records")

        for storage_path, count in rows:
            segments = [
                part.strip()
                for part in (storage_path or "Unfiled").split("/")
                if part.strip()
            ]
            if segments and segments[0] == "Records":
                segments = segments[1:]

            node = root
            node.total_records += count
            for segment in segments or ["Unfiled"]:
                if segment not in node.children:
                    node.children[segment] = _FolderNode(
                        name=segment,
                        path=f"{node.path} / {segment}",
                    )
                node = node.children[segment]
                node.total_records += count
            node.records_count += count

        pinned = self._pinned_paths()
        return sorted(
            (self._serialize(child, pinned) for child in root.children.values()),
            key=lambda child: child["name"].casefold(),
        )

    def _pinned_paths(self) -> set[str]:
        """The current user's pinned folders, in canonical form."""
        if not self._user_id:
            return set()
        rows = (
            self._db.query(RepositoryFolderPin.folder_path)
            .filter(RepositoryFolderPin.user_id == self._user_id)
            .all()
        )
        return {path for (path,) in rows}

    def _serialize(self, node: _FolderNode, pinned: set[str]) -> dict:
        """Convert a folder node into the stable JSON shape returned by the API."""
        return {
            "name": node.name,
            "path": node.path,
            "records_count": node.records_count,
            "total_records": node.total_records,
            "is_pinned": SEP.join(folder_segments(node.path)) in pinned,
            "children": sorted(
                (self._serialize(child, pinned) for child in node.children.values()),
                key=lambda child: child["name"].casefold(),
            ),
        }


class RepositoryRecordSerializer:
    """Convert one stored record into the repository's table-row shape."""

    def serialize(self, record: Record) -> dict:
        """Map record, template, team, and filing metadata into one table row."""
        fmt = record.format
        filed_by = record.storer
        filed_by_name = (
            filed_by.full_name or filed_by.username if filed_by else None
        )
        return {
            "id": record.id,
            "record_id": record.id,
            "document_id": record.document_id,
            "document_name": fmt.title if fmt else record.number,
            "form_name": fmt.title if fmt else None,
            "form_code": fmt.code if fmt else None,
            "document_number": record.number,
            "department": record.team.name if record.team else None,
            "type": (
                format_service.FREQUENCY_LABELS.get(fmt.frequency, fmt.frequency)
                if fmt else None
            ),
            "filed_by": (
                {"id": filed_by.id, "name": filed_by_name}
                if filed_by else None
            ),
            "filed_by_name": filed_by_name,
            "filed_date": record.stored_at,
            "folder_path": record.storage_path or "Unfiled",
            "period": record.period_label,
            "view_url": f"/api/records/{record.id}/sheet",
            "document_url": (
                f"/api/documents/{record.document_id}"
                if record.document_id else None
            ),
            "action": "view",
        }


class RepositoryRecordQuery:
    """Apply repository filters and retrieve a stable, paginated record page."""

    def __init__(self, db: Session):
        self._db = db

    def execute(self, filters: RepositoryFilters) -> tuple[list[Record], int]:
        """Apply requested filters and return the requested page plus total count."""
        query = (
            self._db.query(Record)
            .options(
                joinedload(Record.format),
                joinedload(Record.team),
                joinedload(Record.storer),
            )
            .join(Record.format)
            .outerjoin(Record.team)
            .filter(Record.stage.in_([STAGE_STORED, STAGE_CANCELLED]))

        )

        if filters.search and filters.search.strip():
            term = f"%{filters.search.strip()}%"
            query = query.filter(or_(
                Format.title.ilike(term),
                Format.code.ilike(term),
                Record.number.ilike(term),
                QualityTeam.name.ilike(term),
            ))
        if filters.team_id:
            query = query.filter(Record.team_id == filters.team_id)
        if filters.format_id:
            query = query.filter(Record.format_id == filters.format_id)
        if filters.folder_path:
            normalized_path = filters.folder_path.strip().rstrip(" /")
            if (
                normalized_path.casefold() == "unfiled"
                or normalized_path.casefold().endswith(" / unfiled")
            ):
                query = query.filter(or_(
                    Record.storage_path.is_(None),
                    Record.storage_path == "",
                ))
            else:
                # The tree always says "Records / …" while a record's stored
                # path may not (a format filing to its own root). Compare in the
                # one normalised form, as rename and pin already do.
                query = query.filter(
                    _under_folder(Record.storage_path, folder_segments(normalized_path))
                )
        if filters.date_from:
            query = query.filter(
                func.date(Record.stored_at) >= filters.date_from.isoformat()
            )
        if filters.date_to:
            query = query.filter(
                func.date(Record.stored_at) <= filters.date_to.isoformat()
            )
        if filters.filed_date:
            query = query.filter(
                func.date(Record.stored_at) == filters.filed_date.isoformat()
            )

        total = query.count()
        records = (
            query.order_by(Record.stored_at.desc(), Record.id.asc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
            .all()
        )
        return records, total


# ---------------------------------------------------------------------------
# Folder actions: rename and pin
# ---------------------------------------------------------------------------
def folder_segments(path: Optional[str]) -> list[str]:
    """Split a folder path into clean segments, without the leading 'Records'.

    Stored paths may or may not start with 'Records' while the tree API always
    does, so every path is compared in this one normalised form.
    """
    segments = [part.strip() for part in (path or "").split("/") if part.strip()]
    if segments and segments[0].casefold() == ROOT.casefold():
        segments = segments[1:]
    return segments


def _under_folder(column, segments: list[str]):
    """SQL condition: the column is this folder or anything below it.

    Same substr-with-trailing-separator technique as the folder filter, so
    renaming 'Production' never touches 'Production Support'. Both stored
    styles ('Teams / X' and 'Records / Teams / X') are matched.
    """
    joined = SEP.join(segments)
    conditions = []
    for prefix in (joined, f"{ROOT}{SEP}{joined}"):
        conditions.append(column == prefix)
        conditions.append(
            func.substr(column, 1, len(prefix) + len(SEP)) == f"{prefix}{SEP}"
        )
    return or_(*conditions)


def _swap_prefix(path_value: str, old: list[str], new: list[str]) -> str:
    """Replace the ``old`` folder prefix with ``new``, keeping the stored style."""
    raw = [part.strip() for part in path_value.split("/") if part.strip()]
    has_root = bool(raw) and raw[0].casefold() == ROOT.casefold()
    body = raw[1:] if has_root else raw
    if body[: len(old)] != old:
        return path_value
    return SEP.join(([ROOT] if has_root else []) + new + body[len(old):])


class RepositoryFolderActions:
    """Rename a folder or pin it for one user."""

    def __init__(self, db: Session):
        self._db = db

    # -- rename ------------------------------------------------------------
    def rename(self, folder_path: str, new_name: str) -> dict:
        """Rename the last segment of a folder and every record path beneath it."""
        old = self._target(folder_path)
        name = self._clean_name(new_name)
        new = old[:-1] + [name]

        updated = 0
        if name != old[-1]:
            self._check_sibling_clash(old, name)
            updated = self._apply_rename(old, new)

        return {
            "old_path": SEP.join([ROOT, *old]),
            "new_path": SEP.join([ROOT, *new]),
            "new_name": name,
            "records_updated": updated,
        }

    def _apply_rename(self, old: list[str], new: list[str]) -> int:
        try:
            records = (
                self._db.query(Record)
                .filter(_under_folder(Record.storage_path, old))
                .all()
            )
            for record in records:
                record.storage_path = _swap_prefix(record.storage_path, old, new)

            # Pins follow the folder; drop one if the user already pinned the target.
            taken = {
                (pin.user_id, pin.folder_path)
                for pin in self._db.query(RepositoryFolderPin)
                .filter(_under_folder(RepositoryFolderPin.folder_path, new))
                .all()
            }
            for pin in (
                self._db.query(RepositoryFolderPin)
                .filter(_under_folder(RepositoryFolderPin.folder_path, old))
                .all()
            ):
                moved = _swap_prefix(pin.folder_path, old, new)
                if (pin.user_id, moved) in taken:
                    self._db.delete(pin)
                else:
                    pin.folder_path = moved

            self._db.commit()
            return len(records)
        except Exception:
            self._db.rollback()
            raise

    def _check_sibling_clash(self, old: list[str], name: str) -> None:
        depth, wanted, current = len(old), name.casefold(), old[-1].casefold()
        paths = (
            self._db.query(Record.storage_path)
            .filter(Record.storage_path.isnot(None))
            .distinct()
            .all()
        )
        for (path,) in paths:
            segments = folder_segments(path)
            if len(segments) >= depth and segments[: depth - 1] == old[: depth - 1]:
                sibling = segments[depth - 1].casefold()
                if sibling == wanted and sibling != current:
                    raise FolderConflictError(
                        f"A folder named '{name}' already exists in this location."
                    )

    # -- pin ---------------------------------------------------------------
    def set_pinned(self, user_id: str, folder_path: str, pinned: bool) -> dict:
        """Pin or unpin a folder for this user. Repeating a call changes nothing."""
        segments = self._target(folder_path)
        key = SEP.join(segments)
        existing = (
            self._db.query(RepositoryFolderPin)
            .filter_by(user_id=user_id, folder_path=key)
            .one_or_none()
        )
        try:
            if pinned and existing is None:
                self._db.add(RepositoryFolderPin(user_id=user_id, folder_path=key))
                self._db.commit()
            elif not pinned and existing is not None:
                self._db.delete(existing)
                self._db.commit()
        except IntegrityError:
            self._db.rollback()
            # A concurrent request pinning the same folder is fine. Anything else
            # is a real failure and must not be reported as a successful pin.
            saved = (
                self._db.query(RepositoryFolderPin)
                .filter_by(user_id=user_id, folder_path=key)
                .one_or_none()
                is not None
            )
            if pinned and not saved:
                raise
        return {"folder_path": SEP.join([ROOT, *segments]), "is_pinned": pinned}

    # -- validation --------------------------------------------------------
    @staticmethod
    def _target(folder_path: str) -> list[str]:
        segments = folder_segments(folder_path)
        if not segments:
            raise FolderValidationError("A folder path is required.")
        if segments[-1].casefold() == "unfiled":
            raise FolderValidationError("The 'Unfiled' folder cannot be changed.")
        return segments

    @staticmethod
    def _clean_name(new_name: str) -> str:
        name = " ".join((new_name or "").split())
        if not name:
            raise FolderValidationError("Folder name cannot be empty.")
        if len(name) > MAX_FOLDER_NAME_LENGTH:
            raise FolderValidationError(
                f"Folder name must be {MAX_FOLDER_NAME_LENGTH} characters or fewer."
            )
        if name in {".", ".."} or any(ch in _BAD_NAME_CHARS for ch in name):
            raise FolderValidationError(
                'Folder name cannot contain / \\ < > : " | ? *'
            )
        if name.casefold() in {"unfiled", ROOT.casefold()}:
            raise FolderValidationError(f"'{name}' is a reserved folder name.")
        return name


class DocumentRepositoryService:
    """Coordinate the repository query, folder tree, and row serialization."""

    def __init__(self, db: Session, user_id: Optional[str] = None):
        self._query = RepositoryRecordQuery(db)
        self._folders = RepositoryFolderTree(db, user_id)
        self._folder_actions = RepositoryFolderActions(db)
        self._serializer = RepositoryRecordSerializer()

    def list_documents(self, filters: RepositoryFilters) -> dict:
        """Assemble folders, document rows, pagination metadata, and active filters."""
        records, total = self._query.execute(filters)
        return {
            "folders": self._folders.build(),
            "documents": [self._serializer.serialize(record) for record in records],
            "pagination": {
                "page": filters.page,
                "page_size": filters.page_size,
                "total": total,
                "total_pages": (
                    total + filters.page_size - 1
                ) // filters.page_size,
            },
            "filters": {
                "search": filters.search,
                "folder_path": filters.folder_path,
                "team_id": filters.team_id,
                "format_id": filters.format_id,
                "filed_date": filters.filed_date,
                "date_from": filters.date_from,
                "date_to": filters.date_to,
            },
        }

    def rename_folder(self, folder_path: str, new_name: str) -> dict:
        """Rename a folder and every filed record beneath it."""
        return self._folder_actions.rename(folder_path, new_name)

    def set_folder_pinned(self, user_id: str, folder_path: str, pinned: bool) -> dict:
        """Pin or unpin a folder for one user."""
        return self._folder_actions.set_pinned(user_id, folder_path, pinned)