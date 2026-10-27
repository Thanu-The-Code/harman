"""Folder paths shared by template creation and the Template Repo."""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models_qms import Format, FormatFolder


def normalize_path(path: str | None) -> str | None:
    """Normalize a user-supplied folder path and reject unsafe path segments."""
    if path is None or not path.strip():
        return None

    parts = [part.strip() for part in re.split(r"[\\/]+", path) if part.strip()]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("Folder paths cannot contain '.' or '..' segments.")
    if any(len(part) > 100 or any(ord(char) < 32 for char in part) for part in parts):
        raise ValueError("Folder names must be 100 characters or fewer.")

    normalized = " / ".join(parts)
    if len(normalized) > 500:
        raise ValueError("Folder paths must be 500 characters or fewer.")
    return normalized


def _find_folder(db: Session, path: str) -> FormatFolder | None:
    return (
        db.query(FormatFolder)
        .filter(func.lower(FormatFolder.path) == path.lower())
        .first()
    )


def ensure_folder_path(
    db: Session,
    path: str | None,
    *,
    created_by: str | None = None,
) -> str | None:
    """Persist each path segment and return the canonical folder path."""
    normalized = normalize_path(path)
    if normalized is None:
        return None

    parent_path = None
    current_parts = []
    for name in normalized.split(" / "):
        current_parts.append(name)
        current_path = " / ".join(current_parts)
        folder = _find_folder(db, current_path)
        if folder is None:
            folder = FormatFolder(
                name=name,
                path=current_path,
                parent_path=parent_path,
                created_by=created_by,
            )
            db.add(folder)
            db.flush()
        current_parts[-1] = folder.name
        parent_path = folder.path

    return parent_path


def create_folder(
    db: Session,
    name: str,
    parent_path: str | None,
    *,
    created_by: str | None = None,
) -> FormatFolder:
    """Create a template folder, idempotently returning an existing sibling."""
    clean_name = (name or "").strip()
    if (
        not clean_name
        or len(clean_name) > 100
        or clean_name in {".", ".."}
        or "/" in clean_name
        or "\\" in clean_name
        or any(ord(char) < 32 for char in clean_name)
    ):
        raise ValueError("Enter a valid folder name (1-100 characters).")

    canonical_parent = ensure_folder_path(
        db, parent_path, created_by=created_by
    )
    path = f"{canonical_parent} / {clean_name}" if canonical_parent else clean_name
    existing = _find_folder(db, path)
    if existing:
        return existing

    folder = FormatFolder(
        name=clean_name,
        path=path,
        parent_path=canonical_parent,
        created_by=created_by,
    )
    db.add(folder)
    db.flush()
    return folder


def list_folder_tree(db: Session) -> list[dict]:
    """Return persisted folders plus folder paths on existing templates."""
    folders = db.query(FormatFolder).order_by(FormatFolder.path).all()
    by_path: dict[str, dict] = {}

    def add_path(path: str, folder: FormatFolder | None = None) -> None:
        parts = [part.strip() for part in path.split(" / ") if part.strip()]
        parent_path = None
        accumulated = []
        for name in parts:
            accumulated.append(name)
            current_path = " / ".join(accumulated)
            key = current_path.casefold()
            node = by_path.get(key)
            if node is None:
                node = {
                    "id": None,
                    "name": name,
                    "path": current_path,
                    "parent_path": parent_path,
                    "children": [],
                }
                by_path[key] = node
            if folder and current_path.casefold() == folder.path.casefold():
                node["id"] = folder.id
                node["name"] = folder.name
                node["path"] = folder.path
                node["parent_path"] = folder.parent_path
            parent_path = node["path"]

    for folder in folders:
        add_path(folder.path, folder)
    for (path,) in db.query(Format.storage_path).filter(
        Format.storage_path.isnot(None)
    ).all():
        normalized = normalize_path(path)
        if normalized:
            add_path(normalized)

    roots = []
    for node in by_path.values():
        parent_path = node["parent_path"]
        if parent_path is None:
            roots.append(node)
        else:
            parent = by_path.get(parent_path.casefold())
            if parent is not None:
                parent["children"].append(node)

    def sort_nodes(nodes: list[dict]) -> None:
        nodes.sort(key=lambda node: node["name"].casefold())
        for node in nodes:
            sort_nodes(node["children"])

    sort_nodes(roots)
    return roots
