"""OpenCV detection of the non-text parts of a form: rules, boxes, grids, checkboxes.

PaddleOCR reads text only; everything a person writes *into* (underlines, boxes,
table cells, tick boxes) is found here from the page's line structure.
"""
import cv2
import numpy as np

from . import geometry as g


def binarize(gray):
    w = gray.shape[1]
    block = max(15, (w // 60) | 1)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 15)


def _line_masks(binary):
    h, w = binary.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 50), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, h // 80)))
    horiz = cv2.morphologyEx(binary, cv2.MORPH_OPEN, hk)
    vert = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vk)
    return horiz, vert


def _fill_ratio(binary, b):
    x0, y0, x1, y1 = [int(round(v)) for v in b]
    m = max(2, int(0.22 * min(x1 - x0, y1 - y0)))
    inner = binary[y0 + m:y1 - m, x0 + m:x1 - m]
    if inner.size == 0:
        return 0.0
    return float(inner.mean()) / 255.0


def _cells(grid, page_w, page_h):
    """Enclosed rectangular regions of the page bounded by ruling lines."""
    inv = cv2.bitwise_not(grid)
    n, _, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    cells = []
    min_side = max(8, int(0.006 * page_w))
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if x == 0 or y == 0 or x + w >= page_w or y + h >= page_h:
            continue
        if w < min_side or h < min_side:
            continue
        if a < 0.85 * w * h:
            continue
        if w * h > 0.25 * page_w * page_h:
            continue
        cells.append([float(x - 1), float(y - 1), float(x + w + 1), float(y + h + 1)])
    return cells


def _adjacent(a, b, gap):
    if g.v_overlap(a, b) > 0.3 and (abs(a[2] - b[0]) <= gap or abs(b[2] - a[0]) <= gap):
        return True
    if g.h_overlap(a, b) > 0.3 and (abs(a[3] - b[1]) <= gap or abs(b[3] - a[1]) <= gap):
        return True
    return False


def _group_cells(cells, gap):
    parent = list(range(len(cells)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            if _adjacent(cells[i], cells[j], gap):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(cells)):
        groups.setdefault(find(i), []).append(cells[i])
    return list(groups.values())


def _structure(cells):
    """Assign row/col indices (with spans) to the cells of one grid."""
    med_h = float(np.median([g.height(c) for c in cells]))
    med_w = float(np.median([g.width(c) for c in cells]))
    rows = g.cluster_values([c[1] for c in cells], max(5.0, med_h * 0.3))
    cols = g.cluster_values([c[0] for c in cells], max(5.0, med_w * 0.15))
    out = []
    for c in cells:
        r = g.nearest_index(rows, c[1])
        k = g.nearest_index(cols, c[0])
        rowspan = max(1, sum(1 for y in rows if c[1] - 3 <= y < c[3] - 3))
        colspan = max(1, sum(1 for x in cols if c[0] - 3 <= x < c[2] - 3))
        out.append({"bbox": c, "row": r, "col": k, "rowspan": rowspan, "colspan": colspan})
    out.sort(key=lambda c: (c["row"], c["col"]))
    return out, len(rows), len(cols)


def _is_square(b, lo, hi):
    w, h = g.width(b), g.height(b)
    return lo <= w <= hi and lo <= h <= hi and 0.75 <= w / h <= 1.33


def _tick_boxes(binary, page_w):
    """Small hollow squares (checkboxes) and circles (radio buttons)."""
    lo, hi = max(10, 0.006 * page_w), 0.03 * page_w
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        b = [float(x), float(y), float(x + w), float(y + h)]
        if not _is_square(b, lo, hi):
            continue
        peri = cv2.arcLength(c, True)
        a = cv2.contourArea(c)
        if peri <= 0 or a <= 0:
            continue
        # A tight tolerance keeps printed boxes at 4 corners but splits letters like "D" or "O".
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx) and a > 0.88 * w * h:
            kind = "checkbox"
        elif 4 * np.pi * a / (peri * peri) > 0.8 and a > 0.6 * w * h and min(w, h) >= 0.009 * page_w:
            kind = "radio"  # the size floor keeps full stops and small letter bowls out
        else:
            continue
        found.append({"bbox": b, "kind": kind})
    # Outer and inner contours of the same stroke produce near-duplicates; keep the outer.
    found.sort(key=lambda s: -g.area(s["bbox"]))
    kept = []
    for s in found:
        if any(g.inside(s["bbox"], k["bbox"]) and g.area(s["bbox"]) > 0.4 * g.area(k["bbox"]) for k in kept):
            continue
        if any(g.inside(s["bbox"], k["bbox"]) for k in kept):
            # A smaller shape inside a kept box is the tick mark itself, not another box.
            continue
        kept.append(s)
    for s in kept:
        s["fill"] = round(_fill_ratio(binary, s["bbox"]), 3)
    # Solid squares/discs are bullets, not boxes.
    return [s for s in kept if s["fill"] < 0.85]


