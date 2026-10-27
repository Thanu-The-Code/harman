#!/usr/bin/env python
"""
Frontend contract check: replays the requests the React frontend sends, with
the same payload shapes, against a running system - ideally through the Vite
dev proxy so the browser's path is exercised too.

    python scripts/check_frontend_contract.py [http://127.0.0.1:5173]

Covers Phases 2-9 of INTEGRATION_PLAN.md: template folders, the designer's draft
(layout with limits and a Table / Grid, responsibilities, filing folder), the
release review by a non-admin reviewer, the Resources library, calling a
format, the Template Repository, raising a change request, filling readings
by layout key, evidence, scans and submitting with chosen approvers. It creates data;
run it against a development database (re-seed afterwards for a clean demo).
"""
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
PASSWORD = "Harman@2026"
results = []


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""))


def session(username):
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


admin, po, qms = session("admin"), session("r.kumar"), session("m.shaikh")
people = {p["name"]: p["id"] for p in admin.get("/api/formats/approvers").json()}
team = next(t for t in admin.get("/api/formats/teams").json()["teams"] if t["code"] == "PQ")
stamp = time.strftime("%H%M%S")

print("Template folders")
r1 = admin.post("/api/formats/folders", json={"name": "Process Quality", "parent_path": None})
r2 = admin.post("/api/formats/folders", json={"name": "Machining", "parent_path": "Process Quality"})
check("create folder and subfolder", r1.status_code == 200 and r2.status_code == 200, r2.text)
check("subfolder path", r2.json().get("path") == "Process Quality / Machining", r2.text)

print("Designer: save a draft")
layout = [
    {"id": "h", "element": "Header", "content": "Bore check", "static": True},
    {"id": "n", "element": "NumberInput", "field_name": "number_input_A1", "label": "<p>Bore diameter</p>",
     "unit": "mm", "spec_min": 24.9, "spec_max": 25.1, "spec_text": None},
    {"id": "t", "element": "TextInput", "field_name": "text_input_B2", "label": "Operator",
     "unit": None, "spec_min": None, "spec_max": None, "spec_text": None},
    {"id": "g", "element": "CustomElement", "key": "TableGrid", "field_name": "table_grid_C3", "label": "Control items",
     "columns": [
         {"id": "c1", "name": "STAGE", "width": 140, "type": "text", "kind": "fixed"},
         {"id": "c2", "name": "CONTROL ITEM", "width": 200, "type": "text", "kind": "fixed"},
         {"id": "c3", "name": "READING", "width": 120, "type": "number", "kind": "input"},
         {"id": "c4", "name": "VISUAL", "width": 120, "type": "dropdown", "kind": "input"},
     ],
     "rows": [
         {"id": "r1", "cells": {"c1": "In-process", "c2": "Face run-out"}, "spec_min": 0, "spec_max": 0.05, "unit": "mm"},
         {"id": "r2", "cells": {"c1": "In-process", "c2": "Surface finish"}},
     ]},
]
layout[3]["table_grid"] = {"columns": layout[3]["columns"], "rows": layout[3]["rows"]}
payload = {
    "code": f"QF-PQ-E2E{stamp}", "title": "E2E designed sheet", "description": None,
    "team_id": team["id"], "frequency": "daily", "layout": layout, "fields": [],
    "process_owner_id": people["Ravi Kumar"], "overall_process_owner_id": people["Sunita Iyer"],
    "qms_coordinator_id": people["Mohammed Shaikh"],
    "cft_member_ids": [people["Anil Deshmukh"], people["Priya Nair"]], "cft_target_days": 3,
    "work_instruction_ref": "WI-PQ-012", "work_instruction": "Measure at 3 points.",
    "storage_path": "Process Quality / Machining",
}
made = admin.post("/api/formats/", json=payload)
check("create draft", made.status_code == 200, made.text[:300])
fmt = made.json()
keys = {f["layout_key"]: f for f in fmt.get("fields", [])}
check("readiness is empty", fmt.get("readiness") == [], fmt.get("readiness"))
check("6 recorded fields (2 items + 2 rows x 2 recorded columns)", len(keys) == 6 and len(fmt["fields"]) == 6,
      [f["label"] for f in fmt.get("fields", [])])
