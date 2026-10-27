"""
The template designer's Table / Grid and the OCR import that produces it.

The designer's table (the vendored form builder's `Table` element) has heading
rows over body rows of printed text and cells to fill in, with merged cells.
Every input cell is one field, named by its row's printed text (including a
merged cell above that spans into the row) and its column heading, keyed by
row and column so a filled value finds its cell. A number cell carries its own
limits; a tick cell (✓ / ✗) is judged OK / N-OK.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ocr.formats import UploadedFile, build_registry
from app.services import form_layout as layouts
from app.services.record_service import missing_required

from tests.test_qms_api import _login, client, world  # noqa: F401  (fixtures)

SAMPLES = Path(__file__).parent / "ocr" / "samples" / "client"

TABLE = {
    "id": "t1",
    "element": "Table",
    "field_name": "table_abc",
    "label": "Control items",
    "columns": [
        {"key": "c_no", "text": "No."},
        {"key": "c_item", "text": "Check point"},
        {"key": "c_shift", "text": "Shift"},
        {"key": "c_reading", "text": "Reading", "title": "Torque Reading"},
        {"key": "c_ok", "text": "OK / N-OK"},
    ],
    "header": [[{"text": "No."}, {"text": "Check point"}, {"text": "Shift"}, {"text": "Reading"}, {"text": "OK / N-OK"}]],
    "rows": [
        {"key": "r1", "cells": [
            {"text": "1", "rowspan": 2}, {"text": "Bolt torque", "rowspan": 2}, {"text": "1st"},
            {"input": "number", "spec_min": 20, "spec_max": 25, "unit": "Nm"}, {"input": "check"}]},
        {"key": "r2", "cells": [
            {"covered": True}, {"covered": True}, {"text": "2nd"},
            {"input": "number", "spec_min": 0, "spec_max": 0.05}, {"input": "check", "required": True}]},
    ],
}


def test_every_input_cell_is_a_field_named_by_its_row_and_column():
    fields = {f["layout_key"]: f for f in layouts.to_fields([TABLE])}

    assert set(fields) == {
        "table_abc:r1:c_reading", "table_abc:r1:c_ok",
        "table_abc:r2:c_reading", "table_abc:r2:c_ok",
    }
    first = fields["table_abc:r1:c_reading"]
    assert first["label"] == "1 · Bolt torque · 1st - Torque Reading"
    assert (first["field_type"], first["spec_min"], first["spec_max"], first["unit"]) == ("number", 20, 25, "Nm")
    assert first["help_text"] == "Control items"
    # the second row is under the merged "1 / Bolt torque" cells: it is named by them too
    assert fields["table_abc:r2:c_reading"]["label"] == "1 · Bolt torque · 2nd - Torque Reading"
    # a limit of 0 is a limit
    assert fields["table_abc:r2:c_reading"]["spec_min"] == 0


def test_a_table_cell_is_required_only_when_marked_its_limits_only_judge_it():
    """A monthly sheet has a column per day with the same limits in each; a record fills the days that have come."""
    fields = {f["layout_key"]: f for f in layouts.to_fields([TABLE])}

    reading = fields["table_abc:r1:c_reading"]
    assert (reading["spec_min"], reading["spec_max"], reading["required"]) == (20, 25, False)
    tick = fields["table_abc:r1:c_ok"]
    assert (tick["field_type"], tick["options"], tick["spec_text"]) == ("select", ["OK", "N-OK"], "OK")
    assert tick["required"] is False
    assert fields["table_abc:r2:c_ok"]["required"] is True  # marked Required


def test_a_table_of_printed_text_only_is_a_problem():
    printed = {**TABLE, "rows": [{"key": "r1", "cells": [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}, {"text": "e"}]}]}
    assert any("Make at least one cell an input" in p for p in layouts.problems([printed]))
    assert layouts.problems([TABLE]) == []


def test_on_a_designed_form_the_field_decides_whether_an_entry_is_required():
    def row(label, value, required, spec_text=None, layout_key="k", spec_min=None):
        return SimpleNamespace(label=label, value=value, spec_min=spec_min, spec_max=None, spec_text=spec_text,
                               layout_key=layout_key, field=SimpleNamespace(required=required))

    record = SimpleNamespace(values=[
        row("Tick, judged but optional", None, False, "OK"),
        row("Serial, switched to Required", None, True),
        row("Filled", "x", True),
        # a classic field list (no layout key): an entry with a specification is required
        row("Classic, with a limit", "", True, layout_key=None, spec_min=1),
        row("Classic, without a limit", "", True, layout_key=None),
    ])
    assert missing_required(record) == ["Serial, switched to Required", "Classic, with a limit"]


def test_what_each_designer_element_requires():
    number = {"id": "n", "element": "NumberInput", "field_name": "n1", "label": "Pressure", "spec_min": 1, "required": False}
    text = {"id": "t", "element": "TextInput", "field_name": "t1", "label": "Serial", "required": True}
    note = {"id": "x", "element": "TextInput", "field_name": "x1", "label": "Note", "required": False}
    grid = {"id": "g", "element": "CustomElement", "key": "TableGrid", "field_name": "g1", "label": "Old table",
            "columns": [{"id": "c1", "name": "Item", "kind": "fixed"}, {"id": "c2", "name": "Reading", "type": "number", "kind": "input"}],
            "rows": [{"id": "r1", "cells": {"c1": "Bore"}, "spec_min": 1}, {"id": "r2", "cells": {"c1": "Finish"}}]}
    required = {f["layout_key"]: f["required"] for f in layouts.to_fields([number, text, note, grid])}
    assert required == {
        "n1": True,          # a limit makes a reading required, whatever the switch says
        "t1": True,          # switched on
        "x1": False,
        "g1:r1:c2": True,    # the earlier table, as it always worked: required where it has a limit
        "g1:r2:c2": False,
    }


@pytest.mark.parametrize("name", ["Daily check sheet.xlsx", "IFC Check Sheet.xlsx"])
def test_a_client_check_sheet_imports_as_distinct_fields(name):
    upload = UploadedFile(data=(SAMPLES / name).read_bytes(), filename=name)
    task_data = build_registry("excel").get("excel").build_template(upload)["task_data"]

    assert any(e["element"] == "Table" for e in task_data)
    fields = layouts.to_fields(task_data)
    labels = [f["label"] for f in fields]
    assert len(labels) > 100  # a column per day of the month
    assert len(set(labels)) == len(labels)
    assert not [label for label in labels if label.endswith(")")]  # no "(2)" clashes
    assert max(len(label) for label in labels) <= 200
    assert layouts.problems(task_data) == []


def test_importing_a_document_is_template_authoring(client, world):
    data = (SAMPLES / "IFC Check Sheet.xlsx").read_bytes()
    files = {"file": ("IFC Check Sheet.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    _login(client, world["names"]["po"])
    assert client.post("/api/ocr/template", files=files).status_code == 403
    formats = client.get("/api/ocr/formats")
    assert formats.status_code == 200 and "excel" in {f["key"] for f in formats.json()["formats"]}

    _login(client, world["names"]["admin"])
    made = client.post("/api/ocr/template", files=files)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["stats"]["table"] == 1 and body["document"]["pages"]

    # the imported elements save as a template whose fields come from the table
    saved = client.post("/api/formats/", json={
        "code": "QF-PQ-IFC", "title": "IFC check sheet", "frequency": "daily",
        "team_id": world["team_id"], "layout": body["task_data"], "fields": [],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["field_count"] > 100
    assert saved.json()["readiness"] == []


def test_upload_errors_are_explained(client, world):
    _login(client, world["names"]["admin"])
    empty = client.post("/api/ocr/template", files={"file": ("x.xlsx", b"", "application/octet-stream")})
    assert empty.status_code == 400
    wrong = client.post("/api/ocr/template", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert wrong.status_code == 415


def test_a_template_without_a_code_gets_its_teams_next_one(client, world):
    _login(client, world["names"]["admin"])
    team = world["team_id"]
    suggested = client.get("/api/formats/next-code", params={"team_id": team})
    assert suggested.status_code == 200, suggested.text
    code = suggested.json()["code"]
    assert code.startswith("QF-") and code[-3:].isdigit()

    made = client.post("/api/formats/", json={"title": "Coded by the server", "frequency": "daily", "team_id": team,
                                              "fields": [{"label": "Reading", "field_type": "number"}]})
    assert made.status_code == 200, made.text
    assert made.json()["code"] == code
    # the next one moves on, and a code in use is never handed out again
    after = client.get("/api/formats/next-code", params={"team_id": team}).json()["code"]
    assert int(after[-3:]) == int(code[-3:]) + 1
