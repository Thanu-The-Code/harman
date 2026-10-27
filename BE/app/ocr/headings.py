"""Repairs to the heading rows of a table read off a scan.

A check sheet often numbers its columns 1..N under one heading: the days of the month
under "DATE" / "Result", shifts, sample numbers. Those are one or two small characters
in narrow cells, which OCR misreads more than any other text ("I" for 1, "5" for 3,
"v", "B", "a", or nothing at all). A run of such cells is recognised by position: when
enough of them already read as the number of their own place in the run, the run was
numbered 1..N, and every cell is set to its number.

A heading of numbers that are not a count (sizes 10, 20, 30, a year) does not match by
position and is left alone; so is a run that is mostly words.
"""
from __future__ import annotations

MIN_RUN = 8          # shorter runs are left as read: too few cells to tell a count from chance
MIN_SHARE = 0.3      # at least this share of the run must already read as its own position
MAX_CELL_TEXT = 3    # a numbered cell holds at most "31"; a longer text is a word, not a number

# characters OCR returns for digits in small print
_DIGIT_LOOKALIKES = str.maketrans({"I": "1", "l": "1", "|": "1", "i": "1", "O": "0", "o": "0",
                                   "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6"})


def _number(text: str) -> int | None:
    t = (text or "").strip().translate(_DIGIT_LOOKALIKES)
    return int(t) if t.isdigit() else None


def _is_short(cell: dict) -> bool:
    return (not cell.get("covered") and int(cell.get("colspan") or 1) == 1
            and len((cell.get("text") or "").strip()) <= MAX_CELL_TEXT)


def number_runs(header: list[list[dict]]) -> list[list[dict]]:
    """Renumber, in place, every run of short heading cells that was numbered 1..N."""
    for row in header:
        start = 0
        while start < len(row):
            if not _is_short(row[start]):
                start += 1
                continue
            end = start
            while end < len(row) and _is_short(row[end]):
                end += 1
            run = row[start:end]
            in_place = sum(1 for i, cell in enumerate(run, 1) if _number(cell.get("text", "")) == i)
            if len(run) >= MIN_RUN and in_place >= MIN_SHARE * len(run):
                for i, cell in enumerate(run, 1):
                    cell["text"] = str(i)
            start = end
    return header


def column_texts(columns: list, header: list[list[dict]]) -> list:
    """Columns named after the heading cells over them, bottom-most last (as the designer
    names them): "Result" over "7" gives text "7", title "Result 7"."""
    owner = _owners(header)
    named = []
    for c, column in enumerate(columns):
        texts: list[str] = []
        for r in range(len(header)):
            o = owner[r][c] if c < len(owner[r]) else None
            text = (header[o[0]][o[1]].get("text") or "").strip() if o else ""
            if text and text not in texts:
                texts.append(text)
        base = column if isinstance(column, dict) else {"text": str(column)}
        named.append({**base, "text": texts[-1] if texts else base.get("text", ""), "title": " ".join(texts)})
    return named


def _owners(grid: list[list[dict]]) -> list[list[tuple[int, int] | None]]:
    own: list[list[tuple[int, int] | None]] = [[None] * len(row) for row in grid]
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell.get("covered"):
                continue
            for i in range(r, min(len(grid), r + int(cell.get("rowspan") or 1))):
                for j in range(c, min(len(grid[i]), c + int(cell.get("colspan") or 1))):
                    own[i][j] = (r, c)
    return own
