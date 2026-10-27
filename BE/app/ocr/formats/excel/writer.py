"""Write a form's values back into the workbook: the one the form was made from, or the same
blank form. The rest of the workbook (formatting, logos, formulas, drop-down lists, Form Controls)
is left as it was.

  WritePlanner   which cells / tick boxes get which value (format-neutral writes)
  XlsxPatcher    applies them to .xlsx/.xlsm by editing only the touched XML parts of the package
  XlsPatcher     applies them to .xls (xlutils), keeping every cell's formatting
"""
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from xml.sax.saxutils import escape

from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format

from ... import tables
from ... import values as v
from ...grid_interpreter import INLINE_RE
from ...results import prefix_score, value_fields
from .choices import glyph_options, lone_glyph, set_ticks
from .fill import ExcelFiller, labels_agree
from .package import Package
from .workbook import is_xls, is_xlsx, parse_ref, read_workbook

NOT_WRITTEN = {"Signature": "signatures are images", "FileUpload": "files are not cell values",
               "Camera": "photos are not cell values", "Image": "pictures are not cell values"}


@dataclass
class CellWrite:
    sheet: str
    row: int
    col: int
    value: object               # str | int | float | bool | date | datetime | None (clear)
    text: str = ""              # how to write a date into a cell that is not date-formatted


@dataclass
class WritePlan:
    cells: list = field(default_factory=list)
    controls: list = field(default_factory=list)   # (control, checked)
    written: list = field(default_factory=list)    # labels
    skipped: list = field(default_factory=list)    # {"label", "reason"}


def _label(e):
    return v.plain(e.get("label", "")) or e.get("field_name", "")