check("number item limits kept", keys.get("number_input_A1", {}).get("spec_label", "") != "", keys.get("number_input_A1"))
check("table row limits on reading", keys.get("table_grid_C3:r1:c3", {}).get("spec_max") == 0.05, keys.get("table_grid_C3:r1:c3"))
check("filing preview", fmt.get("storage_preview", "").startswith("Process Quality / Machining"), fmt.get("storage_preview"))

saved = admin.put(f"/api/formats/{fmt['id']}", json={**payload, "title": "E2E designed sheet v2"})
check("save again (PUT)", saved.status_code == 200 and saved.json()["title"] == "E2E designed sheet v2", saved.text[:200])

tab = admin.get("/api/formats/", params={"tab": "all"}).json()
row = next((f for f in tab["formats"] if f["id"] == fmt["id"]), None)
check("builder list shows it as draft", row is not None and row["builder_status"] == "draft")

print("Release review")
sub = admin.post(f"/api/formats/{fmt['id']}/submit-approval", json={
    "priority": "normal",
    "steps": [{"name": "QMS Coordinator review", "reviewer_ids": [people["Mohammed Shaikh"]], "mode": "any", "due_days": 2}],
})
check("send for approval", sub.status_code == 200, sub.text[:300])
mine = qms.get("/api/formats/approvals/mine").json()
check("QMS Coordinator sees it under Template approvals", any(a["format_id"] == fmt["id"] for a in mine["approvals"]))
check("QMS Coordinator (not admin) can open the draft", qms.get(f"/api/formats/{fmt['id']}").status_code == 200)
check("Process Owner cannot open the unreleased draft", po.get(f"/api/formats/{fmt['id']}").status_code == 404)
dec = qms.post(f"/api/formats/{fmt['id']}/approval/decision", json={"decision": "approve", "comment": "Looks right"})
check("approve -> released", dec.status_code == 200 and dec.json()["format"]["status"] == "active", dec.text[:300])

print("Resources library & filing")
lib = po.get("/api/formats/", params={"status": "active"}).json()
check("Process Owner sees it in Resources", any(f["id"] == fmt["id"] for f in lib["formats"]))
callable_ = {f["id"]: f for f in po.get("/api/formats/callable").json()["formats"]}
check("it is callable for today", fmt["id"] in callable_ and callable_[fmt["id"]]["period"]["label"])
rec = po.post("/api/records/call", json={"format_id": fmt["id"], "entry_mode": "digital"})
check("File -> record raised", rec.status_code == 200, rec.text[:200])
rec = rec.json()
check("record values carry layout keys", {v["layout_key"] for v in rec["values"]} == set(keys), rec.get("values"))

repo = admin.get("/api/formats/repository").json()


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n["children"])


node = next((n for n in walk(repo["folders"]) if n["path"] == "Process Quality / Machining"), None)
check("Template Repo files it under its folder", node is not None and any(t["id"] == fmt["id"] for t in node["templates"]))

print("Change request from Resources")
dcr = po.post("/api/change-requests", json={
    "kind": "change_existing", "format_id": fmt["id"], "title": f"Change to {payload['code']}",
    "reason": "Tolerance too tight", "proposed_change": "24.85 - 25.15 mm",
})
check("DCR raised to the QMS Coordinator", dcr.status_code == 200 and dcr.json()["coordinator"]["name"] == "Mohammed Shaikh",
      dcr.text[:300])

