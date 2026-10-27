"""File -> page images -> (shapes + OCR) -> page models, plus the JSON shown to the browser."""
import base64

import cv2

from . import engine
from . import geometry as g
from .document import build_page, page_text
from .extract import CHECKED_FILL
from .loader import deskew, load_pages
from .shapes import detect

PREVIEW_WIDTH = 1200


def analyze(data, filename, recognize=None, page_loader=None):
    """page_loader(data) -> [BGR image]; defaults to sniffing PDF vs image."""
    recognize = recognize or engine.recognize
    images, pages = [], []
    loaded = page_loader(data) if page_loader else load_pages(data, filename)
    for img in loaded:
        img = deskew(img)
        page = build_page(recognize(img), detect(img))
        images.append(img)
        pages.append(page)
    return pages, images


def _preview(img):
    h, w = img.shape[:2]
    if w > PREVIEW_WIDTH:
        img = cv2.resize(img, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii") if ok else None


def document_json(pages, images, with_images=True):
    out = []
    for i, (page, img) in enumerate(zip(pages, images)):
        w, h = page["width"], page["height"]
        lines = page["lines"]
        tables = []
        for grid in page["grids"]:
            cells = []
            for c in grid["cells"]:
                text = " ".join(l["text"] for l in lines if g.contains_point(c["bbox"], g.center(l["bbox"])))
                cells.append({**{k: c[k] for k in ("row", "col", "rowspan", "colspan")}, "bbox": g.normalize(c["bbox"], w, h), "text": text})
            tables.append({"bbox": g.normalize(grid["bbox"], w, h), "n_rows": grid["n_rows"], "n_cols": grid["n_cols"], "cells": cells})
        out.append({
            "index": i,
            "width": w,
            "height": h,
            "image": _preview(img) if with_images else None,
            "lines": [{"text": l["text"], "conf": round(l["conf"], 3), "bbox": g.normalize(l["bbox"], w, h)} for l in lines],
            "checkboxes": [
                {"bbox": g.normalize(t["bbox"], w, h), "kind": t["kind"], "checked": t["fill"] >= CHECKED_FILL}
                for t in page["checkboxes"]
            ],
            "tables": tables,
            "text": page_text(page),
        })
    return {"pages": out, "text": "\n\n".join(p["text"] for p in out)}
