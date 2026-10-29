"""Requirement B: convert analysed pages into an editable form-builder template (task_data).

Every generated element keeps an `ocr` block (page, page size, normalised boxes of
its label and value area). Requirement A uses those boxes to read filled scans.
"""
import re

from . import elements as el
from . import headings
from . import labels
from . import title
from . import tables
from . import textgrid
from . import geometry as g
from .cellgrid import CellGrid, GridCell
from .document import sub_line
from .grid_interpreter import DOC_CONTROL_RE, NOTE_RE, GridInterpreter
from .values import clean_label

COLON_RE = re.compile(r"^(?P<label>[^:：]{1,60}?)\s*[:：]\s*(?P<rest>.*)$")
MAX_LABEL_WORDS = 7
MAX_INLINE_VALUE_WORDS = 12





def infer_type(label, zone_height, line_height):
    t = label.lower()
    if "e-mail" in t or "email" in t:
        return "EmailInput"
    if re.search(r"\b(phone|mobile|tel|telephone|cell|contact no|contact number)\b", t):
        return "PhoneNumber"
    if re.search(r"\bsign(ature|ed)?\b", t):
        return "Signature"
    if re.search(r"\b(date|dob|d\.o\.b)\b", t):
        return "DatePicker"
    if re.search(r"\b(age|qty|quantity|amount|total|salary|income|no\. of|number of)\b", t):
        return "NumberInput"
    if zone_height > 2.2 * line_height or re.search(r"\b(address|remarks|comments|description|notes|details)\b", t):
        return "TextArea"
    return "TextInput"


