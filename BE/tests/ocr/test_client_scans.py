"""OCR route on the client's forms: templates from the blank PDFs, filling from drawn-in scans,
and cross-format filling (template from the Excel workbook, values from a scan). Slow."""
import copy
import re

import cv2
import pytest

from app.ocr.extract import extract
from app.ocr.formats import UploadedFile, build_registry
from app.ocr.loader import pdf_pages
from app.ocr.pipeline import analyze
from app.ocr.template import build_template
from app.ocr.values import plain

from . import client_samples as cs

pytestmark = pytest.mark.skipif(not cs.available(), reason="client samples (tests/ocr/samples/client) not present")
MIN_FIELD_ACCURACY = 0.85
MIN_CELL_ACCURACY = 0.8  # handwritten digits in 1 cm wide cells: an occasional 1050 -> 1051


def scan_like(img):
    """A print-and-scan: slight rotation and scale, JPEG compression."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0.6, 0.97)
    m[0, 2] += 18
    m[1, 2] += 25
    out = cv2.warpAffine(img, m, (w, h), borderValue=(255, 255, 255))
    return cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 80])[1], cv2.IMREAD_COLOR)


@pytest.fixture(scope="module")
def blanks():
    out = {}
    for key in cs.SAMPLES:
        data = cs.read(key, ".pdf")
        pages, images = analyze(data, "blank.pdf")
        out[key] = (build_template(pages)["task_data"], pdf_pages(data))
    return out


@pytest.fixture(scope="module")
def filled(blanks):
    """key -> (values, analysed filled scan) with values drawn at the PDF template's positions."""
    out = {}
    for key, (td, images) in blanks.items():
        values = cs.plan(td, scan=True, table_cells=12)
        drawn = [scan_like(img) for img in cs.draw_scan(images, td, values)]
        pages, imgs = analyze(cs.to_jpg(drawn[0]), "filled.jpg")
        out[key] = (values, pages, imgs)
    return out


def same(a, b):
    """Handwriting OCR may drop the space in 'Bravo 1'; compare without whitespace."""
    squash = lambda x: re.sub(r"\s+", "", str(x)) if x is not None else None  # noqa: E731
    return squash(a) == squash(b)


def accuracy(td, values, answers):
    """(field accuracy, table cell accuracy, misses)."""
    exp = cs.expected_answers(td, values)
    names = {e["field_name"]: plain(e.get("label", "")) for e in td if e.get("field_name")}
    fields_ok = fields_n = cells_ok = cells_n = 0
    misses = []
    for k, want in exp.items():
        got = answers.get(k)
        if isinstance(want, list):
            for r, row in enumerate(want):
                for c, cell in enumerate(row):
                    if cell:
                        cells_n += 1
                        g = got[r][c] if got and r < len(got) and c < len(got[r]) else None
                        cells_ok += same(g, cell)
                        if not same(g, cell):
                            misses.append((names[k], r, c, g, cell))
        else:
            fields_n += 1
            fields_ok += same(got, want)
            if not same(got, want):
                misses.append((names[k], got, want))
    return (fields_ok / fields_n if fields_n else 1.0), (cells_ok / cells_n if cells_n else 1.0), misses


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_template_from_scan_matches_excel_structure(blanks, key):
    td = blanks[key][0]
    excel = build_registry("excel").get("excel")
    xl = excel.build_template(UploadedFile(cs.read(key, cs.EXCEL_EXT[key]), "x" + cs.EXCEL_EXT[key]))["task_data"]
    shape = lambda t: [(len(e["columns"]), len(e["header"])) for e in t if e["element"] == "Table"]  # noqa: E731
    assert shape(td) == shape(xl)
    fields = lambda t: {plain(e["label"]) for e in t if e.get("field_name") and e["element"] not in ("Table",) and e.get("label")}  # noqa: E731
    common = fields(td) & fields(xl)
    assert len(common) >= 0.7 * len(fields(xl)), sorted(fields(xl) - fields(td))


@pytest.mark.parametrize("mode", ["zone", "label"])
@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_fill_from_scan(blanks, filled, key, mode):
    td = blanks[key][0]
    values, pages, imgs = filled[key]
    form = td
    if mode == "label":
        form = copy.deepcopy(td)
        for e in form:
            e.pop("ocr", None)
    result = extract(form, pages, imgs)
    f_acc, c_acc, misses = accuracy(td, values, result["answers"])
    print(f"\n{key}/{mode}: fields {f_acc:.0%}, table cells {c_acc:.0%}, misses: {misses[:12]}")
    if mode == "zone":
        assert f_acc >= MIN_FIELD_ACCURACY and c_acc >= MIN_CELL_ACCURACY, misses
    else:
        # Without positions, duplicate labels ("Sign", "Date of Revision (2)") are ambiguous.
        assert f_acc >= 0.6 and c_acc >= MIN_CELL_ACCURACY, misses


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_excel_template_filled_from_scan(blanks, filled, key):
    """Template built from the workbook; the filled document arrives as a scan."""
    pdf_td = blanks[key][0]
    values, pages, imgs = filled[key]
    excel = build_registry("excel").get("excel")
    xl = excel.build_template(UploadedFile(cs.read(key, cs.EXCEL_EXT[key]), "x" + cs.EXCEL_EXT[key]))["task_data"]
    # Same labels on both templates carry the same expected values.
    by_label = {plain(e.get("label", "")): e["field_name"] for e in pdf_td
                if e.get("field_name") and plain(e.get("label", "")) and e["element"] != "Table"}
    xl_values = {}
    for e in xl:
        src = by_label.get(plain(e.get("label", ""))) if e.get("field_name") and e["element"] != "Table" else None
        if src in values:
            xl_values[e["field_name"]] = values[src]
    tables_pdf = [e for e in pdf_td if e["element"] == "Table"]
    tables_xl = [e for e in xl if e["element"] == "Table"]
    for a, b in zip(tables_pdf, tables_xl):
        if a["field_name"] in values:
            xl_values[b["field_name"]] = values[a["field_name"]]
    result = extract(xl, pages, imgs)
    f_acc, c_acc, misses = accuracy(xl, xl_values, result["answers"])
    print(f"\n{key}/excel-template: fields {f_acc:.0%}, table cells {c_acc:.0%}, alignment {result['alignment']}, misses: {misses[:12]}")
    assert f_acc >= 0.6 and c_acc >= MIN_CELL_ACCURACY, misses
