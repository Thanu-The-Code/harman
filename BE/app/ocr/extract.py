"""Requirement A: read a filled scan and produce answer_data for an existing form.

Two strategies, tried in order for every field:
  zone  - the template came from an image (has `ocr` boxes). The scan is aligned to
          the template with a similarity transform estimated from matched label text,
          and each field's value box is read directly.
  label - fuzzy-find the field's label in the scan and read the text next to it
          (rest of the line, the line to the right, or the line below).
"""
import base64
import re
from collections import Counter

import cv2
import numpy as np
from rapidfuzz import fuzz

from . import geometry as g
from . import tables
from . import values as v
from .cellgrid import CellGrid, GridCell
from .cells import CellReader
from .document import slice_x, sub_line
from .results import NO_VALUE, ResultRecorder, display_order, label_cut, prefix_score, typed_value  # noqa: F401
from .shapes import fill_ratio

ANCHOR_SCORE = 85
LABEL_SCORE = 78
OPTION_SCORE = 80
CHECKED_FILL = 0.1
MAX_ANCHOR_WORDS = 8

CHECK_GLYPHS = set("✓✔☑☒xX✗✘")


def _transform(m, b):
    pts = np.float32([[b[0], b[1]], [b[2], b[1]], [b[0], b[3]], [b[2], b[3]]]).reshape(-1, 1, 2)
    out = cv2.transform(pts, m).reshape(-1, 2)
    return [float(out[:, 0].min()), float(out[:, 1].min()), float(out[:, 0].max()), float(out[:, 1].max())]