def detect(img):
    """Return checkboxes, single input boxes, grids (tables / form grids) and underlines."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    page_h, page_w = gray.shape
    binary = binarize(gray)
    horiz, vert = _line_masks(binary)
    grid = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8), iterations=1)

    cells = _cells(grid, page_w, page_h)
    gap = max(8.0, 0.008 * page_w)
    boxes, grids, ticks = [], [], []
    tick_lo, tick_hi = max(10, 0.006 * page_w), 0.03 * page_w
    for group in _group_cells(cells, gap):
        if len(group) == 1:
            b = group[0]
            if _is_square(b, tick_lo, tick_hi):
                ticks.append({"bbox": b, "kind": "checkbox", "fill": round(_fill_ratio(binary, b), 3)})
            else:
                boxes.append({"bbox": b, "comb": False})
            continue
        structured, n_rows, n_cols = _structure(group)
        bbox = g.union(group)
        small_squares = all(_is_square(c, tick_lo, 0.06 * page_w) for c in group)
        if n_rows == 1 and n_cols >= 3 and small_squares:
            # Character "comb" boxes: one box per letter, read as a single field.
            boxes.append({"bbox": bbox, "comb": True})
            continue
        grids.append({"bbox": bbox, "cells": structured, "n_rows": n_rows, "n_cols": n_cols})

    hlines = []
    structures = [b["bbox"] for b in boxes] + [gr["bbox"] for gr in grids]
    contours, _ = cv2.findContours(horiz, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 0.04 * page_w or h > 0.02 * page_h:
            continue
        b = [float(x), float(y), float(x + w), float(y + h)]
        if any(g.inside(b, g.expand(s, 6)) for s in structures):
            continue
        hlines.append({"bbox": b})

    found = _tick_boxes(binary, page_w)
    for t in found:
        if any(g.iou(t["bbox"], k["bbox"]) > 0.5 for k in ticks):
            continue
        if any(g.inside(t["bbox"], gr["bbox"]) and not _in_cell_with_room(t, gr) for gr in grids):
            continue
        # The squares of a letter-box ("comb") field, or a box the tick fills, are not tick boxes.
        if any(g.inside(t["bbox"], b["bbox"]) and (b["comb"] or g.area(b["bbox"]) < 4 * g.area(t["bbox"])) for b in boxes):
            continue
        ticks.append(t)

    return {
        "width": page_w,
        "height": page_h,
        "checkboxes": ticks,
        "boxes": boxes,
        "grids": grids,
        "hlines": sorted(hlines, key=lambda h: (h["bbox"][1], h["bbox"][0])),
        "binary": binary,
    }


def _in_cell_with_room(tick, grid):
    """A tick box drawn inside a (much larger) table cell is still a tick box."""
    for cell in grid["cells"]:
        if g.inside(tick["bbox"], cell["bbox"]):
            return g.area(cell["bbox"]) > 4 * g.area(tick["bbox"])
    return True


def fill_ratio(binary, bbox):
    return _fill_ratio(binary, bbox)
