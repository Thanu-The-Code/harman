"""
Recovering a table from where the words are on the page.

PaddleOCR's text detector already returns every line with its bounding box.
For a ruled form - which is what a quality record is - that geometry *is* the
table: lines that share a vertical band are a row, and text that shares a
horizontal band down the page is a column. Reading the grid back out of the
boxes costs nothing beyond the recognition we already ran.

The alternative was PaddleOCR's own table pipeline, which detects cells with two
RT-DETR models. It is more accurate on a wildly irregular table, and on a CPU it
took over ten minutes for a single page - unusable for somebody photographing a
sheet at the end of a shift. This gets the same answer on an inspection form in
milliseconds, and the model pipeline stays available for sites that want it and
have a GPU (`ocr.paddle.table_model`).

What it deliberately does not do is guess. A page that is not laid out as a grid
produces no table at all, and the text falls through as ordinary lines - because
a wrong table is worse than none: it silently pairs a reading with the wrong
characteristic.
"""
from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass
class Line:
    """One recognised line of text, and where it sat."""

    text: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: Optional[float] = None

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def height(self) -> float:
        return max(1.0, self.y2 - self.y1)


def line_from_box(text: str, box, confidence: Optional[float] = None) -> Optional[Line]:
    """
    A Line from whatever shape the detector reported.

    PaddleOCR gives four corner points; some paths give a flat x1,y1,x2,y2.
    Both are accepted so the caller does not have to care which model answered.
    """
    text = (text or "").strip()
    if not text or box is None:
        return None
    try:
        points = list(box)
        if points and isinstance(points[0], (list, tuple)):
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
        else:
            values = [float(v) for v in points[:4]]
            xs = [values[0], values[2]]
            ys = [values[1], values[3]]
        return Line(text=text, x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys),
                    confidence=confidence)
    except (TypeError, ValueError, IndexError):
        return None


# ------------------------------------------------------------------- rows


def group_rows(lines: list[Line], tolerance: float = 0.6) -> list[list[Line]]:
    """
    Lines that sit in the same horizontal band, left to right.

    The tolerance is a fraction of the line height rather than a pixel count,
    so the same rule works on a 200 dpi scan and a 600 dpi one.
    """
    if not lines:
        return []

    ordered = sorted(lines, key=lambda l: (l.cy, l.x1))
    rows: list[list[Line]] = [[ordered[0]]]

    for line in ordered[1:]:
        current = rows[-1]
        band = sum(l.height for l in current) / len(current)
        if abs(line.cy - current[-1].cy) <= band * tolerance:
            current.append(line)
        else:
            rows.append([line])

    for row in rows:
        row.sort(key=lambda l: l.x1)
    return rows


# ---------------------------------------------------------------- columns


def column_edges(rows: list[list[Line]], tolerance: float = 0.04) -> list[float]:
    """
    Where the columns start, taken from the left edges that recur down the page.

    A column boundary is a left edge that several rows agree on. One row that
    happens to start a word at x=430 is not a column; five rows that all do is.
    The tolerance is a fraction of the page width, so it scales with resolution.
    """
    multi = [row for row in rows if len(row) > 1]
    if len(multi) < 2:
        return []

    width = max(line.x2 for row in rows for line in row) or 1.0
    gap = width * tolerance

    starts = sorted(line.x1 for row in multi for line in row)
    clusters: list[list[float]] = [[starts[0]]]
    for value in starts[1:]:
        if value - clusters[-1][-1] <= gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])

    # A boundary only counts if at least half the multi-cell rows use it.
    needed = max(2, len(multi) // 2)
    edges = [sum(c) / len(c) for c in clusters if len(c) >= needed]
    return sorted(edges)


def table_columns(rows: list[list[Line]], tolerance: float = 0.04) -> list[float]:
    """
    Where the columns start, given rows already known to be a table.

    `column_edges` has to be forgiving because it looks at a whole page, where
    most rows are not table rows at all. Once the table has been isolated the
    opposite is true, and being forgiving costs accuracy: the rows that share
    the table's shape agree on *every* boundary, so a boundary only some of them
    use is not one.

    The table's shape is the cell count most of its rows have. Rows that fall
    short - a row whose last cell is blank, say - still get placed afterwards,
    they just do not get a vote on where the columns are.
    """
    counts = [len(row) for row in rows if len(row) > 1]
    if not counts:
        return []

    # The table's shape is the one carrying the most cells overall, not simply
    # the most common one. A band holding four job-detail rows and four reading
    # rows is tied on frequency, and the readings are the table; weighting by
    # width settles it, and keeps settling it as more detail rows are added.
    tally = Counter(counts)
    shape = max(tally.items(), key=lambda kv: (kv[1] * kv[0], kv[0]))[0]
    shaped = [row for row in rows if len(row) == shape]
    if len(shaped) < 2:
        return []

    width = max(line.x2 for row in rows for line in row) or 1.0
    gap = width * tolerance

    starts = sorted(line.x1 for row in shaped for line in row)
    clusters: list[list[float]] = [[starts[0]]]
    for value in starts[1:]:
        if value - clusters[-1][-1] <= gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])

    edges = [sum(c) / len(c) for c in clusters if len(c) >= len(shaped)]
    return sorted(edges)


