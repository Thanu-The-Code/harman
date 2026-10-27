"""Text set out in columns without any ruling, such as a revision history under the form:

    S.No   Change description   Rev No   Rev date
      1     Initial release       00     01.11.2014

Read line by line it is a jumble ("Revision history Rev date", "S.No", ...), so it is
kept as a table of fixed text. Nothing in it is filled in. find() works on OCR'd text
lines (scans, PDFs); tabulate() on the fixed-text items of a workbook sheet.
"""
from . import geometry as g

MIN_COLUMNS = 3
MIN_ROWS = 2


def _rows(idx, bbox):
    rows = []
    for i in sorted(idx, key=lambda i: (g.center(bbox(i))[1], bbox(i)[0])):
        if rows and g.v_overlap(bbox(rows[-1][-1]), bbox(i)) >= 0.5:
            rows[-1].append(i)
        else:
            rows.append([i])
    return [sorted(r, key=lambda i: bbox(i)[0]) for r in rows]


def _spaced(row, bbox, min_gap):
    """Items far enough apart to be columns, not the words of one sentence."""
    return len(row) >= MIN_COLUMNS and all(bbox(b)[0] - bbox(a)[2] >= min_gap for a, b in zip(row, row[1:]))


def _bands(row, bbox):
    """Each heading's column: up to halfway to its neighbours."""
    cuts = [(bbox(a)[2] + bbox(b)[0]) / 2 for a, b in zip(row, row[1:])]
    return list(zip([float("-inf")] + cuts, cuts + [float("inf")]))


def _fits(row, bands, bbox):
    return len(row) == len(bands) and all(lo <= g.center(bbox(i))[0] <= hi for i, (lo, hi) in zip(row, bands))


def find(idx, bbox, line_height, min_gap=None):
    """Line indices -> [[[i, ...], ...], ...]: each table's rows, the first one its headings.

    min_gap: the space between two columns (a line height by default; 0 for sheet cells,
    which are columns however close they sit).
    """
    min_gap = line_height if min_gap is None else min_gap
    tables, rows = [], _rows(idx, bbox)
    n = 0
    while n < len(rows):
        head = rows[n]
        if not _spaced(head, bbox, min_gap):
            n += 1
            continue
        bands, table = _bands(head, bbox), [head]
        for row in rows[n + 1:]:
            gap = bbox(row[0])[1] - max(bbox(i)[3] for i in table[-1])
            if gap > 1.5 * line_height or not _fits(row, bands, bbox):
                break
            table.append(row)
        if len(table) >= MIN_ROWS:
            tables.append(table)
        n += len(table)
    return tables


def table_item(rows, bbox, text):
    """The rows found by find() as a template table item (see grid_interpreter's)."""
    boxes = [[bbox(i) for i in r] for r in rows]
    return {
        "kind": "table",
        "reference": True,  # printed for information: the template's validation expects no inputs
        "label": "",
        "label_bbox": None,
        "columns": [{"text": text(i)} for i in rows[0]],
        "header": [[{"text": text(i)} for i in rows[0]]],
        "body": [[{"text": text(i)} for i in r] for r in rows[1:]],
        "header_anchors": [{"text": text(i), "bbox": bbox(i)} for i in rows[0]],
        "cell_boxes": boxes[1:],
        "bbox": g.union([b for r in boxes for b in r]),
    }


def tabulate(items, line_height):
    """A sheet's template items with each run of fixed text set out in columns made one table."""
    static = [i for i, it in enumerate(items) if it["kind"] == "static" and it.get("element") != "Header" and it.get("bbox")]
    bbox, text = (lambda i: items[i]["bbox"]), (lambda i: items[i]["text"])
    tables, drop = {}, set()
    for rows in find(static, bbox, line_height, min_gap=0):
        table = table_item(rows, bbox, text)
        drop.update(i for r in rows for i in r)
        above = [i for i in static if i not in drop and g.h_overlap(bbox(i), table["bbox"]) > 0.5
                 and -0.25 * line_height <= table["bbox"][1] - bbox(i)[3] <= 1.6 * line_height]
        cap = max(above, key=lambda i: bbox(i)[3]) if above else None
        if cap is not None and len(text(cap).split()) <= 10:
            table["label"], table["label_bbox"], table["label_ref"] = text(cap), bbox(cap), items[cap].get("ref")
            table["bbox"] = g.union([table["bbox"], bbox(cap)])
            drop.add(cap)
        tables[rows[0][0]] = table
    return [tables.get(i, it) for i, it in enumerate(items) if i in tables or i not in drop]
