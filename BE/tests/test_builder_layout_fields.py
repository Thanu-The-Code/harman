"""
A template drawn in the React Form Builder records exactly what it shows.

The designer saves the builder's own items as the layout. Every item that
records something becomes a field carrying a `layout_key`, so a filled value is
matched to its place on the form rather than by a label the builder repeats
("Placeholder Label"). A Table / Grid records one field per row and recorded
column, judged against that row's limits.
"""
from app.services import form_layout as layouts

from tests.test_qms_api import _login, client, world  # noqa: F401  (fixtures)

TABLE = {
    "id": "t1",
    "element": "CustomElement",
    "key": "TableGrid",
    "field_name": "table_grid_abc",
    "label": "<b>Control items</b>",
    "columns": [
        {"id": "c_stage", "name": "STAGE", "type": "text", "kind": "fixed"},
        {"id": "c_item", "name": "CONTROL ITEM", "type": "text", "kind": "fixed"},
        {"id": "c_reading", "name": "READING", "type": "number", "kind": "input"},
        {"id": "c_visual", "name": "VISUAL", "type": "dropdown", "kind": "input"},
    ],
    "rows": [
        {"id": "r1", "cells": {"c_stage": "Incoming", "c_item": "Bore"},
         "unit": "mm", "spec_min": 24.9, "spec_max": 25.1},
        {"id": "r2", "cells": {"c_stage": "Incoming", "c_item": "Faceplate"}},
    ],
}

LAYOUT = [
    {"id": "h1", "element": "Header", "content": "Dimensional check"},
    {"id": "n1", "element": "NumberInput", "field_name": "number_input_1",
     "label": "<p>Bore&nbsp;diameter</p>", "unit": "mm", "spec_min": 24.9, "spec_max": 25.1},
    {"id": "n2", "element": "TextInput", "field_name": "text_input_1",
     "label": "Placeholder Label"},
    {"id": "n3", "element": "TextInput", "field_name": "text_input_2",
     "label": "Placeholder Label"},
    {"id": "d1", "element": "Dropdown", "field_name": "dropdown_1", "label": "Shift",
     "options": [{"value": "a", "text": "A", "key": "k1"}, {"value": "b", "text": "B", "key": "k2"}]},
    TABLE,
]


def test_builder_items_become_fields_with_keys_specs_and_options():
    fields = layouts.to_fields(LAYOUT)
    by_key = {f["layout_key"]: f for f in fields}

    # presentation elements record nothing; rich-text labels are flattened
    assert "Dimensional check" not in [f["label"] for f in fields]
    bore = by_key["number_input_1"]
    assert bore["label"] == "Bore diameter"
    assert (bore["field_type"], bore["unit"], bore["spec_min"], bore["spec_max"]) == (
        "number", "mm", 24.9, 25.1)

    # repeated labels stay distinct, and the keys tell them apart regardless
    assert by_key["text_input_1"]["label"] == "Placeholder Label"
    assert by_key["text_input_2"]["label"] == "Placeholder Label (2)"

    assert by_key["dropdown_1"]["field_type"] == "select"
    assert by_key["dropdown_1"]["options"] == ["A", "B"]


def test_a_table_grid_records_each_row_and_recorded_column():
    fields = {f["layout_key"]: f for f in layouts.to_fields([TABLE])}

    assert set(fields) == {
        "table_grid_abc:r1:c_reading", "table_grid_abc:r1:c_visual",
        "table_grid_abc:r2:c_reading", "table_grid_abc:r2:c_visual",
    }
    reading = fields["table_grid_abc:r1:c_reading"]
    assert reading["label"] == "Incoming · Bore - READING"
    assert (reading["field_type"], reading["spec_min"], reading["spec_max"], reading["unit"]) == (
        "number", 24.9, 25.1, "mm")
    assert reading["help_text"] == "Control items"

    visual = fields["table_grid_abc:r2:c_visual"]
    assert visual["field_type"] == "select"
    assert visual["options"] == ["OK", "N-OK"]
    assert visual["spec_text"] == "OK"


def test_a_table_with_only_printed_columns_is_a_problem():
    printed_only = {**TABLE, "columns": [c for c in TABLE["columns"] if c["kind"] == "fixed"]}
    found = layouts.problems([printed_only])
    assert any("records nothing" in problem for problem in found)


def test_fields_in_a_row_come_where_the_row_is():
    """The builder lists a row's fields after everything else; the record reads top to bottom."""
    row = {"id": "row", "element": "TwoColumnRow", "field_name": "two_col_row_1", "childItems": ["dept", "date"]}
    layout = [
        row,
        {"id": "doc", "element": "TextInput", "field_name": "text_input_doc", "label": "Document Number"},
        {"id": "dept", "element": "TextInput", "field_name": "text_input_dept", "label": "Dept.", "parentId": "row"},
        {"id": "date", "element": "DatePicker", "field_name": "date_picker_1", "label": "Date", "parentId": "row"},
    ]
    assert [f["label"] for f in layouts.to_fields(layout)] == ["Dept.", "Date", "Document Number"]


def test_a_printed_reference_table_is_not_a_problem():
    """A revision history copied from the paper form is printed text on purpose."""
    history = {"id": "t2", "element": "Table", "field_name": "table_rev", "label": "Revision history",
               "columns": [{"key": "c1", "text": "Rev No"}, {"key": "c2", "text": "Rev date"}],
               "header": [[{"text": "Rev No"}, {"text": "Rev date"}]],
               "rows": [{"key": "r1", "cells": [{"text": "00"}, {"text": "01.11.2014"}]}]}
    assert any("Every cell in" in problem for problem in layouts.problems([history]))
    assert not any("Every cell in" in problem for problem in layouts.problems([{**history, "reference": True}]))
    assert layouts.to_fields([{**history, "reference": True}]) == []


