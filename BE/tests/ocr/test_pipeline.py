"""End-to-end with the real PaddleOCR models (slow: a few seconds per page)."""
import copy

import pytest

from app.ocr.extract import extract
from app.ocr.pipeline import analyze, document_json
from app.ocr.template import build_template

from .synthetic import ANSWERS, draw_form, png_bytes


@pytest.fixture(scope="module")
def blank():
    return analyze(png_bytes(draw_form()), "blank.png")


@pytest.fixture(scope="module")
def filled():
    return analyze(png_bytes(draw_form(filled=True)), "filled.png")


@pytest.fixture(scope="module")
def template(blank):
    return build_template(blank[0])["task_data"]


def by_label(task_data):
    from app.ocr.values import plain

    return {plain(e.get("label", "")): e for e in task_data if e.get("field_name") and "label" in e}


def test_template_elements(template):
    labels = by_label(template)
    assert labels["Full Name"]["element"] == "TextInput"
    assert labels["Email"]["element"] == "EmailInput"
    assert labels["Date of Birth"]["element"] == "DatePicker"
    assert labels["Phone"]["element"] == "PhoneNumber"
    assert labels["Address"]["element"] == "TextArea"
    assert labels["Signature"]["element"] == "Signature"
    gender = labels["Gender"]
    assert gender["element"] == "Checkboxes"
    assert [o["text"] for o in gender["options"]] == ["Male", "Female"]
    table = labels["Education Details"]
    assert table["element"] == "Table"
    assert [c["text"] for c in table["columns"]] == ["Degree", "Year", "University"]
    assert len(table["rows"]) == 2
    headers = [e for e in template if e["element"] == "Header"]
    assert headers and "EMPLOYEE REGISTRATION FORM" in headers[0]["content"]


def test_template_layout(template):
    # Date of Birth and Phone share a row -> two-column container holding both.
    rows = [e for e in template if e["element"] == "TwoColumnRow"]
    assert len(rows) == 1
    children = [next(x for x in template if x["id"] == cid) for cid in rows[0]["childItems"]]
    assert [c["element"] for c in children] == ["DatePicker", "PhoneNumber"]
    assert all(c["parentId"] == rows[0]["id"] for c in children)
    top = [e for e in template if not e.get("parentId")]
    assert template[: len(top)] == top  # top-level elements first, like the store's updateOrder


def _check(result, template):
    labels = by_label(template)
    a = result["answers"]
    assert a[labels["Full Name"]["field_name"]] == ANSWERS["Full Name"]
    assert a[labels["Email"]["field_name"]] == ANSWERS["Email"]
    assert a[labels["Date of Birth"]["field_name"]] == "03/14/1992"  # DatePicker mask MM/dd/yyyy
    assert a[labels["Phone"]["field_name"]] == ANSWERS["Phone"]
    assert a[labels["Address"]["field_name"]] == ANSWERS["Address"]
    female = next(o["key"] for o in labels["Gender"]["options"] if o["text"] == "Female")
    assert a[labels["Gender"]["field_name"]] == [female]
    assert a[labels["Education Details"]["field_name"]] == ANSWERS["table"]


def test_extract_zone_mode(template, filled):
    result = extract(template, *filled)
    assert result["alignment"][0]["method"] == "anchors"
    _check(result, template)
    sig = by_label(template)["Signature"]["field_name"]
    assert len(result["answers"][sig]) > 100  # base64 PNG of the signature strokes
    methods = {f["label"]: f["method"] for f in result["fields"]}
    assert methods["Full Name"] == "zone"


def test_extract_label_mode(template, filled):
    # Same form designed by hand in the builder: no ocr boxes at all.
    plain_form = copy.deepcopy(template)
    for e in plain_form:
        e.pop("ocr", None)
        for o in e.get("options") or []:
            o.pop("ocr", None)
    result = extract(plain_form, *filled)
    _check(result, plain_form)
    methods = {f["label"]: f["method"] for f in result["fields"]}
    assert methods["Full Name"] == "label"


def test_document_json(filled):
    doc = document_json(*filled)
    assert "Priya Sharma" in doc["text"]
    page = doc["pages"][0]
    assert page["image"].startswith("data:image/jpeg;base64,")
    assert sum(1 for c in page["checkboxes"] if c["checked"]) == 1
    assert page["tables"][0]["n_cols"] == 3