class Extractor:
    def __init__(self, task_data, pages, images, recognize=None):
        self.task_data = [e for e in task_data if isinstance(e, dict)]
        self.pages = pages
        self.images = images
        self.recognize = recognize
        self._grid_cache = {}
        self._cells = None
        self._labels = []
        self._label_of_line = {}
        self.recorder = ResultRecorder()
        self.answers = self.recorder.answers
        self.report = self.recorder.report
        self.alignment = []
        self.label_hits = {}

    # ---- alignment -----------------------------------------------------------------
    def _anchors(self, t_page):
        pairs = []
        for e in self.task_data:
            o = e.get("ocr")
            if not o or o.get("page") != t_page or not o.get("page_size"):
                continue
            w, h = o["page_size"]
            cand = []
            if o.get("text") and o.get("bbox"):
                cand.append((o["text"], o["bbox"]))
            if o.get("label_text") and o.get("label_bbox"):
                cand.append((o["label_text"], o["label_bbox"]))
            for opt in e.get("options") or []:
                tb = (opt.get("ocr") or {}).get("text_bbox")
                if tb:
                    cand.append((opt.get("text", ""), tb))
            for head in o.get("header_anchors") or []:
                if head.get("bbox"):
                    cand.append((head.get("text", ""), head["bbox"]))
            for text, nb in cand:
                if len(v.norm(text)) >= 3 and len(text.split()) <= MAX_ANCHOR_WORDS:
                    pairs.append((text, g.denormalize(nb, w, h), (w, h)))
        counts = Counter(v.norm(p[0]) for p in pairs)
        return [p for p in pairs if counts[v.norm(p[0])] == 1]

    def _match_anchors(self, anchors, page):
        matches = []
        for text, tb, size in anchors:
            best, best_score = None, 0
            for line in page["lines"]:
                s = prefix_score(text, line["text"])
                if s > best_score:
                    best, best_score = line, s
            if best is None or best_score < ANCHOR_SCORE:
                continue
            lb = best["bbox"]
            frac = min(1.0, len(v.norm(text)) / max(1, len(v.norm(best["text"]))))
            ty, sy = g.center(tb)[1], g.center(lb)[1]
            matches.append(([[tb[0], ty], [tb[2], ty]], [[lb[0], sy], [lb[0] + frac * g.width(lb), sy]], size))
        return matches

    def align(self):
        t_pages = sorted({e["ocr"]["page"] for e in self.task_data if e.get("ocr") and "page" in e["ocr"]})
        transforms = {}
        for t in t_pages:
            anchors = self._anchors(t)
            scored = []
            for s, page in enumerate(self.pages):
                m = self._match_anchors(anchors, page)
                scored.append((len(m), s == t, s, m))
            if not scored:
                continue
            n, _, s, matches = max(scored, key=lambda x: (x[0], x[1]))
            if n == 0:
                s = t if t < len(self.pages) else None
                if s is None:
                    continue
            page = self.pages[s]
            size = matches[0][2] if matches else next(e["ocr"]["page_size"] for e in self.task_data if e.get("ocr", {}).get("page") == t)
            m, method = None, "scaled"
            if len(matches) >= 3:
                src = np.float32([p for mt in matches for p in mt[0]])
                dst = np.float32([p for mt in matches for p in mt[1]])
                m, inliers = cv2.estimateAffinePartial2D(
                    src, dst, method=cv2.RANSAC, ransacReprojThreshold=max(8.0, 0.015 * page["width"])
                )
                if m is not None and inliers is not None and int(inliers.sum()) >= 4:
                    scale = float(np.hypot(m[0, 0], m[1, 0]))
                    rot = abs(float(np.degrees(np.arctan2(m[1, 0], m[0, 0]))))
                    if 0.3 < scale < 3.0 and rot < 15:
                        method = "anchors"
                    else:
                        m = None
                else:
                    m = None
            if m is None:
                m = np.float32([[page["width"] / size[0], 0, 0], [0, page["height"] / size[1], 0]])
            transforms[t] = (s, m, method)
            self.alignment.append({"template_page": t, "scan_page": s, "method": method, "anchors": len(matches)})
        return transforms

    # ---- reading text ---------------------------------------------------------------
    def _read_zone(self, page, zone, multiline=False):
        lh = page["line_height"]
        pad = 0.005 * page["width"]
        parts = []
        for line in page["lines"]:
            cy = g.center(line["bbox"])[1]
            if not (zone[1] - 0.3 * lh <= cy <= zone[3] + 0.3 * lh):
                continue
            part = slice_x(line, zone[0] - pad, zone[2] + pad)
            if part:
                parts.append(part)
        if not parts:
            return "", 0.0
        parts.sort(key=lambda p: (p["bbox"][1], p["bbox"][0]))
        rows = []
        for p in parts:
            if rows and g.v_overlap(rows[-1][-1]["bbox"], p["bbox"]) >= 0.5:
                rows[-1].append(p)
            else:
                rows.append([p])
        text = ("\n" if multiline else " ").join(" ".join(p["text"] for p in sorted(r, key=lambda p: p["bbox"][0])) for r in rows)
        total = sum(len(p["text"]) for p in parts)
        conf = sum(p["conf"] * len(p["text"]) for p in parts) / max(1, total)
        return text, conf

    def _find_labels(self, fields):
        """Assign each field label to its best scan line; longer labels win shared lines.

        fields: [(element, candidate page indexes)]. Returns {id: (page, line index, score)}.
        """
        cands = []
        for e, pages in fields:
            label = v.plain(e.get("label", ""))
            if len(v.norm(label)) < 2:
                continue
            for p in pages:
                for i, line in enumerate(self.pages[p]["lines"]):
                    s = prefix_score(label, line["text"])
                    if s >= LABEL_SCORE:
                        cands.append((s, len(v.norm(label)), e["id"], p, i))
        cands.sort(key=lambda c: (-c[0], -c[1], c[3]))
        taken_lines, hits = set(), {}
        for s, _, eid, p, i in cands:
            if eid in hits or (p, i) in taken_lines:
                continue
            hits[eid] = (p, i, s)
            taken_lines.add((p, i))
        return hits

    def _near_label(self, page, line_index, label, label_lines):
        line = page["lines"][line_index]
        lb, lh, w = line["bbox"], page["line_height"], page["width"]
        rest = sub_line(line, label_cut(line["text"], label), len(line["text"]))
        if rest and v.clean_text(rest["text"]):
            return rest["text"], rest["conf"], 0.9, rest["bbox"]
        best, best_d = None, None
        for i, o in enumerate(page["lines"]):
            ob = o["bbox"]
            if i == line_index or i in label_lines:
                continue
            d = ob[0] - lb[2]
            if g.v_overlap(ob, lb) >= 0.5 and -2 <= d <= 0.4 * w and (best_d is None or d < best_d):
                best, best_d = i, d
        if best is not None:
            o = page["lines"][best]
            return o["text"], o["conf"], 0.85, o["bbox"]
        for i, o in enumerate(page["lines"]):
            ob = o["bbox"]
            if i == line_index or i in label_lines:
                continue
            d = ob[1] - lb[3]
            if -0.2 * lh <= d <= 1.8 * lh and (g.h_overlap(ob, lb) >= 0.3 or abs(ob[0] - lb[0]) <= 0.05 * w):
                if best_d is None or d < best_d:
                    best, best_d = i, d
        if best is not None:
            o = page["lines"][best]
            return o["text"], o["conf"], 0.7, o["bbox"]
        return "", 0.0, 0.0, None

    # ---- tick boxes -------------------------------------------------------------------
    def _tick_fill(self, page, bbox):
        size = max(g.width(bbox), 0.01 * page["width"])
        c = g.center(bbox)
        best, best_d = None, None
        for t in page["checkboxes"]:
            d = float(np.hypot(*(np.subtract(g.center(t["bbox"]), c))))
            if d <= 1.5 * size and (best_d is None or d < best_d):
                best, best_d = t, d
        if best is not None:
            return best["fill"]
        if page.get("binary") is None:
            return None
        return fill_ratio(page["binary"], bbox)

    def _glyph_checked(self, page, bbox):
        for line in page["lines"]:
            if g.v_overlap(line["bbox"], bbox) < 0.3:
                continue
            for ch, x0, x1 in line["chars"]:
                if ch in CHECK_GLYPHS and bbox[0] - 2 <= (x0 + x1) / 2 <= bbox[2] + 2:
                    return True
        return False

    def _choice(self, e, s, m):
        if m is not None or e["id"] in self.label_hits:
            return self._choice_on(e, s, m)
        # No position and no label found: use the page where most option texts appear.
        best = (None, 0.0, "none")
        best_n = 0
        for p in range(len(self.pages)):
            value, conf, method, n = self._choice_on(e, p, None, count=True)
            if n > best_n:
                best, best_n = (value, conf, method), n
        return best

    def _choice_on(self, e, s, m, count=False):
        page = self.pages[s]
        opts = e.get("options") or []
        fills = {}
        method = "zone" if m is not None else "label"
        if m is not None:
            for opt in opts:
                box = (opt.get("ocr") or {}).get("box")
                if not box:
                    continue
                w, h = e["ocr"]["page_size"]
                sb = _transform(m, g.denormalize(box, w, h))
                f = self._tick_fill(page, sb)
                if self._glyph_checked(page, sb):
                    f = max(f or 0, 1.0)
                if f is not None:
                    fills[opt["key"]] = f
        if not fills:
            method = "label"
            window = None
            hit = self.label_hits.get(e["id"])
            if hit and hit[0] == s:
                qb, lh = page["lines"][hit[1]]["bbox"], page["line_height"]
                window = [0, qb[1] - lh, page["width"], qb[3] + 8 * lh]
            for opt in opts:
                best, best_s = None, 0
                for line in page["lines"]:
                    if window and not g.inside(line["bbox"], window):
                        continue
                    s = prefix_score(opt.get("text", ""), line["text"])
                    if s > best_s:
                        best, best_s = line, s
                if best is None or best_s < OPTION_SCORE:
                    continue
                lb = best["bbox"]
                tick = None
                for t in page["checkboxes"]:
                    tb = t["bbox"]
                    if g.v_overlap(tb, lb) >= 0.3 and -3 * g.width(tb) <= lb[0] - tb[2] <= 3 * g.width(tb):
                        tick = t
                if tick is None:
                    for t in page["checkboxes"]:
                        tb = t["bbox"]
                        if g.v_overlap(tb, lb) >= 0.3 and 0 <= tb[0] - lb[2] <= 3 * g.width(tb):
                            tick = t
                if tick is not None:
                    fills[opt["key"]] = tick["fill"]
                elif best["text"][:1] in CHECK_GLYPHS and best["text"][1:2] in (" ", ""):
                    fills[opt["key"]] = 1.0
        if not fills:
            return (None, 0.0, "none", 0) if count else (None, 0.0, "none")
        checked = [k for k, f in fills.items() if f >= CHECKED_FILL]
        if e["element"] == "RadioButtons" and len(checked) > 1:
            checked = [max(checked, key=lambda k: fills[k])]
        margin = min(abs(f - CHECKED_FILL) for f in fills.values())
        conf = 0.95 if margin > 0.05 else 0.6
        return (checked, conf, method, len(fills)) if count else (checked, conf, method)

    # ---- tables ---------------------------------------------------------------------
    def _cell_text(self, page, cell):
        parts = [l for l in page["lines"] if g.contains_point(cell, g.center(l["bbox"]))]
        parts.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
        if not parts:
            return "", 1.0
        conf = sum(p["conf"] for p in parts) / len(parts)
        return " ".join(p["text"] for p in parts), conf

    def _grid_cell(self, page, box, min_iou=0.5):
        """The ruled cell of this scan that best matches a box, or None."""
        best, best_iou = None, min_iou
        for grid in page["grids"]:
            if not g.intersection(grid["bbox"], box):
                continue
            for cell in grid["cells"]:
                i = g.iou(cell["bbox"], box)
                if i > best_iou:
                    best, best_iou = cell["bbox"], i
        return best

    def _read_cells(self, s, boxes):
        """[(text, conf)] for ruled cells (ticks/crosses as ✓ / ✗).

        Each cell is read from its own crop. When the page-level OCR has lines lying entirely
        inside the cell, that reading competes on confidence; lines crossing into neighbouring
        cells (narrow day columns) are not trusted.
        """
        if self._cells is None:
            from . import engine
            self._cells = CellReader(engine.recognize_lines, self.recognize or engine.recognize)
        crop_reads = self._cells.read(self.images[s], boxes)
        out = []
        for box, (text, conf) in zip(boxes, crop_reads):
            page_text, page_conf = self._contained_text(self.pages[s], box)
            if page_text and page_conf >= conf and text not in ("✓", "✗"):
                text, conf = page_text, page_conf
            out.append((text, conf))
        return out

    def _contained_text(self, page, box):
        pad = 3
        inner = [l for l in page["lines"] if g.contains_point(box, g.center(l["bbox"]))]
        if not inner or any(l["bbox"][0] < box[0] - pad or l["bbox"][2] > box[2] + pad for l in inner):
            return "", 0.0
        inner.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
        rows = []
        for l in inner:
            if rows and g.v_overlap(rows[-1][-1]["bbox"], l["bbox"]) >= 0.5:
                rows[-1].append(l)
            else:
                rows.append([l])
        text = "\n".join(" ".join(x["text"] for x in sorted(r, key=lambda x: x["bbox"][0])) for r in rows)
        conf = sum(l["conf"] for l in inner) / len(inner)
        return text, conf

    def _cell_near_label(self, s, i):
        """The blank/filled cell right of (or below) the ruled cell holding label line i."""
        line = self.pages[s]["lines"][i]
        lc = g.center(line["bbox"])
        for cg in self._scan_grids(s):
            own = next((c for c in cg.cells if g.contains_point(c.bbox, lc)), None)
            if own is None:
                continue
            label = self._label_of_line.get((s, i), "")
            if label and prefix_score(label, own.text) >= 90 and len(v.norm(own.text)) > len(v.norm(label)) + 3:
                return own.bbox  # the value is written inside the label's own cell ("DATE :-" / date below)
            nb = cg.right_of(own)
            while nb is not None and nb.text.strip().endswith((":", ":-")):
                nb = cg.right_of(nb)  # "Revision Number: | OLD: | [value]"
            for cand in (nb, cg.below(own)):
                if cand is not None and cand is not own and not any(prefix_score(lab, cand.text) >= 85 for lab in self._labels):
                    return cand.bbox
        return None

    def _scan_grids(self, s):
        """This page's ruled grids as CellGrids carrying their OCR text."""
        if s in self._grid_cache:
            return self._grid_cache[s]
        page = self.pages[s]
        out = []
        for grid in page["grids"]:
            cells = []
            for c in grid["cells"]:
                text, _ = self._cell_text(page, c["bbox"])
                cells.append(GridCell(row=c["row"], col=c["col"], rowspan=c["rowspan"], colspan=c["colspan"], text=text, bbox=c["bbox"]))
            out.append(CellGrid(cells, grid["n_rows"], grid["n_cols"]))
        self._grid_cache[s] = out
        return out

    def _locate_table(self, e, s, m):
        """(page, CellGrid, last heading row, column map) found by the column headings."""
        pages = [s] if m is not None else range(len(self.pages))
        found = None
        for p in pages:
            for cg in self._scan_grids(p):
                hit = tables.match_table(cg, e)
                if hit and (found is None or sum(x is not None for x in hit[1]) > sum(x is not None for x in found[3])):
                    found = (p, cg, *hit)
        return found

    def _table(self, e, s, m):
        cols = e.get("columns") or []
        rows = tables.body(e)
        if not cols or not rows:
            return None, 0.0, "none"
        o = e.get("ocr") or {}
        targets = {}  # (r, c) -> box to read
        page_index, method = s, "none"
        found = self._locate_table(e, s, m)
        named = sum(1 for col in cols if (col.get("text") or "").strip())
        if found is not None and sum(x is not None for x in found[3]) >= max(2, 0.6 * named):
            # Structure first: the scan's own cells, matched by the column headings.
            page_index, cg, r_head, mapping = found
            method = "label" if m is None else "zone"
            grid_rows = tables.body_rows(cg, r_head, mapping, len(rows))
            for r, row in enumerate(rows):
                if r >= len(grid_rows):
                    break
                gr = grid_rows[r]
                for c, cell in enumerate(row):
                    gc = mapping[c] if c < len(mapping) else None
                    a = cg.at(gr, gc) if gc is not None else None
                    if tables.is_input(cell) and a is not None and a.row == gr and a.col == gc:
                        targets[(r, c)] = a.bbox
        elif m is not None and o.get("cell_bboxes"):
            method = "zone"
            page = self.pages[s]
            w, h = o["page_size"]
            for r, row in enumerate(rows):
                boxes = o["cell_bboxes"][r] if r < len(o["cell_bboxes"]) else []
                for c, cell in enumerate(row):
                    nb = boxes[c] if c < len(boxes) else None
                    if tables.is_input(cell) and nb:
                        box = _transform(m, g.denormalize(nb, w, h))
                        targets[(r, c)] = self._grid_cell(page, box) or box
        else:
            return None, 0.0, "none"
        keys = list(targets)
        read = dict(zip(keys, self._read_cells(page_index, [targets[k] for k in keys])))
        value = [[read.get((r, c), ("", 1.0))[0] for c in range(len(row))] for r, row in enumerate(rows)]
        confs = [conf for text, conf in read.values() if text]
        if not any(any(c for c in r) for r in value):
            return None, 0.0, method
        return value, (sum(confs) / len(confs) if confs else 0.5), method

    # ---- signatures -------------------------------------------------------------------
    def _signature(self, page_index, zone):
        img = self.images[page_index]
        hgt, wid = img.shape[:2]
        x0, y0 = max(0, int(zone[0])), max(0, int(zone[1]))
        x1, y1 = min(wid, int(zone[2])), min(hgt, int(zone[3]))
        if x1 - x0 < 10 or y1 - y0 < 10:
            return None
        crop = img[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        rules = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, (x1 - x0) // 3), 1)))
        ink = cv2.subtract(ink, rules)
        if ink.mean() / 255.0 < 0.01:
            return None
        ok, buf = cv2.imencode(".png", crop)
        return base64.b64encode(buf.tobytes()).decode("ascii") if ok else None

    # ---- main ------------------------------------------------------------------------------
    def run(self):
        transforms = self.align()
        fields = [e for e in display_order(self.task_data) if e.get("field_name") and e.get("element") not in NO_VALUE]
        self._labels = [v.plain(e.get("label", "")) for e in fields if v.plain(e.get("label", ""))]
        everywhere = list(range(len(self.pages)))
        self.label_hits = self._find_labels(
            [(e, [self._mapped_page(e, transforms)] if self._mapped_page(e, transforms) is not None else everywhere) for e in fields]
        )
        label_lines = {}
        for p, i, _ in self.label_hits.values():
            label_lines.setdefault(p, set()).add(i)

        for e in fields:
            s = self._page_for(e, transforms)
            if s is None:
                self.recorder.record(e, None, 0.0, "none")
                continue
            page = self.pages[s]
            o = e.get("ocr") or {}
            t = transforms.get(o.get("page")) if o else None
            m = t[1] if t and t[0] == s else None
            kind = e["element"]
            if kind in ("Checkboxes", "RadioButtons"):
                self.recorder.record(e, *self._choice(e, s, m))
                continue
            if kind == "Table":
                self.recorder.record(e, *self._table(e, s, m))
                continue
            hit = self.label_hits.get(e["id"])
            hit = hit if hit and hit[0] == s else None
            value, conf, method = None, 0.0, "none"
            if m is not None and o.get("value_bbox"):
                w, h = o["page_size"]
                zone = _transform(m, g.denormalize(o["value_bbox"], w, h))
                if hit:
                    line = page["lines"][hit[1]]
                    lb = line["bbox"]
                    if g.v_overlap(lb, zone) >= 0.5 and lb[0] < zone[0] + 0.02 * page["width"]:
                        cut = line["chars"][min(len(line["chars"]) - 1, label_cut(line["text"], e.get("label", "")))]
                        zone = [max(zone[0], cut[1]), zone[1], zone[2], zone[3]]
                if kind == "Signature":
                    value = self._signature(s, zone)
                    conf, method = (0.8, "zone") if value else (0.0, "none")
                else:
                    if o.get("comb"):
                        # The comb found in this scan is tighter than the projected template box.
                        combs = [(g.iou(zone, b["bbox"]), b["bbox"]) for b in page["boxes"] if b["comb"]]
                        best = max(combs, default=(0, None))
                        raw, ocr_conf = self._read_comb(s, best[1] if best[0] >= 0.3 else zone)
                    else:
                        cell = self._grid_cell(page, zone)
                        if cell is not None:
                            raw, ocr_conf = self._read_cells(s, [cell])[0]
                        else:
                            raw, ocr_conf = self._read_zone(page, zone, multiline=kind == "TextArea")
                    value = typed_value(e, raw) if raw else None
                    if value is not None:
                        quality = 1.0 if transforms[o["page"]][2] == "anchors" else 0.75
                        conf, method = ocr_conf * quality, "zone"
            if value is None and hit:
                _, i, score = hit
                if kind == "Signature":
                    value = self._signature_near_label(s, i)
                    conf, method = (0.6, "label") if value else (0.0, "none")
                else:
                    comb = self._comb_right_of(page, i)
                    if comb is not None:
                        raw, ocr_conf = self._read_comb(s, comb["bbox"])
                        factor = 0.9
                    else:
                        line = page["lines"][i]
                        rest = sub_line(line, label_cut(line["text"], e.get("label", "")), len(line["text"]))
                        self._label_of_line[(s, i)] = e.get("label", "")
                        cell = None if rest and v.clean_text(rest["text"]) else self._cell_near_label(s, i)
                        if cell is not None:
                            raw, ocr_conf = self._read_cells(s, [cell])[0]
                            factor = 0.9
                        else:
                            raw, ocr_conf, factor, _ = self._near_label(page, i, e.get("label", ""), label_lines.get(s, set()) - {i})
                    value = typed_value(e, raw) if raw else None
                    if value is not None:
                        conf, method = ocr_conf * factor * score / 100.0, "label"
            self.recorder.record(e, value, conf, method)
        return {"answers": self.answers, "fields": self.report, "alignment": self.alignment}

    def _comb_right_of(self, page, i):
        """A letter-box field directly to the right of label line i, if any."""
        lb = page["lines"][i]["bbox"]
        for box in page["boxes"]:
            b = box["bbox"]
            if box["comb"] and g.v_overlap(b, lb) >= 0.4 and -2 <= b[0] - lb[2] <= 0.35 * page["width"]:
                return box
        return None

    def _read_comb(self, s, zone):
        """Letter boxes split OCR into fragments and turn '1' into 'I'; erase the box lines and
        read the strip again as one line of text."""
        img = self.images[s]
        hgt, wid = img.shape[:2]
        zh = max(4, int(g.height(zone)))
        pad = max(4, zh // 6)
        x0, y0 = max(0, int(zone[0]) - pad), max(0, int(zone[1]) - pad)
        x1, y1 = min(wid, int(zone[2]) + pad), min(hgt, int(zone[3]) + pad)
        crop = img[y0:y1, x0:x1].copy()
        if crop.size == 0:
            return "", 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        # Box walls span the full box height; letters are shorter, so a 75%-height kernel keeps them.
        vert = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(5, int(0.75 * zh)))))
        horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, (x1 - x0) // 4), 1)))
        rules = cv2.dilate(cv2.bitwise_or(vert, horiz), np.ones((3, 3), np.uint8))
        crop[rules > 0] = 255
        crop = cv2.copyMakeBorder(crop, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        if self.recognize is None:
            from . import engine
            self.recognize = engine.recognize
        lines = sorted(self.recognize(crop), key=lambda l: l["bbox"][0])
        if not lines:
            return "", 0.0
        text = "".join(l["text"] for l in lines)
        conf = sum(l["conf"] for l in lines) / len(lines)
        return re.sub(r"\s+", "", text), conf

    def _signature_near_label(self, s, i):
        """Signature boxes usually sit above their label ("____ / Signature") or to its right."""
        page = self.pages[s]
        lb, lh, w = page["lines"][i]["bbox"], page["line_height"], page["width"]
        above = [lb[0] - 0.01 * w, lb[1] - 3.5 * lh, lb[0] + 0.35 * w, lb[1] - 2]
        right = [lb[2] + 0.005 * w, lb[1] - 1.5 * lh, lb[2] + 0.35 * w, lb[3] + 0.5 * lh]
        # Real text (not short, low-confidence OCR noise on the signature itself) bounds the area.
        real = [l["bbox"] for j, l in enumerate(page["lines"]) if j != i and len(l["text"].strip()) >= 3 and l["conf"] >= 0.7]
        tops = [b[3] for b in real if b[3] <= lb[1] and g.intersection(b, above)]
        if tops:
            above[1] = max(tops) + 2
        for zone in (above, right):
            if g.height(zone) < lh or any(g.intersection(b, zone) for b in real):
                continue
            value = self._signature(s, zone)
            if value:
                return value
        return None

    def _by_id(self, eid):
        return next(e for e in self.task_data if e.get("id") == eid)

    def _mapped_page(self, e, transforms):
        o = e.get("ocr") or {}
        if "page" in o and o["page"] in transforms:
            return transforms[o["page"]][0]
        return None

    def _page_for(self, e, transforms):
        mapped = self._mapped_page(e, transforms)
        if mapped is not None:
            return mapped
        if e["id"] in self.label_hits:
            return self.label_hits[e["id"]][0]
        o = e.get("ocr") or {}
        if "page" in o and o["page"] < len(self.pages):
            return o["page"]
        return 0 if self.pages else None


def extract(task_data, pages, images, recognize=None):
    return Extractor(task_data, pages, images, recognize).run()