def to_grid(rows: list[list[Line]], edges: list[float]) -> list[list[str]]:
    """
    Place every line in the column whose edge it sits nearest.

    Nearest rather than "the last edge it clears by some slack": columns are
    rarely the same width, and a slack derived from one of them is wrong for the
    others. On a real sheet whose first column was twice as wide as the rest,
    that put a reading in the remarks column and merged two cells into one - the
    kind of error that silently pairs a value with the wrong heading.
    """
    if not edges:
        return []

    grid: list[list[str]] = []
    for row in rows:
        cells = [""] * len(edges)
        for line in row:
            index = min(range(len(edges)), key=lambda at: abs(line.x1 - edges[at]))
            cells[index] = (cells[index] + " " + line.text).strip()
        grid.append(cells)
    return grid


# ------------------------------------------------------------------ tables


def table_band(rows: list[list[Line]], min_rows: int = 3, min_columns: int = 2
               ) -> Optional[tuple[int, int]]:
    """
    Which consecutive rows form the table, as an inclusive ``(first, last)``.

    A table is an unbroken run of rows that each fill more than one column. A
    heading above it and a signature line below it break the run, so they are
    not swept in - which the old "everything between the first and last
    multi-cell row" rule did, letting them vote on the columns.

    Where a page holds several such runs, the best is the longest and widest:
    length times width, so a six-row four-column grid beats a three-row pair of
    columns. Returns ``None`` when no run is big enough to be a table.
    """
    best: Optional[tuple[int, int]] = None
    best_score = 0

    start = 0
    while start < len(rows):
        if len(rows[start]) < min_columns:
            start += 1
            continue

        end = start
        while end + 1 < len(rows) and len(rows[end + 1]) >= min_columns:
            end += 1

        length = end - start + 1
        if length >= min_rows:
            score = length * max(len(row) for row in rows[start:end + 1])
            if score > best_score:
                best_score, best = score, (start, end)
        start = end + 1

    return best


def find_table(lines: list[Line], min_rows: int = 3, min_columns: int = 2
               ) -> tuple[Optional[str], list[Line]]:
    """
    The table on this page, as HTML, and the lines that were not part of it.

    Returns ``(None, lines)`` when the page is not laid out as a grid. That is
    the important case: a wrong table pairs a reading with the wrong
    characteristic, which is worse than having no table at all.
    """
    rows = group_rows(lines)
    band = table_band(rows, min_rows, min_columns)
    if band is None:
        return None, lines

    first, last = band
    body = rows[first:last + 1]

    # The columns come from the table's own rows. When the whole page votes, a
    # "Part No:" in the job details lands between two of the table's columns and
    # stops the boundary between them from ever being found - which merges two
    # columns into one and loses a reading behind its own specification.
    edges = table_columns(body)
    if len(edges) < min_columns:
        return None, lines

    outside = [line for i, row in enumerate(rows)
               if i < first or i > last for line in row]

    grid = to_grid(body, edges)
    if not grid:
        return None, lines

    return grid_to_html(grid), outside


def grid_to_html(grid: list[list[str]]) -> str:
    """
    The grid as a plain HTML table.

    The first row becomes a header when every one of its cells has text and no
    cell holds a number - which is what a column heading looks like and a row
    of readings does not.
    """
    if not grid:
        return ""

    def numeric(cell: str) -> bool:
        return any(ch.isdigit() for ch in cell)

    head = grid[0]
    is_header = all(c.strip() for c in head) and not any(numeric(c) for c in head)

    parts = ["<table>"]
    for at, row in enumerate(grid):
        tag = "th" if (at == 0 and is_header) else "td"
        cells = "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in row)
        parts.append(f"<tr>{cells}</tr>")
    parts.append("</table>")
    return "".join(parts)


def lines_outside(lines: list[Line]) -> str:
    """The text that was not part of the table, in reading order."""
    return "\n".join(
        line.text for line in sorted(lines, key=lambda l: (l.cy, l.x1))
    ).strip()
