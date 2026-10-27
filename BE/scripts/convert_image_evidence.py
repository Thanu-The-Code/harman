#!/usr/bin/env python
"""
Turn record evidence stored as a picture into a PDF of that picture.

Signatures are stamped onto a record's document when it is viewed or downloaded,
and only a PDF can carry them. Pictures attached as the scanned hard copy are
converted on upload now (evidence_service.ingest); this converts the ones
attached before that. Each document keeps its id and the hash of the file as it
was scanned (how the same sheet is recognised again).

    python scripts/convert_image_evidence.py            # convert
    python scripts/convert_image_evidence.py --dry-run  # only list them

Safe to run again: a document that is already a PDF is left alone.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Document  # noqa: E402
from app.services.evidence_service import IMAGE_SCANS, _as_pdf  # noqa: E402
from app.services.file_utils import get_file_info  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list the documents, change nothing")
    args = parser.parse_args()

    db = SessionLocal()
    converted = failed = 0
    try:
        for document in db.query(Document).all():
            path = Path(document.file_path or "")
            if not path.is_absolute():
                path = ROOT / path
            if path.suffix.lower() not in IMAGE_SCANS:
                continue
            if not path.exists():
                print(f"  ! {document.id}: {path} is missing")
                failed += 1
                continue
            print(f"  {'would convert' if args.dry_run else 'converting'} {document.original_filename} ({document.id})")
            if args.dry_run:
                continue
            try:
                pdf = _as_pdf(path)
            except Exception as exc:  # an unreadable picture stays as it is
                print(f"  ! could not convert {path.name}: {exc}")
                failed += 1
                continue
            document.file_path = str(pdf.relative_to(ROOT)) if pdf.is_relative_to(ROOT) else str(pdf)
            document.filename = pdf.name
            document.mime_type = "application/pdf"
            document.file_size = get_file_info(pdf)["size"]
            db.commit()
            path.unlink(missing_ok=True)
            converted += 1
    finally:
        db.close()
    print(f"{converted} converted, {failed} could not be converted")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
