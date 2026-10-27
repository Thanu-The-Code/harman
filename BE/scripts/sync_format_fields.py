#!/usr/bin/env python
"""
Bring each template's fields in line with how its form is read now.

Two rules of form_layout.to_fields changed, and templates saved before keep
what they were given:

  * order: fields in a row's columns (the Dept. and Date at the top of a form)
    were listed after every other field; they are read in place now;
  * required: a table cell with limits was required, so a monthly sheet
    reported every day still to come as missing; a cell is required only when
    marked so now.

Each field keeps its id, label and limits; only its order and whether it is
required are updated. Records already made are left as they were filed.

    python scripts/sync_format_fields.py            # update
    python scripts/sync_format_fields.py --dry-run  # only list the templates

Safe to run again: a template already in line is left alone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Format  # noqa: E402
from app.services import form_layout as layouts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list the templates, change nothing")
    args = parser.parse_args()

    db = SessionLocal()
    changed = 0
    try:
        for fmt in db.query(Format).all():
            blocks = layouts.parse(fmt.layout) if fmt.layout else []
            if not blocks or not fmt.fields:
                continue
            derived = [f for f in layouts.to_fields(blocks) if f.get("layout_key")]
            wanted = {f["layout_key"]: n for n, f in enumerate(derived)}
            required = {f["layout_key"]: bool(f.get("required")) for f in derived}
            current = sorted(fmt.fields, key=lambda f: f.order_index or 0)
            # fields the layout does not place keep their relative order, after the placed ones
            ordered = sorted(current, key=lambda f: (wanted.get(f.layout_key, len(wanted)), current.index(f)))
            to_relax = [f for f in current if f.layout_key in required and bool(f.required) != required[f.layout_key]]
            if ordered == current and not to_relax:
                continue
            print(f"  {'would update' if args.dry_run else 'updating'} {fmt.code} {fmt.title}: "
                  f"{'re-ordered, ' if ordered != current else ''}{len(to_relax)} required flag(s) changed")
            changed += 1
            if not args.dry_run:
                for index, field in enumerate(ordered):
                    field.order_index = index
                for field in to_relax:
                    field.required = required[field.layout_key]
                db.commit()
    finally:
        db.close()
    print(f"{changed} template(s) {'to update' if args.dry_run else 'updated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
