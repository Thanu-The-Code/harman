"""
The record process over HTTP, through the real application.

The service-level suite in `test_qms_record_workflow.py` proves the rules. This
one proves they are actually reachable: that the routers are wired, that
permissions are enforced at the edge and not only in the services, and - most
importantly - that rejecting the final decision *through the ordinary workflow
API* produces the chart's loop back to the CFT rather than a terminated
approval. An approver acts from My Tasks, not from a record screen, so that
path is the one that has to be right.
"""
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AuditLog, User
from app.models_qms import Record, RecordEvent, STAGE_FINAL, STAGE_STORED
from app.services import format_service as fmts


@pytest.fixture
def client(monkeypatch):
    """The whole application against an in-memory database."""
    monkeypatch.setenv("AUTHENTICATION_ENABLED", "true")
    from app.config import reset_settings

    reset_settings()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    test_client = TestClient(app)
    test_client.db_factory = Session
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        reset_settings()


def _make_user(db, username, **kwargs):
    user = User(
        username=username,
        email=f"{username}@harman.example",
        full_name=username.replace("_", " ").title(),
        is_active=True,
        is_admin=kwargs.pop("is_admin", False),
        department="Quality",
        can_approve=True,
        can_sign=True,
        **kwargs,
    )
    user.set_password("Passw0rd!secret")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def world(client):
    """Four responsibilities, one released format, and a signed-in admin."""
    db = client.db_factory()
    try:
        people = {
            "admin": _make_user(db, "admin", is_admin=True),
            "po": _make_user(db, "process_owner"),
            "opo": _make_user(db, "overall_process_owner"),
            "cft1": _make_user(db, "cft_one"),
            "cft2": _make_user(db, "cft_two"),
            "qms": _make_user(db, "qms_coordinator"),
        }
        fmts.ensure_teams(db)
        from app.models_qms import QualityTeam
        team = db.query(QualityTeam).filter(QualityTeam.code == "PQ").first()

        fmt = fmts.create_format(db, people["admin"], {
            "code": "QF-PQ-001",
            "title": "In-process dimensional check",
            "team_id": team.id,
            "frequency": "daily",
            "cft_target_days": 3,
            "process_owner_id": people["po"].id,
            "overall_process_owner_id": people["opo"].id,
            "qms_coordinator_id": people["qms"].id,
            "cft_member_ids": [people["cft1"].id, people["cft2"].id],
            "fields": [
                {"label": "Bore diameter", "field_type": "number", "unit": "mm",
                 "spec_min": 24.9, "spec_max": 25.1},
                {"label": "Operator", "field_type": "text"},
            ],
        })
        fmts.activate(db, fmt, people["admin"])

        return {
            "ids": {k: v.id for k, v in people.items()},
            "names": {k: v.username for k, v in people.items()},
            "format_id": fmt.id,
            "team_id": team.id,
        }
    finally:
        db.close()


def _login(client, username):
    """Sign in and retain the authentication session cookie."""
    res = client.post("/api/auth/login",
                      json={"username": username, "password": "Passw0rd!secret"})
    assert res.status_code == 200, res.text
    return res


SIGNATURE = {"dataUrl": "data:image/png;base64,iVBORw0KGgo=", "name": "Tester"}


def _detail(res):
    """Return the message from either wrapped or standard HTTP errors."""
    body = res.json()
    if isinstance(body.get("error"), dict):
        return str(body["error"].get("detail", ""))
    return str(body.get("detail", ""))


def _decide(client, workflow_id, step_id, action, **kwargs):
    body = {"action": action, "comment": kwargs.get("comment", ""),
            "reason": kwargs.get("reason", "")}
    if kwargs.get("sign", True) and action == "approve":
        body["signature"] = SIGNATURE
    return client.post(
        f"/api/workflow/{workflow_id}/steps/{step_id}/decide", json=body)


def _current_step(client, workflow_id):
    res = client.get(f"/api/workflow/{workflow_id}")
    assert res.status_code == 200, res.text
    return res.json()["current_step"]