# ======================================================================= Phase 3
print("Phase 3 - fill: readings by layout key")
rid = rec["id"]
by_key = {v["layout_key"]: v for v in rec["values"]}
saved = po.put(f"/api/records/{rid}/values", json={"values": [
    {"id": by_key["number_input_A1"]["id"], "layout_key": "number_input_A1", "value": "25.0", "remark": ""},
    {"id": by_key["text_input_B2"]["id"], "layout_key": "text_input_B2", "value": "R. Kumar", "remark": ""},
    {"id": by_key["table_grid_C3:r1:c3"]["id"], "layout_key": "table_grid_C3:r1:c3", "value": "0.09",
     "remark": "Run-out high on part 2"},
    {"id": by_key["table_grid_C3:r1:c4"]["id"], "layout_key": "table_grid_C3:r1:c4", "value": "OK", "remark": ""},
]})
check("save readings", saved.status_code == 200, saved.text[:200])
body = saved.json()
vals = {v["layout_key"]: v for v in body["values"]}
check("in-spec reading judged OK", vals["number_input_A1"]["in_spec"] is True)
check("table cell over its row limit judged N-OK", vals["table_grid_C3:r1:c3"]["in_spec"] is False)
check("remark kept", vals["table_grid_C3:r1:c3"]["remark"] == "Run-out high on part 2")
check("record observation N-OK", body["observation_status"] == "not_ok")
# required = has a specification (record_service.missing_required): only the unfilled VISUAL cell
check("blank required entries listed", body["missing"] == ["In-process · Surface finish - VISUAL"], body["missing"])

print("Phase 3 - evidence")
up = po.post(f"/api/records/{rid}/attachments", files={"file": ("gauge.txt", b"gauge 7 calibrated", "text/plain")},
             data={"caption": "Gauge certificate"})
check("upload attachment", up.status_code == 200, up.text[:200])
att = up.json()
got = po.get(att["href"])
check("open attachment", got.status_code == 200 and got.content == b"gauge 7 calibrated")
listed = po.get(f"/api/records/{rid}").json()["attachments"]
check("attachment listed on the record with caption", any(a["id"] == att["id"] and a["caption"] == "Gauge certificate" for a in listed))
check("remove attachment", po.delete(f"/api/records/{rid}/attachments/{att['id']}").status_code == 200)

scan_rec = po.post("/api/records/call", json={"format_id": fmt["id"], "entry_mode": "digital"}).json()
# a real one-page PDF (the server refuses one it cannot open), unique per run: the server
# refuses one identical file as evidence for two records
def one_page_pdf(note: str) -> bytes:
    import io
    from PyPDF2 import PdfWriter

    out, writer = io.BytesIO(), PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_metadata({"/Subject": note})
    writer.write(out)
    return out.getvalue()


pdf = one_page_pdf(f"run {stamp} {time.time()}")
scan = po.post(f"/api/records/{scan_rec['id']}/scan", files={"file": ("scan.pdf", pdf, "application/pdf")})
check("attach scanned hard copy", scan.status_code == 200 and scan.json().get("document_id"), scan.text[:200])
scanned = po.get(f"/api/records/{scan_rec['id']}").json()
check("scan becomes the record's document", scanned["document_id"] == scan.json().get("document_id")
      and scanned["entry_mode"] == "hardcopy")

print("Phase 3 - submit with chosen approvers")
pickers = po.get(f"/api/formats/{fmt['id']}/people").json()
check("approver pickers for each role", all(pickers.get(k) for k in ("process_owner", "overall_process_owner", "cft_members")))
overrides = {"process_owner": [people["Ravi Kumar"]], "overall_process_owner": [people["Sunita Iyer"]],
             "cft_members": [people["Anil Deshmukh"], people["Priya Nair"]]}
sub = po.post(f"/api/records/{rid}/submit", json={"approval_overrides": overrides})
check("submit", sub.status_code == 200, sub.text[:300])
sub = sub.json()
check("stage is Process Owner approval", sub["stage"] == "po_approval")
check("N-OK flag raised to the OPO", sub["nok_open"] and (sub["nok_flagged_to"] or {}).get("name") == "Sunita Iyer")
check("tracking is red", sub["rag"] == "red")
check("a generated PDF backs the record", bool(sub["document_id"]))
wf = po.get(f"/api/workflow/{sub['workflow_id']}").json()
check("chain has the four process steps", [s["qms_stage"] for s in wf["steps"]] ==
      ["po_approval", "opo_approval", "cft_review", "final_decision"])
check("first step is with the chosen Process Owner",
      wf["steps"][0]["status"] == "current" and [a["name"] for a in wf["steps"][0]["assignees"]] == ["Ravi Kumar"])
