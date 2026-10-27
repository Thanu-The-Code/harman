#!/usr/bin/env python
"""
Put the system back to a clean, known state for a demonstration.

Running the demo leaves marks. Records get called, sheets get attached, formats
get created, and the acceptance check leaves a couple of dozen throwaway formats
of its own. None of it is harmful, but a Formats screen with thirty entries and a
register full of half-filled records is not what you want on a shared screen.

The one that actually stops a demo is the hard copy. A scanned sheet may only
ever be the evidence for one record - the system refuses a sheet it has already
filed, so nobody can quietly reuse one. Once you have attached
`harman-inspection-sheet-nok.pdf`, that file is spent, and the next attempt is
refused. This clears the filed evidence *and* stamps fresh sheets, so the sheets
in the project root are attachable again.

    python scripts/reset_demo.py

What it removes:

    data/documents.db      the database - every record, format and account
    data/storage/**        the filed evidence PDFs
    data/staging/**        anything waiting to be picked up
    data/scans/**          scratch scans

Then it rebuilds: the database, the three quality teams and their formats, the
seven people, the four worked examples, and a fresh pair of inspection sheets.

Stop the server first - it holds the database open.

    --yes     do not ask for confirmation (for scripting)
    --keep-sheets   leave the sample PDFs alone
"""
from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATABASE = ROOT / "data" / "documents.db"
# SQLite leaves these beside the database in write-ahead mode. Deleting the
# database without them resurrects the last transactions into an empty schema.
DATABASE_SIDECARS = ("-wal", "-shm", "-journal")

DIRECTORIES = (
    ROOT / "data" / "storage",
    ROOT / "data" / "staging",
    ROOT / "data" / "scans",
)


def server_is_running(port: int = 8000) -> bool:
    """Whether something is answering on the port the server uses."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.6)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def count_files(folder: Path) -> int:
    return sum(1 for item in folder.rglob("*") if item.is_file())


def run(*command: str) -> None:
    """Run one of the project's own scripts with the interpreter running this."""
    result = subprocess.run([sys.executable, *command], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"\n  {' '.join(command)} failed. Nothing else was run.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true",
                        help="do not ask for confirmation")
    parser.add_argument("--keep-sheets", action="store_true",
                        help="do not regenerate the sample inspection sheets")
    args = parser.parse_args()

    if server_is_running():
        sys.exit(
            "The server is still running, and it holds the database open.\n"
            "  Stop it first - Ctrl+C in the window running `python cli.py serve` -\n"
            "  then run this again.")

    filed = sum(count_files(d) for d in DIRECTORIES if d.exists())
    print("This will delete:")
    print(f"  the database          {'yes' if DATABASE.exists() else 'already gone'}")
    print(f"  filed and staged files {filed}")
    if not args.keep_sheets:
        print("  and stamp a fresh pair of sample inspection sheets")

    if not args.yes:
        print()
        answer = input("Everything above is rebuilt from the seed. Continue? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            return print("Nothing was changed.") or 0

    print("\nClearing")
    for suffix in ("", *DATABASE_SIDECARS):
        target = DATABASE.with_name(DATABASE.name + suffix)
        if target.exists():
            target.unlink()
            print(f"  removed {target.relative_to(ROOT)}")

    for folder in DIRECTORIES:
        if not folder.exists():
            continue
        removed = count_files(folder)
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        print(f"  emptied {folder.relative_to(ROOT)} ({removed} file(s))")

    print("\nRebuilding")
    run("cli.py", "init")
    run("scripts/seed_quality_records.py")
    if not args.keep_sheets:
        # --fresh stamps a new batch number. The readings are unchanged, so the
        # demo script still matches, but the sheets are new evidence and can be
        # attached again.
        run("scripts/make_sample_sheet.py", "--fresh")

    print("\n" + "=" * 70)
    print("  Ready. Start the server and sign in as admin / Harman@2026:")
    print()
    print("      python cli.py serve          then http://127.0.0.1:8000")
    print()
    print("  Attach harman-inspection-sheet-nok.pdf - it is unused again.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