class WritePlanner:
    def __init__(self, task_data, answers, sheets):
        self.answers = answers or {}
        self.task_data = [e for e in task_data if isinstance(e, dict)]
        self.reader = ExcelFiller(self.task_data, sheets)  # finds cells exactly as filling does
        self.plan = WritePlan()

    # ---- helpers ---------------------------------------------------------------------------
    def _skip(self, e, reason):
        self.plan.skipped.append({"label": _label(e), "reason": reason})

    def _cell(self, sheet, r, c, value, text=""):
        if (r, c) in sheet.formulas:
            return False  # calculated cells are never overwritten
        if (value is None or value == "") and (r, c) not in sheet.values:
            return True  # nothing to clear
        self.plan.cells.append(CellWrite(sheet.name, r, c, None if value == "" else value, text))
        return True

    @staticmethod
    def _typed(e, raw, kind=None):
        """(value for the cell, text fallback). kind: table input type."""
        text = "" if raw is None else str(raw).strip()
        if not text:
            return "", ""
        element = kind or e.get("element")
        if element in ("NumberInput", "Rating", "Range", "number"):
            n = v.clean_number(text)
            if n:
                return (int(n) if re.fullmatch(r"-?\d+", n) else float(n)), text
        if element in ("DatePicker", "date"):
            mask = v.date_mask(e) if element == "DatePicker" else "yyyy-MM-dd"
            parsed = v.parse_date(text, day_first=mask.lower().startswith("d"))
            if parsed:
                return parsed, text
        if element == "Dropdown":
            opt = next((o for o in e.get("options") or [] if o.get("value") == raw), None)
            return (opt.get("text") if opt else text), text
        return text, text

    # ---- fields ----------------------------------------------------------------------------
    def _target(self, e):
        """(sheet, row, col, inline) where this field's value goes, or None."""
        meta = e.get("excel") or {}
        sheet = self.reader._sheet(meta.get("sheet")) if meta.get("cell") else None
        if sheet is not None:
            ok = True
            if meta.get("label_cell") and not meta.get("inline"):
                ok = labels_agree(e.get("label", ""), sheet.texts.get(parse_ref(meta["label_cell"]), ""))
            if ok:
                r, c = parse_ref(meta["cell"])
                return sheet, r, c, bool(meta.get("inline"))
        best = self.reader.find_label(e)
        if best is None:
            return None
        layout, cell = best
        grid, label = layout.grid(), v.plain(e.get("label", ""))
        right = grid.right_of(cell)
        while right is not None and right.text.strip().endswith((":", ":-")):
            right = grid.right_of(right)
        for nxt in (right, grid.below(cell)):
            if nxt is not None and not nxt.options and not nxt.computed and (
                    nxt.is_blank and nxt.boxed or nxt.text and prefix_score(label, nxt.text) < 70 and nxt.boxed):
                r, c = parse_ref(nxt.ref)
                return layout.sheet, r, c, False
        if INLINE_RE.match(cell.text.strip()):
            r, c = parse_ref(cell.ref)
            return layout.sheet, r, c, True  # "Work Station :" with the value after the colon
        return None

    def _field(self, e, raw):
        target = self._target(e)
        if target is None:
            return self._skip(e, "no matching cell in the workbook")
        sheet, r, c, inline = target
        value, text = self._typed(e, raw)
        if inline:
            current = sheet.texts.get((r, c), "")
            m = INLINE_RE.match(current.strip())
            head = current.strip()[:m.start("value")].rstrip() if m else current.strip()
            value = f"{head} {text}".strip() if text else head
        if not self._cell(sheet, r, c, value, text):
            return self._skip(e, "the cell is calculated by a formula")
        self.plan.written.append(_label(e))

    # ---- tick boxes ------------------------------------------------------------------------
    def _option_cells(self, e):
        """[(option, {"cell", "index"}, sheet)] for the element's options."""
        meta = e.get("excel") or {}
        sheet = self.reader._sheet(meta.get("sheet")) if meta.get("options") else None
        if sheet is not None:
            return [(o, at, sheet) for o, at in zip(e.get("options") or [], meta["options"]) if at]
        label = v.plain(e.get("label", ""))
        scored = [(prefix_score(label, it["label"]), lay, it) for lay, it in self.reader._sheet_questions() if it["label"]]
        scored = [x for x in scored if x[0] >= 78]
        if not scored:
            return []
        _, layout, item = max(scored, key=lambda x: x[0])
        out = []
        for opt in e.get("options") or []:
            hit = max(item["options"], key=lambda o: prefix_score(opt.get("text", ""), o["text"]), default=None)
            if hit is not None and prefix_score(opt.get("text", ""), hit["text"]) >= 85:
                out.append((opt, hit["cell"], layout.sheet))
        return out

    def _tick(self, sheet, ref, states, captions):
        """Set tick boxes in one cell: states {option index: checked}."""
        layout = self.reader.layout_of.get(sheet.name)
        controls = layout.controls_at(ref) if layout is not None else []
        if controls:
            for index, checked in states.items():
                ctl = next((c for c in controls if c.get("text") and captions.get(index)
                            and prefix_score(captions[index], c["text"]) >= 85), None)
                ctl = ctl or (controls[index] if index < len(controls) else controls[0])
                self.plan.controls.append((ctl, checked))
                link = ctl.get("link")
                if link and "!" not in link:
                    self.plan.cells.append(CellWrite(sheet.name, *parse_ref(link), bool(checked)))
            return True
        r, c = parse_ref(ref)
        text = sheet.texts.get((r, c), "")
        if lone_glyph(text) or glyph_options(text):
            return self._cell(sheet, r, c, set_ticks(text, states))
        # An empty box drawn with borders: a tick goes in as a mark.
        return self._cell(sheet, r, c, "✓" if any(states.values()) else "")

    def _choice(self, e, raw):
        picked = set(raw if isinstance(raw, list) else [raw])
        cells = self._option_cells(e)
        if not cells:
            return self._skip(e, "no matching tick boxes in the workbook")
        by_ref = {}
        for opt, at, sheet in cells:
            key = (sheet.name, at["cell"])
            entry = by_ref.setdefault(key, (sheet, {}, {}))
            entry[1][at.get("index", 0)] = opt.get("key") in picked or opt.get("value") in picked
            entry[2][at.get("index", 0)] = opt.get("text", "")
        for (_, ref), (sheet, states, captions) in by_ref.items():
            self._tick(sheet, ref, states, captions)
        self.plan.written.append(_label(e))

    # ---- tables ----------------------------------------------------------------------------
    def _table(self, e, raw):
        sheet, refs, _ = self.reader.table_refs(e)
        if sheet is None:
            return self._skip(e, "the table's headings were not found in the workbook")
        rows = raw if isinstance(raw, list) else []
        for r, body_row in enumerate(tables.body(e)):
            for c, cell in enumerate(body_row):
                ref = refs[r][c] if r < len(refs) and c < len(refs[r]) else None
                if not ref or not tables.is_input(cell):
                    continue
                value = rows[r][c] if r < len(rows) and isinstance(rows[r], list) and c < len(rows[r]) else ""
                kind = tables.normalize_cell(cell).get("input")
                rr, cc = parse_ref(ref)
                if kind == "check":
                    layout = self.reader.layout_of.get(sheet.name)
                    current = sheet.texts.get((rr, cc), "")
                    if layout is not None and layout.controls_at(ref):
                        self._tick(sheet, ref, {0: value == "✓"}, {})
                        continue
                    if lone_glyph(current):  # a typed box: ☑ ticked, ☒ crossed, ☐ empty
                        self._cell(sheet, rr, cc, {"✓": "☑", "✗": "☒"}.get(value, "☐"))
                        continue
                    self._cell(sheet, rr, cc, value or "")
                    continue
                typed, text = self._typed(e, value, kind)
                self._cell(sheet, rr, cc, typed, text)
        self.plan.written.append(_label(e))

    def run(self):
        for e in value_fields(self.task_data):
            name = e["field_name"]
            if name not in self.answers:
                continue
            raw = self.answers[name]
            kind = e["element"]
            if kind in NOT_WRITTEN:
                if raw:
                    self._skip(e, NOT_WRITTEN[kind])
                continue
            if kind == "Table":
                self._table(e, raw)
            elif kind in ("Checkboxes", "RadioButtons"):
                self._choice(e, raw)
            elif isinstance(raw, (list, dict)):
                self._skip(e, "this kind of value is not written to cells")
            else:
                self._field(e, raw)
        return self.plan