class PageTemplate:
    def __init__(self, page, page_index, filled=False):
        self.filled = filled  # a filled-in copy: writing on lines / in boxes is a value
        self.page = page
        self.index = page_index
        self.W, self.H = page["width"], page["height"]
        self.lh = page["line_height"] or 0.012 * self.H
        self.lines = page["lines"]
        self.used = set()
        self.items = []
        self.zones = []
        right = [l["bbox"][2] for l in self.lines]
        right += [s["bbox"][2] for s in page["boxes"] + page["grids"] + page["hlines"]]
        self.content_right = max(right) if right else 0.95 * self.W

    # ---- helpers -------------------------------------------------------------------
    def free(self):
        return [i for i in range(len(self.lines)) if i not in self.used]

    def bbox(self, i):
        return self.lines[i]["bbox"]

    def text(self, i):
        return self.lines[i]["text"].strip()

    def _left_label(self, zone, band=None):
        band = band or zone
        best, best_d = None, None
        for i in self.free():
            b = self.bbox(i)
            d = zone[0] - b[2]
            if d < -0.01 * self.W or d > 0.35 * self.W:
                continue
            if g.v_overlap(b, band) < 0.4:
                continue
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _above_label(self, zone):
        best, best_d = None, None
        for i in self.free():
            b = self.bbox(i)
            d = zone[1] - b[3]
            if d < -0.25 * self.lh or d > 1.6 * self.lh:
                continue
            if g.h_overlap(b, zone) < 0.3 and abs(b[0] - zone[0]) > 0.05 * self.W:
                continue
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _below_label(self, zone):
        best, best_d = None, None
        for i in self.free():
            b = self.bbox(i)
            d = b[1] - zone[3]
            if d < -0.25 * self.lh or d > 1.2 * self.lh or g.h_overlap(b, zone) < 0.5:
                continue
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    def _right_limit(self, b):
        limit = self.content_right
        others = [self.bbox(i) for i in range(len(self.lines))]
        others += self.zones + [t["bbox"] for t in self.page["checkboxes"]]
        for o in others:
            if o[0] > b[2] + 1 and g.v_overlap(o, b) >= 0.4:
                limit = min(limit, o[0] - 0.005 * self.W)
        return limit

    def _overlaps_zone(self, b):
        return any(g.v_overlap(b, z) > 0.5 and g.h_overlap(b, z) > 0.5 for z in self.zones)

    def _add_field(self, label_idx, zone, label_text=None, kind_hint=None, comb=False):
        label_bbox = self.bbox(label_idx) if label_idx is not None else None
        if label_text is None:
            label_text = clean_label(self.text(label_idx)) if label_idx is not None else ""
        if label_idx is not None:
            self.used.add(label_idx)
        boxes = [zone] + ([label_bbox] if label_bbox else [])
        self.zones.append(zone)
        self.items.append({
            "kind": "field",
            "label": label_text,
            "label_bbox": label_bbox,
            "zone": zone,
            "element": kind_hint,
            "comb": comb,
            "bbox": g.union(boxes),
        })

    # ---- 1. checkbox / radio groups ---------------------------------------------
    def choices(self):
        ticks = sorted(self.page["checkboxes"], key=lambda t: (t["bbox"][1], t["bbox"][0]))
        if not ticks:
            return
        options = []
        for t in ticks:
            tb, tw = t["bbox"], g.width(t["bbox"])
            best, best_d = None, None
            for i in self.free():
                b = self.bbox(i)
                if g.v_overlap(b, tb) < 0.3:
                    continue
                d = b[0] - tb[2]
                if -2 <= d <= 3 * tw and (best_d is None or d < best_d):
                    best, best_d = i, d
            if best is None:
                for i in self.free():
                    b = self.bbox(i)
                    d = tb[0] - b[2]
                    if g.v_overlap(b, tb) >= 0.3 and -2 <= d <= 3 * tw and (best_d is None or d < best_d):
                        best, best_d = i, d
            if best is not None:
                self.used.add(best)
            options.append(best)

        parent = list(range(len(ticks)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def has_question(i):
            # A free (non-option) text to the left on the same row starts a new question.
            tb = ticks[i]["bbox"]
            return any(
                g.v_overlap(self.bbox(j), tb) >= 0.4 and 0 <= tb[0] - self.bbox(j)[2] <= 0.35 * self.W
                for j in self.free()
            )

        starts = [has_question(i) for i in range(len(ticks))]
        for a in range(len(ticks)):
            for b in range(a + 1, len(ticks)):
                if ticks[a]["kind"] != ticks[b]["kind"]:
                    continue
                ta, tb = ticks[a]["bbox"], ticks[b]["bbox"]
                same_row = g.v_overlap(ta, tb) >= 0.5 and abs(tb[0] - ta[2]) <= 0.3 * self.W
                stacked = (
                    abs(ta[0] - tb[0]) <= 1.5 * g.width(ta)
                    and 0 <= tb[1] - ta[3] <= 2.5 * self.lh
                    and not starts[b]
                )
                if same_row or stacked:
                    parent[find(a)] = find(b)
        groups = {}
        for i in range(len(ticks)):
            groups.setdefault(find(i), []).append(i)

        for members in sorted(groups.values(), key=lambda m: (ticks[m[0]]["bbox"][1], ticks[m[0]]["bbox"][0])):
            members.sort(key=lambda i: (ticks[i]["bbox"][1], ticks[i]["bbox"][0]))
            first = ticks[members[0]]["bbox"]
            opts = []
            for i in members:
                li = options[i]
                text = self.text(li) if li is not None else f"Option {len(opts) + 1}"
                opts.append({"text": text, "box": ticks[i]["bbox"], "text_bbox": self.bbox(li) if li is not None else None})
            all_boxes = [o["box"] for o in opts] + [o["text_bbox"] for o in opts if o["text_bbox"]]
            group_bbox = g.union(all_boxes)
            q = self._left_label(first, band=first)
            if q is None:
                q = self._above_label(group_bbox)
            label = clean_label(self.text(q)) if q is not None else ""
            label_bbox = self.bbox(q) if q is not None else None
            if q is not None:
                self.used.add(q)
            radios = sum(1 for i in members if ticks[i]["kind"] == "radio")
            element = "RadioButtons" if radios > len(members) / 2 else "Checkboxes"
            self.items.append({
                "kind": "choice",
                "element": element,
                "label": label,
                "label_bbox": label_bbox,
                "options": opts,
                "bbox": g.union(all_boxes + ([label_bbox] if label_bbox else [])),
            })

    # ---- 2. ruled grids: header blocks, key/value grids and data tables ----------------
    def grids(self):
        ticks = self.page["checkboxes"]
        for grid in self.page["grids"]:
            cells = []
            free = self.free()
            for c in grid["cells"]:
                idx = [i for i in free if g.contains_point(c["bbox"], g.center(self.bbox(i)))]
                idx.sort(key=lambda i: (self.bbox(i)[1], self.bbox(i)[0]))
                rows = []
                for i in idx:
                    if rows and g.v_overlap(self.bbox(rows[-1][-1]), self.bbox(i)) >= 0.5:
                        rows[-1].append(i)
                    else:
                        rows.append([i])
                text = "\n".join(" ".join(self.text(i) for i in sorted(r, key=lambda i: self.bbox(i)[0])) for r in rows)
                heights = sorted(g.height(self.bbox(i)) for i in idx)
                cells.append(GridCell(
                    row=c["row"], col=c["col"], rowspan=c["rowspan"], colspan=c["colspan"], text=text,
                    bbox=c["bbox"], size=heights[len(heights) // 2] if heights else 0.0, lines=idx,
                    occupied=any(g.inside(t["bbox"], c["bbox"]) for t in ticks),
                    text_bbox=g.union([self.bbox(i) for i in idx]) if idx else None,
                ))
            for c in cells:
                self.used.update(c.lines)  # before the caption search below, so it only sees text outside
            interpreter = GridInterpreter(CellGrid(cells, grid["n_rows"], grid["n_cols"]), text_size=self.lh, filled=self.filled)
            for item in interpreter.interpret():
                if item["kind"] == "table" and not item["label"]:
                    cap = self._above_label(item["bbox"])
                    if cap is not None and len(self.text(cap).split()) <= 10:
                        item["label"], item["label_bbox"] = clean_label(self.text(cap)), self.bbox(cap)
                        item["bbox"] = g.union([item["bbox"], item["label_bbox"]])
                        self.used.add(cap)
                if item["kind"] == "field":
                    self.zones.append(item["zone"])
                elif item["kind"] == "table":
                    self.zones.append(item["bbox"])
                self.items.append(item)
            for c in cells:
                self.used.update(c.lines)

    # ---- 3. single boxes, underlines and ____ blanks -------------------------------
    def boxes(self):
        for box in sorted(self.page["boxes"], key=lambda b: (b["bbox"][1], b["bbox"][0])):
            bb = box["bbox"]
            inner = [i for i in self.free() if g.inside(self.bbox(i), bb)]
            if len(inner) > 2:
                continue
            if inner:
                inner.sort(key=lambda i: (self.bbox(i)[1], self.bbox(i)[0]))
                i = inner[0]
                b = self.bbox(i)
                if g.width(b) > 0.7 * g.width(bb) or self.filled:
                    outside = self._left_label(bb) if self.filled else None
                    if outside is None:
                        outside = self._above_label(bb) if self.filled else None
                    if outside is not None and outside not in inner:
                        self.used.update(inner)  # the box holds a written value
                        self._add_field(outside, bb)
                    continue
                self.used.update(inner)
                if g.height(bb) > 1.8 * g.height(b):
                    zone = [bb[0], b[3], bb[2], bb[3]]
                else:
                    zone = [b[2], bb[1], bb[2], bb[3]]
                self._add_field(i, zone)
                continue
            label = self._left_label(bb)
            if label is None:
                label = self._above_label(bb)
            if label is None:
                label = self._below_label(bb)
            self._add_field(label, bb, label_text=None if label is not None else "", comb=box["comb"])

    def write_lines(self):
        candidates = [("blank", b["bbox"]) for b in self.page["blanks"]]
        for h in self.page["hlines"]:
            hb = h["bbox"]
            candidates.append(("hline", [hb[0], hb[3] - 1.5 * self.lh, hb[2], hb[3] + 2]))
        candidates.sort(key=lambda c: (c[1][1], c[1][0]))
        for kind, zone in candidates:
            if self._overlaps_zone(zone):
                continue
            if kind == "hline":
                above = [i for i in self.free() if g.v_overlap(self.bbox(i), zone) >= 0.5 and g.h_overlap(self.bbox(i), zone) > 0.5]
                covered = sum(g.width(g.intersection(self.bbox(i), [zone[0], 0, zone[2], self.H]) or [0, 0, 0, 0]) for i in above)
                if covered > 0.6 * g.width(zone):
                    label = self._left_label(zone, band=zone) if self.filled else None
                    if label is not None and label not in above:
                        self.used.update(above)  # a value written on the line
                        self._add_field(label, zone)
                    continue  # otherwise underlined text, not a write-in line
                if above:
                    i = min(above, key=lambda i: self.bbox(i)[0])
                    if self.bbox(i)[0] - zone[0] < 0.05 * self.W:
                        self._add_field(i, [self.bbox(i)[2], zone[1], zone[2], zone[3]])
                        continue
            label = self._left_label(zone)
            if label is None:
                label = self._above_label(zone) if kind == "blank" else None
            if label is None:
                label = self._below_label(zone)
            if label is None:
                continue
            self._add_field(label, zone)

    # ---- 4. "Label: value" and "Label:" with room to write -----------------------------
    def colon_labels(self):
        for i in self.free():
            if i in self.used:
                continue
            line = self.lines[i]
            m = COLON_RE.match(line["text"])
            if not m or len(m.group("label").split()) > MAX_LABEL_WORDS:
                continue
            if DOC_CONTROL_RE.match(clean_label(m.group("label"))) or NOTE_RE.match(clean_label(m.group("label"))):
                continue  # "Format No.: HPU/F/FAC/007", "Note: ..." are document text, not fields
            rest = m.group("rest").strip()
            label_part = sub_line(line, 0, m.end("label"))
            if label_part is None:
                continue
            if rest:
                if len(rest.split()) > MAX_INLINE_VALUE_WORDS:
                    continue
                value_part = sub_line(line, m.start("rest"), len(line["text"]))
                vb = value_part["bbox"] if value_part else line["bbox"]
                zone = [vb[0], line["bbox"][1], max(vb[2], self._right_limit(line["bbox"])), line["bbox"][3]]
                self.used.add(i)
                self.zones.append(zone)
                self.items.append({
                    "kind": "field", "label": clean_label(m.group("label")), "label_bbox": label_part["bbox"],
                    "zone": zone, "element": None, "bbox": g.union([line["bbox"], zone]),
                })
                continue
            b = line["bbox"]
            sample = None
            for j in self.free():
                o = self.bbox(j)
                if j != i and o[0] > b[2] and g.v_overlap(o, b) >= 0.5 and not COLON_RE.match(self.text(j)):
                    if sample is None or o[0] < self.bbox(sample)[0]:
                        sample = j
            if sample is not None and self.bbox(sample)[0] - b[2] < 0.3 * self.W:
                zone = [self.bbox(sample)[0], b[1], max(self.bbox(sample)[2], self._right_limit(self.bbox(sample))), b[3]]
                self.used.add(sample)
                self._add_field(i, zone)
                continue
            limit = self._right_limit(b)
            if limit - b[2] >= 0.06 * self.W:
                self._add_field(i, [b[2] + 0.005 * self.W, b[1] - 0.2 * self.lh, limit, b[3] + 0.2 * self.lh])
                continue
            below = [b[0], b[3], min(self.content_right, b[0] + 0.4 * self.W), b[3] + 1.5 * self.lh]
            if not any(g.intersection(self.bbox(j), below) for j in range(len(self.lines)) if j != i):
                self._add_field(i, below)

    # ---- 5. text in columns without ruling (a revision history): a table of fixed text ---
    def text_tables(self):
        for rows in textgrid.find(self.free(), self.bbox, self.lh):
            item = textgrid.table_item(rows, self.bbox, self.text)
            self.used.update(i for r in rows for i in r)
            cap = self._above_label(item["bbox"])
            if cap is not None and len(self.text(cap).split()) <= 10:
                item["label"], item["label_bbox"] = clean_label(self.text(cap)), self.bbox(cap)
                item["bbox"] = g.union([item["bbox"], item["label_bbox"]])
                self.used.add(cap)
            self.items.append(item)

    # ---- 6. remaining text: headers, labels, paragraphs ------------------------------------
    def statics(self):
        free = sorted(self.free(), key=lambda i: (self.bbox(i)[1], self.bbox(i)[0]))
        blocks = []
        for i in free:
            b, h = self.bbox(i), g.height(self.bbox(i))
            merged = False
            for blk in blocks[-3:]:
                last = self.bbox(blk[-1])
                gap = b[1] - last[3]
                aligned = abs(b[0] - self.bbox(blk[0])[0]) < 0.05 * self.W or g.h_overlap(b, last) > 0.5
                similar = 0.77 < h / max(1.0, g.height(last)) < 1.3
                if -0.2 * h < gap < 0.7 * h and aligned and similar and not self._is_header(blk[0], len(blocks) == 1):
                    blk.append(i)
                    merged = True
                    break
            if not merged:
                blocks.append([i])
        for n, blk in enumerate(blocks):
            text = " ".join(self.text(i) for i in blk)
            bbox = g.union([self.bbox(i) for i in blk])
            if len(blk) == 1 and self._is_header(blk[0], n == 0):
                element = "Header"
            elif len(blk) == 1 and len(text.split()) <= 8:
                element = "Label"
            else:
                element = "Paragraph"
            self.used.update(blk)
            self.items.append({"kind": "static", "element": element, "text": text, "bbox": bbox})

    def _is_header(self, i, first_block):
        b, text = self.bbox(i), self.text(i)
        h = g.height(b)
        words = len(text.split())
        if h >= 1.35 * self.lh and words <= 15:
            return True
        centred = abs(g.center(b)[0] - self.W / 2) < 0.1 * self.W
        if text.isupper() and words <= 8 and centred:
            return True
        return first_block and words <= 10 and h >= 1.15 * self.lh

    def build(self):
        self.choices()
        self.grids()
        self.boxes()
        self.write_lines()
        self.colon_labels()
        self.text_tables()
        self.statics()
        # One title per page: the top-most Header wins, other candidates become bold labels.
        headers = sorted((it for it in self.items if it.get("element") == "Header"), key=lambda it: it["bbox"][1])
        for it in headers[1:]:
            it["element"], it["bold"] = "Label", True
        return self.items


# ---- items -> task_data -------------------------------------------------------------------

def _rows(items, page_w):
    rows = []
    for item in sorted(items, key=lambda it: (it["bbox"][1], it["bbox"][0])):
        # a table, or printed text across the page, stands alone; fields on one printed
        # line share it however wide their boxes ("Dept. [............]  Date [....]")
        wide = item["kind"] == "table" or (item["kind"] == "static" and g.width(item["bbox"]) > 0.6 * page_w)
        if not wide and rows and not rows[-1]["wide"]:
            row = rows[-1]
            cy = g.center(item["bbox"])[1]
            ratio = g.height(item["bbox"]) / max(1.0, g.height(row["bbox"]))
            similar = 0.4 <= ratio <= 2.5  # a cell spanning several rows is not on "this" row
            if similar and row["bbox"][1] <= cy <= row["bbox"][3] and g.v_overlap(row["bbox"], item["bbox"]) >= 0.5:
                row["items"].append(item)
                row["bbox"] = g.union([row["bbox"], item["bbox"]])
                continue
        rows.append({"items": [item], "bbox": list(item["bbox"]), "wide": wide})
    for row in rows:
        row["items"].sort(key=lambda it: it["bbox"][0])
    return rows


def _to_element(item, meta, page_w, page_h, line_height, sheet=None):
    def n(b):
        return g.normalize(b, page_w, page_h) if b else None

    kind = item["kind"]
    if kind == "static":
        text = tables.normalize_legend(item["text"])  # "V OK" -> "✓ OK"
        e = el.static_element(item["element"], text, bold=item.get("bold", False))
        e["ocr"] = {**meta, "bbox": n(item["bbox"]), "text": item["text"]}
        if sheet and item.get("ref"):
            e["excel"] = {"sheet": sheet, "cell": item["ref"]}
        return e
    if kind == "image":
        e = el.image_element(item["src"], item.get("width"), item.get("height"))
        e["ocr"] = {**meta, "bbox": n(item["bbox"])}
        return e
    label = item.get("label") or ""
    if kind == "field":
        element = item.get("element") or infer_type(label, g.height(item["zone"]), line_height)
        hint = item.get("hint") or {}
        # What the source says about the input (Excel data validation) beats the label's wording;
        # a number format only refines a plain text input.
        if hint.get("element") and (hint.get("strong") or element == "TextInput") and not item.get("element"):
            element = hint["element"]
        if element == "Dropdown":
            e = el.option_element("Dropdown", label or "Field", hint.get("options") or [])
        else:
            e = el.input_element(element, label or "Field")
        e["ocr"] = {**meta, "label_text": label, "label_bbox": n(item.get("label_bbox")), "value_bbox": n(item["zone"])}
        if item.get("comb"):
            e["ocr"]["comb"] = True  # one letter per box: read without spaces
        if item.get("inline"):
            e["ocr"]["inline"] = True  # label and value share a cell: "Work Station : IQC"
            if item.get("sample"):
                e["ocr"]["sample"] = item["sample"]  # the value printed on the blank form
        if sheet and item.get("ref"):
            e["excel"] = {"sheet": sheet, "cell": item["ref"], "label_cell": item.get("label_ref"), "inline": bool(item.get("inline"))}
        return e
    if kind == "choice":
        e = el.option_element(item["element"], label, [o["text"] for o in item["options"]])
        for opt, src in zip(e["options"], item["options"]):
            opt["ocr"] = {"box": n(src["box"]), "text_bbox": n(src["text_bbox"])}
        e["ocr"] = {**meta, "label_text": label, "label_bbox": n(item.get("label_bbox")), "bbox": n(item["bbox"])}
        if sheet and any(o.get("cell") for o in item["options"]):
            e["excel"] = {"sheet": sheet, "options": [o.get("cell") for o in item["options"]], "label_cell": item.get("label_ref")}
        return e
    if kind == "table":
        # a numbered run of columns (1..31 under "DATE") that OCR partly misread is renumbered,
        # and the columns are named after the repaired headings
        header = headings.number_runs([[dict(c) if isinstance(c, dict) else {"text": c} for c in r] for r in item["header"]])
        e = el.table_element(label, headings.column_texts(item["columns"], header), header, item["body"],
                             reference=item.get("reference", False))
        e["ocr"] = {
            **meta,
            "label_text": label,
            "label_bbox": n(item.get("label_bbox")),
            "bbox": n(item["bbox"]),
            "header_anchors": [{"text": h["text"], "bbox": n(h["bbox"])} for h in item["header_anchors"]],
            "cell_bboxes": [[n(b) for b in row] for row in item["cell_boxes"]],
        }
        if sheet and any(any(r) for r in item.get("cell_refs") or []):
            e["excel"] = {"sheet": sheet, "cells": item["cell_refs"], "label_cell": item.get("label_ref")}
        return e
    raise ValueError(kind)


def assemble(page_items, preserve_geometry=False):
    """page_items: [{"items", "width", "height", "line_height", "sheet"?}] -> task_data.

    Items on one visual row become a Two/Three/Multi column row; pages after the first start
    with a page break. Shared by every format (OCR pages, Excel sheets).
    """
    top, children = [], []
    counts = {}
    for p_index, page in enumerate(page_items):
        meta = {"page": p_index, "page_size": [page["width"], page["height"]]}
        page_start = len(top)
        for row in _rows(page["items"], page["width"]):
            elems = [
                _to_element(it, meta, page["width"], page["height"], page["line_height"], page.get("sheet"))
                for it in row["items"]
            ]
            if preserve_geometry:
                for elem, item in zip(elems, row["items"]):
                    if item.get("bbox"):
                        elem["layout_position"] = {
                            "left": item["bbox"][0] / page["width"],
                            "top": (p_index + item["bbox"][1] / page["height"]) / len(page_items),
                            "width": g.width(item["bbox"]) / page["width"],
                            "height": g.height(item["bbox"]) / page["height"] / len(page_items),
                        }
                        elem["layout_page"] = p_index
                        elem["layout_page_count"] = len(page_items)
                        elem["layout_page_size"] = [page["width"], page["height"]]
            for it in row["items"]:
                counts[it["kind"]] = counts.get(it["kind"], 0) + 1
            has_input = any(it["kind"] in ("field", "choice") for it in row["items"])
            if not preserve_geometry and 2 <= len(elems) <= 6 and has_input:
                container = el.container_element(len(elems))
                parent_index = len(top)
                for col, child in enumerate(elems):
                    child["parentId"] = container["id"]
                    child["parentIndex"] = parent_index
                    child["col"] = col
                    container["childItems"].append(child["id"])
                    children.append(child)
                top.append(container)
            else:
                top.extend(elems)
        if not preserve_geometry and p_index > 0 and len(top) > page_start:
            top[page_start]["pageBreakBefore"] = True
    task_data = labels.disambiguate(top + children)
    title.lead_with_title(task_data)
    return {"task_data": task_data, "stats": counts}


def build_template(pages, filled=False):
    """OCR'd pages -> task_data. filled=True when the pages are a filled-in copy."""
    return assemble([
        {"items": PageTemplate(page, i, filled=filled).build(), "width": page["width"], "height": page["height"],
         "line_height": page["line_height"]}
        for i, page in enumerate(pages)
    ])
