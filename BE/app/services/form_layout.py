"""
The shape of a form, as opposed to the list of things it records.

A quality format on paper is not a list of fields. It is a letterhead, a block
of job details, one or more ruled tables, a checklist of things to confirm
before starting, a space for observations, and a row of signatures at the
bottom. Somebody handed the printed sheet recognises it by that shape, and a
digital version that throws the shape away and shows twelve stacked inputs is a
different document that happens to collect the same numbers.

So a template carries a *layout*: an ordered list of blocks describing the form
as it is printed. And - the part that makes this safe to add - every block that
records something still produces an ordinary `FormatField`, in reading order.
That is deliberate:

  * `record_service` judges ok from N-ok against those fields, so limits keep
    working exactly as before.
  * `record_extraction` matches what OCR read off a scanned sheet against those
    fields, so reading the paper keeps working.
  * A template that has no layout at all - every one that exists today - still
    behaves exactly as it did.

The layout is therefore presentation and structure; the fields remain the
record's data. Nothing has two sources of truth.

Block kinds
-----------
``header``     the letterhead and the job details printed above the table
``table``      a ruled table: columns, and either fixed rows or ones the person
               filling it adds as they go
``checklist``  things to tick before starting
``fields``     plain labelled entries, the old flat list
``signatures`` the row of signature spaces at the foot of the sheet
``note``       printed instruction text that records nothing
"""
from __future__ import annotations

import html
import json
import re
from typing import Any, Optional

from loguru import logger

HEADER = "header"
TABLE = "table"
CHECKLIST = "checklist"
FIELDS = "fields"
SIGNATURES = "signatures"
NOTE = "note"

KINDS = (HEADER, TABLE, CHECKLIST, FIELDS, SIGNATURES, NOTE)

# What a cell or entry may collect. Kept to what a quality form actually uses;
# anything else is a text box with a longer name.
VALUE_TYPES = ("text", "number", "date", "boolean", "select")

# A table's rows either come from the template - one row per characteristic,
# which is the common case on an inspection sheet - or are added by whoever is
# filling it, for a log where the number of entries is not known in advance.
ROWS_FIXED = "fixed"
ROWS_OPEN = "open"


