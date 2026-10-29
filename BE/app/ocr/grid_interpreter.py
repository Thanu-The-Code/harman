"""Turn a CellGrid (from Excel or from an OCR'd ruled form) into form items.

Recognised structures:
  data table   a header row of short texts (optionally continued by more header rows, e.g.
               "DATE" over 1..31) followed by rows that contain blank boxed cells
  field        a blank boxed cell labelled by the text cell to its left (or above it);
               "Revision Number: | OLD: | [ ]" gives "Revision Number OLD"
  inline field "Work Station : IQC" / "DATE : -" in one cell (document-control text such as
               "Document No.:- HPU/QA/DC/01" stays static)
  section      a single wide text row ("Request Details"); the first big one is the header
  image        a picture anchored in a cell (Excel logos)
  choice       tick boxes in a row ("Married | ☐ Yes | ☐ No", Excel Form Controls) with their captions
Items use the same shape as the OCR template builder, so one assembler turns both into elements.
"""
import bisect
import re
from statistics import median

from . import geometry as g
from .tables import normalize_mark
from .values import clean_label

INLINE_RE = re.compile(r"^(?P<label>[^:：\n]{1,60}?)\s*(?::\s*-|-\s*:|:|：|\s-\s)\s*(?P<value>.*)$", re.S)
DOC_CONTROL_RE = re.compile(
    r"^(doc(ument)?\.?\s*no|format\s*no|rev(ision)?\.?\s*(no|date)?\.?$|rev(ision)?\.?\s*(no|date)|issue\s*date|page\s*no)",
    re.I,
)
MAX_HEADER_WORDS = 8
MAX_REPEATED_BOXES = 3  # "Changes Approved By: [a] [b] [c]"
# Wording that is never a field label: notes, and company names next to blank areas.
NOTE_RE = re.compile(r"^(note|notes|nb|n\.b|instructions?)$", re.I)
MARK_RE = re.compile(r"^\s*(✓|✔|✗|✘|√|☑|☒|x|X|ok|OK|not ok|NOT OK)\s*$")
MAX_CAPTION_WORDS = 4
TABLE_INPUT = {"DatePicker": "date", "NumberInput": "number"}
NOT_A_LABEL_RE = re.compile(r"\b(ltd|limited|pvt|inc|llp|llc|gmbh)\b\.?", re.I)


def _words(text):
    return len(text.split())


def input_cell(cell):
    """Table body cell to fill in, typed by what the source says about it."""
    if cell.options:
        return {"input": "check"}
    hint = cell.hint or {}
    kind = TABLE_INPUT.get(hint.get("element"), "text")
    if hint.get("element") == "Dropdown" and all(normalize_mark(o) in ("✓", "✗") for o in hint.get("options") or ["?"]):
        kind = "check"
    return {"input": kind}


