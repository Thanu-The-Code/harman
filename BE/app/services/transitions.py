"""
One status change, made once.

Reading a request's status and then writing the next one lets two clicks (or two
people) both pass the check: a change request executed twice made two drafts of
the same revision. `claim` makes the move a single conditional UPDATE, so only
one caller ever moves a row out of the status it was in.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session


def claim(db: Session, model, row_id: str, from_statuses: Iterable[str], **values) -> bool:
    """Set `values` on the row if its status is still one of `from_statuses`; True if this call did."""
    moved = (db.query(model)
             .filter(model.id == row_id, model.status.in_(list(from_statuses)))
             .update(values, synchronize_session=False))
    db.commit()
    return moved == 1