check("N-OK record goes as high priority", wf["priority"] == "high")
ver = po.get("/api/records/documents-listing", params={"tab": "verification", "q": rec["number"]}).json()
check("My Documents lists it under On Verification", any(i["id"] == rid for i in ver["items"]))
opo = session("s.iyer")
notes = opo.get("/api/records/notifications/mine").json()["notifications"]
check("OPO notified of the N-OK flag", any(n["kind"] == "record.nok_flagged" and n["related_id"] == rid for n in notes))

print("Phase 3 - a format with its roles left blank")
open_fmt = admin.post("/api/formats/", json={
    "code": f"QF-PQ-OPEN{stamp}", "title": "Roles chosen at submission", "frequency": "per_event",
    "team_id": team["id"], "fields": [{"label": "Reading", "field_type": "number", "spec_min": 1, "spec_max": 5}],
}).json()
admin.post(f"/api/formats/{open_fmt['id']}/publish-without-approval")
open_rec = po.post("/api/records/call", json={"format_id": open_fmt["id"]}).json()
po.put(f"/api/records/{open_rec['id']}/values", json={"values": [{"id": open_rec["values"][0]["id"], "value": "3"}]})
refused = po.post(f"/api/records/{open_rec['id']}/submit", json={})
check("submit without approvers is refused, naming the roles", refused.status_code == 400 and "Process Owner" in refused.text,
      refused.text[:200])
accepted = po.post(f"/api/records/{open_rec['id']}/submit", json={"approval_overrides": overrides})
check("submit with chosen approvers is accepted", accepted.status_code == 200 and accepted.json()["stage"] == "po_approval",
      accepted.text[:200])

# ======================================================================= Phase 4
SIG = {"dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                  "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "method": "draw"}
cft_a, cft_b = session("a.deshmukh"), session("p.nair")
wf_id = sub["workflow_id"]


def current(client):
    return next((s for s in client.get(f"/api/workflow/{wf_id}").json()["steps"] if s["status"] == "current"), None)


def decide(client, action, note="", signature=None, name=None):
    step = current(client)
    body = {"action": action, "comment": note, "reason": "" if action == "approve" else note}
    if signature:
        body["signature"] = {**signature, "name": name}
    return client.post(f"/api/workflow/{wf_id}/steps/{step['id']}/decide", json=body)


def record_of(client):
    return client.get(f"/api/records/{rid}").json()


print("Phase 4 - Process Owner")
queue = po.get("/api/my-approvals", params={"tab": "pending"}).json()
check("record is in the PO's My Approvals", any(i["record_id"] == rid and i["stage"] == "po_approval" for i in queue["items"]))
step = current(po)
check("PO can act on a signed step", step["can_act"] and step["requires_signature"], step)
check("approving without a signature is refused", decide(po, "approve").status_code == 400)
check("approve and sign", decide(po, "approve", "Within condition", SIG, "Ravi Kumar").status_code == 200)
check("stage is OPO approval", record_of(po)["stage"] == "opo_approval")
check("PO no longer has an action", not current(po)["can_act"])

print("Phase 4 - Overall Process Owner")
r = record_of(opo)
check("OPO may clear the N-OK flag", r["can"]["clear_nok"] is True)
cleared = opo.post(f"/api/records/{rid}/nok/clear", json={"note": "Part quarantined, gauge re-checked"})
check("N-OK flag closed", cleared.status_code == 200 and cleared.json()["nok_open"] is False, cleared.text[:200])
check("OPO approves and signs", decide(opo, "approve", "", SIG, "Sunita Iyer").status_code == 200)
r = record_of(opo)
check("CFT joint review open with a target date", r["stage"] == "cft_review" and bool(r["cft_target_date"]))

print("Phase 4 - Quality CFT joint review")
check("first member objects", decide(cft_a, "reject", "Run-out trend needs a second look").status_code == 200)
check("objection carried on the record", "Run-out" in (record_of(po)["cft_objection"] or ""))
check("review stays open until every member answers", record_of(po)["stage"] == "cft_review")
check("second member agrees", decide(cft_b, "approve").status_code == 200)
check("goes to the final decision", record_of(po)["stage"] == "final_decision")

