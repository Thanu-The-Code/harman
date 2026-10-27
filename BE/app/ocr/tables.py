"""Table element helpers shared by every extractor.

A Table element's rows hold cells that are either legacy strings ("" = input, "x" = fixed text)
or dicts ({"text"}, {"input"}, {"covered": True}, with optional rowspan/colspan).
Values are always a 2-D list [row][leaf column] of strings ("" for fixed/covered cells).
"""
import re

from rapidfuzz import fuzz

from . import values as v

TICKS = {"✓", "✔", "☑", "v", "V", "√", "/"}
CROSSES = {"✗", "✘", "x", "X", "×", "☒"}
EMPTY_MARKS = {"☐", "□", "▢", "○", "◯"}  # an unticked box typed into the cell


def normalize_cell(cell):
    if isinstance(cell, dict):
        return cell
    return {"text": cell} if cell else {"input": "text"}


def is_input(cell):
    cell = normalize_cell(cell)
    return not cell.get("covered") and ("input" in cell or not (cell.get("text") or "").strip())


def body(element):
    n = len(element.get("columns") or [])
    out = []
    for row in element.get("rows") or []:
        cells = [normalize_cell(c) for c in (row.get("cells") or [])][:n]
        out.append(cells + [{"input": "text"}] * (n - len(cells)))
    return out


_LEGEND_RE = re.compile(r"^\s*(\S)\s+(OK|NOT\s*OK|N-?OK)\s*$", re.I)


def normalize_legend(text):
    """A check sheet's key, "√ OK" / "× NOT OK", with the marks the form is filled with.

    OCR reads a printed tick as "V" or "√"; the key then says "V OK", which nobody filling
    the form would recognise as the ✓ they are asked for.
    """
    m = _LEGEND_RE.match(text or "")
    if not m:
        return text
    mark = "✓" if m.group(1) in TICKS else "✗" if m.group(1) in CROSSES else None
    return f"{mark} {m.group(2).upper()}" if mark else text


def normalize_mark(text):
    """A cell that only holds a tick or a cross reads as ✓ / ✗."""
    t = (text or "").strip()
    if t in TICKS:
        return "✓"
    if t in CROSSES:
        return "✗"
    if t in EMPTY_MARKS:
        return ""
    return t


def match_table(grid, element, min_score=70):
    """Find the element's table inside a CellGrid by its column headings.

    Returns (last_header_row, [grid column per leaf column or None]) or None.
    """
    cols = [v.norm(c.get("text", "")) for c in element.get("columns") or []]
    wanted = [c for c in cols if c]
    if not wanted:
        return None
    best = None
    for r in range(grid.n_rows):
        anchors = {}
        for gc in range(grid.n_cols):
            a = grid.at(r, gc)
            if a is not None and a.col == gc and a.text.strip():
                anchors[gc] = (a, v.norm(a.text))
        mapping, score, last = [], 0, -1
        for ct in cols:
            choice = None
            if ct:
                cands = [(fuzz.ratio(ct, t), gc) for gc, (a, t) in anchors.items() if gc > last]
                if cands:
                    s, gc = max(cands)
                    if s >= min_score:
                        choice, score = gc, score + s
            mapping.append(choice)
            if choice is not None:
                last = choice
        matched = sum(1 for m in mapping if m is not None)
        if matched < max(2, len(wanted) // 2):
            continue
        if best is None or (matched, score) > best[0]:
            best = ((matched, score), r, mapping)
    if best is None:
        return None
    _, r, mapping = best
    # Columns without a heading sit right after the previous mapped column; the first body row
    # shows the real cell boundaries (a blank heading can span several columns).
    for i, gc in enumerate(mapping):
        if gc is None and i > 0 and mapping[i - 1] is not None:
            for row in (r + 1, r):
                prev = grid.at(row, mapping[i - 1])
                nxt = grid.at(row, prev.end_col) if prev is not None else None
                if nxt is not None:
                    mapping[i] = nxt.col
                    break
    return r, mapping


def body_rows(grid, r_head, mapping, count):
    """Grid row indexes holding the table's body rows: after the last heading row, skipping
    blank spacer strips that span the whole table (the template leaves those out)."""
    cols = [gc for gc in mapping if gc is not None]
    rows, r = [], r_head + 1
    while len(rows) < count and r < grid.n_rows:
        owners = {id(grid.at(r, gc)) for gc in cols if grid.at(r, gc) is not None}
        cell = grid.at(r, cols[0]) if cols else None
        spacer = len(owners) == 1 and cell is not None and cell.is_blank and len(cols) > 2
        if not spacer:
            rows.append(r)
        r += 1
    return rows