def test_notification_outbox_uses_live_user_email_when_row_email_is_blank(client, world):
    db = client.db_factory()
    try:
        user = db.query(User).filter(User.username == world["names"]["po"]).first()
        assert user is not None

        from app.models_qms import Notification
        row = Notification(
            kind="record.submitted",
            subject="Approval required",
            body="body",
            to_user_id=user.id,
            to_email=None,
            status="queued",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        _login(client, world["names"]["admin"])
        res = client.get("/api/records/notifications/outbox")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["mail_configured"] in (True, False)
        assert any(n["id"] == row.id and n["to_email"] == user.email for n in body["notifications"])
    finally:
        db.close()


def _document(db):
    from app.models import Document
    doc = Document(
        filename="scan.pdf", original_filename="scan.pdf",
        file_hash=f"h{datetime.utcnow().timestamp()}", file_path="/tmp/scan.pdf",
        file_size=1024, mime_type="application/pdf", title="Filled record",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc.id


# --------------------------------------------------------------------- B1


def test_format_library_is_reachable_and_lists_the_released_format(client, world):
    _login(client, world["names"]["admin"])
    res = client.get("/api/formats/")
    assert res.status_code == 200, res.text

    body = res.json()
    codes = [f["code"] for f in body["formats"]]
    assert "QF-PQ-001" in codes
    assert {f["value"] for f in body["frequencies"]} >= {"daily", "monthly", "yearly"}

    fmt = next(f for f in body["formats"] if f["code"] == "QF-PQ-001")
    assert fmt["status"] == "active"
    assert fmt["readiness"] == []
    assert fmt["storage_preview"].startswith("Records / Process Quality / QF-PQ-001 /")


def test_template_folders_can_be_created_selected_and_browsed_in_the_repo(client, world):
    _login(client, world["names"]["admin"])
    root = client.post("/api/formats/folders", json={"name": "Teams"})
    assert root.status_code == 200, root.text
    child = client.post("/api/formats/folders", json={
        "name": "Quality Control",
        "parent_path": root.json()["path"],
    })
    assert child.status_code == 200, child.text
    selected_folder = client.post("/api/formats/folders", json={
        "name": "Procedures",
        "parent_path": child.json()["path"],
    })
    assert selected_folder.status_code == 200, selected_folder.text
    folder_path = selected_folder.json()["path"]

    created = client.post("/api/formats", json={
        "code": "QF-PQ-FOLDER-001",
        "title": "Folder selection test",
        "frequency": "daily",
        "storage_path": folder_path,
        "fields": [],
    })
    assert created.status_code == 200, created.text
    assert created.json()["storage_path"] == folder_path
    assert created.json()["folder_path"] == folder_path

    db = client.db_factory()
    try:
        released = fmts.get(db, world["format_id"])
        released.storage_path = folder_path
        db.commit()
    finally:
        db.close()

    repository = client.get("/api/formats/repository")
    assert repository.status_code == 200, repository.text
    body = repository.json()
    teams = next(folder for folder in body["folders"] if folder["name"] == "Teams")
    quality_control = teams["children"][0]
    procedures = quality_control["children"][0]
    assert procedures["path"] == folder_path
    assert any(template["id"] == world["format_id"] for template in procedures["templates"])

    tree = client.get("/api/formats/folders")
    assert tree.status_code == 200, tree.text
    assert tree.json()["folders"][0]["path"] == "Teams"
    assert tree.json()["folders"][0]["children"][0]["path"] == child.json()["path"]


def test_template_folder_api_rejects_unsafe_paths(client, world):
    _login(client, world["names"]["admin"])
    invalid_folder = client.post("/api/formats/folders", json={
        "name": "..",
    })
    assert invalid_folder.status_code == 422

    invalid_format = client.post("/api/formats", json={
        "code": "QF-PQ-UNSAFE-001",
        "title": "Unsafe folder path",
        "frequency": "daily",
        "storage_path": "Teams/../Private",
        "fields": [],
    })
    assert invalid_format.status_code == 400


def test_resource_library_lists_latest_revision_and_historical_details_are_admin_only(client, world):
    db = client.db_factory()
    try:
        original = fmts.get(db, world["format_id"])
        admin = db.query(User).filter(User.id == world["ids"]["admin"]).first()
        successor = fmts.new_revision(db, original, admin, {})
        fmts.activate(db, successor, admin)
        successor_id = successor.id
    finally:
        db.close()

    _login(client, world["names"]["po"])
    listed = client.get("/api/formats/").json()["formats"]
    matching = [fmt for fmt in listed if fmt["code"] == "QF-PQ-001"]
    assert [(fmt["revision"], fmt["status"]) for fmt in matching] == [("01", "active")]
    old_revision = client.get(f"/api/formats/{world['format_id']}")
    assert old_revision.status_code == 404
    assert "replaced by a newer revision" in old_revision.text  # an old link says where the form went
    rejected_request = client.post("/api/change-requests/", json={
        "kind": "change_existing",
        "format_id": world["format_id"],
        "title": "Change an old revision",
        "reason": "Testing that historical revisions are immutable.",
        "proposed_change": "Change the old revision.",
    })
    assert rejected_request.status_code == 400

    current = client.get(f"/api/formats/{successor_id}")
    assert current.status_code == 200, current.text
    assert current.json()["previous_revisions"] == []

    _login(client, world["names"]["admin"])
    listed = client.get("/api/formats/").json()["formats"]
    matching = [fmt for fmt in listed if fmt["code"] == "QF-PQ-001"]
    assert [(fmt["revision"], fmt["status"]) for fmt in matching] == [("01", "active")]
    historical = client.get(f"/api/formats/{successor_id}")
    assert historical.status_code == 200, historical.text
    assert [revision["revision"] for revision in historical.json()["previous_revisions"]] == ["00"]


def test_admin_format_repository_returns_template_groups_and_revision_metadata(client, world):
    db = client.db_factory()
    try:
        original = fmts.get(db, world["format_id"])
        admin = db.query(User).filter(User.id == world["ids"]["admin"]).first()
        successor = fmts.new_revision(db, original, admin, {})
        fmts.activate(db, successor, admin)
        successor_id = successor.id
    finally:
        db.close()

    _login(client, world["names"]["admin"])
    response = client.get("/api/formats/repository")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    template = body["templates"][0]
    assert template["id"] == successor_id
    assert template["code"] == "QF-PQ-001"
    assert template["version_count"] == 2
    assert [version["revision"] for version in template["versions"]] == ["01", "00"]
    assert template["latest_version"]["id"] == successor_id
    assert template["released_version"]["id"] == successor_id

    detail = client.get(f"/api/formats/{template['id']}")
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert [version["revision"] for version in detail_body["versions"]] == ["01", "00"]
    assert all(version["fields"] for version in detail_body["versions"])
    assert {version["id"] for version in detail_body["versions"]} == {
        world["format_id"],
        successor_id,
    }

    _login(client, world["names"]["po"])
    forbidden = client.get("/api/formats/repository")
    assert forbidden.status_code == 403


def test_latest_template_detail_contains_full_details_for_every_revision(client, world):
    db = client.db_factory()
    try:
        original = fmts.get(db, world["format_id"])
        admin = db.query(User).filter(User.id == world["ids"]["admin"]).first()
        successor = fmts.new_revision(db, original, admin, {})
        fmts.activate(db, successor, admin)
        latest_id = successor.id
    finally:
        db.close()

    _login(client, world["names"]["admin"])
    response = client.get(f"/api/formats/{latest_id}")

    assert response.status_code == 200, response.text
    versions = response.json()["versions"]
    assert [version["revision"] for version in versions] == ["01", "00"]
    assert all(version["fields"] for version in versions)
    assert {version["id"] for version in versions} == {
        world["format_id"],
        latest_id,
    }


def test_the_three_quality_teams_are_seeded(client, world):
    _login(client, world["names"]["admin"])
    teams = client.get("/api/formats/teams").json()["teams"]
    assert {t["code"] for t in teams} == {"PQ", "SQ", "CQ"}


# ----------------------------------------------------------------- B2, B3


def test_only_the_process_owner_sees_the_format_as_callable(client, world):
    _login(client, world["names"]["cft1"])
    mine = client.get("/api/formats/callable").json()["formats"]
    assert mine == []

    _login(client, world["names"]["po"])
    mine = client.get("/api/formats/callable").json()["formats"]
    assert [f["code"] for f in mine] == ["QF-PQ-001"]
    assert mine[0]["existing_for_period"] is None


def test_calling_filling_and_submitting_over_http(client, world):
    _login(client, world["names"]["po"])

    called = client.post("/api/records/call", json={"format_id": world["format_id"]})
    assert called.status_code == 200, called.text
    record = called.json()
    assert record["stage"] == "filling"
    assert record["rag"] == "yellow"
    assert len(record["values"]) == 2

    bore = next(v for v in record["values"] if v["label"] == "Bore diameter")
    filled = client.put(f"/api/records/{record['id']}/values", json={"values": [
        {"id": bore["id"], "value": "25.0"},
        {"id": next(v["id"] for v in record["values"] if v["label"] == "Operator"),
         "value": "R. Kumar"},
    ]})
    assert filled.status_code == 200, filled.text
    assert filled.json()["observation_status"] == "ok"
    assert filled.json()["missing"] == []

    db = client.db_factory()
    try:
        document_id = _document(db)
    finally:
        db.close()

    submitted = client.post(f"/api/records/{record['id']}/submit",
                            json={"document_id": document_id})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["stage"] == "po_approval"
    assert submitted.json()["workflow_id"]


def test_an_empty_record_cannot_be_submitted(client, world):
    """Blanks are allowed through; a form nobody has touched is not."""
    _login(client, world["names"]["po"])
    record = client.post("/api/records/call",
                         json={"format_id": world["format_id"]}).json()

    db = client.db_factory()
    try:
        document_id = _document(db)
    finally:
        db.close()

    res = client.post(f"/api/records/{record['id']}/submit",
                      json={"document_id": document_id})
    assert res.status_code == 400
    assert "Nothing has been filled in" in _detail(res)


def test_a_half_filled_record_with_no_scan_is_accepted(client, world):
    """The two things that used to block a submission, together."""
    _login(client, world["names"]["po"])
    record = client.post("/api/records/call",
                         json={"format_id": world["format_id"]}).json()
    client.put(f"/api/records/{record['id']}/values",
               json={"values": [{"label": "Bore diameter", "value": "25.0"}]})

    res = client.post(f"/api/records/{record['id']}/submit", json={})

    assert res.status_code == 200, _detail(res)
    assert res.json()["stage"] == "po_approval"


def test_somebody_who_is_not_the_process_owner_cannot_fill(client, world):
    _login(client, world["names"]["po"])
    record = client.post("/api/records/call",
                         json={"format_id": world["format_id"]}).json()

    _login(client, world["names"]["cft1"])
    res = client.put(f"/api/records/{record['id']}/values",
                     json={"values": [{"label": "Bore diameter", "value": "25"}]})
    assert res.status_code == 403


# --------------------------------------------------------------- helpers


def _submit_record(client, world, bore="25.0"):
    _login(client, world["names"]["po"])
    record = client.post("/api/records/call",
                         json={"format_id": world["format_id"]}).json()
    client.put(f"/api/records/{record['id']}/values", json={"values": [
        {"label": "Bore diameter", "value": bore},
        {"label": "Operator", "value": "R. Kumar"},
    ]})
    db = client.db_factory()
    try:
        document_id = _document(db)
    finally:
        db.close()
    return client.post(f"/api/records/{record['id']}/submit",
                       json={"document_id": document_id}).json()


def test_approval_detail_api_includes_record_summary_assignment_and_timeline(client, world):
    record = _submit_record(client, world)
    _login(client, world["names"]["po"])

    detail = client.get(f"/api/records/{record['id']}/sheet")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["record"]["total_items"] == 2
    assert body["record"]["completed_items"] == 2
    assert {value["label"] for value in body["values"]} == {
        "Bore diameter", "Operator",
    }
    assert body["document"]["title"] == "Filled record"
    assert body["document"]["mime_type"] == "application/pdf"
    assert body["document"]["file_url"].endswith(
        f"/api/documents/{record['document_id']}/file"
    )
    assert body["approval"]["priority"] == "normal"
    assert body["approval"]["submitted_by"]["id"] == record["filled_by"]["id"]
    assert body["approval"]["submitted_at"]
    assert [person["id"] for person in body["approval"]["assigned_to"]] == [
        world["ids"]["po"],
    ]
    assert body["approval"]["current_step"] == "Process Owner approval"
    assert body["approval"]["progress"] == {"completed": 0, "total": 4}
    assert body["approvals"][0]["assigned_to"][0]["id"] == world["ids"]["po"]
    assert body["approvals"][0]["status"] == "current"
    assert body["approvals"][0]["due_date"]


def _advance_to_final(client, world):
    """Take a fresh record all the way to the final decision."""
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    step = _current_step(client, wf_id)
    assert _decide(client, wf_id, step["id"], "approve").status_code == 200

    _login(client, world["names"]["opo"])
    step = _current_step(client, wf_id)
    assert _decide(client, wf_id, step["id"], "approve").status_code == 200

    for who in ("cft1", "cft2"):
        _login(client, world["names"][who])
        step = _current_step(client, wf_id)
        assert _decide(client, wf_id, step["id"], "approve",
                       sign=False).status_code == 200

    return record


# ----------------------------------------------------------------- B4, B6


def test_the_chain_is_built_from_the_format_not_by_hand(client, world):
    record = _submit_record(client, world)
    _login(client, world["names"]["po"])

    workflow = client.get(f"/api/workflow/{record['workflow_id']}").json()
    assert [s["name"] for s in workflow["steps"]] == [
        "Process Owner approval",
        "Overall Process Owner approval",
        "CFT joint review",
        "Final decision",
    ]

    cft = workflow["steps"][2]
    assert cft["approval_mode"] == "all", "the joint review is not joint"
    assert len(cft["assignees"]) == 2
    assert workflow["steps"][0]["assignees"][0]["id"] == world["ids"]["po"]
    assert workflow["steps"][1]["assignees"][0]["id"] == world["ids"]["opo"]


def test_one_cft_member_does_not_close_the_joint_review(client, world):
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")
    _login(client, world["names"]["opo"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")

    _login(client, world["names"]["cft1"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve", sign=False)

    step = _current_step(client, wf_id)
    assert step["name"] == "CFT joint review"
    assert [p["id"] for p in step["outstanding"]] == [world["ids"]["cft2"]]


def test_rag_turns_green_once_both_approvals_are_done(client, world):
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")
    assert client.get(f"/api/records/{record['id']}").json()["rag"] == "yellow"

    _login(client, world["names"]["opo"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")

    _login(client, world["names"]["po"])
    body = client.get(f"/api/records/{record['id']}").json()
    assert body["rag"] == "green"
    assert body["rag_label"] == "Ok for final review"
    assert body["stage"] == "cft_review"


# --------------------------------------------------------------------- B5


def test_an_out_of_spec_reading_flags_the_overall_process_owner(client, world):
    record = _submit_record(client, world, bore="26.4")

    assert record["observation_status"] == "not_ok"
    assert record["nok_open"] is True
    assert record["nok_flagged_to"]["id"] == world["ids"]["opo"]
    assert record["rag"] == "red"

    # And the Overall Process Owner can see it waiting for them.
    _login(client, world["names"]["opo"])
    mine = client.get("/api/records/notifications/mine").json()
    assert any(n["kind"] == "record.nok_flagged" for n in mine["notifications"])


def test_only_the_overall_process_owner_closes_an_nok_flag(client, world):
    record = _submit_record(client, world, bore="26.4")

    _login(client, world["names"]["po"])
    res = client.post(f"/api/records/{record['id']}/nok/clear",
                      json={"note": "looked at it"})
    assert res.status_code == 403

    _login(client, world["names"]["opo"])
    res = client.post(f"/api/records/{record['id']}/nok/clear",
                      json={"note": "Tool changed, batch quarantined."})
    assert res.status_code == 200, res.text
    assert res.json()["nok_open"] is False


# ------------------------------------------------------------------ D1 "No"


def test_rejecting_the_final_decision_returns_the_record_to_the_cft(client, world):
    """
    The single most important behaviour in the build.

    An approver rejects from the ordinary workflow API, exactly as they would
    on any document. For a record, that must NOT end the process: the chart's
    arrow goes back up to the CFT joint review.
    """
    record = _advance_to_final(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    step = _current_step(client, wf_id)
    assert step["name"] == "Final decision"

    res = _decide(client, wf_id, step["id"], "reject",
                  reason="Bore readings disagree with the gauge log.")
    assert res.status_code == 200, res.text

    workflow = res.json()
    assert workflow["status"] == "active", "the approval was terminated"
    assert workflow["current_step"]["name"] == "CFT joint review"
    # Last round's approvals cannot count towards this one.
    assert {p["id"] for p in workflow["current_step"]["outstanding"]} == {
        world["ids"]["cft1"], world["ids"]["cft2"]}

    body = client.get(f"/api/records/{record['id']}").json()
    assert body["stage"] == "cft_review"
    assert body["reverify_count"] == 1
    assert body["rag"] == "red"
    assert body["rag_label"] == "Needs to reverify with CFT"


def test_a_reverified_record_can_still_be_completed_and_filed(client, world):
    record = _advance_to_final(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "reject",
            reason="Re-check against the gauge log.")

    for who in ("cft1", "cft2"):
        _login(client, world["names"][who])
        _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve", sign=False)

    _login(client, world["names"]["po"])
    step = _current_step(client, wf_id)
    assert step["name"] == "Final decision"
    assert _decide(client, wf_id, step["id"], "approve").status_code == 200

    _login(client, world["names"]["opo"])
    stored = client.post(f"/api/records/{record['id']}/store", json={})
    assert stored.status_code == 200, stored.text
    assert stored.json()["stage"] == "stored"


# --------------------------------------------------------------------- B8


def test_an_approved_record_is_filed_in_a_date_wise_folder(client, world):
    record = _advance_to_final(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")

    _login(client, world["names"]["opo"])
    stored = client.post(f"/api/records/{record['id']}/store", json={})
    assert stored.status_code == 200, stored.text

    now = datetime.utcnow()
    expected = (f"Records / Process Quality / QF-PQ-001 / "
                f"{now:%Y} / {now:%m-%b} / {now:%d}")
    assert stored.json()["storage_path"] == expected

    tree = client.get("/api/records/storage/tree").json()
    assert tree["total"] == 1
    assert tree["folders"][0]["path"] == expected


def test_document_repository_lists_and_filters_filed_records(client, world):
    from app.models import ApprovalStep, ApprovalWorkflow, WorkflowEvent
    from app.models_qms import RecordFieldValue

    db = client.db_factory()
    try:
        folder_path = "Records / Process Quality / QF-PQ-001 / 2026 / Oct / 09"
        record = Record(
            number="REC-QF-PQ-001-20261009-01",
            format_id=world["format_id"],
            team_id=world["team_id"],
            stage=STAGE_STORED,
            storage_path=folder_path,
            stored_at=datetime.utcnow(),
            stored_by=world["ids"]["opo"],
        )
        not_filed = Record(
            number="REC-QF-PQ-001-20261009-02",
            format_id=world["format_id"],
            team_id=world["team_id"],
            stage=STAGE_FINAL,
        )
        db.add_all([record, not_filed])
        db.flush()

        document_id = _document(db)
        record.document_id = document_id
        record.values.append(RecordFieldValue(
            label="Bore diameter",
            field_type="number",
            unit="mm",
            value="25.0",
            in_spec=True,
        ))
        workflow = ApprovalWorkflow(
            document_id=document_id,
            name="Repository approval",
            status="approved",
            priority="normal",
            created_by=world["ids"]["po"],
            started_at=datetime.utcnow(),
        )
        db.add(workflow)
        db.flush()
        record.workflow_id = workflow.id
        step = ApprovalStep(
            workflow_id=workflow.id,
            order_index=0,
            name="Verify invoice",
            department="Quality",
            status="approved",
            decided_at=datetime.utcnow(),
            decided_by=world["ids"]["po"],
            comment="Checked against the work instruction.",
        )
        db.add(step)
        db.flush()
        db.add(WorkflowEvent(
            workflow_id=workflow.id,
            step_id=step.id,
            actor_id=world["ids"]["po"],
            kind="approved",
            summary="Process Owner approved the record",
            detail="Checked against the work instruction.",
        ))
        # the record's own history: one that restates the approval, one that only it has
        db.add_all([
            RecordEvent(record_id=record.id, actor_id=world["ids"]["po"], kind="po_approved",
                        summary="Process Owner approved the record as within specification"),
            RecordEvent(record_id=record.id, actor_id=world["ids"]["opo"], kind="stored",
                        summary=f"Filed the record at {folder_path}"),
        ])
        db.commit()
        record_id = record.id
    finally:
        db.close()

    _login(client, world["names"]["admin"])

    repository = client.get("/api/documents/repository").json()
    assert repository["pagination"]["total"] == 1
    assert len(repository["documents"]) == 1
    assert repository["folders"][0]["name"] == "Process Quality"
    assert repository["folders"][0]["children"][0]["name"] == "QF-PQ-001"
    document = repository["documents"][0]
    assert document["record_id"] == record_id
    assert document["document_name"] == "In-process dimensional check"
    assert document["department"] == "Process Quality"
    assert document["type"] == "Daily"
    assert document["filed_by_name"] == "Overall Process Owner"
    assert document["folder_path"] == folder_path
    assert document["view_url"] == f"/api/records/{record_id}/sheet"

    summary = client.get(
        f"/api/documents/repository/{record_id}/summary"
    )
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["record_id"] == record_id
    assert summary_body["summary"]["name"] == "In-process dimensional check"
    assert summary_body["summary"]["code"] == "QF-PQ-001"
    assert summary_body["summary"]["department"] == "Process Quality"
    assert summary_body["summary"]["total_items"] == 1
    assert summary_body["summary"]["completed_items"] == 1
    assert summary_body["document"]["id"] == document_id

    timeline = client.get(
        f"/api/documents/repository/{record_id}/approval-timeline"
    )
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["record_id"] == record_id
    assert timeline.json()["steps"][0]["name"] == "Verify invoice"
    assert timeline.json()["steps"][0]["status"] == "approved"
    assert timeline.json()["steps"][0]["comment"] == (
        "Checked against the work instruction."
    )
    kinds = [event["kind"] for event in timeline.json()["events"]]
    # the approval's own trail, and around it the record's: called, filed - not its approvals twice
    assert "approved" in kinds and "stored" in kinds and "po_approved" not in kinds

    searched = client.get(
        "/api/documents/repository",
        params={
            "search": "Process Quality",
            "folder_path": folder_path,
            "filed_date": datetime.utcnow().date().isoformat(),
            "date_from": datetime.utcnow().date().isoformat(),
            "date_to": datetime.utcnow().date().isoformat(),
        },
    ).json()
    assert searched["pagination"]["total"] == 1
    assert searched["documents"][0]["record_id"] == record_id

    future = client.get(
        "/api/documents/repository",
        params={"date_from": "2999-01-01"},
    ).json()
    assert future["pagination"]["total"] == 0


def test_activity_log_supports_date_range_pagination_and_module_filter(client, world):
    today = date.today()
    db = client.db_factory()
    try:
        db.add_all([
            AuditLog(
                user_id=world["ids"]["admin"],
                action="format.created",
                resource_type="format",
                resource_id="format-one",
                created_at=datetime.combine(today, time(9, 0)),
            ),
            AuditLog(
                user_id=world["ids"]["admin"],
                action="format.updated",
                resource_type="format",
                resource_id="format-two",
                created_at=datetime.combine(today, time(10, 0)),
            ),
            AuditLog(
                user_id=world["ids"]["admin"],
                action="record.created",
                resource_type="record",
                resource_id="record-one",
                created_at=datetime.combine(today, time(11, 0)),
            ),
            AuditLog(
                user_id=world["ids"]["admin"],
                action="format.created",
                resource_type="format",
                resource_id="old-format",
                created_at=datetime.combine(today - timedelta(days=1), time(23, 59)),
            ),
        ])
        db.commit()
    finally:
        db.close()

    _login(client, world["names"]["admin"])
    response = client.get(
        "/api/audit",
        params={
            "date_from": today.isoformat(),
            "date_to": today.isoformat(),
            "module": "Template Builder",
            "page": 2,
            "page_size": 1,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["resource_id"] == "format-one"
    assert body["events"][0]["module"] == "Template Builder"
    assert body["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }

    modules = client.get("/api/audit/modules")
    assert modules.status_code == 200
    assert "Template Builder" in modules.json()["modules"]
    assert "My Documents" in modules.json()["modules"]


def test_activity_log_rejects_reversed_date_ranges(client, world):
    _login(client, world["names"]["admin"])
    response = client.get(
        "/api/audit",
        params={"date_from": "2026-10-02", "date_to": "2026-10-01"},
    )

    assert response.status_code == 422


def test_a_record_that_is_not_approved_cannot_be_filed(client, world):
    record = _submit_record(client, world)
    _login(client, world["names"]["opo"])
    res = client.post(f"/api/records/{record['id']}/store", json={})
    assert res.status_code == 400
    assert "not been fully approved" in _detail(res)


# --------------------------------------------------------------------- B9


def test_an_active_format_cannot_be_edited_directly_over_http(client, world):
    _login(client, world["names"]["admin"])
    res = client.put(f"/api/formats/{world['format_id']}",
                     json={"title": "Sneaky edit"})
    assert res.status_code == 400
    assert "change request" in _detail(res)


def test_change_request_reaches_the_coordinator_and_creates_a_revision(client, world):
    _login(client, world["names"]["po"])
    raised = client.post("/api/change-requests/", json={
        "kind": "change_existing",
        "format_id": world["format_id"],
        "title": "Widen the bore tolerance",
        "reason": "Capability study shows the band is too tight.",
        "proposed_change": "24.8 to 25.2 mm.",
    })
    assert raised.status_code == 200, raised.text
    request = raised.json()
    assert request["status"] == "submitted"
    assert request["coordinator"]["id"] == world["ids"]["qms"]

    # It is waiting on the coordinator, and on nobody else.
    _login(client, world["names"]["opo"])
    assert client.get("/api/change-requests/?waiting=true").json()["requests"] == []

    _login(client, world["names"]["qms"])
    waiting = client.get("/api/change-requests/?waiting=true").json()
    assert [r["number"] for r in waiting["requests"]] == [request["number"]]

    # The Process Owner cannot approve their own change request.
    _login(client, world["names"]["po"])
    res = client.post(f"/api/change-requests/{request['id']}/decide",
                      json={"action": "approve"})
    assert res.status_code == 403  # the wrong person, not a bad request
    assert "QMS Coordinator" in _detail(res)

    # Execution is refused before approval.
    _login(client, world["names"]["qms"])
    res = client.post(f"/api/change-requests/{request['id']}/execute", json={})
    assert res.status_code == 400

    approved = client.post(f"/api/change-requests/{request['id']}/decide",
                           json={"action": "approve", "comment": "Agreed."})
    assert approved.status_code == 200, approved.text

    executed = client.post(f"/api/change-requests/{request['id']}/execute", json={})
    assert executed.status_code == 200, executed.text
    created = executed.json()["format"]
    assert created["revision"] == "01"
    assert created["status"] == "draft", "a revision must be released deliberately"

    _login(client, world["names"]["admin"])
    old = client.get(f"/api/formats/{world['format_id']}").json()
    assert old["status"] == "superseded"


def test_record_change_request_api_lists_assigns_decides_and_tracks_implementation(client, world):
    _login(client, world["names"]["po"])
    unfilled = client.post("/api/records/call", json={
        "format_id": world["format_id"],
    }).json()
    not_filled = client.post("/api/record-change-requests/", json={
        "record_id": unfilled["id"],
        "reason": "This request should be refused until the record is filled.",
    })
    assert not_filled.status_code == 400

    record = _submit_record(client, world)

    raised = client.post("/api/record-change-requests/", json={
        "record_id": record["id"],
        "reason": "Remove obsolete inspection columns from the current record.",
    })
    assert raised.status_code == 200, raised.text
    request = raised.json()
    assert request["status"] == "open"
    assert request["record"]["document_name"] == "In-process dimensional check"
    assert request["record"]["department"] == "Process Quality"
    assert request["record"]["filled_by"]["id"] == record["filled_by"]["id"]
    assert request["record"]["total_items"] == 2
    assert request["record"]["completed_items"] == 2
    assert request["record"]["completion_percent"] == 100
    assert request["assigned_to"]["id"] == world["ids"]["qms"]

    # Search, department filtering, status tabs, counts, and page metadata.
    listed = client.get(
        "/api/record-change-requests/?status=open&department=Process%20Quality"
        "&search=inspection&page=1&page_size=1"
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [item["id"] for item in body["requests"]] == [request["id"]]
    assert body["stats"]["open"] == 1
    assert body["total"] == 1
    assert body["pages"] == 1
    second_page = client.get(
        "/api/record-change-requests/?status=open&department=Process%20Quality"
        "&search=inspection&page=2&page_size=1"
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["requests"] == []

    # Admins can reassign, while the requester can edit an open request.
    _login(client, world["names"]["admin"])
    assigned = client.post(
        f"/api/record-change-requests/{request['id']}/assign",
        json={"assigned_to_id": world["ids"]["qms"]},
    )
    assert assigned.status_code == 200, assigned.text
    unassigned = client.post(
        f"/api/record-change-requests/{request['id']}/assign",
        json={"assigned_to_id": None},
    )
    assert unassigned.status_code == 200, unassigned.text

    _login(client, world["names"]["qms"])
    waiting = client.get("/api/record-change-requests/?waiting=true").json()
    assert [item["id"] for item in waiting["requests"]] == [request["id"]]

    _login(client, world["names"]["admin"])
    reassigned = client.post(
        f"/api/record-change-requests/{request['id']}/assign",
        json={"assigned_to_id": world["ids"]["qms"]},
    )
    assert reassigned.status_code == 200, reassigned.text

    _login(client, world["names"]["po"])
    edited = client.patch(
        f"/api/record-change-requests/{request['id']}",
        json={"reason": "Remove the obsolete inspection columns."},
    )
    assert edited.status_code == 200, edited.text

    forbidden = client.post(
        f"/api/record-change-requests/{request['id']}/decide",
        json={"action": "approve"},
    )
    assert forbidden.status_code == 403

    # Only the assigned approver can decide; implementation is a separate step.
    _login(client, world["names"]["qms"])
    approved = client.post(
        f"/api/record-change-requests/{request['id']}/decide",
        json={"action": "approve", "comment": "Approved for implementation."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    implemented = client.post(
        f"/api/record-change-requests/{request['id']}/implement",
        json={"note": "Removed the two obsolete columns."},
    )
    assert implemented.status_code == 200, implemented.text
    assert implemented.json()["status"] == "implemented"
    assert implemented.json()["implementation_note"] == (
        "Removed the two obsolete columns."
    )
    assert implemented.json()["implemented_by"]["id"] == world["ids"]["qms"]


def test_record_change_request_requires_rejection_reason_and_prevents_duplicate_open_requests(
    client, world,
):
    record = _submit_record(client, world)
    raised = client.post("/api/record-change-requests/", json={
        "record_id": record["id"],
        "reason": "The current inspection sheet needs a correction.",
    })
    assert raised.status_code == 200, raised.text
    request_id = raised.json()["id"]

    duplicate = client.post("/api/record-change-requests/", json={
        "record_id": record["id"],
        "reason": "Another change.",
    })
    assert duplicate.status_code == 400

    _login(client, world["names"]["qms"])
    rejected = client.post(
        f"/api/record-change-requests/{request_id}/decide",
        json={"action": "not_approved"},
    )
    assert rejected.status_code == 400
    rejected = client.post(
        f"/api/record-change-requests/{request_id}/decide",
        json={"action": "not_approved", "comment": "Insufficient evidence."},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "not_approved"


# ------------------------------------------------------------- the screens


@pytest.mark.parametrize("path", [
    "/formats", "/records", "/records/new", "/storage", "/change-requests",
])
def test_every_process_screen_is_served(client, world, path):
    """The navigation follows the chart, so each of its stops must exist."""
    _login(client, world["names"]["admin"])
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 200, f"{path} returned {res.status_code}"
    assert "text/html" in res.headers["content-type"]
    if path == "/formats":
        assert "This is the project process screen." in res.text


def test_the_format_library_is_administrators_only(client, world):
    """Building a format is a set-up act, not part of filling one."""
    _login(client, world["names"]["po"])
    res = client.get("/formats", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/tasks"


def test_a_process_owner_still_reaches_the_screens_they_work_on(client, world):
    _login(client, world["names"]["po"])
    for path in ("/records/new", "/records", "/storage", "/change-requests"):
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 200, f"{path} redirected a Process Owner away"


# ===========================================================================
# The negative branches, over HTTP.
#
# An approver acts from My Tasks, through the ordinary workflow API. So it is
# that path - not the record API - that has to turn a disagreement into the
# right thing: an objection, a return for correction, or a send back to the
# CFT. None of them may end the process.
# ===========================================================================


def test_a_cft_member_disagreeing_from_my_tasks_records_an_objection(client, world):
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")
    _login(client, world["names"]["opo"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")

    # The CFT member presses the negative button on their task.
    _login(client, world["names"]["cft1"])
    step = _current_step(client, wf_id)
    assert step["qms_stage"] == "cft_review", "the screen cannot label the button"
    res = _decide(client, wf_id, step["id"], "reject",
                  reason="Bore readings disagree with the gauge log.")
    assert res.status_code == 200, res.text

    workflow = res.json()
    assert workflow["status"] == "active", "an objection ended the process"
    assert workflow["current_step"]["name"] == "CFT joint review"
    assert [p["id"] for p in workflow["current_step"]["outstanding"]] == [
        world["ids"]["cft2"]]

    body = client.get(f"/api/records/{record['id']}").json()
    assert body["rag"] == "red"
    assert "gauge log" in (body["cft_objection"] or "").lower()


def test_the_review_concludes_and_the_objection_reaches_the_final_decision(client, world):
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")
    _login(client, world["names"]["opo"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve")

    _login(client, world["names"]["cft1"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "reject",
            reason="Doubtful.")
    _login(client, world["names"]["cft2"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "approve", sign=False)

    _login(client, world["names"]["po"])
    step = _current_step(client, wf_id)
    assert step["name"] == "Final decision"

    body = client.get(f"/api/records/{record['id']}").json()
    assert body["stage"] == "final_decision"
    assert body["cft_objection"], "the final decision cannot see what the CFT said"

    # And the record can still be concluded and filed.
    assert _decide(client, wf_id, step["id"], "approve").status_code == 200
    _login(client, world["names"]["opo"])
    assert client.post(f"/api/records/{record['id']}/store", json={}).status_code == 200


def test_the_process_owner_returning_a_record_does_not_end_it(client, world):
    """B4 - not within specification, so it goes back to be corrected."""
    record = _submit_record(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    step = _current_step(client, wf_id)
    assert step["qms_stage"] == "po_approval"
    res = _decide(client, wf_id, step["id"], "reject",
                  reason="Readings disagree with the gauge log.")
    assert res.status_code == 200, res.text

    body = client.get(f"/api/records/{record['id']}").json()
    assert body["stage"] == "filling", "the record was not handed back"
    assert body["workflow_id"] is None
    assert body["can"]["amend"] is True


def test_a_returned_record_is_corrected_and_run_again_over_http(client, world):
    record = _submit_record(client, world)
    _login(client, world["names"]["po"])
    client.post(f"/api/records/{record['id']}/return",
                json={"reason": "Re-measure the bore."})

    filled = client.put(f"/api/records/{record['id']}/values", json={"values": [
        {"label": "Bore diameter", "value": "25.05"},
        {"label": "Operator", "value": "R. Kumar"},
    ]})
    assert filled.status_code == 200, filled.text

    again = client.post(f"/api/records/{record['id']}/submit", json={})
    assert again.status_code == 200, again.text
    assert again.json()["number"] == record["number"], "a correction made a new record"
    assert again.json()["stage"] == "po_approval"


def test_a_sent_back_record_is_open_for_correction_over_http(client, world):
    """The "No" branch returns through the ok / N-ok step, so it reopens."""
    record = _advance_to_final(client, world)
    wf_id = record["workflow_id"]

    _login(client, world["names"]["po"])
    _decide(client, wf_id, _current_step(client, wf_id)["id"], "reject",
            reason="Re-check against the gauge log.")

    body = client.get(f"/api/records/{record['id']}").json()
    assert body["can"]["amend"] is True

    corrected = client.put(f"/api/records/{record['id']}/values", json={"values": [
        {"label": "Bore diameter", "value": "25.05"},
        {"label": "Operator", "value": "R. Kumar"},
    ]})
    assert corrected.status_code == 200, corrected.text

    # And the CFT is asked again, rather than inheriting last round's answers.
    workflow = client.get(f"/api/workflow/{wf_id}").json()
    assert {p["id"] for p in workflow["current_step"]["outstanding"]} == {
        world["ids"]["cft1"], world["ids"]["cft2"]}


def test_a_record_step_reports_its_stage_so_buttons_can_be_labelled(client, world):
    """
    "Reject" is never the truth on a record. The screens need to know which
    stage a step is to say what the button actually does.
    """
    record = _submit_record(client, world)
    workflow = client.get(f"/api/workflow/{record['workflow_id']}").json()
    assert [s["qms_stage"] for s in workflow["steps"]] == [
        "po_approval", "opo_approval", "cft_review", "final_decision"]


def test_an_ordinary_document_step_has_no_qms_stage(client, world):
    """The document spine is untouched and still rejects normally."""
    _login(client, world["names"]["admin"])
    db = client.db_factory()
    try:
        document_id = _document(db)
    finally:
        db.close()

    made = client.post("/api/workflow/", json={
        "document_id": document_id,
        "name": "Ordinary approval",
        "steps": [{"name": "Review", "assignee_ids": [world["ids"]["po"]]}],
    })
    assert made.status_code == 200, made.text
    workflow = made.json()
    assert workflow["steps"][0]["qms_stage"] is None

    _login(client, world["names"]["po"])
    res = _decide(client, workflow["id"], workflow["steps"][0]["id"], "reject",
                  reason="Not acceptable")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"


def test_admins_stay_visible_in_team_scoped_approver_lists(client, world):
    """Admins are eligible approvers even when a format belongs to a quality team."""
    _login(client, world["names"]["admin"])
    db = client.db_factory()
    try:
        from app.models import User
        admin = db.query(User).filter(User.username == "admin").first()
        assert admin is not None
        team = db.query(User).filter(User.username == "process_owner").first()
        assert team is not None
        team.department = "Quality"
        admin.department = "Quality"
        db.commit()
    finally:
        db.close()

    fmt = client.get(f"/api/formats/{world['format_id']}/people")
    assert fmt.status_code == 200, fmt.text
    body = fmt.json()
    ids = {p["id"] for p in body["process_owner"] + body["overall_process_owner"] + body["cft_members"] + body["qms_coordinator"]}
    assert world["ids"]["admin"] in ids


def test_cancelled_workflows_are_shown_by_default_and_can_be_filtered_out(client, world):
    """The status/tracking list should show all documents by default."""
    _login(client, world["names"]["admin"])
    db = client.db_factory()
    try:
        document_id = _document(db)
    finally:
        db.close()

    made = client.post("/api/workflow/", json={
        "document_id": document_id,
        "name": "Ordinary approval",
        "steps": [{"name": "Review", "assignee_ids": [world["ids"]["po"]]}],
    })
    assert made.status_code == 200, made.text
    workflow_id = made.json()["id"]

    cancel = client.post(f"/api/workflow/{workflow_id}/cancel")
    assert cancel.status_code == 200, cancel.text

    active = client.get("/api/workflow/?limit=100")
    assert active.status_code == 200, active.text
    body = active.json()
    assert body["count"] == 1, body
    assert len(body["workflows"]) == 1

    excluded = client.get("/api/workflow/?limit=100&include_cancelled=false")
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["count"] == 0


def test_a_format_whose_owner_cannot_sign_is_refused_release(client, world):
    _login(client, world["names"]["admin"])

    # Take away the signature authority of somebody we then try to appoint.
    db = client.db_factory()
    try:
        from app.models import User
        person = db.query(User).filter(User.username == "cft_one").first()
        person.can_sign = False
        db.commit()
        cft_one_id = person.id
    finally:
        db.close()

    made = client.post("/api/formats/", json={
        "code": "QF-PQ-060", "title": "Unsignable", "team_id": world["team_id"],
        "frequency": "daily",
        "process_owner_id": cft_one_id,
        "overall_process_owner_id": world["ids"]["opo"],
        "qms_coordinator_id": world["ids"]["qms"],
        "cft_member_ids": [world["ids"]["cft2"]],
        "fields": [{"label": "R", "field_type": "number", "spec_max": 5}],
    })
    assert made.status_code == 200, made.text
    assert any("signature" in p for p in made.json()["readiness"])

    res = client.post(f"/api/formats/{made.json()['id']}/activate", json={})
    assert res.status_code == 400
    assert "signature" in _detail(res)


def test_admin_can_publish_a_ready_draft_without_approval(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-062",
        "title": "Directly published template",
        "team_id": world["team_id"],
        "frequency": "daily",
        "process_owner_id": world["ids"]["po"],
        "overall_process_owner_id": world["ids"]["opo"],
        "qms_coordinator_id": world["ids"]["qms"],
        "cft_member_ids": [world["ids"]["cft1"]],
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
    })
    assert made.status_code == 200, made.text
    format_id = made.json()["id"]

    published = client.post(
        f"/api/formats/{format_id}/publish-without-approval"
    )

    assert published.status_code == 200, published.text
    assert published.json()["status"] == "active"
    assert published.json()["published_without_approval"] is True

    from app.models import AuditLog
    db = client.db_factory()
    try:
        audit = db.query(AuditLog).filter(
            AuditLog.action == "format.published_without_approval",
            AuditLog.resource_id == format_id,
        ).first()
        assert audit is not None
        assert '"approval_bypassed": true' in audit.details
    finally:
        db.close()

    _login(client, world["names"]["po"])
    forbidden = client.post(
        f"/api/formats/{format_id}/publish-without-approval"
    )
    assert forbidden.status_code == 403


def test_admin_cannot_bypass_an_in_progress_template_approval(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-063",
        "title": "Approval in progress",
        "team_id": world["team_id"],
        "frequency": "daily",
        "process_owner_id": world["ids"]["po"],
        "overall_process_owner_id": world["ids"]["opo"],
        "qms_coordinator_id": world["ids"]["qms"],
        "cft_member_ids": [world["ids"]["cft1"]],
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
    })
    assert made.status_code == 200, made.text
    format_id = made.json()["id"]

    submitted = client.post(f"/api/formats/{format_id}/submit-approval", json={
        "steps": [{
            "name": "Process Owner approval",
            "reviewer_ids": [world["ids"]["po"]],
            "mode": "any",
        }],
    })
    assert submitted.status_code == 200, submitted.text

    bypass = client.post(
        f"/api/formats/{format_id}/publish-without-approval"
    )
    assert bypass.status_code == 409
    assert "approval in progress" in _detail(bypass)


def test_template_releases_only_after_ordered_approvals(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-061",
        "title": "Reviewed template",
        "team_id": world["team_id"],
        "frequency": "daily",
        "approval_route": [{
            "name": "Old unsigned review",
            "addressed_to": "people",
            "people_ids": [world["ids"]["admin"]],
            "mode": "any",
            "requires_signature": False,
        }],
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
    })
    assert made.status_code == 200, made.text
    format_id = made.json()["id"]

    submitted = client.post(f"/api/formats/{format_id}/submit-approval", json={
        "steps": [
            {"name": "Process Owner approval", "reviewer_ids": [world["ids"]["po"]], "mode": "any"},
            {"name": "CFT joint review", "reviewer_ids": [world["ids"]["cft1"], world["ids"]["cft2"]], "mode": "all"},
            {"name": "Final decision", "reviewer_ids": [world["ids"]["po"]], "mode": "any"},
        ],
    })
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending"
    assert client.get(f"/api/formats/{format_id}").json()["status"] == "in_review"
    assert client.get(f"/api/formats/{format_id}").json()["route_is_default"] is True
    assert client.post(f"/api/formats/{format_id}/activate", json={}).status_code == 400

    _login(client, world["names"]["po"])
    assert client.get(f"/api/formats/{format_id}/approval").json()["can_act"] is True
    first = client.post(f"/api/formats/{format_id}/approval/decision", json={"decision": "approve"})
    assert first.status_code == 200, first.text
    assert first.json()["review"]["current_step"] == 1
    assert first.json()["format"]["status"] == "in_review"

    _login(client, world["names"]["cft1"])
    one_cft_vote = client.post(f"/api/formats/{format_id}/approval/decision", json={"decision": "approve"})
    assert one_cft_vote.status_code == 200, one_cft_vote.text
    assert one_cft_vote.json()["review"]["current_step"] == 1
    assert one_cft_vote.json()["format"]["status"] == "in_review"

    _login(client, world["names"]["cft2"])
    cft_complete = client.post(f"/api/formats/{format_id}/approval/decision", json={"decision": "approve"})
    assert cft_complete.status_code == 200, cft_complete.text
    assert cft_complete.json()["review"]["current_step"] == 2
    assert cft_complete.json()["review"]["status"] == "pending"
    assert cft_complete.json()["format"]["status"] == "in_review"

    _login(client, world["names"]["po"])
    assert client.get(f"/api/formats/{format_id}/approval").json()["can_act"] is True
    final_decision = client.post(f"/api/formats/{format_id}/approval/decision", json={"decision": "approve"})
    assert final_decision.status_code == 200, final_decision.text
    assert final_decision.json()["review"]["status"] == "approved"
    assert final_decision.json()["format"]["status"] == "active"


def test_create_format_without_team_and_route_to_all_selected_approvers(client, world):
    _login(client, world["names"]["admin"])
    from app.models import Role

    db = client.db_factory()
    try:
        approval_role = Role(
            name="Test Approval Role",
            permissions='["documents.approve", "documents.sign"]',
        )
        db.add(approval_role)
        cft1 = db.query(User).filter(User.id == world["ids"]["cft1"]).one()
        cft2 = db.query(User).filter(User.id == world["ids"]["cft2"]).one()
        cft1.roles.append(approval_role)
        cft2.roles.append(approval_role)
        db.commit()
        approval_role_id = approval_role.id
    finally:
        db.close()

    approvers = client.get(
        "/api/formats/approvers",
        params={"role_id": approval_role_id},
    )
    assert approvers.status_code == 200, approvers.text
    assert {person["id"] for person in approvers.json()} == {
        world["ids"]["cft1"],
        world["ids"]["cft2"],
    }

    created = client.post("/api/formats/", json={
        "code": "QF-PQ-APPROVAL-TEST",
        "title": "Multi-approver test form",
        "frequency": "daily",
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["team"] is None
    assert body["status"] == "draft"
    assert body["approval_status"] is None
    format_id = body["id"]
    draft_detail = client.get(f"/api/formats/{format_id}")
    assert draft_detail.status_code == 200, draft_detail.text
    assert draft_detail.json()["approval"]["status"] == "none"
    assert draft_detail.json()["approval"]["steps"] == []

    submitted = client.post(
        f"/api/formats/{format_id}/submit-approval",
        json={
            "priority": "urgent",
            "steps": [{
                "name": "Test Approval Role",
                "role_id": approval_role_id,
                "reviewer_ids": [
                    world["ids"]["cft1"],
                    world["ids"]["cft2"],
                ],
                "mode": "all",
                "due_days": 5,
            }],
        },
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["steps"][0]["role_id"] == approval_role_id
    assert submitted.json()["steps"][0]["role_name"] == "Test Approval Role"
    assert submitted.json()["priority"] == "urgent"
    assert submitted.json()["steps"][0]["due_days"] == 5
    _login(client, world["names"]["admin"])
    detail = client.get(f"/api/formats/{format_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["approval"]["status"] == "pending"
    assert detail.json()["approval"]["steps"][0]["reviewer_ids"] == [
        world["ids"]["cft1"],
        world["ids"]["cft2"],
    ]
    assert detail.json()["approval"]["priority"] == "urgent"
    assert detail.json()["approval"]["steps"][0]["due_days"] == 5

    _login(client, world["names"]["cft1"])
    inbox = client.get("/api/formats/approvals/mine")
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["count"] == 1
    assert inbox.json()["approvals"][0]["format_id"] == format_id
    assert inbox.json()["approvals"][0]["code"] == "QF-PQ-APPROVAL-TEST"
    approval = client.get(f"/api/formats/{format_id}/approval")
    assert approval.status_code == 200
    assert approval.json()["can_act"] is True, approval.json()
    first = client.post(
        f"/api/formats/{format_id}/approval/decision",
        json={"decision": "approve"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["review"]["status"] == "pending"

    _login(client, world["names"]["cft2"])
    approval = client.get(f"/api/formats/{format_id}/approval")
    assert approval.json()["can_act"] is True
    second = client.post(
        f"/api/formats/{format_id}/approval/decision",
        json={"decision": "approve"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["review"]["status"] == "approved"
    assert second.json()["format"]["status"] == "active"


def test_template_builder_lists_unpublished_templates_by_status(client, world):
    _login(client, world["names"]["admin"])

    def create(code):
        response = client.post("/api/formats/", json={
            "code": code,
            "title": f"{code} template",
            "frequency": "daily",
            "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
        })
        assert response.status_code == 200, response.text
        return response.json()["id"]

    draft_id = create("QF-BUILDER-DRAFT")
    review_id = create("QF-BUILDER-REVIEW")
    changes_id = create("QF-BUILDER-CHANGES")

    pending = client.post(
        f"/api/formats/{review_id}/submit-approval",
        json={"steps": [{
            "name": "Review",
            "reviewer_ids": [world["ids"]["cft1"]],
            "mode": "any",
        }]},
    )
    assert pending.status_code == 200, pending.text

    rejected = client.post(
        f"/api/formats/{changes_id}/submit-approval",
        json={"steps": [{
            "name": "Review",
            "reviewer_ids": [world["ids"]["cft1"]],
            "mode": "any",
        }]},
    )
    assert rejected.status_code == 200, rejected.text
    _login(client, world["names"]["cft1"])
    response = client.post(
        f"/api/formats/{changes_id}/approval/decision",
        json={"decision": "reject", "comment": "Please update the form."},
    )
    assert response.status_code == 200, response.text

    _login(client, world["names"]["admin"])
    all_templates = client.get("/api/formats?tab=all")
    assert all_templates.status_code == 200, all_templates.text
    body = all_templates.json()
    assert body["summary"] == {
        "total_document": 3,
        "on_verification": 1,
        "change_request": 1,
        "draft": 1,
        "published": 1,
    }
    status_by_id = {
        item["id"]: item["builder_status"] for item in body["formats"]
    }
    assert status_by_id == {
        draft_id: "draft",
        review_id: "on_verification",
        changes_id: "change_request",
    }

    searched = client.get(
        "/api/formats",
        params={"tab": "draft", "q": "BUILDER-DRAFT"},
    )
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["formats"][0]["id"] == draft_id


def test_template_approval_status_and_rejection_comment_remain_visible(client, world):
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-064",
        "title": "Template with review history",
        "team_id": world["team_id"],
        "frequency": "daily",
        "process_owner_id": world["ids"]["po"],
        "overall_process_owner_id": world["ids"]["opo"],
        "qms_coordinator_id": world["ids"]["qms"],
        "cft_member_ids": [world["ids"]["cft1"]],
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 10}],
    })
    assert made.status_code == 200, made.text
    format_id = made.json()["id"]
    submit_payload = {"steps": [{
        "name": "Process Owner approval",
        "reviewer_ids": [world["ids"]["po"]],
        "mode": "any",
    }]}

    submitted = client.post(
        f"/api/formats/{format_id}/submit-approval",
        json=submit_payload,
    )
    assert submitted.status_code == 200, submitted.text

    _login(client, world["names"]["po"])
    missing_reason = client.post(
        f"/api/formats/{format_id}/approval/decision",
        json={"decision": "reject"},
    )
    assert missing_reason.status_code == 400

    reason = "Please correct the inspection limits before release."
    rejected = client.post(
        f"/api/formats/{format_id}/approval/decision",
        json={"decision": "reject", "comment": reason},
    )
    assert rejected.status_code == 200, rejected.text

    latest = client.get(f"/api/formats/{format_id}/approval")
    assert latest.status_code == 200, latest.text
    latest_review = latest.json()
    assert latest_review["status"] == "rejected"
    assert latest_review["decision_comments"] == [{
        "step": "Process Owner approval",
        "decision": "reject",
        "comment": reason,
        "reviewer": "Process Owner",
        "at": latest_review["decision_comments"][0]["at"],
    }]
    _login(client, world["names"]["admin"])
    detail = client.get(f"/api/formats/{format_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["approval"]["status"] == "rejected"
    assert detail.json()["approval"]["decision_comments"][0]["comment"] == reason

    _login(client, world["names"]["admin"])
    resubmitted = client.post(
        f"/api/formats/{format_id}/submit-approval",
        json=submit_payload,
    )
    assert resubmitted.status_code == 200, resubmitted.text

    history = client.get(f"/api/formats/{format_id}/approval/history")
    assert history.status_code == 200, history.text
    history_body = history.json()
    assert history_body["total"] == 2
    assert history_body["latest_status"] == "pending"
    assert [review["status"] for review in history_body["reviews"]] == [
        "pending", "rejected",
    ]
    assert history_body["reviews"][1]["decision_comments"][0]["comment"] == reason
