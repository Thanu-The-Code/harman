"""Reading a filled-in document as a form plus its values in one pass (digitize -> fill / edit)."""
import re

import pytest
from fastapi.testclient import TestClient

from app.ocr.extract import extract
from app.ocr.formats import UploadedFile, build_registry
from app.ocr.loader import pdf_pages
from app.ocr.pipeline import analyze
from app.ocr.template import build_template
from app.ocr.values import plain

from . import client_samples as cs
from .test_client_scans import scan_like

pytestmark = pytest.mark.skipif(not cs.available(), reason="client samples (tests/ocr/samples/client) not present")


def squash(x):
    return re.sub(r"\s+", "", str(x)) if x is not None else None


def by_label(fields):
    return {f["label"]: f["value"] for f in fields}


@pytest.fixture(scope="module")
def excel():
    return build_registry("excel").get("excel")


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_filled_workbook_reads_back_as_form_and_values(excel, key):
    ext = cs.EXCEL_EXT[key]
    blank = excel.build_template(UploadedFile(cs.read(key, ext), "x" + ext))["task_data"]
    values = cs.plan(blank)
    data = cs.read(key, ext)
    filled = cs.fill_xls(data, blank, values) if ext == ".xls" else cs.fill_xlsx(data, blank, values)
    result = excel.read_form(UploadedFile(filled, "filled" + ext))
    assert set(result) >= {"task_data", "answers", "fields", "document"}
    got = by_label(result["fields"])
    want = {plain(e["label"]): values[e["field_name"]][1] for e in blank
            if e.get("field_name") in values and e["element"] != "Table" and values[e["field_name"]][1] is not None}
    wrong = {k: (got.get(k, "<no field>"), v) for k, v in want.items() if squash(got.get(k)) != squash(v)}
    assert wrong == {}
    # Tables: the filled rows are values in input cells, not headings or fixed text.
    for b, r in zip([e for e in blank if e["element"] == "Table"], [e for e in result["task_data"] if e["element"] == "Table"]):
        assert (len(b["columns"]), len(b["rows"])) == (len(r["columns"]), len(r["rows"]))
        planned = values.get(b["field_name"], (None, None))[1]
        if planned:
            assert result["answers"][r["field_name"]][0][:8] == [c for c in planned[0][:8]]


@pytest.mark.parametrize("key", ["daily", "change"])
def test_filled_scan_reads_back_as_form_and_values(key):
    data = cs.read(key, ".pdf")
    blank = build_template(analyze(data, "blank.pdf")[0])["task_data"]
    values = cs.plan(blank, scan=True, table_cells=12)
    drawn = scan_like(cs.draw_scan(pdf_pages(data), blank, values)[0])
    pages, images = analyze(cs.to_jpg(drawn), "filled.jpg")
    template = build_template(pages, filled=True)
    result = extract(template["task_data"], pages, images)
    got = by_label(result["fields"])
    want = {plain(e["label"]): values[e["field_name"]][1] for e in blank
            if e.get("field_name") in values and e["element"] != "Table"}
    ok = sum(1 for k, v in want.items() if squash(got.get(k)) == squash(v))
    assert ok >= 0.8 * len(want), {k: (got.get(k), v) for k, v in want.items() if squash(got.get(k)) != squash(v)}
    assert "DAILY CHECKLIST" not in [str(v) for v in got.values()]  # the title is never a value


def test_read_form_endpoint():
    from .api_app import app

    client = TestClient(app)
    with open(cs.path("change", ".xls"), "rb") as fh:
        r = client.post("/ocr/read-form", files={"file": ("form.xls", fh.read(), "application/vnd.ms-excel")})
    assert r.status_code == 200
    body = r.json()
    assert body["task_data"] and body["document"]["pages"]
    formats = client.get("/ocr/formats").json()["formats"]
    assert all("read_form" in f["capabilities"] for f in formats)