# ---- patchers -----------------------------------------------------------------------------

_ROW_RE = re.compile(r"<row\b[^>]*?(?:/>|>.*?</row>)", re.S)
_CELL_RE = re.compile(r"<c\b[^>]*?(?:/>|>.*?</c>)", re.S)
_ATTR_RE = re.compile(r'([\w:]+)="([^"]*)"')
_XML_INVALID = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DATE_FORMAT_IDS = {14, 15, 16, 17, 22, 27, 28, 29, 30, 31, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58}


def _col_letters(c):
    s, n = "", c + 1
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _serial(value, date1904):
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    if not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    delta = value - base
    return delta.days + delta.seconds / 86400.0


class _SheetXml:
    """The <sheetData> of one worksheet part, editable cell by cell; the rest stays byte-identical."""

    def __init__(self, xml):
        self.xml = xml
        m = re.search(r"<sheetData\s*/>|<sheetData\b[^>]*>(.*?)</sheetData>", xml, re.S)
        if m is None:
            raise ValueError("worksheet without sheetData")
        self.span = m.span()
        self.rows = {}  # row number -> [open tag attrs dict, {col: cell xml}]
        next_row = 1
        for row_xml in _ROW_RE.findall(m.group(1) or ""):
            head = re.match(r"<row\b([^>]*?)/?>", row_xml).group(1)
            attrs = dict(_ATTR_RE.findall(head))
            rnum = int(attrs.get("r", next_row))
            attrs["r"] = str(rnum)
            next_row = rnum + 1
            cells, next_col = {}, 0
            body = row_xml[len(re.match(r"<row\b[^>]*?>", row_xml).group(0)):] if not row_xml.endswith("/>") else ""
            for cell_xml in _CELL_RE.findall(body):
                cattrs = dict(_ATTR_RE.findall(re.match(r"<c\b([^>]*?)/?>", cell_xml).group(1)))
                if "r" in cattrs:
                    col = parse_ref(cattrs["r"])[1]
                else:
                    col = next_col
                    cell_xml = cell_xml.replace("<c", f'<c r="{_col_letters(col)}{rnum}"', 1)
                cells[col] = cell_xml
                next_col = col + 1
            self.rows[rnum] = [attrs, cells]

    def style(self, r, c):
        row = self.rows.get(r + 1)
        xml = row[1].get(c) if row else None
        if xml is None:
            return None
        m = re.search(r'\bs="(\d+)"', xml.split(">", 1)[0])
        return int(m.group(1)) if m else None

    def set(self, r, c, value):
        rnum, ref = r + 1, f"{_col_letters(c)}{r + 1}"
        row = self.rows.setdefault(rnum, [{"r": str(rnum)}, {}])
        row[0].pop("spans", None)  # a hint Excel recomputes; it may no longer cover the row's cells
        style = self.style(r, c)
        s = f' s="{style}"' if style is not None else ""
        if value is None:
            xml = f'<c r="{ref}"{s}/>'
        elif isinstance(value, bool):
            xml = f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
        elif isinstance(value, (int, float)):
            xml = f'<c r="{ref}"{s}><v>{value!r}</v></c>'
        else:
            text = _XML_INVALID.sub("", str(value))
            xml = f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'
        row[1][c] = xml

    def to_xml(self):
        parts = []
        for rnum in sorted(self.rows):
            attrs, cells = self.rows[rnum]
            head = " ".join(f'{k}="{val}"' for k, val in attrs.items())
            parts.append(f"<row {head}>" + "".join(cells[c] for c in sorted(cells)) + "</row>")
        return self.xml[:self.span[0]] + "<sheetData>" + "".join(parts) + "</sheetData>" + self.xml[self.span[1]:]


