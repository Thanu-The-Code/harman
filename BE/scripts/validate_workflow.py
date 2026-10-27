#!/usr/bin/env python
"""
Acceptance check for the Record Filling & Record Approval Process.

Runs the client's flowchart against a *running* system, over HTTP, signed in as
each person the process names. Every check states a business expectation and
carries the box of the chart it defends, so a failure tells you which rule of
the process has stopped holding - not which function changed.

    1. python cli.py init                      (once)
    2. python scripts/seed_quality_records.py  (once - people, formats, records)
    3. python cli.py serve                     (leave running)
    4. python scripts/validate_workflow.py

Exit code 0 means the system matches the process. Anything else lists what does
not, and nothing is left behind that a later run trips over.

Options:
    --url http://127.0.0.1:8000   where the system is running
    --password Harman@2026        the seeded password
    --quick                       skip the slow parts (all eight frequencies,
                                  and the concurrency checks)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import sys
import uuid
import warnings
from datetime import datetime

# This script is read by people, not by a linter. A deprecation notice from a
# library in the middle of an acceptance report is noise that makes a passing
# run look like a failing one.
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("httpx is needed. Install the requirements first.")


# A valid 1x1 PNG. The truncated stub that used to be here decoded to
# nothing, so every record the validation run signed carried a broken
# image - which then showed up on the printed record.
SIGNATURE = {
    "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
               "CAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "name": "Validation",
}

GREEN, RED, GREY, BOLD, OFF = "\033[32m", "\033[31m", "\033[90m", "\033[1m", "\033[0m"


class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.findings: list[tuple[str, str, str]] = []

    def check(self, box: str, expectation: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print(f"  {GREEN}PASS{OFF}  {GREY}{box:<16}{OFF} {expectation}")
        else:
            self.findings.append((box, expectation, detail))
            print(f"  {RED}FAIL{OFF}  {GREY}{box:<16}{OFF} {expectation}")
            if detail:
                print(f"        {RED}{detail}{OFF}")
        return ok

    def section(self, title: str) -> None:
        print(f"\n{BOLD}{title}{OFF}")

    def finish(self) -> int:
        print("\n" + "=" * 74)
        if self.findings:
            print(f"  {RED}{len(self.findings)} finding(s){OFF}, {self.passed} passed\n")
            for box, expectation, detail in self.findings:
                print(f"  [{box}] {expectation}")
                if detail:
                    print(f"      {detail}")
        else:
            print(f"  {GREEN}{self.passed} checks passed. "
                  f"The system matches the process flow.{OFF}")
        print("=" * 74)
        return 1 if self.findings else 0


class Person:
    """One signed-in participant."""

    def __init__(self, base: str, username: str, password: str) -> None:
        self.username = username
        self.c = httpx.Client(base_url=base, follow_redirects=False, timeout=90)
        r = self.c.post("/api/auth/login",
                        json={"username": username, "password": password})
        if r.status_code != 200:
            sys.exit(f"Could not sign in as {username}. Has the seed been run?\n"
                     f"  {r.status_code}: {r.text[:200]}")
    def get(self, path, **kw):
        return self.c.get(path, **kw)

    def post(self, path, **kw):
        return self.c.post(path, **kw)

    def put(self, path, **kw):
        return self.c.put(path, **kw)

    def step(self, workflow_id):
        return self.get(f"/api/workflow/{workflow_id}").json()["current_step"]

    def record(self, record_id):
        return self.get(f"/api/records/{record_id}").json()

    def decide(self, workflow_id, step_id, action, sign=True, **kw):
        body = {"action": action, "comment": kw.get("comment", ""),
                "reason": kw.get("reason", "")}
        if sign and action == "approve":
            body["signature"] = SIGNATURE
        return self.post(
            f"/api/workflow/{workflow_id}/steps/{step_id}/decide", json=body)


def why(res) -> str:
    """The message a refused request came back with, whichever layer refused."""
    try:
        body = res.json()
    except Exception:
        return res.text[:200]
    if isinstance(body.get("error"), dict):
        return str(body["error"].get("detail", ""))
    return str(body.get("detail", ""))


def a_scanned_sheet() -> bytes:
    """
    A distinct, openable one-page PDF, so no two records share one sheet.

    It used to be a PDF header with no pages in it. That satisfied every check
    in this file and left the records it created unopenable: anybody who
    pressed "view the sheet" on one afterwards got a black rectangle and the
    browser's own error. Test data that cannot be opened teaches people to
    ignore a real failure, so this writes a real page.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw

    mark = uuid.uuid4().hex[:8]
    sheet = Image.new("RGB", (1000, 640), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((40, 40), f"Acceptance check sheet {mark}", fill=(20, 20, 20))
    draw.text((40, 90), "Written by scripts/validate_workflow.py.", fill=(90, 90, 90))
    draw.text((40, 130), "Not a real quality record.", fill=(90, 90, 90))

    buffer = BytesIO()
    sheet.save(buffer, "PDF", resolution=150)
    return buffer.getvalue()


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--password", default="Harman@2026")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    print(f"{BOLD}Validating the record process at {base}{OFF}")

    try:
        httpx.get(f"{base}/health", timeout=10)
    except Exception:
        sys.exit(f"Nothing is answering at {base}. Start the server first:\n"
                 f"  python cli.py serve")

    r = Report()

    admin = Person(base, "admin", args.password)
    po = Person(base, "r.kumar", args.password)        # Process Owner
    opo = Person(base, "s.iyer", args.password)        # Overall Process Owner
    cft1 = Person(base, "a.deshmukh", args.password)   # Quality CFT
    cft2 = Person(base, "p.nair", args.password)       # Quality CFT
    qms = Person(base, "m.shaikh", args.password)      # QMS Coordinator
    sq_po = Person(base, "k.reddy", args.password)     # Supplier Quality owner

    people = {u["username"]: u for u in admin.get("/api/auth/users").json()}
    teams = {t["code"]: t for t in admin.get("/api/formats/teams").json()["teams"]}

    # The seed leaves one change request open on purpose. Settle it so the
    # checks below can raise their own.
    for pending in qms.get("/api/change-requests/?waiting=true").json()["requests"]:
        qms.post(f"/api/change-requests/{pending['id']}/decide",
                 json={"action": "reject", "comment": "Closed by the validation run."})

    stamp = uuid.uuid4().hex[:6].upper()

    def build_format(suffix, frequency="daily", cft=None, owner=None, team="PQ"):
        code = f"QV-{stamp}-{suffix}"
        made = admin.post("/api/formats/", json={
            "code": code, "title": f"Validation {frequency} check",
            "team_id": teams[team]["id"], "frequency": frequency,
            "cft_target_days": 3,
            "process_owner_id": owner or people["r.kumar"]["id"],
            "overall_process_owner_id": people["s.iyer"]["id"],
            "qms_coordinator_id": people["m.shaikh"]["id"],
            "cft_member_ids": cft or [people["a.deshmukh"]["id"],
                                      people["p.nair"]["id"]],
            "fields": [{"label": "Reading", "field_type": "number",
                        "unit": "mm", "spec_min": 1, "spec_max": 10},
                       {"label": "Operator", "field_type": "text"}],
        })
        if made.status_code != 200:
            sys.exit(f"Could not build a validation format: {why(made)}")
        # Releasing needs an approved template review; the validation formats
        # take the audited administrator bypass instead.
        live = admin.post(
            f"/api/formats/{made.json()['id']}/publish-without-approval", json={})
        if live.status_code != 200:
            sys.exit(f"Could not release a validation format: {why(live)}")
        return live.json()

    def fill_and_submit(fmt, reading="5", who=po):
        rec = who.post("/api/records/call", json={"format_id": fmt["id"]}).json()
        who.put(f"/api/records/{rec['id']}/values", json={"values": [
            {"label": "Reading", "value": reading},
            {"label": "Operator", "value": "Validation"}]})
        who.post(f"/api/records/{rec['id']}/scan",
                 files={"file": ("sheet.pdf", a_scanned_sheet(), "application/pdf")})
        return who.post(f"/api/records/{rec['id']}/submit", json={}).json()

    def advance(rec, to):
        """Move a submitted record forward to a named stage."""
        w = rec["workflow_id"]
        if to == "po_approval":
            return po.record(rec["id"])
        po.decide(w, po.step(w)["id"], "approve")
        if to == "opo_approval":
            return po.record(rec["id"])
        opo.decide(w, opo.step(w)["id"], "approve")
        if to == "cft_review":
            return po.record(rec["id"])
        cft1.decide(w, cft1.step(w)["id"], "approve", sign=False)
        cft2.decide(w, cft2.step(w)["id"], "approve", sign=False)
        if to == "final_decision":
            return po.record(rec["id"])
        po.decide(w, po.step(w)["id"], "approve")
        if to == "approved":
            return po.record(rec["id"])
        opo.post(f"/api/records/{rec['id']}/store", json={})
        return po.record(rec["id"])

    # ==================================================================== B1
    r.section("B1  Blank formats live on the server, filled at a stated frequency")

    library = admin.get("/api/formats/").json()
    r.check("B1", "the format library is readable",
            bool(library["formats"]))
    r.check("B1", "every frequency the process needs is offered",
            {f["value"] for f in library["frequencies"]} >= {
                "shift", "daily", "weekly", "monthly", "quarterly",
                "half_yearly", "yearly", "per_event"})
    r.check("B1", "the three dedicated quality teams exist",
            {"PQ", "SQ", "CQ"} <= set(teams))

    half_built = admin.post("/api/formats/", json={
        "code": f"QV-{stamp}-BAD", "title": "Half built",
        "team_id": teams["PQ"]["id"], "frequency": "daily",
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 5}]})
    # Responsibilities may be left blank: the approvers are then chosen on the
    # record at submission. What may not be skipped is the template review.
    r.check("B1", "a format may be drafted without naming its responsibilities",
            half_built.status_code == 200)
    if half_built.status_code == 200:
        blocked = admin.post(
            f"/api/formats/{half_built.json()['id']}/activate", json={})
        r.check("B1", "a draft is not released until its template review is approved",
                blocked.status_code == 400 and "approval" in why(blocked),
                why(blocked))

    fmt = build_format("A")

    # ==================================================================== B2
    r.section("B2  The Process Owner calls the format to be filled")

    mine = po.get("/api/formats/callable").json()["formats"]
    r.check("B2", "the Process Owner is offered their own formats",
            any(f["id"] == fmt["id"] for f in mine))
    r.check("B2", "a CFT member is not offered somebody else's format to fill",
            cft1.post("/api/records/call",
                      json={"format_id": fmt["id"]}).status_code == 400)

    called = po.post("/api/records/call", json={"format_id": fmt["id"]})
    r.check("B2", "calling a format raises a record for the current period",
            called.status_code == 200 and called.json()["period_label"])
    started = called.json()
    r.check("B2", "a new record starts yellow - filling in progress",
            started["rag"] == "yellow" and started["stage"] == "filling")

    offered = [f for f in po.get("/api/formats/callable").json()["formats"]
               if f["id"] == fmt["id"]][0]
    r.check("B2", "a second call is warned the period is already covered",
            offered["existing_for_period"] is not None)

    # ================================================================ B3, B5
    r.section("B3  The record is filled, and judged against its specification")

    def observation(value):
        rec = po.post("/api/records/call", json={"format_id": fmt["id"]}).json()
        got = po.put(f"/api/records/{rec['id']}/values", json={"values": [
            {"label": "Reading", "value": value},
            {"label": "Operator", "value": "Validation"}]}).json()
        return got["observation_status"]

    r.check("B5", "a reading on the lower limit is within specification",
            observation("1") == "ok")
    r.check("B5", "a reading on the upper limit is within specification",
            observation("10") == "ok")
    r.check("B5", "a reading below the limit is N-ok",
            observation("0.9") == "not_ok")
    r.check("B5", "a reading above the limit is N-ok",
            observation("10.1") == "not_ok")

    blank = po.post("/api/records/call", json={"format_id": fmt["id"]}).json()
    r.check("B3", "a record with a blank reading cannot be submitted",
            po.post(f"/api/records/{blank['id']}/submit",
                    json={}).status_code == 400)

    scanned = po.post(f"/api/records/{blank['id']}/scan",
                      files={"file": ("hard-copy.pdf", a_scanned_sheet(),
                                      "application/pdf")})
    r.check("B3", "a filled paper copy can be scanned in and read",
            scanned.status_code == 200 and "text" in scanned.json(),
            why(scanned))

    ok_record = fill_and_submit(fmt, "5")
    r.check("B3", "a complete record submits for approval",
            ok_record["stage"] == "po_approval")
    r.check("B5", "and is on the server at its given path, with its verdict",
            bool(ok_record["storage_path"]) and ok_record["observation_status"] == "ok")

    told = po.get("/api/records/notifications/mine").json()["notifications"]
    r.check("B3c", "the Process Owner is notified that a record needs approval",
            any(n["kind"] == "record.submitted" for n in told))

    # ==================================================================== B4
    r.section("B4  The Process Owner approves it if it is within specification")

    w = ok_record["workflow_id"]
    r.check("B4", "the chain is built from the format, not by hand",
            [s["name"] for s in po.get(f"/api/workflow/{w}").json()["steps"]] == [
                "Process Owner approval", "Overall Process Owner approval",
                "CFT joint review", "Final decision"])
    r.check("B4", "the Overall Process Owner cannot take the first approval",
            opo.decide(w, opo.step(w)["id"], "approve").status_code == 400)

    approved = po.decide(w, po.step(w)["id"], "approve")
    r.check("B4", "the Process Owner approves their own step",
            approved.status_code == 200, why(approved))
    r.check("B4c", "the Overall Process Owner is notified for their approval",
            any(n["kind"] == "record.po_approved"
                for n in opo.get("/api/records/notifications/mine").json()["notifications"]))

    returned = fill_and_submit(fmt, "5")
    number = returned["number"]
    sent_back = po.decide(returned["workflow_id"],
                          po.step(returned["workflow_id"])["id"],
                          "reject", reason="Readings disagree with the gauge log.")
    body = po.record(returned["id"])
    r.check("B4", "a record found out of specification is returned, not rejected",
            sent_back.status_code == 200 and body["stage"] == "filling",
            f"stage={body['stage']}")
    po.put(f"/api/records/{returned['id']}/values",
           json={"values": [{"label": "Reading", "value": "6"}]})
    again = po.post(f"/api/records/{returned['id']}/submit", json={}).json()
    r.check("B4", "the corrected record runs again under the same number",
            again.get("number") == number)

    # ==================================================================== B5
    r.section("B5  Any N-ok observation is flagged to the Overall Process Owner")

    flagged = fill_and_submit(fmt, "42")
    r.check("B5c", "an out-of-specification record raises a flag at once",
            flagged["nok_open"] and flagged["stage"] == "po_approval")
    r.check("B5c", "the flag is addressed to the Overall Process Owner",
            flagged["nok_flagged_to"]
            and flagged["nok_flagged_to"]["id"] == people["s.iyer"]["id"])
    r.check("B6c", "a flagged record reads red",
            flagged["rag"] == "red")
    r.check("B5c", "the Process Owner cannot close their own flag",
            po.post(f"/api/records/{flagged['id']}/nok/clear",
                    json={"note": "x"}).status_code == 403)

    flagged = advance(flagged, "approved")
    blocked = opo.post(f"/api/records/{flagged['id']}/store", json={})
    r.check("B8", "an approved record with an open flag cannot be filed",
            blocked.status_code == 400 and "N-ok" in why(blocked), why(blocked))
    opo.post(f"/api/records/{flagged['id']}/nok/clear",
             json={"note": "Batch quarantined, tool reset."})
    r.check("B8", "once the action is recorded, it can be filed",
            opo.post(f"/api/records/{flagged['id']}/store",
                     json={}).status_code == 200)

    # ==================================================================== B6
    r.section("B6  The joint review goes to every CFT member, to a target date")

    rec = advance(fill_and_submit(fmt, "5"), "cft_review")
    w = rec["workflow_id"]
    r.check("B6", "the review is addressed to every CFT member",
            len(po.step(w)["assignees"]) == 2)
    r.check("B6", "with a target date",
            bool(rec["cft_target_date"]))
    r.check("B6c", "a record cleared by both approvals reads green",
            rec["rag"] == "green", f"rag={rec['rag']}")
    r.check("B6", "every member is told a review has opened",
            any(n["kind"] == "record.cft_review" for n in
                cft1.get("/api/records/notifications/mine").json()["notifications"]))

    cft1.decide(w, cft1.step(w)["id"], "approve", sign=False)
    r.check("B6", "one member agreeing does not conclude a joint review",
            po.step(w)["name"] == "CFT joint review")
    r.check("B6", "a member cannot answer the same review twice",
            cft1.decide(w, po.step(w)["id"], "approve",
                        sign=False).status_code == 400)
    cft2.decide(w, cft2.step(w)["id"], "approve", sign=False)
    r.check("B7", "the final decision opens once the CFT has concluded",
            po.step(w)["name"] == "Final decision")

    objected = advance(fill_and_submit(fmt, "5"), "cft_review")
    w2 = objected["workflow_id"]
    dissent = cft1.decide(w2, cft1.step(w2)["id"], "reject",
                          reason="Gauge log disagrees.")
    r.check("B6", "a member's disagreement does not end the process",
            dissent.status_code == 200 and dissent.json()["status"] == "active")
    cft2.decide(w2, cft2.step(w2)["id"], "approve", sign=False)
    body = po.record(objected["id"])
    r.check("B7c", "the objection reaches whoever takes the final decision",
            bool(body["cft_objection"]), "no objection carried")
    r.check("B6c", "an objected record does not read as ok for final review",
            body["rag"] == "red")

    # ==================================================================== B7
    r.section("B7  The final decision, and D1's two branches")

    rec = advance(fill_and_submit(fmt, "5"), "final_decision")
    w = rec["workflow_id"]
    r.check("B7", "a CFT member cannot take the final decision",
            cft1.decide(w, po.step(w)["id"], "approve").status_code == 400)
    r.check("B7", "sending a record back must say why",
            po.decide(w, po.step(w)["id"], "reject", reason="").status_code == 400)

    back = po.decide(w, po.step(w)["id"], "reject",
                     reason="Re-check against the gauge log.")
    body = po.record(rec["id"])
    r.check("D1 No", "the approval stays alive",
            back.json()["status"] == "active", f"status={back.json()['status']}")
    r.check("D1 No", "the record returns to the CFT",
            body["stage"] == "cft_review")
    r.check("D1 No", "and turns red - needs to reverify with CFT",
            body["rag"] == "red" and body["rag_label"] == "Needs to reverify with CFT")
    r.check("D1 No", "every previous CFT answer is cleared",
            len(po.step(w)["outstanding"]) == 2)
    r.check("D1 No", "the round is counted", body["reverify_count"] == 1)
    r.check("D1 No", "the record can be corrected while it is back",
            po.put(f"/api/records/{rec['id']}/values",
                   json={"values": [{"label": "Reading",
                                     "value": "7"}]}).status_code == 200)

    cft1.decide(w, cft1.step(w)["id"], "approve", sign=False)
    cft2.decide(w, cft2.step(w)["id"], "approve", sign=False)
    po.decide(w, po.step(w)["id"], "approve")
    r.check("D1 Yes", "a re-verified record can still be approved",
            po.record(rec["id"])["workflow_status"] == "approved")

    # ==================================================================== B8
    r.section("B8  The Overall Process Owner files it, by frequency")

    now = datetime.utcnow()
    frequencies = {
        "daily":       f"{now:%Y} / {now:%m-%b} / {now:%d}",
        "weekly":      f"{now.isocalendar()[0]:04d} / W{now.isocalendar()[1]:02d}",
        "monthly":     f"{now:%Y} / {now:%m-%b}",
        "quarterly":   f"{now:%Y} / Q{(now.month - 1) // 3 + 1}",
        "yearly":      f"{now:%Y}",
    }
    if not args.quick:
        frequencies.update({
            "shift":       f"{now:%Y} / {now:%m-%b} / {now:%d}",
            "half_yearly": f"{now:%Y} / H{1 if now.month <= 6 else 2}",
            "per_event":   f"{now:%Y} / {now:%m-%b}",
        })

    for i, (frequency, tail) in enumerate(sorted(frequencies.items())):
        one = build_format(f"F{i}", frequency=frequency)
        filed = advance(fill_and_submit(one, "5"), "stored")
        want = f"Records / Process Quality / {one['code']} / {tail}"
        r.check("B8", f"a {frequency} record is filed at .../{tail}",
                filed["storage_path"] == want, filed["storage_path"])

    r.check("B8", "a CFT member cannot file a record",
            cft1.post(f"/api/records/{filed['id']}/store",
                      json={}).status_code in (400, 403))

    tree = opo.get("/api/records/storage/tree").json()
    register = admin.get("/api/records/?limit=1000").json()
    in_tree = sum(len(f["records"]) for f in tree["folders"])
    in_register = len([x for x in register["records"] if x["stage"] == "stored"])
    r.check("B8", "the storage view and the register agree",
            in_tree == in_register, f"storage={in_tree} register={in_register}")

    # ================================================================ D2, B9
    r.section("B9  No format changes without the QMS Coordinator")

    r.check("B9", "an active format cannot be edited directly, even by an admin",
            admin.put(f"/api/formats/{fmt['id']}",
                      json={"title": "Edited"}).status_code == 400)

    dcr = po.post("/api/change-requests/", json={
        "kind": "change_existing", "format_id": fmt["id"],
        "title": "Widen the tolerance", "reason": "Capability study.",
        "proposed_change": "0.5 to 12 mm."})
    r.check("B9", "a Process Owner can raise a change request",
            dcr.status_code == 200, why(dcr))
    dcr = dcr.json()
    r.check("B9c1", "it is addressed to the QMS Coordinator",
            dcr["coordinator"]["id"] == people["m.shaikh"]["id"])
    r.check("B9c1", "who is notified",
            any(n["kind"] == "dcr.submitted" for n in
                qms.get("/api/records/notifications/mine").json()["notifications"]))
    r.check("B9", "only one change request may be open on a format at a time",
            po.post("/api/change-requests/", json={
                "kind": "change_existing", "format_id": fmt["id"], "title": "Second",
                "reason": "x", "proposed_change": "y"}).status_code == 400)
    r.check("B9", "nobody approves their own change request",
            po.post(f"/api/change-requests/{dcr['id']}/decide",
                    json={"action": "approve"}).status_code == 403)
    r.check("B9", "a change cannot be executed before it is approved",
            qms.post(f"/api/change-requests/{dcr['id']}/execute",
                     json={}).status_code == 400)

    qms.post(f"/api/change-requests/{dcr['id']}/decide",
             json={"action": "approve", "comment": "Agreed."})
    done = qms.post(f"/api/change-requests/{dcr['id']}/execute", json={})
    r.check("B9", "approval then execution creates the next revision",
            done.status_code == 200 and done.json()["format"]["revision"] == "01",
            why(done))
    if done.status_code == 200:
        successor = done.json()["format"]
        r.check("B9", "the new revision starts as a draft",
                successor["status"] == "draft")
        r.check("B9", "the previous revision is superseded, not deleted",
                admin.get(f"/api/formats/{fmt['id']}").json()["status"] == "superseded")
        r.check("B9", "a superseded format can no longer be filled",
                po.post("/api/records/call",
                        json={"format_id": fmt["id"]}).status_code == 400)
        r.check("B9", "records keep the revision they were filled against",
                po.record(ok_record["id"])["format_revision"] == "00")
        admin.post(f"/api/formats/{successor['id']}/publish-without-approval", json={})
        r.check("B9c2", "the released revision is what is called from now on",
                any(f["id"] == successor["id"]
                    for f in po.get("/api/formats/callable").json()["formats"]))

    # ================================================================= teams
    r.section("Teams  each of the three owns its own formats and records")

    supplier = sq_po.get("/api/formats/callable").json()["formats"]
    r.check("teams", "a Supplier Quality owner is offered only SQ formats",
            all(f["team"]["code"] == "SQ" for f in supplier))
    r.check("teams", "a Process Quality owner is not offered SQ formats",
            not any(f["team"]["code"] == "SQ"
                    for f in po.get("/api/formats/callable").json()["formats"]))
    if supplier:
        r.check("teams", "and cannot raise another team's record",
                po.post("/api/records/call",
                        json={"format_id": supplier[0]["id"]}).status_code == 400)

    # =========================================================== concurrency
    if not args.quick:
        r.section("Concurrency  two people acting at the same moment")

        shared = build_format("CONC")
        rec = advance(fill_and_submit(shared, "5"), "cft_review")
        w = rec["workflow_id"]
        step_id = po.step(w)["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            codes = [f.result().status_code for f in [
                pool.submit(who.decide, w, step_id, "approve", False)
                for who in (cft1, cft2)]]
        r.check("B6", "both CFT members can answer simultaneously",
                codes.count(200) == 2, f"HTTP {codes}")
        nxt = po.step(w)
        r.check("B6", "and the review concludes exactly once",
                nxt and nxt["name"] == "Final decision",
                f"at {nxt['name'] if nxt else 'nothing - the review deadlocked'}")

        po.decide(w, po.step(w)["id"], "approve")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            [f.result() for f in [
                pool.submit(opo.post, f"/api/records/{rec['id']}/store", json={})
                for _ in range(2)]]
        tree = admin.get("/api/records/storage/tree").json()
        number = po.record(rec["id"])["number"]
        appearances = sum(1 for f in tree["folders"] for x in f["records"]
                          if x["number"] == number)
        r.check("B8", "filing twice files the record once",
                appearances == 1, f"appears {appearances} times")

    # =========================================================== the numbers
    r.section("Reporting  the register, the trail, and the numbers")

    data = admin.get("/api/records/?limit=1000").json()
    stats, records = data["stats"], data["records"]
    r.check("BI", "the total matches the number of records",
            stats["total"] == len(records), f"{stats['total']} vs {len(records)}")
    r.check("BI", "the traffic-light counts add up to the total",
            stats["green"] + stats["yellow"] + stats["red"] == stats["total"])
    r.check("BI", "every record is in exactly one stage",
            sum(stats[k] for k in ("filling", "po_approval", "opo_approval",
                                   "cft_review", "final_decision", "stored"))
            == stats["total"])
    r.check("BI", "the open-flag count matches the records carrying one",
            stats["nok_open"] == len([x for x in records if x["nok_open"]]))

    fired = set()
    for who in (po, opo, cft1, cft2, qms):
        for n in who.get("/api/records/notifications/mine").json()["notifications"]:
            fired.add(n["kind"])
    for kind in ("record.submitted", "record.po_approved", "record.nok_flagged",
                 "record.cft_review", "record.reverify", "record.stored",
                 "dcr.submitted", "dcr.decided"):
        r.check("trail", f"the '{kind}' trigger fires", kind in fired)

    r.check("trail", "the audit log is readable",
            admin.get("/api/audit/?limit=100").status_code == 200)

    # ============================================================== the doors
    r.section("Access  the screens and who may open them")

    for path in ("/formats", "/records", "/records/new", "/storage",
                 "/change-requests", "/track", "/tasks"):
        r.check("screens", f"{path} is served", admin.get(path).status_code == 200)

    r.check("screens", "the format library is administrators only",
            po.get("/formats").status_code == 302)
    r.check("screens", "a Process Owner still reaches the screens they work on",
            all(po.get(p).status_code == 200
                for p in ("/records/new", "/records", "/storage", "/change-requests")))

    stranger = httpx.Client(base_url=base, follow_redirects=False, timeout=30)
    r.check("security", "an unauthenticated caller cannot read the register",
            stranger.get("/api/records/").status_code in (401, 403))
    r.check("security", "an unauthenticated visitor is sent to sign in",
            stranger.get("/records").status_code == 302)

    r.section("Robustness  the awkward requests")
    r.check("robust", "an unknown record answers 404",
            po.get("/api/records/no-such-thing").status_code == 404)
    r.check("robust", "an unknown format answers 404",
            po.post("/api/records/call",
                    json={"format_id": "no-such-thing"}).status_code == 404)
    r.check("robust", "a malformed request answers 422, not 500",
            po.post("/api/records/call", json={}).status_code == 422)

    return r.finish()


if __name__ == "__main__":
    raise SystemExit(main())