print("Phase 4 - final decision: No, then Yes")
check("Process Owner may send it back", record_of(po)["can"]["send_back"] is True)
check("send back to CFT", decide(po, "reject", "Re-verify run-out with the CFT").status_code == 200)
r = record_of(po)
check("back with the CFT, red, re-verify counted", r["stage"] == "cft_review" and r["rag"] == "red" and r["reverify_count"] == 1)
check("member agrees again", decide(cft_a, "approve").status_code == 200)
check("member agrees again (2)", decide(cft_b, "approve").status_code == 200)
check("final approval signed", decide(po, "approve", "Accepted", SIG, "Ravi Kumar").status_code == 200)
wf_done = po.get(f"/api/workflow/{wf_id}").json()
check("workflow approved", wf_done["status"] == "approved")

print("Phase 4 - filing")
check("only the OPO is offered File", record_of(opo)["can"]["store"] is True and record_of(po)["can"]["store"] is False)
stored = opo.post(f"/api/records/{rid}/store")
check("record filed", stored.status_code == 200 and stored.json()["stage"] == "stored", stored.text[:200])
check("filed in its date folder", "Process Quality / Machining" in (stored.json()["storage_path"] or ""), stored.json().get("storage_path"))
filed_id, filed_path = rid, stored.json()["storage_path"]
pdf = po.get(f"/api/signatures/{wf_id}/preview")
check("stamped PDF carries the signatures", pdf.status_code == 200 and pdf.headers.get("content-type", "").startswith("application/pdf")
      and int(pdf.headers.get("x-signature-count", "0")) >= 3, dict(pdf.headers))
check("task stats answer", set(po.get("/api/workflow/tasks/stats").json()) >= {"pending", "approved_today", "returned", "overdue"})

print("Phase 4 - return for correction")
again = po.post("/api/records/call", json={"format_id": fmt["id"]}).json()
first = {v["layout_key"]: v for v in again["values"]}["number_input_A1"]
po.put(f"/api/records/{again['id']}/values", json={"values": [{"id": first["id"], "value": "25.0"}]})
again = po.post(f"/api/records/{again['id']}/submit", json={"approval_overrides": overrides}).json()
wf_id, rid = again["workflow_id"], again["id"]
check("PO returns it for correction", decide(po, "reject", "Fill the operator name").status_code == 200)
back = po.get("/api/my-approvals", params={"tab": "returned"}).json()
check("filler sees it under Returned", any(i["record_id"] == rid and i["stage"] == "filling" for i in back["items"]))

# ======================================================================= Phase 5
print("Phase 5 - Doc Repository")
repo_all = opo.get("/api/documents/repository", params={"page": 1, "page_size": 100}).json()
check("filed record is listed", any(d["record_id"] == filed_id for d in repo_all["documents"]))


def find(nodes, path):
    for n in nodes:
        if n["path"] == path:
            return n
        hit = find(n["children"], path)
        if hit:
            return hit
    return None


# the tree always names folders "Records / ..."; the UI filters with those paths
tree_path = filed_path if filed_path.startswith("Records / ") else f"Records / {filed_path}"
check("its day folder is in the tree", find(repo_all["folders"], tree_path) is not None, tree_path)
parent = " / ".join(tree_path.split(" / ")[:-1])
in_month = opo.get("/api/documents/repository", params={"folder_path": parent}).json()
check("a month folder lists the records in its day folders", any(d["record_id"] == filed_id for d in in_month["documents"]))
by_number = opo.get("/api/documents/repository", params={"search": rec["number"]}).json()
check("search by record number", any(d["record_id"] == filed_id for d in by_number["documents"]))
summary = opo.get(f"/api/documents/repository/{filed_id}/summary")
check("record summary with its readings", summary.status_code == 200 and summary.json()["summary"]["fields"], summary.text[:200])
timeline = opo.get(f"/api/documents/repository/{filed_id}/approval-timeline").json()
check("approval timeline with signatures", sum(1 for s in timeline["steps"] if s.get("signature")) >= 3)
doc_file = opo.get(summary.json()["document"]["file_url"])
check("filed document downloads", doc_file.status_code == 200 and len(doc_file.content) > 100)
pin = opo.put("/api/documents/repository/folders/pin", json={"folder_path": parent, "pinned": True})
check("pin a folder", pin.status_code == 200 and pin.json()["is_pinned"] is True, pin.text[:200])
check("pin is remembered", (find(opo.get("/api/documents/repository").json()["folders"], parent) or {}).get("is_pinned") is True)
renamed = admin.patch("/api/documents/repository/folders/rename",
                      json={"folder_path": tree_path, "new_name": f"{tree_path.split(' / ')[-1]}-{stamp}"})