class XlsxPatcher:
    def __init__(self, data):
        self.zf = zipfile.ZipFile(io.BytesIO(data))
        self.pkg = Package(self.zf)
        self.changed = {}   # part -> new bytes
        self.sheets = {}    # sheet name -> _SheetXml
        wb_xml = self.zf.read("xl/workbook.xml").decode("utf-8")
        self.date1904 = bool(re.search(r'<workbookPr\b[^>]*\bdate1904="(1|true)"', wb_xml))
        self.date_styles = self._date_styles()

    def _date_styles(self):
        if "xl/styles.xml" not in self.pkg.names:
            return set()
        xml = self.zf.read("xl/styles.xml").decode("utf-8")
        custom = {int(i): code for i, code in re.findall(r'<numFmt\b[^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]*)"', xml)}
        m = re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", xml, re.S)
        out = set()
        for index, xf in enumerate(re.findall(r"<xf\b[^>]*>", m.group(1) if m else "")):
            fid = re.search(r'numFmtId="(\d+)"', xf)
            fid = int(fid.group(1)) if fid else 0
            code = custom.get(fid) or BUILTIN_FORMATS.get(fid, "")
            if fid in DATE_FORMAT_IDS or (code and is_date_format(code.replace("&quot;", '"'))):
                out.add(index)
        return out

    def _sheet(self, name):
        if name not in self.sheets:
            part = self.pkg.sheet_parts[name]
            self.sheets[name] = _SheetXml(self.zf.read(part).decode("utf-8"))
        return self.sheets[name]

    def set_cell(self, w):
        sheet = self._sheet(w.sheet)
        value = w.value
        if isinstance(value, (date, datetime)):
            value = _serial(value, self.date1904) if sheet.style(w.row, w.col) in self.date_styles else (w.text or value.isoformat())
        sheet.set(w.row, w.col, value)

    def set_control(self, ctl, checked):
        vml = ctl.get("vml")
        if vml and ctl.get("spid"):
            text = self.changed.get(vml, self.zf.read(vml)).decode("utf-8", "ignore")
            m = re.search(rf'<v:shape\b[^>]*o:spid="_x0000_s{ctl["spid"]}".*?</v:shape>', text, re.S | re.I)
            if m:
                shape = re.sub(r"\s*<x:Checked>.*?</x:Checked>", "", m.group(0), flags=re.S | re.I)
                if checked:
                    shape = re.sub(r"</x:ClientData>", "<x:Checked>1</x:Checked></x:ClientData>", shape, count=1, flags=re.I)
                text = text[:m.start()] + shape + text[m.end():]
                self.changed[vml] = text.encode("utf-8")
        prop = ctl.get("ctrl_prop")
        if prop:
            xml = self.changed.get(prop, self.zf.read(prop)).decode("utf-8")
            xml = re.sub(r'\s+checked="\w+"', "", xml)
            if checked:
                xml = xml.replace("<formControlPr", '<formControlPr checked="Checked"', 1)
            self.changed[prop] = xml.encode("utf-8")

    def save(self):
        for name, sheet in self.sheets.items():
            self.changed[self.pkg.sheet_parts[name]] = sheet.to_xml().encode("utf-8")
        wb_xml = self.zf.read("xl/workbook.xml").decode("utf-8")
        # Formulas recalculate on open, so totals reflect the values written.
        if re.search(r"<calcPr\b", wb_xml):
            wb_xml = re.sub(r'(<calcPr\b[^>]*?)\s*fullCalcOnLoad="\w+"', r"\1", wb_xml)
            wb_xml = re.sub(r"<calcPr\b", '<calcPr fullCalcOnLoad="1"', wb_xml, count=1)
        else:
            m = re.search(r"<(oleSize|customWorkbookViews|pivotCaches|smartTagPr|smartTagTypes|webPublishing|fileRecoveryPr|webPublishObjects|extLst)\b|</workbook>", wb_xml)
            wb_xml = wb_xml[:m.start()] + '<calcPr fullCalcOnLoad="1"/>' + wb_xml[m.start():]
        self.changed["xl/workbook.xml"] = wb_xml.encode("utf-8")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in self.zf.infolist():
                dst.writestr(info, self.changed.get(info.filename, self.zf.read(info.filename)))
        return out.getvalue()


