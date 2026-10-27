"""Sheet -> CellGrid with page geometry.

Column widths (characters) and row heights (points) become pixel boxes as Excel draws them,
so a template made from a workbook also carries positions that can be matched against a
scanned print-out of the same form.

A cell is a place to fill in when it is drawn as a box (borders) or styled as one: a
background fill, unlocked for editing, or restricted by data validation. Data validation and
number formats also say what kind of input it is (drop-down list, date, number).
"""
import bisect
from collections import Counter
from statistics import median

from openpyxl.styles.numbers import is_date_format

from ... import geometry as g
from ...cellgrid import CellGrid, GridCell
from .choices import glyph_options, is_ticked, kind_of, lone_glyph
from .workbook import cell_ref, is_number_format, parse_ref

STYLE_REACH = 3  # styled input cells this many rows/cols past the last text still belong to the form


def col_px(width_chars):
    return 0 if width_chars <= 0 else int(round(width_chars * 7 + 5))


def row_px(height_pt):
    return height_pt * 96.0 / 72.0


class SheetLayout:
    def __init__(self, sheet):
        self.sheet = sheet
        self._input_fill_keys, self._use_unlocked = self._style_signals()
        r0, r1, c0, c1 = sheet.print_area or self._used_range()
        self.rows = [r for r in range(r0, r1) if r not in sheet.hidden_rows and sheet.row_heights.get(r, 1) > 0]
        self.cols = [c for c in range(c0, c1) if c not in sheet.hidden_cols and sheet.col_widths.get(c, 1) > 0]
        self.row_index = {r: i for i, r in enumerate(self.rows)}
        self.col_index = {c: i for i, c in enumerate(self.cols)}
        self.xs = [0.0]
        for c in self.cols:
            self.xs.append(self.xs[-1] + col_px(sheet.col_widths.get(c, sheet.default_col_width)))
        self.ys = [0.0]
        for r in self.rows:
            self.ys.append(self.ys[-1] + row_px(sheet.row_heights.get(r, sheet.default_row_height)))
        heights = [self.ys[i + 1] - self.ys[i] for i in range(len(self.rows))]
        self.line_height = median(heights) if heights else 20.0
        self.styled = self._styled_cells()
        self._grid = None
        self._controls_at = {}

    @property
    def width(self):
        return max(1.0, self.xs[-1])

    @property
    def height(self):
        return max(1.0, self.ys[-1])

    # ---- input styling ---------------------------------------------------------------------
    def _style_signals(self):
        """Which fills and whether unlocking mark inputs on this sheet.

        A colour that most labels share is the sheet's background, not an input marker; when
        most labels are unlocked too, the author did not use locking to mark inputs.
        """
        sh = self.sheet
        texts = [k for k, t in sh.texts.items() if t.strip()]
        common = Counter(sh.fills.get(k) for k in texts).most_common(1)
        background = common[0][0] if common and common[0][0] and common[0][1] > 0.5 * len(texts) else None
        fill_keys = {key for key in sh.fills.values() if key != background}
        unlocked_labels = sum(1 for k in texts if k in sh.unlocked)
        use_unlocked = bool(sh.unlocked) and unlocked_labels <= 0.5 * max(1, len(texts))
        return fill_keys, use_unlocked

    def _style_keys(self, r_end, c_end):
        sh = self.sheet
        keys = {k for k, key in sh.fills.items() if key in self._input_fill_keys and k[0] < r_end and k[1] < c_end}
        if self._use_unlocked:
            keys |= {k for k in sh.unlocked if k[0] < r_end and k[1] < c_end}
        for dv in sh.validations:
            for r0, r1, c0, c1 in dv.ranges:
                for r in range(r0, min(r1 or r_end, r_end)):
                    for c in range(c0, min(c1 or c_end, c_end)):
                        keys.add((r, c))
        return keys

    def _styled_cells(self):
        """{(r, c): reason} for blank-able cells styled as inputs inside the laid-out area."""
        if not self.rows or not self.cols:
            return {}
        sh = self.sheet
        keys = self._style_keys(self.rows[-1] + 1, self.cols[-1] + 1)
        out = {}
        for k in keys:
            if k[0] not in self.row_index or k[1] not in self.col_index:
                continue
            if sh.validation_at(*k) is not None:
                out[k] = "validation"
            elif self._use_unlocked and k in sh.unlocked:
                out[k] = "unlocked"
            else:
                out[k] = "fill"
        return out

    def _hint(self, r, c):
        """What kind of input the cell is, from data validation (strong) or its number format (weak)."""
        sh = self.sheet
        dv = sh.validation_at(r, c)
        if dv is not None:
            if dv.kind == "list" and dv.options:
                return {"element": "Dropdown", "options": list(dv.options), "strong": True}
            if dv.kind == "date":
                return {"element": "DatePicker", "strong": True}
            if dv.kind in ("whole", "decimal"):
                return {"element": "NumberInput", "strong": True}
        fmt = sh.number_formats.get((r, c))
        if fmt is None and (r, c) in sh.values and hasattr(sh.values[(r, c)], "year"):
            return {"element": "DatePicker", "strong": False}
        if fmt:
            if is_date_format(fmt):
                return {"element": "DatePicker", "strong": False}
            if is_number_format(fmt):
                return {"element": "NumberInput", "strong": False}
        return None

    # ---- geometry --------------------------------------------------------------------------
    def _used_range(self):
        sh = self.sheet
        keys = list(sh.texts) + list(sh.borders) + list(sh.formulas)
        keys += [(r1 - 1, c1 - 1) for _, r1, _, c1 in sh.merged]
        if not keys:
            return 0, 0, 0, 0
        r1, c1 = max(k[0] for k in keys) + 1, max(k[1] for k in keys) + 1
        # Styled input cells just past the text (a shaded box under the last label) are part
        # of the form; formatting dragged down thousands of rows is not.
        extra = self._style_keys(r1 + STYLE_REACH, c1 + STYLE_REACH)
        if extra:
            r1 = max(r1, max(k[0] for k in extra) + 1)
            c1 = max(c1, max(k[1] for k in extra) + 1)
        return 0, r1, 0, c1

    def _visible(self, r0, r1, c0, c1):
        rows = [r for r in range(r0, r1) if r in self.row_index]
        cols = [c for c in range(c0, c1) if c in self.col_index]
        return rows, cols

    def _bbox(self, rows, cols):
        i0, i1 = self.row_index[rows[0]], self.row_index[rows[-1]] + 1
        j0, j1 = self.col_index[cols[0]], self.col_index[cols[-1]] + 1
        return [self.xs[j0], self.ys[i0], self.xs[j1], self.ys[i1]]

    def _edges(self, r0, r1, c0, c1):
        b = self.sheet.borders
        has = lambda rc, side: side in b.get(rc, ())  # noqa: E731
        top = any(has((r0, c), "t") or has((r0 - 1, c), "b") for c in range(c0, c1))
        bottom = any(has((r1 - 1, c), "b") or has((r1, c), "t") for c in range(c0, c1))
        left = any(has((r, c0), "l") or has((r, c0 - 1), "r") for r in range(r0, r1))
        right = any(has((r, c1 - 1), "r") or has((r, c1), "l") for r in range(r0, r1))
        return top, bottom, left, right

    def _text(self, r, c):
        """Displayed text; a formula Excel never calculated (no cached value) shows as the formula."""
        sh = self.sheet
        text = sh.texts.get((r, c), "")
        if not text.strip() and (r, c) in sh.formulas:
            return sh.formulas[(r, c)]
        return text

    def _control_links(self):
        out = set()
        for ctl in self.sheet.controls:
            link = ctl.get("link")
            if link and "!" not in link:
                try:
                    out.add(parse_ref(link))
                except ValueError:
                    pass
        return out

    def _labelled_row(self, rg):
        """A label sits right beside this range: it is a box of its own ("Phone | [shaded]")."""
        r, c0 = rg[0], rg[2]
        return any(self._text(r, c).strip() for c in range(max(0, c0 - 2), c0))

    def _visual_boxes(self):
        """Sheet ranges as they look on paper.

        Excel forms often leave neighbouring cells unmerged but draw no border between them;
        printed, they are one box. A blank cell joins its neighbour when the two share the same
        outer borders and nothing is drawn between them, or when both are blank and shaded alike.
        """
        sh = self.sheet
        ranges, covered = [], set()
        for r0, r1, c0, c1 in sh.merged:
            ranges.append([r0, r1, c0, c1])
            covered.update((r, c) for r in range(r0, r1) for c in range(c0, c1))
        links = self._control_links()
        for (r, c) in sorted(set(sh.texts) | set(sh.borders) | set(sh.formulas) | set(self.styled)):
            if (r, c) in covered or (r, c) in links and not sh.borders.get((r, c)):
                continue  # a Form Control's linked cell holds its state, it is not part of the form
            if not self._text(r, c).strip() and not sh.borders.get((r, c)) and (r, c) not in self.styled:
                continue
            ranges.append([r, r + 1, c, c + 1])
        blank = lambda rg: not self._text(rg[0], rg[2]).strip()  # noqa: E731
        pictured = {(p["row"], p["col"]) for p in sh.images}
        self._spill(ranges, blank, pictured | links)
        fill = lambda rg: sh.fills.get((rg[0], rg[2])) if (rg[0], rg[2]) in self.styled else None  # noqa: E731
        changed = True
        while changed:
            changed = False
            by_start = {(rg[0], rg[2]): rg for rg in ranges}
            for rg in sorted(ranges, key=lambda x: (x[0], x[2])):
                r0, r1, c0, c1 = rg
                if (r0, c0) in pictured:
                    continue
                top, bottom, left, right = self._edges(r0, r1, c0, c1)
                # A shaded input box spanning several cells; in a filled copy its first cell holds
                # the value (it is still the input when a label sits to its left).
                shaded = fill(rg) if blank(rg) or self._labelled_row(rg) else None
                nb = by_start.get((r0, c1))  # neighbour to the right
                if (nb is not None and nb is not rg and nb[1] == r1 and blank(nb) and (nb[0], nb[2]) not in pictured
                        and not right and (self._edges(*nb)[:2] == (top, bottom) and (top or bottom)
                                           or shaded and fill(nb) == shaded)):
                    rg[3] = nb[3]
                    ranges.remove(nb)
                    changed = True
                    break
                nb = by_start.get((r1, c0))  # neighbour below
                if (nb is not None and nb is not rg and nb[3] == c1 and blank(nb) and (nb[0], nb[2]) not in pictured
                        and not bottom and (self._edges(*nb)[2:] == (left, right) and (left or right)
                                            or shaded and fill(nb) == shaded and not self._labelled_row(nb))):
                    rg[1] = nb[1]
                    ranges.remove(nb)
                    changed = True
                    break
        return ranges

    # Average width of a character, as a share of the font size, for text Excel lays out
    # in its default proportional fonts (Calibri, Arial): 11 pt text runs about 6 px a character.
    CHAR_WIDTH = 0.55

    def _spill(self, ranges, blank, fixed):
        """A label longer than its cell runs over the empty cells to its right, as Excel draws it.

        "Requester Sign:" in a narrow column A covers B on paper (whatever borders B has), so
        B is part of the label, not a box to write in - the scan of the same form reads it so.
        Only single-line text in a row of normal height spills; it covers the blank cells its
        width reaches and stops at the first cell holding anything.
        """
        by_start = {(rg[0], rg[2]): rg for rg in ranges}
        for rg in sorted(ranges, key=lambda x: (x[0], x[2])):
            r0, r1, c0, c1 = rg
            text = self._text(r0, c0).strip()
            if (not text or "\n" in text or r1 - r0 != 1 or c1 - c0 != 1 or rg not in ranges
                    or r0 not in self.row_index or c0 not in self.col_index):
                continue
            i = self.row_index[r0]
            size = (self.sheet.fonts.get((r0, c0)) or (11.0, False))[0] or 11.0
            if self.ys[i + 1] - self.ys[i] > 2.2 * size:
                continue  # a tall row: the text wraps inside its cell
            reach = len(text) * size * self.CHAR_WIDTH
            j = self.col_index[c0]
            right = self.xs[j + 1]
            while reach > right - self.xs[j] + 4:
                nb = by_start.get((r0, rg[3]))
                if (nb is None or nb not in ranges or nb[1] != r1 or not blank(nb) or (nb[0], nb[2]) in fixed
                        or nb[3] - nb[2] != 1 or nb[2] not in self.col_index):
                    break
                rg[3] = nb[3]
                ranges.remove(nb)
                right = self.xs[self.col_index[nb[2]] + 1]

    def _is_input_style(self, r0, r1, c0, c1, bbox):
        """Styled (not drawn) as an input. A thin coloured strip is decoration, not a box."""
        reason = self.styled.get((r0, c0))
        if reason is None:
            return False
        if reason == "fill" and bbox[3] - bbox[1] < 0.6 * self.line_height:
            return False
        return True

    def _control_cell(self, ctl):
        """Sheet (row, col) under the tick box of a Form Control (its left edge, vertical middle)."""
        c0, dx0, r0, dy0, c1, dx1, r1, dy1 = ctl["anchor"]
        if c0 not in self.col_index or r0 not in self.row_index:
            return None
        x = self.xs[self.col_index[c0]] + dx0 + 6
        y0 = self.ys[self.row_index[r0]] + dy0
        y1 = self.ys[self.row_index[r1]] + dy1 if r1 in self.row_index else y0 + 16
        y = (y0 + max(y0, y1)) / 2
        i = min(len(self.rows) - 1, max(0, bisect.bisect_right(self.ys, y) - 1))
        j = min(len(self.cols) - 1, max(0, bisect.bisect_right(self.xs, x) - 1))
        return self.rows[i], self.cols[j]

    def grid(self):
        """CellGrid of the visible print area; refs are the original sheet addresses."""
        if self._grid is not None:
            return self._grid
        sh = self.sheet
        cells = []
        for r0, r1, c0, c1 in self._visual_boxes():
            rows, cols = self._visible(r0, r1, c0, c1)
            if not rows or not cols:
                continue
            text = self._text(r0, c0).strip()
            size, bold = sh.fonts.get((r0, c0), (0.0, False))
            top, bottom, left, right = self._edges(r0, r1, c0, c1)
            bbox = self._bbox(rows, cols)
            cell = GridCell(
                row=self.row_index[rows[0]], col=self.col_index[cols[0]], rowspan=len(rows), colspan=len(cols),
                text=text, boxed=(top + bottom + left + right) >= 2 or bottom or self._is_input_style(r0, r1, c0, c1, bbox),
                bbox=bbox, ref=cell_ref(r0, c0, r1, c1), size=size if text else 0.0, bold=bold,
                hint=self._hint(r0, c0), computed=(r0, c0) in sh.formulas,
            )
            glyph = lone_glyph(text)
            if glyph:
                # A lone "☐" is a tick box to fill in; its caption sits in a neighbouring cell.
                cell.text, cell.size, cell.boxed = "", 0.0, True
                cell.options = [{"text": "", "checked": is_ticked(glyph), "kind": kind_of(glyph), "source": "glyph"}]
            else:
                parsed = glyph_options(text)
                if parsed:
                    cell.option_prefix = parsed[0]
                    cell.options = [{**o, "source": "glyph"} for o in parsed[1]]
            cells.append(cell)
        grid = CellGrid(cells, len(self.rows), len(self.cols))
        for pic in sh.images:
            r, c = pic["row"], pic["col"]
            if r not in self.row_index or c not in self.col_index:
                continue
            cell = grid.at(self.row_index[r], self.col_index[c])
            if cell is None:
                cell = GridCell(row=self.row_index[r], col=self.col_index[c], boxed=False,
                                bbox=self._bbox([r], [c]), ref=cell_ref(r, c))
                cells.append(cell)
                grid = CellGrid(cells, len(self.rows), len(self.cols))
            cell.image = {"src": pic["src"], "width": pic.get("width"), "height": pic.get("height")}
        for ctl in sh.controls:
            at = self._control_cell(ctl)
            if at is None:
                continue
            cell = grid.at(self.row_index[at[0]], self.col_index[at[1]])
            if cell is None:
                cell = GridCell(row=self.row_index[at[0]], col=self.col_index[at[1]], boxed=False,
                                bbox=self._bbox([at[0]], [at[1]]), ref=cell_ref(*at))
                cells.append(cell)
                grid = CellGrid(cells, len(self.rows), len(self.cols))
            cell.options.append({"text": ctl["text"], "checked": ctl["checked"], "kind": ctl["kind"], "source": "control"})
            self._controls_at.setdefault(cell.ref.split(":")[0], []).append(ctl)
        self._grid = grid
        return grid

    def controls_at(self, ref):
        """Form Controls placed in the grid cell whose address starts at `ref`."""
        self.grid()
        return self._controls_at.get((ref or "").split(":")[0], [])

    @property
    def text_size(self):
        sizes = [c.size for c in self.grid().cells if c.text and c.size]
        return median(sizes) if sizes else 11.0

    @staticmethod
    def _text_box(cell):
        """Where the text sits in its cell: as tall as its font (not the whole merged cell),
        vertically centred, so the digital copy shows it at its real size."""
        x0, y0, x1, y1 = cell.bbox
        font_px = (cell.size or 11.0) * 96.0 / 72.0
        per_line = max(1.0, (x1 - x0) / (0.52 * font_px))  # characters that fit across the cell
        lines = sum(max(1, -(-len(part) // int(per_line))) for part in cell.text.split("\n"))
        text_h = min(y1 - y0, lines * font_px * 1.3)
        top = y0 + ((y1 - y0) - text_h) / 2
        return [x0, top, x1, top + text_h]

    def document_page(self, index):
        """Digitized view of the sheet in the same shape as an OCR'd page."""
        grid = self.grid()
        w, h = self.width, self.height
        # "size": font height as a fraction of the page height (the viewer draws text at its real size).
        lines = [{"text": c.text, "conf": 1.0, "bbox": g.normalize(self._text_box(c), w, h),
                  "size": round((c.size or 11.0) * 96.0 / 72.0 / h, 5)} for c in grid.cells if c.text]
        boxed = [c for c in grid.cells if c.boxed]
        tables = []
        if boxed:
            tables.append({
                "bbox": g.normalize(g.union([c.bbox for c in boxed]), w, h),
                "n_rows": grid.n_rows,
                "n_cols": grid.n_cols,
                "cells": [{"row": c.row, "col": c.col, "rowspan": c.rowspan, "colspan": c.colspan,
                           "bbox": g.normalize(c.bbox, w, h), "text": c.text} for c in boxed],
            })
        # Tick boxes (typed glyphs and Form Controls) show as boxes, ticked or not.
        checkboxes = []
        for c in grid.cells:
            if not c.options or not c.bbox or c.text:
                continue  # "☐ Yes ☐ No" typed in a cell is shown by its text
            side = max(6.0, min(c.bbox[3] - c.bbox[1] - 4, 13.0))
            y0, x = (c.bbox[1] + c.bbox[3] - side) / 2, c.bbox[0] + 3
            for o in c.options:
                checkboxes.append({"bbox": g.normalize([x, y0, x + side, y0 + side], w, h),
                                   "checked": bool(o["checked"]), "kind": o["kind"]})
                x += side + 3
                if o["text"]:  # a Form Control's caption is not cell text
                    end = min(c.bbox[2], x + 7 * len(o["text"]) + 4)
                    lines.append({"text": o["text"], "conf": 1.0, "bbox": g.normalize([x, c.bbox[1], end, c.bbox[3]], w, h),
                                  "size": round(11.0 * 96.0 / 72.0 / h, 5)})
                    x = end + 4
        rows = {}
        for c in grid.cells:
            if c.text:
                rows.setdefault(c.row, []).append(c)
        text = "\n".join("    ".join(" ".join(x.text.split()) for x in sorted(rows[r], key=lambda x: x.col)) for r in sorted(rows))
        return {"index": index, "width": w, "height": h, "image": None, "sheet": self.sheet.name,
                "lines": lines, "checkboxes": checkboxes, "tables": tables, "text": text}