check("admin renames a folder", renamed.status_code == 200 and renamed.json()["records_updated"] >= 1, renamed.text[:200])

# ======================================================================= Phase 6
print("Phase 6 - format change request (DCR)")
dcr_id = dcr.json()["id"]
waiting = qms.get("/api/change-requests", params={"waiting": True}).json()
check("QMS Coordinator sees it waiting", any(r["id"] == dcr_id for r in waiting["requests"]) and waiting["waiting_on_me"] >= 1)
check("raiser cannot decide it", po.get(f"/api/change-requests/{dcr_id}").json()["can"]["decide"] is False)
check("start review", qms.post(f"/api/change-requests/{dcr_id}/review").json().get("status") == "under_review")
approved = qms.post(f"/api/change-requests/{dcr_id}/decide", json={"action": "approve", "comment": "Agreed at the quality meeting"})
check("coordinator approves", approved.status_code == 200 and approved.json()["status"] == "approved", approved.text[:200])
check("only now can it be executed", approved.json()["can"]["execute"] is True)
executed = qms.post(f"/api/change-requests/{dcr_id}/execute", json={})
check("execute creates the next revision as a draft", executed.status_code == 200
      and executed.json()["format"]["revision"] == "01" and executed.json()["format"]["status"] == "draft", executed.text[:300])
check("request is implemented and points at it",
      qms.get(f"/api/change-requests/{dcr_id}").json()["resulting_format"]["id"] == executed.json()["format"]["id"])

new_fmt = po.post("/api/change-requests", json={
    "kind": "new_format", "team_id": team["id"], "qms_coordinator_id": people["Mohammed Shaikh"],
    "title": "Torque audit sheet",
    "reason": "New torque line", "proposed_change": "Torque per station, 3 readings"})
check("raise a new-format request, naming its coordinator", new_fmt.status_code == 200
      and (new_fmt.json()["coordinator"] or {}).get("name") == "Mohammed Shaikh", new_fmt.text[:200])
no_comment = qms.post(f"/api/change-requests/{new_fmt.json()['id']}/decide", json={"action": "reject", "comment": ""})
check("rejecting needs a comment", no_comment.status_code == 400)
rejected = qms.post(f"/api/change-requests/{new_fmt.json()['id']}/decide", json={"action": "reject", "comment": "Use QF-PQ-001"})
check("coordinator rejects with a comment", rejected.status_code == 200 and rejected.json()["status"] == "rejected")

print("Phase 6 - record change request (RCR)")
raised = po.post("/api/record-change-requests", json={"record_id": filed_id, "reason": "Operator name misspelt"})
check("raise on a filed record", raised.status_code == 200, raised.text[:200])
rcr_req = raised.json()
check("assigned to the format's QMS Coordinator", (rcr_req["assigned_to"] or {}).get("name") == "Mohammed Shaikh")
edited = po.patch(f"/api/record-change-requests/{rcr_req['id']}", json={"title": "Fix operator name", "reason": "Operator name misspelt on the sheet"})
check("raiser edits it", edited.status_code == 200 and edited.json()["title"] == "Fix operator name")
mine = qms.get("/api/record-change-requests", params={"waiting": True}).json()
check("assignee sees it waiting", any(r["id"] == rcr_req["id"] for r in mine["requests"]))
reassigned = admin.post(f"/api/record-change-requests/{rcr_req['id']}/assign", json={"assigned_to_id": people["Mohammed Shaikh"]})
check("admin (re)assigns it", reassigned.status_code == 200, reassigned.text[:200])
decided = qms.post(f"/api/record-change-requests/{rcr_req['id']}/decide", json={"action": "approve", "comment": "Correct it"})
check("assignee approves", decided.status_code == 200 and decided.json()["status"] == "approved", decided.text[:200])
done = po.post(f"/api/record-change-requests/{rcr_req['id']}/implement", json={"note": "Corrected and re-filed"})
check("raiser marks it implemented", done.status_code == 200 and done.json()["status"] == "implemented", done.text[:200])
listed = po.get("/api/record-change-requests", params={"status": "implemented", "search": "operator"}).json()
check("found under Implemented by search", any(r["id"] == rcr_req["id"] for r in listed["requests"]))

