"""Read ruled form cells one by one: crop, erase the cell borders, then OCR or classify a mark.

Reading a whole page merges text across narrow neighbouring cells ("X105q✓" for three day
columns); reading each cell's crop on its own does not.
"""
import cv2
import numpy as np

from . import tables
from . import values as v

MIN_INK_PIXELS = 40  # less ink than this (after removing borders) is an empty cell
SECOND_OPINION = 0.9  # below this recognition score, also try detect+recognise on the crop


def _crop(img, box):
    hgt, wid = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    m = max(3, min(8, int(0.06 * min(bw, bh))))  # clear of the borders, not of the writing
    x0, y0 = max(0, int(box[0]) + m), max(0, int(box[1]) + m)
    x1, y1 = min(wid, int(box[2]) - m), min(hgt, int(box[3]) - m)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None, None
    crop = img[y0:y1, x0:x1].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if int(gray.max()) - int(gray.min()) < 60:
        return crop, np.zeros(gray.shape, np.uint8)  # flat: nothing written
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    rules = _border_leftovers(ink)
    ink = cv2.subtract(ink, rules)
    crop[cv2.dilate(rules, np.ones((3, 3), np.uint8)) > 0] = 255
    return crop, ink


def _border_leftovers(ink, edge=2):
    """Straight line pieces touching the crop's edges: what is left of the cell's own borders.

    Only edge-touching pieces are removed, so letter strokes inside the cell (the 'l' in
    'Delta', a '1') survive even when they are as tall as a thin row.
    """
    h, w = ink.shape
    out = np.zeros_like(ink)
    for k, horizontal in (((max(8, w // 3), 1), True), ((1, max(6, int(h * 0.6))), False)):
        lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, k))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
        for i in range(1, n):
            x, y, cw, ch, _ = stats[i]
            touches = (y <= edge or y + ch >= h - edge) if horizontal else (x <= edge or x + cw >= w - edge)
            if touches:
                out[labels == i] = 255
    return out


def _bands(ink, min_gap=5):
    """Vertical extents of the text lines in a cell."""
    rows = np.where(ink.sum(axis=1) > 0)[0]
    if rows.size == 0:
        return []
    bands, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r - prev > min_gap:
            bands.append((start, prev + 1))
            start = r
        prev = r
    bands.append((start, prev + 1))
    return [b for b in bands if b[1] - b[0] >= 4]


def _trim(crop, ink, pad=6):
    ys, xs = np.nonzero(ink)
    y0, y1 = max(0, ys.min() - pad), min(ink.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(ink.shape[1], xs.max() + pad + 1)
    return cv2.copyMakeBorder(crop[y0:y1, x0:x1], 4, 4, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def classify_mark(ink):
    """'✓', '✗' or '' for a hand-drawn mark (ink mask with the cell borders removed)."""
    if ink is None or ink.size == 0 or ink.mean() / 255.0 < 0.01:
        return ""
    ys, xs = np.nonzero(ink)
    mark = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1] > 0
    mh, mw = mark.shape
    if mh < 5 or mw < 5:
        return ""

    def q(r0, r1, c0, c1):
        return mark[int(r0 * mh):int(r1 * mh), int(c0 * mw):int(c1 * mw)].mean()

    # A cross reaches all four corners of its box and its centre; a tick leaves the top-left empty.
    corners = (q(0, 0.3, 0, 0.3), q(0, 0.3, 0.7, 1), q(0.7, 1, 0, 0.3), q(0.7, 1, 0.7, 1))
    if min(corners) > 0.04 and q(0.35, 0.65, 0.35, 0.65) > 0.04:
        return "✗"
    return "✓"


class CellReader:
    def __init__(self, recognize_lines, recognize_page):
        self.recognize_lines = recognize_lines   # [crop] -> [(text, score)], single-line crops
        self.recognize_page = recognize_page     # crop -> [line], for multi-line cells

    def read(self, img, boxes):
        """[(text, confidence)] per box; '✓' / '✗' for cells holding just a tick or cross."""
        out = [("", 1.0)] * len(boxes)
        singles, inks = [], {}
        for i, box in enumerate(boxes):
            crop, ink = _crop(img, box)
            if crop is None or int(np.count_nonzero(ink)) < MIN_INK_PIXELS:
                continue
            inks[i] = ink
            bands = _bands(ink)
            if len(bands) > 1:
                lines = self.recognize_page(cv2.copyMakeBorder(crop, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=(255, 255, 255)))
                lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
                text = "\n".join(l["text"] for l in lines)
                conf = sum(l["conf"] for l in lines) / len(lines) if lines else 0.0
                out[i] = (text, conf)
            else:
                singles.append((i, _trim(crop, ink)))
        for (i, crop), (text, score) in zip(singles, self.recognize_lines([c for _, c in singles])):
            if score < SECOND_OPINION:
                # Unsure: let the full detector find the text inside the crop and keep the surer read.
                lines = self.recognize_page(cv2.copyMakeBorder(crop, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=(255, 255, 255)))
                if lines:
                    lines.sort(key=lambda l: l["bbox"][0])
                    alt_conf = sum(l["conf"] for l in lines) / len(lines)
                    if alt_conf > score:
                        text, score = " ".join(l["text"] for l in lines), alt_conf
            out[i] = (text if score >= 0.5 else "", score)
        for i, ink in inks.items():
            text, conf = out[i]
            text = tables.normalize_mark(v.clean_text(text)) if "\n" not in text else text.strip()
            if not text or (len(text) <= 2 and not any(ch.isdigit() for ch in text) and text not in ("✓", "✗")):
                mark = classify_mark(ink)
                if mark:
                    text, conf = mark, 0.7
            out[i] = (text, conf)
        return out
