"""Excel route on the client's workbooks: template structure, and filling from filled copies."""
import copy
import re

import pytest

from app.ocr.formats import UploadedFile, build_registry
from app.ocr.values import plain

from . import client_samples as cs

pytestmark = pytest.mark.skipif(not cs.available(), reason="client samples (tests/ocr/samples/client) not present")

EXPECTED = {
    "daily": {
        "header": "DAILY CHECKLIST",
        "fields": {"Work Station": "TextInput", "Month": "TextInput", "Equipment Number": "TextInput", "Location": "TextInput"},
        "tables": [(35, 2, 16)],  # leaf columns, header rows, body rows
    },
    "change": {
        "header": "Document Creation / Change Request",  # the title, not the letterhead
        "fields": {
            "Dept.": "TextInput", "Date": "DatePicker", "Revision required for": "TextInput",
            "Type of Document": "TextInput", "Document Number": "TextInput", "Revision in force": "TextInput",
            "Details of doc. Creation / Change": "TextArea", "Reason for doc. Creation / Change": "TextArea",
            "Requester Name": "TextInput", "Req.HOD Name": "TextInput", "Requester Sign": "Signature",
            "Changes Done": "TextInput", "Update": "TextArea", "Addition": "TextArea", "Deletion": "TextArea",
            "Date of Revision": "DatePicker", "Changes Approved By (M.R.)": "TextArea",
        },
        "tables": [(5, 1, 4), (5, 1, 3), (4, 1, 1)],  # distribution list, disposition, revision history
    },
    "ifc": {
        "header": "DAILY INITIAL FLOW MANAGEMENT CONTROL ITEMS MONITORING",
        "fields": {"PART NO.": "TextInput", "Model": "TextInput", "DATE": "DatePicker"},
        "tables": [(38, 2, 26)],  # as the scan reads it: no row made of merged cells only
    },
}


@pytest.fixture(scope="module")
def handler():
    return build_registry("excel").get("excel")


@pytest.fixture(scope="module")
def templates(handler):
    out = {}
    for key, ext in cs.EXCEL_EXT.items():
        up = UploadedFile(cs.read(key, ext), cs.SAMPLES[key] + ext)
        out[key] = handler.build_template(up)
    return out


def by_label(task_data):
    return {plain(e.get("label", "")): e for e in task_data if e.get("field_name") and e.get("label")}


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_template_structure(templates, key):
    result, want = templates[key], EXPECTED[key]
    td = result["task_data"]
    labels = by_label(td)
    for label, kind in want["fields"].items():
        assert label in labels, f"missing {label}"
        assert labels[label]["element"] == kind, label
        assert labels[label]["excel"]["cell"]
    shapes = [(len(e["columns"]), len(e["header"]), len(e["rows"])) for e in td if e["element"] == "Table"]
    assert shapes == want["tables"]
    headers = [plain(e["content"]) for e in td if e["element"] == "Header"]
    assert len(headers) == 1 and headers[0].startswith(want["header"])
    page = result["document"]["pages"][0]
    assert page["image"] is None and page["lines"] and page["tables"]


def test_daily_table_layout(templates):
    table = next(e for e in templates["daily"]["task_data"] if e["element"] == "Table")
    top = [c.get("text") for c in table["header"][0] if not c.get("covered")]
    assert top[:5] == ["Sr.\nNo.", "Check points", "Criteria", "Shift", "DATE"]
    assert table["header"][0][4]["colspan"] == 31  # DATE over the 31 day columns
    assert [c["text"] for c in table["columns"][4:7]] == ["1", "2", "3"]
    first = table["rows"][0]["cells"]
    assert first[1]["text"].startswith("Check the lights") and first[1]["rowspan"] == 3
    assert first[3]["text"] == "1st" and first[4] == {"input": "text"}


def test_logo_is_kept(templates):
    images = [e for e in templates["daily"]["task_data"] if e["element"] == "Image"]
    assert len(images) == 1 and images[0]["src"].startswith("data:image/")


def _fill(key, td, values):
    data = cs.read(key, cs.EXCEL_EXT[key])
    return cs.fill_xls(data, td, values) if cs.EXCEL_EXT[key] == ".xls" else cs.fill_xlsx(data, td, values)


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_fill_from_filled_workbook(handler, templates, key):
    td = templates[key]["task_data"]
    values = cs.plan(td)
    filled = _fill(key, td, values)
    result = handler.extract(UploadedFile(filled, "filled" + cs.EXCEL_EXT[key]), td)
    expected = cs.expected_answers(td, values)
    assert expected
    wrong = {k: (result["answers"].get(k), v) for k, v in expected.items() if result["answers"].get(k) != v}
    assert wrong == {}
    assert all(f["method"] in ("cell", "none") for f in result["fields"])


@pytest.mark.parametrize("key", list(cs.SAMPLES))
def test_fill_by_labels_only(handler, templates, key):
    """A template without cell addresses (e.g. drawn in the builder) is matched by labels/headings."""
    td = templates[key]["task_data"]
    values = cs.plan(td)
    filled = _fill(key, td, values)
    bare = copy.deepcopy(td)
    for e in bare:
        e.pop("excel", None)
        e.pop("ocr", None)
    result = handler.extract(UploadedFile(filled, "filled" + cs.EXCEL_EXT[key]), bare)
    labels = [plain(e.get("label", "")) for e in bare if e.get("field_name")]
    expected = cs.expected_answers(td, values)
    # Labels that are not unique on the sheet ("Sign", "Date of Revision (2)") cannot be told apart by text.
    unique = {e["field_name"] for e in bare if e.get("field_name") and labels.count(plain(e.get("label", ""))) == 1
              and not re.search(r"\(\d+\)$", plain(e.get("label", "")))}
    wrong = {k: (result["answers"].get(k), v) for k, v in expected.items() if k in unique and result["answers"].get(k) != v}
    assert wrong == {}