# ======================================================================= Phase 7
print("Phase 7 - people, roles, teams, departments")
dept = admin.post("/api/departments", json={"name": f"Assembly {stamp}"})
check("add a department", dept.status_code == 201, dept.text[:200])
dept = dept.json()
role = admin.post("/api/roles", json={"name": f"Line Inspector {stamp}", "description": "Fills checks",
                                      "permissions": ["documents.view", "records.fill"]})
check("add a role with capabilities", role.status_code == 201 and set(role.json()["permissions"]) == {"documents.view", "records.fill"},
      role.text[:200])
role = role.json()
new_team = admin.post("/api/formats/teams", json={"code": f"T{stamp[-4:]}", "name": f"Test Quality {stamp}"})
check("add a quality team", new_team.status_code == 200, new_team.text[:200])
new_team = new_team.json()
check("edit the team", admin.put(f"/api/formats/teams/{new_team['id']}",
                                 json={"code": new_team["code"], "name": f"Test Quality {stamp} B"}).status_code == 200)
check("retire and restore the team",
      admin.post(f"/api/formats/teams/{new_team['id']}/retire").json().get("is_active") is False
      and admin.post(f"/api/formats/teams/{new_team['id']}/restore").json().get("is_active") is True)

uname = f"inspector{stamp}"
person = admin.post("/api/auth/users", json={
    "username": uname, "email": f"{uname}@harman.example", "full_name": "Test Inspector",
    "password": "Inspector@2026", "role_id": role["id"], "department_id": dept["id"], "job_title": "Line Inspector"})
check("add a person with role and department", person.status_code == 200 and person.json()["role_names"] == [role["name"]],
      person.text[:200])
person = person.json()
moved = admin.put(f"/api/auth/users/{person['id']}", json={"quality_team_id": new_team["id"]})
check("put them in a quality team", moved.status_code == 200 and moved.json()["quality_team_id"] == new_team["id"])
check("team lists them", any(p["id"] == person["id"] for t in admin.get("/api/formats/teams").json()["teams"]
                             if t["id"] == new_team["id"] for p in t["people"]))

login = httpx.post(f"{BASE}/api/auth/login", json={"username": uname, "password": "Inspector@2026"})
check("they can sign in", login.status_code == 200)
me_now = httpx.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
check("a fill-only role cannot approve", me_now["can_approve"] is False and "records.fill" in me_now["permissions"])
approver_role = next(r for r in admin.get("/api/roles").json() if r["name"] == "Quality Approver")
check("change their role", admin.put(f"/api/roles/users/{person['id']}", json={"role_id": approver_role["id"]}).status_code == 200)
me_now = httpx.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
check("the new role's authority applies", me_now["can_approve"] is True and me_now["can_sign"] is True)
check("a role in use cannot be deleted", admin.delete(f"/api/roles/{approver_role['id']}").status_code == 409)
check("deactivate them", admin.put(f"/api/auth/users/{person['id']}", json={"is_active": False}).json()["is_active"] is False)
inactive = httpx.post(f"{BASE}/api/auth/login", json={"username": uname, "password": "Inspector@2026"})
check("an inactive person cannot sign in, and is told why",
      inactive.status_code == 403 and "deactivated" in inactive.text, inactive.text[:160])
check("delete the person", admin.delete(f"/api/auth/users/{person['id']}").status_code == 200)
check("delete the unused role", admin.delete(f"/api/roles/{role['id']}").status_code == 200)
check("delete the department", admin.delete(f"/api/departments/{dept['id']}").status_code == 200)
check("only admins manage people", po.get("/api/auth/users").status_code == 403)

