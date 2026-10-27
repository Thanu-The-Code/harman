"""The client's sample forms (tests/ocr/samples/client) and helpers to make filled copies with known answers.

Filled copies are generated from a template: every field and some table cells get a value,
written either into the workbook cells (Excel route) or drawn with a handwriting font into
the scanned page at the template's value boxes (OCR route).
"""
import io
import os
from datetime import date

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.ocr import tables
from app.ocr import values as v
from app.ocr.results import value_fields

ROOT = os.path.join(os.path.dirname(__file__), "samples", "client")
SAMPLES = {
    "daily": "Daily check sheet",
    "change": "HPU-F-MR-04_Document _Creation_Change Request",
    "ifc": "IFC Check Sheet",
}
EXCEL_EXT = {"daily": ".xlsx", "change": ".xls", "ifc": ".xlsx"}
WORDS = ["Alpha", "Bravo", "Delta", "Kilo", "Lima", "Oscar", "Sierra", "Tango", "Victor", "Zulu"]
PEN = (25, 45, 150)


def path(key, ext):
    return os.path.join(ROOT, SAMPLES[key] + ext)


def read(key, ext):
    with open(path(key, ext), "rb") as fh:
        return fh.read()


def available():
    return os.path.isdir(ROOT) and all(os.path.exists(path(k, EXCEL_EXT[k])) for k in SAMPLES)


# ---- what to write and what should come back ---------------------------------------------

def plan(task_data, table_cells=6, scan=False):
    """{field_name: (value to write, expected answer)}; tables: (grid to write, expected grid).

    scan=True: "Label: value" cells already printed on the form are not written over; the
    printed value is what a scan should give back.
    """
    out = {}
    for n, e in enumerate(value_fields(task_data)):
        kind = e["element"]
        sample = (e.get("ocr") or {}).get("sample")
        if scan and sample:
            out[e["field_name"]] = (None, sample)
            continue
        if kind == "Table":
            rows = tables.body(e)
            write = [["" for _ in r] for r in rows]
            marks = ["✓", "✗", "1050"]
            placed = 0
            for r, row in enumerate(rows):
                for c, cell in enumerate(row):
                    if tables.is_input(cell) and placed < table_cells and r < 4:
                        write[r][c] = marks[placed % len(marks)]
                        placed += 1
            out[e["field_name"]] = (write, write if placed else None)
        elif kind == "DatePicker":
            d = date(2025, 3, 13 + n % 12)
            out[e["field_name"]] = (d, v.format_date(d, v.date_mask(e)))
        elif kind == "NumberInput":
            out[e["field_name"]] = (str(120 + n), str(120 + n))
        elif kind == "PhoneNumber":
            out[e["field_name"]] = (f"98765432{n % 10}{(n + 3) % 10}",) * 2
        elif kind == "EmailInput":
            out[e["field_name"]] = (f"user{n}@mail.com",) * 2
        elif kind in ("TextInput", "TextArea"):
            word = f"{WORDS[n % len(WORDS)]} {n}"
            out[e["field_name"]] = (word, word)
    return out


def expected_answers(task_data, values):
    return {k: exp for k, (_, exp) in values.items() if exp is not None}


# ---- filled workbooks ---------------------------------------------------------------------

def _cells_to_write(task_data, values):
    """[(sheet, ref, value)] for every planned value with a remembered cell."""
    writes = []
    for e in value_fields(task_data):
        meta = e.get("excel") or {}
        if e["field_name"] not in values or not meta:
            continue
        value = values[e["field_name"]][0]
        if e["element"] == "Table":
            for r, row in enumerate(value):
                for c, cell in enumerate(row):
                    ref = meta["cells"][r][c] if cell else None
                    if ref:
                        writes.append((meta["sheet"], ref.split(":")[0], cell))
        elif meta.get("cell"):
            if meta.get("inline"):
                value = f"{v.plain(e['label'])} : {value}"
            writes.append((meta["sheet"], meta["cell"].split(":")[0], value))
    return writes