class GridInterpreter:
    def __init__(self, grid, text_size=None, filled=False):
        """filled=True: the grid comes from a filled-in copy, so written values sit where a
        blank form has blanks (next to "Label:" cells, in table input columns)."""
        self.g = grid
        self.filled = filled
        sizes = [c.size for c in grid.cells if c.text.strip() and c.size]
        self.size = text_size or (median(sizes) if sizes else 0)
        self.used = set()
        self.items = []
        self.table_rows = set()
        self.fields_by_cell = {}
        self.row_label = {}  # blank cell -> the row's label: "Revision Number: | OLD: [ ] | NEW: [ ]"
        self.header_done = False
        self._title_candidate = None

    # ---- helpers -------------------------------------------------------------------
    def _mark(self, *cells):
        for c in cells:
            if c is not None:
                self.used.add(id(c))

    def _is_used(self, cell):
        return id(cell) in self.used

    def _in_table(self, cell):
        return any(r in self.table_rows for r in range(cell.row, cell.end_row))

    def _is_section(self, cell, width=None):
        width = width or self.g.n_cols
        return bool(cell.text.strip()) and cell.colspan >= max(2, 0.6 * width)

    def _inline(self, cell):
        """(label, value) for 'Label: value' cells, else None."""
        m = INLINE_RE.match(cell.text.strip())
        if not m or _words(m.group("label")) > 6:
            return None
        value = m.group("value").strip()
        label = clean_label(m.group("label"))
        if _words(value) > 12 or (value not in ("", "-", "–", "_") and NOTE_RE.match(label)):
            return None
        return label, "" if value in ("-", "–", "_") else value

    # ---- tables --------------------------------------------------------------------
    def _header_run(self, r):
        anchors = self.g.row_anchors(r)
        runs, run = [], []
        for a in anchors:
            if run and (a.col != run[-1].end_col or not a.boxed):
                runs.append(run)
                run = []
            if a.boxed:
                run.append(a)
        if run:
            runs.append(run)
        best = None
        for run in runs:
            texts = [a for a in run if not a.is_blank]
            if len(texts) < 2:
                continue
            idx = [run.index(a) for a in texts]
            blanks = len(run) - len(texts)
            if any(run[i].is_blank for i in range(min(idx), max(idx))):
                continue  # labels interleaved with blanks: a key/value row, not a header
            if blanks > len(texts):
                continue  # mostly blank: a body row with a few labels on the left
            if any(_words(a.text) > MAX_HEADER_WORDS for a in texts):
                continue
            if sum(1 for a in texts if a.text.strip().endswith((":", ":-"))) * 2 >= len(texts):
                continue
            if any(self._inline(a) for a in texts):
                continue  # "DATE : -" / "Label: value" cells belong to a header block, not a table head
            if best is None or len(texts) > best[2]:
                best = (run[0].col, run[-1].end_col, len(texts))
        return best[:2] if best else None

    def _header_continues(self, r, c0, c1):
        anchors = self.g.row_anchors(r, c0, c1)
        if not anchors:
            return False
        # Small heading text (e.g. day numbers 1..31) is not always readable in a scan.
        if sum(1 for a in anchors if not a.is_blank) < 0.6 * len(anchors):
            return False
        if not all(self.g.at(r, c) is not None for c in range(c0, c1)):
            return False
        # A further heading row subdivides a heading cell above it ("DATE" over 1..31); a row
        # that merely repeats the columns is data (e.g. the first row of a filled-in table).
        above = {id(self.g.at(r - 1, c)) for c in range(c0, c1)}
        return any(
            sum(1 for a in anchors if a.col >= h.col and a.end_col <= h.end_col) > 1
            for h in (self.g.at(r - 1, c) for c in range(c0, c1)) if h is not None and id(h) in above and not h.is_blank
        )

    def _body_row(self, r, c0, c1):
        width = c1 - c0
        anchors = self.g.row_anchors(r, c0, c1)
        cover = [self.g.at(r, c) for c in range(c0, c1)]
        if all(c is None for c in cover):
            return False
        if any(a.is_blank and not a.boxed for a in anchors):
            return False
        if self._spacer(r, c0, c1):
            return True
        if anchors and not any(a.is_blank and a.boxed for a in anchors):
            # Nothing to fill in: a footer / note row closes the table. A filled-in copy has
            # complete rows too, so there only document-control / note text closes it.
            if not self.filled or any(self._footer_text(a) for a in anchors):
                return False
        wide = sum(a.colspan for a in anchors if not a.is_blank and a.colspan >= max(3, 0.25 * width))
        return wide < 0.5 * width

    def _label_like(self, cell):
        """'Dept.:' or 'Approved By: (M.R.)' - a caption whose value is written next to it."""
        text = cell.text.strip()
        if text.endswith((":", ":-")):
            return True
        parsed = self._inline(cell)
        return bool(parsed and re.fullmatch(r"\(.*\)", parsed[1] or ""))

    def _caption_text(self, cell):
        text = cell.text.strip()
        return (0 < _words(text) <= 3 and "\n" not in text and not self._inline(cell) and not self._is_section(cell)
                and not re.match(r"^[✓✔✗✘√×]", text))

    def _caption(self, cell):
        """A short caption without a colon ("PART NO.", "Model") - in a filled copy the text to
        its right is its value."""
        return self._caption_text(cell) and cell is not self._title_candidate

    def _footer_text(self, cell):
        """'Note:- ...', 'Format No.: ...' - text that closes a table."""
        text = cell.text.strip()
        if not text:
            return False
        if re.match(r"^(note|notes|nb|n\.b)\b", text, re.I):
            return True
        parsed = self._inline(cell)
        label = parsed[0] if parsed else clean_label(text)
        return bool(DOC_CONTROL_RE.match(label) or NOTE_RE.match(label))

    def _spacer(self, r, c0, c1):
        """A blank ruled strip across the whole table (e.g. under the heading)."""
        anchors = self.g.row_anchors(r, c0, c1)
        return len(anchors) == 1 and anchors[0].is_blank and anchors[0].colspan >= 0.9 * (c1 - c0)

    def _find_tables(self):
        tables, r = [], 0
        while r < self.g.n_rows:
            span = self._header_run(r)
            if span:
                c0, c1 = span
                h_end = r + 1
                while h_end < self.g.n_rows and self._header_continues(h_end, c0, c1):
                    h_end += 1
                b_end = h_end
                while b_end < self.g.n_rows and self._body_row(b_end, c0, c1):
                    b_end += 1
                blanks = [a for rr in range(h_end, b_end) for a in self.g.row_anchors(rr, c0, c1) if a.is_blank and a.boxed]
                if b_end > h_end and len(blanks) >= 2:
                    tables.append((r, h_end, b_end, c0, c1))
                    self.table_rows.update(range(r, b_end))
                    r = b_end
                    continue
            r += 1
        return tables

    def _table_item(self, r0, h_end, b_end, c0, c1):
        full_grid = r0 == 0 and h_end == 0
        cells = [a for a in self.g.cells if r0 <= a.row < b_end and c0 <= a.col < c1]
        bounds = sorted({a.col for a in cells} | {c1})
        leaf = lambda c: bisect.bisect_right(bounds, c) - 1  # noqa: E731
        n_leaf = len(bounds) - 1
        if self.filled:
            # Judge input columns on the data rows only: sign-off rows under a "Note:" row
            # (Prepared by / Approved by) leave cells blank that are not for filling in.
            data_end = next((r for r in range(h_end, b_end)
                             if any(self._footer_text(a) for a in self.g.row_anchors(r, c0, c1))), b_end)
            input_cols = self._input_columns(cells, h_end, data_end, leaf)
        else:
            input_cols = set()

        def build(rows, body):
            pos = {r: i for i, r in enumerate(rows)}
            grid = [[None] * n_leaf for _ in rows]
            boxes = [[None] * n_leaf for _ in rows]
            refs = [[None] * n_leaf for _ in rows]
            for a in cells:
                if a.row not in pos:
                    continue
                cs = leaf(min(a.end_col, c1) - 1) - leaf(a.col) + 1
                rs = sum(1 for r in range(a.row, a.end_row) if r in pos)
                lr, lc = pos[a.row], leaf(a.col)
                if body and leaf(a.col) in input_cols:
                    cell = input_cell(a)  # a written value in an input column of a filled copy
                else:
                    # Only a visibly boxed/styled blank is an answer area. Unruled empty
                    # worksheet cells are layout whitespace and must not become inputs.
                    cell = (
                        {"text": a.text.strip()}
                        if not a.is_blank
                        else (input_cell(a) if body and a.boxed else {"text": ""})
                    )
                if cs > 1:
                    cell["colspan"] = cs
                if rs > 1:
                    cell["rowspan"] = rs
                grid[lr][lc] = cell
                boxes[lr][lc] = a.bbox
                refs[lr][lc] = a.ref
                for rr in range(lr, lr + rs):
                    for cc in range(lc, lc + cs):
                        if (rr, cc) != (lr, lc):
                            grid[rr][cc] = {"covered": True}
            for row in grid:
                for i, cell in enumerate(row):
                    if cell is None:
                        row[i] = {"text": ""}
            return grid, boxes, refs

        header, header_boxes, _ = build(list(range(r0, h_end)), body=False)
        # a row on which no cell begins lies wholly inside cells merged from the row above
        # (a tall Excel row split in two): it is not a row of the form
        body_rows = [r for r in range(h_end, b_end)
                     if (full_grid or not self._spacer(r, c0, c1))
                     and self.g.row_anchors(r, c0, c1)]
        body, cell_boxes, cell_refs = build(body_rows, body=True)
        columns = []
        for lc in range(n_leaf):
            texts = []
            for hr in range(h_end - r0):
                a = self.g.at(r0 + hr, bounds[lc])
                if a is not None and a.text.strip() and a.text.strip() not in texts:
                    texts.append(a.text.strip())
            columns.append({"text": texts[-1] if texts else "", "title": " ".join(texts)})
        header_anchors = [
            {"text": a.text.strip(), "bbox": a.bbox} for a in cells if a.row < h_end and a.text.strip() and a.bbox
        ]

        label, label_bbox, label_ref = "", None, None
        if r0 > 0:
            above = [a for a in self.g.row_anchors(r0 - 1) if not a.is_blank]
            if len(above) == 1 and above[0].colspan >= 0.5 * (c1 - c0) and not self._is_used(above[0]):
                label, label_bbox, label_ref = clean_label(above[0].text), above[0].bbox, above[0].ref
                self._mark(above[0])
        self._mark(*cells)
        boxes = [a.bbox for a in cells if a.bbox] + ([label_bbox] if label_bbox else [])
        return {
            "kind": "table",
            "label": label,
            "label_bbox": label_bbox,
            "label_ref": label_ref,
            "columns": columns,
            "header": header,
            "body": body,
            "header_anchors": header_anchors,
            "cell_boxes": cell_boxes,
            "cell_refs": cell_refs,
            "bbox": g.union(boxes) if boxes else None,
        }

    @staticmethod
    def _input_columns(cells, h_end, b_end, leaf):
        """Leaf columns that are for filling in: mostly blank, or holding ticks/crosses."""
        by_col = {}
        for a in cells:
            # Only cells sitting in one column count: a full-width spacer or a heading-like
            # merged cell says nothing about whether that column is filled in.
            if h_end <= a.row < b_end and leaf(a.col) == leaf(a.end_col - 1):
                by_col.setdefault(leaf(a.col), []).append(a)
        out = set()
        for lc, items in by_col.items():
            blanks = sum(1 for a in items if a.is_blank)
            if blanks >= 2 and blanks >= 0.25 * len(items) or any(MARK_RE.match(a.text) for a in items):
                out.add(lc)
        return out

    # ---- fields --------------------------------------------------------------------
    def _label_for(self, blank):
        left = self.g.left_of(blank)
        if left is not None and not self._in_table(left):
            if not left.is_blank and not self._is_section(left) and not NOT_A_LABEL_RE.search(left.text):
                text = clean_label(left.text)
                outer = self.g.left_of(left)
                sub = left.text.strip().endswith(":") and _words(left.text) <= 3
                if (outer is not None and not outer.is_blank and outer.text.strip().endswith((":", ":-")) and sub):
                    self.row_label[id(blank)] = clean_label(outer.text)
                    text = f"{self.row_label[id(blank)]} {text}"
                    self._mark(outer)
                elif outer is not None and outer.is_blank and id(outer) in self.row_label and sub:
                    # the row's next sub-label ("NEW:") belongs to the same row label
                    self.row_label[id(blank)] = self.row_label[id(outer)]
                    text = f"{self.row_label[id(blank)]} {text}"
                return left, text
            if left.is_blank and id(left) in self.fields_by_cell:
                base, n = self.fields_by_cell[id(left)]
                if n >= MAX_REPEATED_BOXES:
                    return None, None  # a long run of blanks is a grid, not repeated boxes of one label
                return None, (base, n + 1)
        above = self.g.above(blank)
        if (above is not None and not above.is_blank and above.col == blank.col and not self._in_table(above)
                and not self._is_section(above) and not self._inline(above) and not NOT_A_LABEL_RE.search(above.text)):
            return above, clean_label(above.text)
        return None, None

    def _field(self, label, label_cell, zone_cell, inline=False, sample=""):
        return {
            "sample": sample,
            "kind": "field",
            "label": label,
            "label_bbox": label_cell.bbox if label_cell is not None and label_cell.bbox else None,
            "zone": zone_cell.bbox,
            "element": None,
            "bbox": g.union([b for b in (zone_cell.bbox, label_cell.bbox if label_cell else None) if b]) if zone_cell.bbox else None,
            "rows": zone_cell.rowspan,
            "ref": zone_cell.ref,
            "label_ref": label_cell.ref if label_cell is not None else None,
            "inline": inline,
            "hint": None if inline else zone_cell.hint,
        }

    def _form_cells(self):
        for cell in self.g.cells:
            if self._is_used(cell) or self._in_table(cell):
                continue
            if cell.is_blank and cell.boxed:
                label_cell, label = self._label_for(cell)
                if label is None:
                    continue
                if isinstance(label, tuple):
                    base, n = label
                    label = f"{base} ({n})"
                    self.fields_by_cell[id(cell)] = (base, n)
                else:
                    self.fields_by_cell[id(cell)] = (label, 1)
                if not label:
                    continue
                self._mark(cell, label_cell)
                self.items.append(self._field(label, label_cell, cell))
        if self.filled:
            # "Dept.: | Quality": a written value next to a "Label:" cell.
            for cell in self.g.cells:
                if self._is_used(cell) or self._in_table(cell) or cell.is_blank:
                    continue
                colon = self._label_like(cell)
                if not (colon or self._caption(cell)) or NOT_A_LABEL_RE.search(cell.text):
                    continue
                label, n, value = clean_label(cell.text), 1, self.g.right_of(cell)
                if not colon and value is not None and not value.boxed:
                    continue  # unruled text beside a bare caption is a column of printed text (a revision history)
                outer = self.g.left_of(cell)
                sub = colon and _words(cell.text) <= 3
                if (sub and outer is not None and not self._is_used(outer) and outer.text.strip().endswith((":", ":-"))):
                    label = f"{clean_label(outer.text)} {label}"  # "Revision Number: | OLD: | [value]"
                    self._mark(outer)
                    if value is not None:
                        self.row_label[id(value)] = clean_label(outer.text)
                elif sub and outer is not None and id(outer) in self.row_label:
                    # the row's next sub-label ("NEW:" after OLD's value) belongs to the same row label
                    label = f"{self.row_label[id(outer)]} {label}"
                    if value is not None:
                        self.row_label[id(value)] = self.row_label[id(outer)]
                # One label can head several boxes: "Changes Approved By: [a] [b] [c]".
                while (value is not None and value is not cell and not value.is_blank and not self._is_used(value)
                       and not self._in_table(value) and not self._label_like(value) and not self._inline(value)
                       and value is not self._title_candidate and not value.computed):
                    self._mark(cell, value)
                    self.items.append(self._field(label if n == 1 else f"{label} ({n})", cell, value))
                    if not colon or n >= MAX_REPEATED_BOXES:
                        break  # a bare caption ("PART NO. | ABC-1") heads one value only
                    n, value = n + 1, self.g.right_of(value)
        # "Label: value" / "DATE : -" cells that do not label a neighbouring blank.
        for cell in self.g.cells:
            if self._is_used(cell) or self._in_table(cell) or cell.is_blank:
                continue
            parsed = self._inline(cell)
            if not parsed or not parsed[0] or DOC_CONTROL_RE.match(parsed[0]):
                continue
            self._mark(cell)
            item = self._field(parsed[0], cell, cell, inline=True, sample=parsed[1])
            if cell.text_bbox:
                item["label_bbox"] = cell.text_bbox  # where the printed "Label: value" sits (OCR)
            self.items.append(item)
        # A short label at the top of a tall box (OCR only): the rest of the box is for writing.
        for cell in self.g.cells:
            if (self._is_used(cell) or self._in_table(cell) or cell.is_blank or not cell.text_bbox or not cell.bbox
                    or "\n" in cell.text.strip() or _words(cell.text) > 7 or self._is_section(cell)
                    or NOT_A_LABEL_RE.search(cell.text)):
                continue
            tb, cb = cell.text_bbox, cell.bbox
            if g.height(cb) > 2.2 * g.height(tb) and tb[1] - cb[1] < 0.4 * g.height(cb):
                self._mark(cell)
                item = self._field(clean_label(cell.text), cell, cell)
                item["zone"] = [cb[0], tb[3], cb[2], cb[3]]
                item["label_bbox"] = tb
                self.items.append(item)

    # ---- tick boxes ------------------------------------------------------------------
    def _caption_cell(self, cell, slot):
        """A short text right beside a tick box: its caption ("Yes")."""
        return (cell is not None and not cell.options and not cell.is_blank and not self._is_used(cell)
                and _words(cell.text) <= MAX_CAPTION_WORDS and "\n" not in cell.text.strip()
                and (cell.col == slot.end_col or cell.end_col == slot.col))

    @staticmethod
    def _captionless(cell):
        return bool(cell.options) and not any(o["text"] for o in cell.options)

    def _choice_groups(self, anchors):
        """Split one row into questions: [{"label": cell, "prefix": (text, cell), "options": [...]}].

        Captions of lone tick boxes sit to their right ("☐ | Yes") unless the last box ends the
        row, in which case they sit to the left ("Yes | ☐").
        """
        slots = [i for i, a in enumerate(anchors) if self._captionless(a)]
        right = True
        if slots:
            last = slots[-1]
            right = last + 1 < len(anchors) and self._caption_cell(anchors[last + 1], anchors[last])
        groups, cur, label, pending = [], None, None, None
        i = 0
        while i < len(anchors):
            a = anchors[i]
            if a.options:
                if cur is not None and a.option_prefix:
                    groups.append(cur)  # "Married: ☐ Yes ☐ No | Smoker: ☐ Yes ☐ No"
                    cur = None
                if cur is None:
                    cur, label = {"label": label, "prefix": None, "options": []}, None
                if a.option_prefix:
                    cur["prefix"] = (a.option_prefix, a)
                for k, o in enumerate(a.options):
                    caption = None
                    if not o["text"]:
                        if right and i + 1 < len(anchors) and self._caption_cell(anchors[i + 1], a):
                            i += 1
                            caption = anchors[i]
                        elif not right and pending is not None:
                            caption = pending
                    pending = None
                    text = o["text"] or (" ".join(caption.text.split()) if caption is not None else "")
                    cur["options"].append({"text": text, "cell": a, "index": k, "caption": caption, "kind": o["kind"]})
            elif not a.is_blank:
                nxt = anchors[i + 1] if i + 1 < len(anchors) else None
                if not right and nxt is not None and self._captionless(nxt) and self._caption_cell(a, nxt):
                    pending = a
                else:
                    if cur is not None:
                        groups.append(cur)
                        cur = None
                    label = a
            i += 1
        if cur is not None:
            groups.append(cur)
        return groups

    def _choices(self):
        for r in range(self.g.n_rows):
            anchors = [a for a in self.g.row_anchors(r) if not self._is_used(a) and not self._in_table(a)]
            if not any(a.options for a in anchors):
                continue
            for grp in self._choice_groups(anchors):
                label_cell, label = grp["label"], ""
                if grp["prefix"]:
                    label, label_cell = clean_label(grp["prefix"][0]), grp["prefix"][1]
                elif label_cell is not None and _words(label_cell.text) <= MAX_HEADER_WORDS:
                    label = clean_label(label_cell.text)
                else:
                    first = grp["options"][0]["cell"]
                    above = self.g.above(first)
                    label_cell = None
                    if (above is not None and not above.is_blank and not above.options and not self._is_used(above)
                            and not self._in_table(above) and _words(above.text) <= MAX_HEADER_WORDS):
                        label, label_cell = clean_label(above.text), above
                options = []
                for n, o in enumerate(grp["options"]):
                    text = o["text"] or (label if len(grp["options"]) == 1 else "") or f"Option {n + 1}"
                    options.append({
                        "text": text, "box": o["cell"].bbox,
                        "text_bbox": (o["caption"] or o["cell"]).bbox,
                        "cell": {"cell": o["cell"].ref, "index": o["index"]},
                    })
                    self._mark(o["cell"], o["caption"])
                self._mark(label_cell)
                boxes = [b for b in [x["box"] for x in options] + [x["text_bbox"] for x in options]
                         + [label_cell.bbox if label_cell is not None else None] if b]
                radio = all(o["kind"] == "radio" for o in grp["options"])
                self.items.append({
                    "kind": "choice",
                    "element": "RadioButtons" if radio else "Checkboxes",
                    "label": label,
                    "label_bbox": label_cell.bbox if label_cell is not None else None,
                    "label_ref": label_cell.ref if label_cell is not None else None,
                    "options": options,
                    "bbox": g.union(boxes) if boxes else None,
                })

    # ---- everything else ---------------------------------------------------------------
    def _images(self):
        for cell in self.g.cells:
            if cell.image and not self._is_used(cell):
                self._mark(cell)
                self.items.append({"kind": "image", **cell.image, "bbox": cell.bbox})

    def _title(self):
        """The form title: the most prominent text near the top (large and/or wide)."""
        top = [c for c in self.g.cells if not self._is_used(c) and not c.is_blank and c.row <= max(3, self.g.n_rows // 6)]
        if self.filled:
            # Handwriting is often larger than print: a value next to a label is never the title.
            def value_position(c):
                left = self.g.left_of(c)
                return left is not None and not left.is_blank and self._label_like(left)
            top = [c for c in top if not value_position(c)]
        if not top:
            return None
        def score(c):
            s = (c.size or self.size or 1) * (1 + 2 * c.colspan / max(1, self.g.n_cols))
            return s * (0.5 if _words(c.text) < 2 else 1.0)  # a lone word is usually a logo, not the title

        best = max(top, key=score)
        prominent = (self.size and best.size >= 1.15 * self.size) or best.colspan >= 0.4 * self.g.n_cols
        return best if prominent else None

    def _statics(self):
        title_cell = None if self.header_done else self._title()
        for cell in self.g.cells:
            if self._is_used(cell) or cell.is_blank:
                continue
            text = " ".join(cell.text.split())
            title = cell is title_cell
            if title:
                element = "Header"
                self.header_done = True
            elif _words(text) <= 8:
                element = "Label"
            else:
                element = "Paragraph"
            self._mark(cell)
            self.items.append({
                "kind": "static", "element": element, "text": text, "bbox": cell.bbox,
                "bold": bool(cell.bold or self._is_section(cell)) and element != "Header", "ref": cell.ref,
            })

    def interpret(self):
        tables = self._find_tables()
        # A ruled grid that encloses the detected data table is itself one form table.
        # Keep its leading title/metadata rows inside the same editable cell matrix.
        if (
            len(tables) == 1
            and tables[0][0] > 0
            and tables[0][3] == 0
            and tables[0][4] == self.g.n_cols
            and tables[0][2] == self.g.n_rows
        ):
            tables = [(0, 0, self.g.n_rows, 0, self.g.n_cols)]
        for t in tables:
            self.items.append(self._table_item(*t))
        self._images()
        self._choices()
        self._title_candidate = self._title()
        self._form_cells()
        self._statics()
        return self.items