# ======================================================================= Phase 8
print("Phase 8 - dashboard, notifications, activity log")
dash = po.get("/api/actions/dashboard", params={"days": 7}).json()
check("dashboard totals", {"total", "completed", "pending", "failed", "pass_rate"} <= set(dash["totals"]))
check("trend buckets carry the chart's series",
      dash["trend"] and all({"label", "passed", "failed", "open", "completed"} <= set(b) for b in dash["trend"]))
check("recent records listed", isinstance(dash["recent"], list) and len(dash["recent"]) > 0)
check("task stats for the KPI tile", "pending" in po.get("/api/workflow/tasks/stats").json())

notes = opo.get("/api/records/notifications/mine", params={"limit": 200}).json()
check("notifications list with an unread count", notes["notifications"] and notes["unread"] >= 1)
first_unread = next(n for n in notes["notifications"] if not n["read"])
check("a notification carries what it is about", bool(first_unread["related_type"]) and bool(first_unread["related_id"]))
one = opo.post("/api/records/notifications/read", json={"ids": [first_unread["id"]]}).json()
check("mark one read", one["marked"] == 1 and one["unread"] == notes["unread"] - 1, one)
everything = opo.post("/api/records/notifications/read", json={}).json()
check("mark all read", everything["unread"] == 0)
check("the bell's count drops to zero",
      opo.get("/api/records/notifications/mine", params={"unread_only": True, "limit": 1}).json()["unread"] == 0)

page1 = po.get("/api/audit", params={"page": 1, "page_size": 5}).json()
check("activity log pages", len(page1["events"]) == 5 and page1["pagination"]["total_pages"] >= 2)
modules = po.get("/api/audit/modules").json()["modules"]
check("activity modules listed", "Template Builder" in modules)
by_module = po.get("/api/audit", params={"module": "Template Builder", "page_size": 50}).json()
check("filter by module", by_module["events"] and all(e["module"] == "Template Builder" for e in by_module["events"]))
today = time.strftime("%Y-%m-%d")
ranged = po.get("/api/audit", params={"date_from": today, "date_to": today, "page_size": 5}).json()
check("filter by date range", ranged["pagination"]["total"] >= 1)
searched = po.get("/api/audit", params={"q": "Sunita", "page_size": 5}).json()
check("search the log", searched["pagination"]["total"] >= 1)

# ======================================================================= Phase 9
print("Phase 9 - access control (scenario E)")
probe = po.post("/api/records/call", json={"format_id": open_fmt["id"]}).json()
po.put(f"/api/records/{probe['id']}/values", json={"values": [{"id": probe["values"][0]["id"], "value": "2"}]})
probe = po.post(f"/api/records/{probe['id']}/submit", json={"approval_overrides": overrides}).json()
step = next(s for s in cft_b.get(f"/api/workflow/{probe['workflow_id']}").json()["steps"] if s["status"] == "current")
check("a CFT member is not offered the PO step", step["can_act"] is False and bool(step["blocked_reason"]))
refused = cft_b.post(f"/api/workflow/{probe['workflow_id']}/steps/{step['id']}/decide",
                     json={"action": "approve", "comment": "", "reason": "", "signature": SIG})
check("and cannot approve it", refused.status_code in (400, 403))
check("a non-admin cannot author templates", po.post("/api/formats/", json=payload).status_code == 403)
check("a non-admin cannot browse the template repository", po.get("/api/formats/repository").status_code == 403)
check("a non-admin cannot see the email outbox", po.get("/api/records/notifications/outbox").status_code in (401, 403))
draft = admin.post("/api/formats/", json={**payload, "code": f"QF-PQ-DRAFT{stamp}"}).json()
check("an unreleased draft is hidden from people not reviewing it", cft_b.get(f"/api/formats/{draft['id']}").status_code == 404)
bad = httpx.get(f"{BASE}/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
check("a bad token is refused", bad.status_code == 401)
check("no token is refused", httpx.get(f"{BASE}/api/records/documents-listing").status_code == 401)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