def _text(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def _value_type(raw: Any) -> str:
    kind = str(raw or "text").strip().lower()
    return kind if kind in VALUE_TYPES else "text"


def _number(raw: Any) -> Optional[float]:
    # not `raw in (None, "", False)`: 0 == False, and a limit of 0 is a real limit
    if raw is None or isinstance(raw, bool) or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


_TAG = re.compile(r"<[^>]+>")


def _plain(value: Any, limit: int = 200) -> str:
    """Builder labels are rich text ("<b>Bore</b>&nbsp;diameter"); fields are plain."""
    text = html.unescape(_TAG.sub(" ", str(value or "")))
    return " ".join(text.split())[:limit]


# React Form Builder elements that print something but record nothing.
PRESENTATION_ELEMENTS = {
    "header", "label", "paragraph", "text", "html", "divider", "section",
    "title", "linebreak", "image", "hyperlink", "download", "signature",
    "fieldset", "twocolumnrow", "threecolumnrow", "multicolumnrow",
}

# React Form Builder element -> the value type the record judges.
REACT_VALUE_TYPES = {
    "number": "number", "numberinput": "number", "range": "number", "rating": "number",
    "date": "date", "datepicker": "date",
    "checkbox": "boolean", "checkboxgroup": "boolean", "check": "boolean",
    "select": "select", "dropdown": "select", "radiobuttons": "select",
    # a tick-box group on a check sheet is answered with one of its options ("Yes" / "No")
    "checkboxes": "select",
}

# Table element cell input -> value type. A tick cell is answered OK (✓) or N-OK (✗).
TABLE_CELL_TYPES = {"text": "text", "number": "number", "date": "date", "check": "select"}

# TableGrid column type -> value type.
TABLE_VALUE_TYPES = {
    "number": "number", "date": "date", "checkbox": "boolean", "dropdown": "select",
}


def _spec(raw: dict) -> dict:
    """The limits on one recorded thing, however they were supplied."""
    return {
        "unit": _text(raw.get("unit"), 24) or None,
        "spec_min": _number(raw.get("spec_min")),
        "spec_max": _number(raw.get("spec_max")),
        "spec_text": _text(raw.get("spec_text"), 120) or None,
        "required": bool(raw.get("required", True)),
    }


# --------------------------------------------------------------- the blocks


def _clean_header(raw: dict) -> dict:
    return {
        "kind": HEADER,
        "title": _text(raw.get("title")) or "",
        # The letterhead. Off by default only because a template built from a
        # scanned sheet already has the letterhead printed on the paper.
        "show_logo": bool(raw.get("show_logo", True)),
        # Job details: what the sheet says above the readings. These *are*
        # recorded - the batch number on an inspection sheet is not decoration.
        "fields": [
            {
                "label": _text(item.get("label")),
                "type": _value_type(item.get("type")),
                **_spec(item),
            }
            for item in (raw.get("fields") or [])
            if _text(item.get("label"))
        ],
    }


def _clean_table(raw: dict) -> dict:
    columns = [
        {
            "label": _text(column.get("label"), 80),
            "type": _value_type(column.get("type")),
            # A column that records nothing - a printed specification, a row
            # heading - is shown but never collected.
            "readonly": bool(column.get("readonly")),
            "unit": _text(column.get("unit"), 24) or None,
        }
        for column in (raw.get("columns") or [])
        if _text(column.get("label"), 80)
    ]

    mode = str(raw.get("rows_mode") or ROWS_FIXED).lower()
    if mode not in (ROWS_FIXED, ROWS_OPEN):
        mode = ROWS_FIXED

    rows = []
    for row in (raw.get("rows") or []):
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label"))
        if not label:
            continue
        rows.append({
            "label": label,
            # What is printed in each read-only column for this row - the
            # specification against which the reading is judged.
            "printed": {
                _text(key, 80): _text(value, 120)
                for key, value in (row.get("printed") or {}).items()
            },
            **_spec(row),
        })

    return {
        "kind": TABLE,
        "title": _text(raw.get("title")) or "",
        "columns": columns,
        "rows_mode": mode,
        "rows": rows,
        # How many blank rows to print when the person filling it adds their own.
        "blank_rows": max(1, min(40, int(raw.get("blank_rows") or 5))),
    }


def _clean_checklist(raw: dict) -> dict:
    return {
        "kind": CHECKLIST,
        "title": _text(raw.get("title")) or "",
        "items": [
            {
                "label": _text(item.get("label") if isinstance(item, dict) else item),
                "required": bool(item.get("required", True))
                            if isinstance(item, dict) else True,
            }
            for item in (raw.get("items") or [])
            if _text(item.get("label") if isinstance(item, dict) else item)
        ],
    }


def _clean_fields(raw: dict) -> dict:
    return {
        "kind": FIELDS,
        "title": _text(raw.get("title")) or "",
        "fields": [
            {
                "label": _text(item.get("label")),
                "type": _value_type(item.get("type")),
                "help_text": _text(item.get("help_text"), 200) or None,
                **_spec(item),
            }
            for item in (raw.get("fields") or [])
            if _text(item.get("label"))
        ],
    }


def _clean_signatures(raw: dict) -> dict:
    return {
        "kind": SIGNATURES,
        "title": _text(raw.get("title")) or "",
        "slots": [
            {
                "label": _text(slot.get("label"), 80) or "Signature",
                # Which responsibility signs here, so the space is filled from
                # the approval rather than typed in by hand.
                "role": _text(slot.get("role"), 40) or None,
                "with_date": bool(slot.get("with_date", True)),
            }
            for slot in (raw.get("slots") or [])
        ],
    }


def _clean_note(raw: dict) -> dict:
    return {
        "kind": NOTE,
        "title": _text(raw.get("title")) or "",
        "body": _text(raw.get("body"), 2000),
    }


CLEANERS = {
    HEADER: _clean_header,
    TABLE: _clean_table,
    CHECKLIST: _clean_checklist,
    FIELDS: _clean_fields,
    SIGNATURES: _clean_signatures,
    NOTE: _clean_note,
}


# ---------------------------------------------------------------- the layout


def parse(stored: Optional[str]) -> list[dict]:
    """
    Read either the legacy quality-form layout or the React Form Builder
    layout without losing any builder information.
    """
    if not stored:
        return []

    try:
        raw = json.loads(stored)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Could not read the form layout: {exc}")
        return []

    if not isinstance(raw, list):
        return []

    blocks = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        # React Form Builder layout.
        # Keep the complete object exactly as it was saved.
        if item.get("element") or item.get("field_name"):
            blocks.append(item)
            continue

        # Legacy Paperless layout.
        cleaner = CLEANERS.get(
            str(item.get("kind") or "").lower()
        )

        if cleaner:
            blocks.append(cleaner(item))

    return blocks

def dump(blocks: Optional[list[dict]]) -> Optional[str]:
    """
    Store the complete layout.

    React Form Builder objects are preserved as-is.
    Legacy Paperless layout blocks continue to use their cleaners.
    """
    cleaned = []

    for item in (blocks or []):
        if not isinstance(item, dict):
            continue

        # React Form Builder layout.
        # IMPORTANT: do not clean/filter these objects because the builder
        # contains its own structure, ids, widths, props, table data, etc.
        if item.get("element") or item.get("field_name"):
            cleaned.append(item)
            continue

        # Legacy Paperless layout.
        cleaner = CLEANERS.get(
            str(item.get("kind") or "").lower()
        )

        if cleaner:
            cleaned.append(cleaner(item))

    return json.dumps(cleaned) if cleaned else None


# ------------------------------------------------------- layout -> the fields


def _table_cell(cell) -> dict:
    """A Table element cell: {text} printed, {input} to fill in, {covered} under a merge.
    A plain string is the legacy shape: "" is an input, anything else printed text."""
    if isinstance(cell, dict):
        return cell
    return {"text": str(cell)} if cell else {"input": "text"}


def _has_spec(spec: dict) -> bool:
    """Whether a recorded thing has anything to be judged against."""
    return any(spec.get(k) is not None for k in ("spec_min", "spec_max", "spec_text"))


def _span_owners(grid: list[list[dict]]) -> list[list[Optional[tuple[int, int]]]]:
    """For every position of a Table grid, the (row, column) of the cell that occupies it -
    itself, or the merged cell whose rowspan / colspan covers it."""
    owner: list[list[Optional[tuple[int, int]]]] = [[None] * len(row) for row in grid]
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell.get("covered"):
                continue
            for i in range(r, min(len(grid), r + max(1, int(cell.get("rowspan") or 1)))):
                for j in range(c, min(len(grid[i]), c + max(1, int(cell.get("colspan") or 1)))):
                    owner[i][j] = (r, c)
    return owner


def _short(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a word where possible."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return cut.rstrip(" ,;:-·") + "…"


def _table_input(cell: dict) -> bool:
    return not cell.get("covered") and ("input" in cell or not str(cell.get("text") or "").strip())


def _table_printed(cell: dict) -> bool:
    return not cell.get("covered") and not _table_input(cell)



def reading_order(blocks: list[dict]) -> list[dict]:
    """
    The builder's items as somebody reads the form: the fields in a row's
    columns where the row is, column by column.

    The builder keeps a row's fields after all the other items (linked by
    `parentId` / `childItems`), so taken as listed, the Dept. and Date at the
    top of a form would come after every table below it.
    """
    by_id = {str(b.get("id")): b for b in blocks if isinstance(b, dict) and b.get("id") is not None}
    placed: set[int] = set()
    ordered: list[dict] = []

    def place(block: dict):
        if id(block) in placed:
            return
        placed.add(id(block))
        ordered.append(block)
        for child_id in block.get("childItems") or []:
            child = by_id.get(str(child_id)) if child_id is not None else None
            if child is not None:
                place(child)

    for block in blocks:
        if isinstance(block, dict) and not (block.get("parentId") and str(block["parentId"]) in by_id):
            place(block)
    for block in blocks:  # a child whose row lists it nowhere still counts
        if isinstance(block, dict):
            place(block)
    return ordered


def to_fields(blocks: list[dict]) -> list[dict]:
    """
    Every recorded thing on this form, in reading order, as plain fields.

    This is the join between the two halves of the design. The layout says how
    the form looks; these are what it collects, and everything downstream -
    judging a reading against its limits, matching what OCR read off a scanned
    sheet, deciding ok from N-ok - works off these and knows nothing about
    blocks.

    Labels are made unique because a field is matched by its label, and two
    rows both called "Reading" would be one field that overwrote itself. Where
    a duplicate arises it is qualified by the block or row it came from, which
    is also what somebody reading the record would call it.
    """
    fields: list[dict] = []
    seen: dict[str, int] = {}

    def add_react_item(item: dict):
        """
        Convert a React Form Builder item into FormatFields.

        The complete React item remains in layout; this only creates the
        flattened field metadata the record system works from. Each field
        carries a `layout_key` - the builder's `field_name`, plus the row and
        column for a table cell - so a filled value is matched to its place on
        the form without relying on labels, which repeat ("Placeholder Label").
        """
        element = str(
            item.get("element")
            or item.get("type")
            or ""
        ).strip()
        element_lower = element.lower()

        # Non-data / presentation elements
        if element_lower in PRESENTATION_ELEMENTS:
            return

        if element_lower == "customelement" and str(item.get("key") or "") == "TableGrid":
            add_table_grid(item)
            return

        if element_lower == "table":
            add_table(item)
            return

        label = _plain(
            item.get("label")
            or item.get("field_name")
            or item.get("name")
            or item.get("content")
        )

        if not label:
            return

        field_type = REACT_VALUE_TYPES.get(element_lower, "text")
        options = [
            _plain(option.get("text") or option.get("value"))
            for option in item.get("options") or []
            if isinstance(option, dict)
        ]

        # required when switched on in Field Properties, and always when it has a limit
        spec = _spec(item)
        spec["required"] = bool(item.get("required")) or _has_spec(spec)
        add(
            label,
            spec,
            field_type,
            _plain(item.get("help_text")) or None,
            layout_key=_text(item.get("field_name"), 120) or None,
            options=[o for o in options if o] or None,
        )

    def add_table_grid(item: dict):
        """
        A builder table: printed columns describe each row (stage, control
        item, method), recorded columns are filled in. Every row x recorded
        column is one field, judged against that row's limits.
        """
        grid = item.get("table_grid") if isinstance(item.get("table_grid"), dict) else {}
        columns = [c for c in (item.get("columns") or grid.get("columns") or [])
                   if isinstance(c, dict) and c.get("id")]
        rows = [r for r in (item.get("rows") or grid.get("rows") or [])
                if isinstance(r, dict) and r.get("id")]
        recorded = [c for c in columns if c.get("kind", "input") == "input"]
        printed = [c for c in columns if c.get("kind", "input") == "fixed"]
        table = _plain(item.get("label")) or "Table"
        base_key = _text(item.get("field_name"), 80) or "table"

        for index, row in enumerate(rows, start=1):
            cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
            row_label = " \u00b7 ".join(
                text for text in (_plain(cells.get(c["id"])) for c in printed) if text
            ) or f"{table} row {index}"
            for column in recorded:
                column_type = str(column.get("type") or "text").lower()
                label = (row_label if len(recorded) == 1
                         else f"{row_label} - {_plain(column.get('name')) or 'Value'}")
                if column_type == "number":
                    spec = _spec(row)
                else:
                    spec = {
                        "unit": None, "spec_min": None, "spec_max": None,
                        "spec_text": _text(column.get("spec_text"), 120) or (
                            "OK" if column_type == "dropdown" else None),
                    }
                # as this table always worked: a cell with a specification must be filled
                spec["required"] = _has_spec(spec)
                add(
                    label,
                    spec,
                    TABLE_VALUE_TYPES.get(column_type, "text"),
                    table,
                    layout_key=f"{base_key}:{row['id']}:{column['id']}",
                    options=["OK", "N-OK"] if column_type == "dropdown" else None,
                )

    def add_table(item: dict):
        """
        The designer's Table / Grid (also what a scanned or Excel form becomes):
        heading rows over body rows of printed text and cells to fill in, with
        merged cells. Every input cell is one field, named by its row's printed
        text and its column heading, judged against the cell's own limits.

        Cells are only required when marked required. A limit says how a
        reading is judged, not that one is due: a monthly check sheet has a
        column per day with the same limits in each, and a record fills the
        days that have come.
        """
        columns = [c if isinstance(c, dict) else {"text": str(c)} for c in item.get("columns") or []]
        rows = [r for r in item.get("rows") or [] if isinstance(r, dict)]
        table = _plain(item.get("label")) or "Table"
        base_key = _text(item.get("field_name"), 80) or "table"

        grid = []
        for row in rows:
            cells = [_table_cell(c) for c in (row.get("cells") or [])][:len(columns)]
            grid.append(cells + [{"input": "text"}] * (len(columns) - len(cells)))
        owner = _span_owners(grid)

        for r, row in enumerate(rows):
            cells = grid[r]
            row_key = _text(row.get("key"), 80) or f"row_{r + 1}"
            # printed text of the row, including a merged cell above that spans into it
            anchors = list(dict.fromkeys(o for o in owner[r] if o is not None))
            printed = [_short(_plain(grid[ar][ac].get("text")), 48)
                       for ar, ac in anchors if _table_printed(grid[ar][ac])]
            # a check sheet's printed cells can be whole sentences: keep the row part short
            # so the column heading (what tells two cells of a row apart) always survives
            row_label = _short(" · ".join(t for t in printed if t), 120) or f"{table} row {r + 1}"
            inputs = [(c, cell) for c, cell in enumerate(cells) if _table_input(cell)]
            for c, cell in inputs:
                column = columns[c]
                heading = _short(_plain(column.get("title") or column.get("text")), 60) or f"Column {c + 1}"
                label = row_label if len(inputs) == 1 and printed else f"{row_label} - {heading}"
                kind = str(cell.get("input") or "text").lower()
                spec = _spec(cell)
                if kind == "check":
                    spec["spec_text"] = spec["spec_text"] or "OK"
                spec["required"] = bool(cell.get("required"))
                add(
                    label,
                    spec,
                    TABLE_CELL_TYPES.get(kind, "text"),
                    table,
                    layout_key=f"{base_key}:{row_key}:{_text(column.get('key'), 80) or c}",
                    options=["OK", "N-OK"] if kind == "check" else None,
                )

    def add(label: str, spec: dict, field_type: str = "text",
            help_text: Optional[str] = None, *,
            layout_key: Optional[str] = None,
            options: Optional[list[str]] = None):
        name = label.strip()[:200]
        if not name:
            return
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        fields.append({
            "label": name,
            "field_type": field_type,
            "unit": spec.get("unit"),
            "spec_min": spec.get("spec_min"),
            "spec_max": spec.get("spec_max"),
            "spec_text": spec.get("spec_text"),
            "required": spec.get("required", True),
            "help_text": help_text,
            "layout_key": layout_key,
            "options": options,
        })

    for block in reading_order(blocks):
        # React Form Builder item
        if block.get("element") or block.get("field_name"):
            add_react_item(block)
            continue
        
        kind = block.get("kind")

        if kind == HEADER:
            for item in block.get("fields", []):
                add(item["label"], item, item.get("type", "text"))

        elif kind == TABLE:
            collected = [c for c in block.get("columns", []) if not c.get("readonly")]

            if block.get("rows_mode") == ROWS_OPEN:
                # Rows are added while filling, so the columns themselves are
                # what gets recorded; the values arrive as a repeated group.
                for column in collected:
                    add(column["label"], {"unit": column.get("unit")},
                        column.get("type", "text"))
                continue

            for row in block.get("rows", []):
                if len(collected) == 1:
                    # The common inspection sheet: one row per characteristic,
                    # one column collected. The row's own name is the field.
                    add(row["label"], row, collected[0].get("type", "number"))
                else:
                    for column in collected:
                        add(f"{row['label']} - {column['label']}", row,
                            column.get("type", "text"))

        elif kind == CHECKLIST:
            for item in block.get("items", []):
                add(item["label"],
                    {"required": item.get("required", True), "spec_text": "yes"},
                    "boolean")

        elif kind == FIELDS:
            for item in block.get("fields", []):
                add(item["label"], item, item.get("type", "text"),
                    item.get("help_text"))

        # Signatures and notes record nothing. A signature is captured by the
        # approval itself, against the person who gave it - not as a value
        # somebody could type into a form.

    return fields


def problems(blocks: list[dict]) -> list[str]:
    """What would make this form impossible to fill, in words somebody can act on."""
    found: list[str] = []

    if not blocks:
        return found

    for block in blocks:
        kind = block.get("kind")
        where = block.get("title") or kind

        if kind == TABLE:
            if not block.get("columns"):
                found.append(f"The table '{where}' has no columns.")
            elif all(c.get("readonly") for c in block["columns"]):
                found.append(
                    f"Every column in '{where}' is printed only, so the table "
                    "records nothing.")
            if block.get("rows_mode") == ROWS_FIXED and not block.get("rows"):
                found.append(f"The table '{where}' has no rows.")

        elif kind == CHECKLIST and not block.get("items"):
            found.append(f"The checklist '{where}' has no items.")

        elif kind == FIELDS and not block.get("fields"):
            found.append(f"The section '{where}' has no entries.")

        elif str(block.get("element") or "") == "Table":
            where = _plain(block.get("label")) or "Table"
            if not block.get("columns"):
                found.append(f"The table '{where}' has no columns.")
            if not block.get("rows"):
                found.append(f"The table '{where}' has no rows.")
            elif (not block.get("reference")  # a printed reference table (revision history) records nothing by design
                  and not any(_table_input(_table_cell(c)) for r in block["rows"] if isinstance(r, dict)
                              for c in (r.get("cells") or []))
                  and len(block["rows"][0].get("cells") or []) >= len(block.get("columns") or [])):
                found.append(
                    f"Every cell in '{where}' is printed text, so the table records "
                    "nothing. Make at least one cell an input.")

        elif str(block.get("key") or "") == "TableGrid":
            grid = block.get("table_grid") if isinstance(block.get("table_grid"), dict) else {}
            where = _plain(block.get("label")) or "Table"
            columns = block.get("columns") or grid.get("columns") or []
            if not any(isinstance(c, dict) and c.get("kind", "input") == "input"
                       for c in columns):
                found.append(
                    f"Every column in '{where}' is printed only, so the table "
                    "records nothing. Mark at least one column as recorded.")
            if not (block.get("rows") or grid.get("rows")):
                found.append(f"The table '{where}' has no rows.")

    if not to_fields(blocks):
        found.append(
            "This form records nothing. Add at least one reading, entry or "
            "checklist item.")

    return found


# --------------------------------------------------------------- a starting point


def starter(title: str = "") -> list[dict]:
    """
    A form shaped like the inspection sheets this replaces.

    What the designer opens on for a new template. It is a working form rather
    than an empty canvas, because the first question anybody has in front of a
    blank designer is "what is this supposed to look like" - and the answer, on
    a shop floor, is nearly always: letterhead, job details, a ruled table of
    characteristics, observations, signatures.
    """
    return [
        {
            "kind": HEADER,
            "title": title or "In-process check",
            "show_logo": True,
            "fields": [
                {"label": "Plant", "type": "text", "required": False},
                {"label": "Line", "type": "text", "required": False},
                {"label": "Shift", "type": "text", "required": False},
                {"label": "Part number", "type": "text", "required": True},
                {"label": "Batch", "type": "text", "required": True},
                {"label": "Date", "type": "date", "required": True},
            ],
        },
        {
            "kind": CHECKLIST,
            "title": "Before you start",
            "items": [
                {"label": "Gauge is within calibration", "required": True},
                {"label": "Work instruction is available at the station",
                 "required": True},
            ],
        },
        {
            "kind": TABLE,
            "title": "Readings",
            "columns": [
                {"label": "Characteristic", "type": "text", "readonly": True},
                {"label": "Specification", "type": "text", "readonly": True},
                {"label": "Reading", "type": "number", "readonly": False},
            ],
            "rows_mode": ROWS_FIXED,
            "rows": [
                {"label": "Bore diameter", "unit": "mm",
                 "spec_min": 24.90, "spec_max": 25.10,
                 "printed": {"Specification": "24.90 - 25.10"}},
                {"label": "Surface finish", "unit": "Ra", "spec_max": 1.6,
                 "printed": {"Specification": "max 1.6"}},
            ],
            "blank_rows": 5,
        },
        {
            "kind": FIELDS,
            "title": "Observations",
            "fields": [
                {"label": "Observations", "type": "text", "required": False,
                 "help_text": "Anything abnormal noticed during the shift."},
            ],
        },
        {
            "kind": SIGNATURES,
            "title": "Sign-off",
            "slots": [
                {"label": "Filled by", "role": "process_owner", "with_date": True},
                {"label": "Verified by", "role": "overall_process_owner",
                 "with_date": True},
            ],
        },
    ]