def _format_with_layout(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-LAY", "title": "Designed sheet", "frequency": "daily",
        "team_id": world["team_id"],
        "process_owner_id": world["ids"]["po"],
        "overall_process_owner_id": world["ids"]["opo"],
        "qms_coordinator_id": world["ids"]["qms"],
        "cft_member_ids": [world["ids"]["cft1"], world["ids"]["cft2"]],
        "layout": LAYOUT, "fields": [],
    })
    assert made.status_code == 200, made.text
    fmt = made.json()
    assert {f["layout_key"] for f in fmt["fields"]} >= {
        "number_input_1", "table_grid_abc:r1:c_reading"}
    published = client.post(f"/api/formats/{fmt['id']}/publish-without-approval")
    assert published.status_code == 200, published.text
    return fmt["id"]


def test_values_are_saved_and_judged_by_layout_key(client, world):
    format_id = _format_with_layout(client, world)
    _login(client, world["names"]["po"])

    record = client.post("/api/records/call", json={"format_id": format_id}).json()
    keys = {v["layout_key"] for v in record["values"]}
    assert "table_grid_abc:r1:c_reading" in keys

    saved = client.put(f"/api/records/{record['id']}/values", json={"values": [
        {"layout_key": "number_input_1", "value": "25.0"},
        {"layout_key": "table_grid_abc:r1:c_reading", "value": "25.4"},  # out of spec
        {"layout_key": "table_grid_abc:r2:c_visual", "value": "OK"},
        {"layout_key": "dropdown_1", "value": "A"},
    ]})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    by_key = {v["layout_key"]: v for v in body["values"]}
    assert by_key["number_input_1"]["in_spec"] is True
    assert by_key["table_grid_abc:r1:c_reading"]["in_spec"] is False
    assert by_key["table_grid_abc:r2:c_visual"]["in_spec"] is True
    assert by_key["dropdown_1"]["options"] == ["A", "B"]
    assert body["observation_status"] == "not_ok"


def test_a_reviewer_can_open_the_draft_they_are_asked_to_approve(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-REV", "title": "Needs review", "frequency": "daily",
        "team_id": world["team_id"],
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 5}],
    }).json()
    submitted = client.post(f"/api/formats/{made['id']}/submit-approval", json={
        "steps": [{"name": "QMS review", "reviewer_ids": [world["ids"]["qms"]], "mode": "any"}],
    })
    assert submitted.status_code == 200, submitted.text

    _login(client, world["names"]["qms"])
    assert client.get(f"/api/formats/{made['id']}").status_code == 200

    _login(client, world["names"]["cft1"])  # not a reviewer
    assert client.get(f"/api/formats/{made['id']}").status_code == 404


def test_a_format_without_a_process_owner_can_be_filled_by_whoever_called_it(client, world):
    """Roles left blank are chosen at submission; the person who called it fills it."""
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-OPEN", "title": "Roles chosen at submission", "frequency": "per_event",
        "team_id": world["team_id"],
        "fields": [{"label": "Reading", "field_type": "number", "spec_min": 1, "spec_max": 5}],
    }).json()
    assert client.post(f"/api/formats/{made['id']}/publish-without-approval").status_code == 200

    _login(client, world["names"]["cft1"])
    record = client.post("/api/records/call", json={"format_id": made["id"]}).json()
    assert record["can"]["amend"] is True
    saved = client.put(f"/api/records/{record['id']}/values",
                       json={"values": [{"id": record["values"][0]["id"], "value": "3"}]})
    assert saved.status_code == 200, saved.text

    refused = client.post(f"/api/records/{record['id']}/submit", json={})
    assert refused.status_code == 400 and "Process Owner" in refused.text

    overrides = {"process_owner": [world["ids"]["po"]], "overall_process_owner": [world["ids"]["opo"]],
                 "cft_members": [world["ids"]["cft1"], world["ids"]["cft2"]]}
    submitted = client.post(f"/api/records/{record['id']}/submit", json={"approval_overrides": overrides})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["stage"] == "po_approval"

    _login(client, world["names"]["cft2"])  # did not call it
    other = client.post("/api/records/call", json={"format_id": made["id"]}).json()
    _login(client, world["names"]["cft1"])
    assert client.put(f"/api/records/{other['id']}/values",
                      json={"values": [{"id": other["values"][0]["id"], "value": "3"}]}).status_code == 403


def test_a_limit_of_zero_is_a_limit():
    # 0 == False in Python: a run-out of "0 to 0.05" must not lose its minimum
    zero_row = {**TABLE, "rows": [{"id": "r1", "cells": {}, "unit": "mm", "spec_min": 0, "spec_max": 0.05}]}
    number = {"id": "n1", "element": "NumberInput", "field_name": "n_zero", "label": "Offset",
              "spec_min": 0.0, "spec_max": "0"}
    fields = {f["layout_key"]: f for f in layouts.to_fields([number, zero_row])}
    assert (fields["n_zero"]["spec_min"], fields["n_zero"]["spec_max"]) == (0.0, 0.0)
    reading = next(f for key, f in fields.items() if key.endswith(":r1:c_reading"))
    assert (reading["spec_min"], reading["spec_max"]) == (0.0, 0.05)