class XlsPatcher:
    def __init__(self, data):
        import xlrd
        from xlutils.filter import XLRDReader, XLWTWriter, process

        self.rb = xlrd.open_workbook(file_contents=data, formatting_info=True)
        writer = XLWTWriter()
        process(XLRDReader(self.rb, "form.xls"), writer)
        self.wb, self.styles = writer.output[0][1], writer.style_list
        self.names = [s.name for s in self.rb.sheets()]

    def set_cell(self, w):
        import xlwt

        rs = self.rb.sheet_by_name(w.sheet)
        ws = self.wb.get_sheet(self.names.index(w.sheet))
        xf = rs.cell_xf_index(w.row, w.col) if w.row < rs.nrows and w.col < rs.ncols else None
        style = self.styles[xf] if xf is not None else xlwt.Style.default_style
        value = w.value
        if isinstance(value, (date, datetime)):
            fmt = self.rb.format_map.get(self.rb.xf_list[xf].format_key) if xf is not None else None
            if fmt is not None and fmt.type == 1:  # a date-formatted cell
                value = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
            else:
                value = w.text or value.isoformat()
        if value is None:
            ws.write(w.row, w.col, "", style)
        else:
            ws.write(w.row, w.col, value, style)

    def set_control(self, ctl, checked):  # .xls Form Controls are not read, so never planned
        pass

    def save(self):
        out = io.BytesIO()
        self.wb.save(out)
        return out.getvalue()


def write_workbook(data, task_data, answers):
    """-> (bytes, plan). The workbook with the form's values written in."""
    sheets = read_workbook(data)
    plan = WritePlanner(task_data, answers, sheets).run()
    patcher = XlsxPatcher(data) if is_xlsx(data) else XlsPatcher(data) if is_xls(data) else None
    for w in plan.cells:
        patcher.set_cell(w)
    for ctl, checked in plan.controls:
        patcher.set_control(ctl, checked)
    return patcher.save(), plan

