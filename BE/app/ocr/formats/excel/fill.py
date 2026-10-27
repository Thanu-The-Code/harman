"""Fill a form from a filled-in workbook. No OCR: values are read straight from cells.

  cell   the template was made from this workbook layout: read the remembered cell
         (after checking the label cell still says the same thing)
  label  any other template: find the label cell and read the cell to its right / below;
         tables are found by their column headings
"""
from datetime import date, datetime

from ... import tables
from ... import values as v
from ...grid_interpreter import INLINE_RE, GridInterpreter
from ...results import ResultRecorder, prefix_score, typed_value, value_fields
from .choices import glyph_options, is_ticked, lone_glyph
from .layout import SheetLayout
from .workbook import parse_ref

LABEL_SCORE = 78
MARKS = {"✓", "✔", "☑", "✗", "✘", "☒", "x", "X", "■", "●", "yes", "Yes", "YES", "y", "Y"}


_parse_ref = parse_ref


def labels_agree(label, label_text):
    """The template's label still reads as its label cell - itself, or qualified by its
    row ("Revision Number NEW" for the cell "NEW:")."""
    if prefix_score(label, label_text) >= 70:
        return True
    own = v.norm(v.clean_label(label_text))
    return len(own) >= 2 and v.norm(v.plain(label)).endswith(own)