def fill_xlsx(data, task_data, values):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data))
    for sheet, ref, value in _cells_to_write(task_data, values):
        wb[sheet][ref].value = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def fill_xls(data, task_data, values):
    import xlrd
    import xlwt
    from xlutils.copy import copy

    rb = xlrd.open_workbook(file_contents=data, formatting_info=True)
    wb = copy(rb)
    style = xlwt.easyxf("borders: left thin, right thin, top thin, bottom thin")
    date_style = xlwt.easyxf("borders: left thin, right thin, top thin, bottom thin", num_format_str="DD-MM-YYYY")
    names = [s.name for s in rb.sheets()]
    from openpyxl.utils.cell import coordinate_to_tuple
    for sheet, ref, value in _cells_to_write(task_data, values):
        r, c = coordinate_to_tuple(ref)
        ws = wb.get_sheet(names.index(sheet))
        ws.write(r - 1, c - 1, value, date_style if isinstance(value, date) else style)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---- filled scans ---------------------------------------------------------------------------

def _font(size):
    return ImageFont.truetype("C:/Windows/Fonts/Inkfree.ttf", max(12, int(size)))


def _mark(d, box, kind):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    s = min(w, h) * 0.5
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    width = max(2, int(s / 8))
    if kind == "✓":
        d.line([(cx - s * 0.5, cy), (cx - s * 0.1, cy + s * 0.45), (cx + s * 0.55, cy - s * 0.5)], fill=PEN, width=width)
    else:
        d.line([(cx - s * 0.45, cy - s * 0.45), (cx + s * 0.45, cy + s * 0.45)], fill=PEN, width=width)
        d.line([(cx - s * 0.45, cy + s * 0.45), (cx + s * 0.45, cy - s * 0.45)], fill=PEN, width=width)


def _text(d, box, text):
    x0, y0, x1, y1 = box
    size = min(36, (y1 - y0) * 0.75)  # handwriting fills most of a row...
    while size > 12 and _font(size).getlength(text) > (x1 - x0) - 12:
        size -= 1  # ...but stays inside its cell
    d.text((x0 + 6, (y0 + y1) / 2), text, font=_font(size), fill=PEN, anchor="lm")


def draw_scan(images, task_data, values):
    """Draw the planned values into copies of the template's page images (zone positions)."""
    pages = [Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) for img in images]
    draws = [ImageDraw.Draw(p) for p in pages]
    for e in value_fields(task_data):
        o = e.get("ocr") or {}
        if e["field_name"] not in values or "page" not in o:
            continue
        p = o["page"]
        w, h = o["page_size"]
        value = values[e["field_name"]][0]
        if value is None:
            continue
        if e["element"] == "Table":
            for r, row in enumerate(value):
                for c, cell in enumerate(row):
                    nb = o["cell_bboxes"][r][c]
                    if cell and nb:
                        box = [nb[0] * w, nb[1] * h, nb[2] * w, nb[3] * h]
                        _mark(draws[p], box, cell) if cell in ("✓", "✗") else _text(draws[p], box, cell)
            continue
        nb = o.get("value_bbox")
        if not nb:
            continue
        box = [nb[0] * w, nb[1] * h, nb[2] * w, nb[3] * h]
        if o.get("inline") and o.get("label_bbox"):
            lb = [o["label_bbox"][0] * w, o["label_bbox"][1] * h, o["label_bbox"][2] * w, o["label_bbox"][3] * h]
            if box[3] - box[1] > 2.2 * (lb[3] - lb[1]):
                box[1] = lb[3] + 4  # tall cell: write under the printed label
            else:
                box[0] = max(box[0], lb[2] + 10)  # write after the printed label
        text = value.strftime("%d/%m/%Y") if isinstance(value, date) else str(value)
        if e["element"] == "TextArea":
            box[3] = box[1] + min(box[3] - box[1], 60)
        _text(draws[p], box, text)
    return [cv2.cvtColor(np.array(p), cv2.COLOR_RGB2BGR) for p in pages]


def to_jpg(img, q=90):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes()