class ExcelFiller:
    def __init__(self, task_data, sheets):
        self.task_data = [e for e in task_data if isinstance(e, dict)]
        self.sheets = sheets
        self.by_name = {sh.name: sh for sh in sheets}
        self.layouts = [SheetLayout(sh) for sh in sheets]
        self.layout_of = {lay.sheet.name: lay for lay in self.layouts}
        self.recorder = ResultRecorder()
        self._questions = None

    # ---- reading cells ------------------------------------------------------------------
    def _sheet(self, name):
        if name in self.by_name:
            return self.by_name[name]
        return self.sheets[0] if len(self.sheets) == 1 else None

    @staticmethod
    def _raw(sheet, ref):
        rc = _parse_ref(ref)
        value = sheet.values.get(rc)
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m-%d")  # unambiguous for the date parser
        return sheet.texts.get(rc, "")

    @staticmethod
    def _control_checked(sheet, ctl):
        """A Form Control's state: its linked cell (TRUE/FALSE) when it has one, else the control."""
        link = ctl.get("link")
        if link and "!" not in link:
            try:
                value = sheet.values.get(parse_ref(link))
            except ValueError:
                value = None
            if isinstance(value, bool):
                return value
        return bool(ctl.get("checked"))

    def _option_ticked(self, sheet, ref, index, caption):
        """Is the tick box at `ref` ticked? (Form Control, typed glyph, or a mark typed in its place)"""
        layout = self.layout_of.get(sheet.name)
        controls = layout.controls_at(ref) if layout is not None else []
        if controls:
            ctl = next((c for c in controls if c.get("text") and caption and prefix_score(caption, c["text"]) >= 85), None)
            ctl = ctl or (controls[index] if index < len(controls) else controls[0])
            return self._control_checked(sheet, ctl)
        text = sheet.texts.get(parse_ref(ref), "")
        glyph = lone_glyph(text)
        if glyph:
            return is_ticked(glyph)
        parsed = glyph_options(text)
        if parsed:
            opts = parsed[1]
            hit = next((o for o in opts if caption and o["text"] and prefix_score(caption, o["text"]) >= 85), None)
            hit = hit or (opts[index] if index < len(opts) else None)
            return bool(hit and hit["checked"])
        return text.strip() in MARKS

    @staticmethod
    def _after_label(text):
        m = INLINE_RE.match((text or "").strip())
        return m.group("value").strip() if m else ""

    # ---- strategies ------------------------------------------------------------------------
    def _by_cell(self, e, meta):
        sheet = self._sheet(meta.get("sheet"))
        if sheet is None:
            return None
        if meta.get("label_cell") and not meta.get("inline"):
            label_text = sheet.texts.get(_parse_ref(meta["label_cell"]), "")
            if not labels_agree(e.get("label", ""), label_text):
                return None  # layout differs from the template's: fall back to labels
        raw = self._raw(sheet, meta["cell"])
        if meta.get("inline"):
            if prefix_score(e.get("label", ""), raw) < 70:
                return None
            raw = self._after_label(raw)
        return raw

    def find_label(self, e):
        """(layout, cell) of the cell that best reads as this element's label, or None."""
        label = v.plain(e.get("label", ""))
        if len(v.norm(label)) < 2:
            return None
        best, best_score = None, LABEL_SCORE - 1
        for layout in self.layouts:
            for cell in layout.grid().cells:
                if not cell.text:
                    continue
                s = prefix_score(label, cell.text)
                if s > best_score and len(cell.text) <= 3 * len(label) + 10:
                    best, best_score = (layout, cell), s
        return best and self._sub_label(best, label)

    @staticmethod
    def _sub_label(found, label):
        """"Revision Number NEW" is the "NEW:" cell after "Revision Number:" on its row."""
        layout, cell = found
        head, whole = v.norm(v.clean_label(cell.text)), v.norm(label)
        rest = whole[len(head):].strip() if head and whole.startswith(head) else ""
        nxt = layout.grid().right_of(cell) if rest else None
        while nxt is not None:
            if nxt.text and v.norm(v.clean_label(nxt.text)) == rest:
                return layout, nxt
            nxt = layout.grid().right_of(nxt)
        return found

    def _by_label(self, e):
        best = self.find_label(e)
        if best is None:
            return None
        label = v.plain(e.get("label", ""))
        layout, cell = best
        grid = layout.grid()
        inline = self._after_label(cell.text)
        if inline and inline not in ("-", "–") and v.norm(inline) not in v.norm(label):
            return inline  # "Work Station : IQC"; but "Approved By: (M.R.)" is all label
        right = grid.right_of(cell)
        while right is not None and right.text.strip().endswith((":", ":-")):
            right = grid.right_of(right)  # "Revision Number: | OLD: | [value]"
        for nxt in (right, grid.below(cell)):
            if nxt is not None and nxt.text and prefix_score(label, nxt.text) < 70:
                return nxt.text
        return None

    def table_refs(self, e):
        """(sheet, refs, method): the sheet cell of every table body cell ([row][leaf col], None
        where there is none), by the remembered addresses or by finding the column headings."""
        rows = tables.body(e)
        meta = e.get("excel") or {}
        sheet = self._sheet(meta.get("sheet")) if meta.get("cells") else None
        if sheet is not None:
            refs = meta["cells"]
            return sheet, [[refs[r][c] if r < len(refs) and c < len(refs[r]) else None for c in range(len(row))]
                           for r, row in enumerate(rows)], "cell"
        found = None
        for layout in self.layouts:
            hit = tables.match_table(layout.grid(), e)
            if hit and (found is None or sum(x is not None for x in hit[1]) > sum(x is not None for x in found[3])):
                found = (layout, layout.grid(), *hit)
        if found is None:
            return None, None, "none"
        layout, grid, r_head, mapping = found
        grid_rows = tables.body_rows(grid, r_head, mapping, len(rows))
        refs = []
        for r, row in enumerate(rows):
            gr = grid_rows[r] if r < len(grid_rows) else None
            out = []
            for c in range(len(row)):
                gc = mapping[c] if c < len(mapping) else None
                a = grid.at(gr, gc) if gc is not None and gr is not None else None
                out.append(a.ref if a is not None and a.row == gr else None)
            refs.append(out)
        return layout.sheet, refs, "label"

    def _table(self, e):
        sheet, refs, method = self.table_refs(e)
        if sheet is None:
            return None, 0.0, "none"
        value = [[self._table_cell(sheet, ref, cell) if ref and tables.is_input(cell) else "" for ref, cell in zip(refs[r], row)]
                 for r, row in enumerate(tables.body(e))]
        if not any(any(x for x in r) for r in value):
            return None, 0.0, method
        return value, 1.0, method

    def _table_cell(self, sheet, ref, cell):
        layout = self.layout_of.get(sheet.name)
        if tables.normalize_cell(cell).get("input") == "check" and layout is not None and layout.controls_at(ref):
            return "✓" if self._option_ticked(sheet, ref, 0, "") else ""
        return tables.normalize_mark(v.clean_text(self._raw(sheet, ref)))

    def _choice_by_cell(self, e, meta):
        """Options remembered by cell address: read each tick box where the template found it."""
        sheet = self._sheet(meta.get("sheet"))
        if sheet is None:
            return None
        picked = []
        for opt, at in zip(e.get("options") or [], meta.get("options") or []):
            if at and at.get("cell") and self._option_ticked(sheet, at["cell"], at.get("index", 0), opt.get("text", "")):
                picked.append(opt["key"])
        return picked

    def _sheet_questions(self):
        """Tick-box questions on the filled sheets, grouped exactly as a template would group them."""
        if self._questions is None:
            self._questions = []
            for layout in self.layouts:
                items = GridInterpreter(layout.grid(), text_size=layout.text_size, filled=True).interpret()
                self._questions += [(layout, it) for it in items if it["kind"] == "choice"]
        return self._questions

    def _choice_by_question(self, e):
        """The question with this label on the sheet: read its own tick boxes. None if not found."""
        label = v.plain(e.get("label", ""))
        if len(v.norm(label)) < 2:
            return None
        scored = [(prefix_score(label, it["label"]), layout, it) for layout, it in self._sheet_questions() if it["label"]]
        scored = [x for x in scored if x[0] >= LABEL_SCORE]
        if not scored:
            return None
        _, layout, item = max(scored, key=lambda x: x[0])
        picked = []
        for opt in e.get("options") or []:
            caption = opt.get("text", "")
            hit = max(item["options"], key=lambda o: prefix_score(caption, o["text"]), default=None)
            if hit is None or prefix_score(caption, hit["text"]) < 85:
                continue
            at = hit["cell"]
            if self._option_ticked(layout.sheet, at["cell"], at["index"], caption):
                picked.append(opt["key"])
        return picked

    def _choice_by_label(self, e):
        """Options found by their captions: in the question with this label, else anywhere on the sheet."""
        picked = self._choice_by_question(e)
        if picked is not None:
            return picked
        picked = []
        for layout in self.layouts:
            grid = layout.grid()
            for opt in e.get("options") or []:
                caption = opt.get("text", "")
                for cell in grid.cells:
                    hit = False
                    for k, o in enumerate(cell.options):  # "☑ Yes ☐ No" / a Form Control captioned "Yes"
                        if o["text"] and prefix_score(caption, o["text"]) >= 85:
                            hit = hit or self._option_ticked(layout.sheet, cell.ref, k, caption)
                    if cell.text and not cell.options and prefix_score(caption, cell.text.lstrip("☐☑☒✓✔✗✘[]() ")) >= 85:
                        first = cell.text.strip()[:1]
                        neighbours = [n for n in (grid.left_of(cell), grid.right_of(cell)) if n is not None]
                        hit = hit or first in "☑☒✓✔✗✘■" or any(
                            n.text.strip() in MARKS or (n.options and not n.text and self._option_ticked(layout.sheet, n.ref, 0, ""))
                            for n in neighbours)
                    if hit and opt["key"] not in picked:
                        picked.append(opt["key"])
        return picked

    def _choice(self, e):
        """Ticked options: by the remembered tick-box cells, else by option captions, else the
        option's text written as the value."""
        meta = e.get("excel") or {}
        picked = self._choice_by_cell(e, meta) if meta.get("options") else None
        method = "cell"
        if picked is None:
            picked, method = self._choice_by_label(e), "label"
        if not picked and method == "label":
            raw = self._by_label(e)
            opt = v.match_option(raw or "", e.get("options") or [])
            if opt:
                picked = [opt["key"]]
        if e["element"] == "RadioButtons":
            picked = picked[:1]
        return (picked or None), (1.0 if method == "cell" else 0.9) if picked else 0.0, method

    def run(self):
        for e in value_fields(self.task_data):
            kind = e["element"]
            if kind == "Table":
                self.recorder.record(e, *self._table(e))
                continue
            if kind in ("Checkboxes", "RadioButtons"):
                self.recorder.record(e, *self._choice(e))
                continue
            if kind in ("Signature",):
                self.recorder.record(e, None, 0.0, "none")  # signatures are not cell values
                continue
            value, conf, method = None, 0.0, "none"
            meta = e.get("excel")
            if meta and meta.get("cell"):
                raw = self._by_cell(e, meta)
                value = typed_value(e, raw) if raw else None
                if value is not None:
                    conf, method = 1.0, "cell"
            if value is None:
                raw = self._by_label(e)
                value = typed_value(e, raw) if raw else None
                if value is not None:
                    conf, method = 0.9, "label"
            self.recorder.record(e, value, conf, method)
        return {"answers": self.recorder.answers, "fields": self.recorder.report, "alignment": []}
