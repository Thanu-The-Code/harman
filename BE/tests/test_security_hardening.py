"""
What the acceptance test's security track found, kept found.

Each test is one way a person could act outside the process: approve their own
record, take over another record's approval, plant a page in an attachment,
keep a token after signing out, or decide their own change request.
"""
import io


from tests.test_qms_api import SIGNATURE, _detail, _login, client, world  # noqa: F401  (fixtures)


def _pdf() -> bytes:
    from PyPDF2 import PdfWriter

    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(out)
    return out.getvalue()


def _record(client, world):
    _login(client, world["names"]["po"])
    rec = client.post("/api/records/call", json={"format_id": world["format_id"]}).json()
    values = [{"id": v["id"], "value": "25.0" if v["label"] == "Bore diameter" else "A. Operator"} for v in rec["values"]]
    assert client.put(f"/api/records/{rec['id']}/values", json={"values": values}).status_code == 200
    return rec["id"]


def test_one_person_cannot_hold_every_approval_role(client, world):
    rid = _record(client, world)
    me = world["ids"]["po"]
    res = client.post(f"/api/records/{rid}/submit", json={"approval_overrides": {
        "process_owner": [me], "overall_process_owner": [me], "cft_members": [me]}})
    assert res.status_code == 400
    assert "cannot be both the Process Owner and the Overall Process Owner" in _detail(res)


def test_a_cft_member_cannot_also_approve_the_record(client, world):
    rid = _record(client, world)
    res = client.post(f"/api/records/{rid}/submit", json={"approval_overrides": {
        "cft_members": [world["ids"]["opo"], world["ids"]["cft1"]]}})
    assert res.status_code == 400 and "Quality CFT" in _detail(res)


def test_only_the_choosable_roles_may_be_chosen(client, world):
    rid = _record(client, world)
    res = client.post(f"/api/records/{rid}/submit", json={"approval_overrides": {"qms_coordinator": [world["ids"]["po"]]}})
    assert res.status_code == 400


def test_a_proper_choice_still_submits(client, world):
    rid = _record(client, world)
    res = client.post(f"/api/records/{rid}/submit", json={"approval_overrides": {
        "overall_process_owner": [world["ids"]["opo"]], "cft_members": [world["ids"]["cft1"]]}})
    assert res.status_code == 200, res.text


def test_another_records_document_cannot_be_submitted(client, world):
    first = _record(client, world)
    # a hard copy attached to the first record ...
    res = client.post(f"/api/records/{first}/scan", files={"file": ("a.pdf", _pdf(), "application/pdf")})
    assert res.status_code == 200, res.text
    doc = client.get(f"/api/records/{first}").json()["document_id"]
    assert doc
    second = client.post("/api/records/call", json={"format_id": world["format_id"]}).json()["id"]
    # ... cannot be the second record's
    res = client.post(f"/api/records/{second}/submit", json={"document_id": doc})
    assert res.status_code == 400 and "not this record's hard copy" in _detail(res)


def test_an_attachment_is_never_served_as_a_web_page(client, world):
    rid = _record(client, world)
    page = b"<html><script>alert(document.cookie)</script></html>"
    att = client.post(f"/api/records/{rid}/attachments",
                      files={"file": ("photo.png", page, "text/html")}).json()
    res = client.get(f"/api/records/{rid}/attachments/{att['id']}")
    assert res.headers["content-type"] == "image/png"  # decided by the server, not the uploader
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in res.headers["content-security-policy"]


def test_a_hard_copy_must_be_a_readable_pdf_or_picture(client, world):
    rid = _record(client, world)
    for name, body in (("empty.pdf", b""), ("notes.pdf", b"just some text"), ("sheet.txt", b"text")):
        res = client.post(f"/api/records/{rid}/scan", files={"file": (name, body, "application/pdf")})
        assert res.status_code == 400, (name, res.text)


def test_signing_out_ends_the_token(client, world):
    token = _login(client, world["names"]["po"]).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=auth).status_code == 200
    client.post("/api/auth/logout", headers=auth)
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_a_password_change_ends_the_other_sign_ins_but_not_this_one(client, world):
    old = _login(client, world["names"]["po"]).json()["access_token"]
    client.cookies.clear()
    res = client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {old}"},
                      json={"current_password": "Passw0rd!secret", "new_password": "N3w-Passw0rd!"})
    assert res.status_code == 200, res.text
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    fresh = res.json()["access_token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_weak_and_empty_passwords_are_refused(client, world):
    token = _login(client, world["names"]["po"]).json()["access_token"]
    for weak in ("", "aaaaaaaa", "abcdefgh"):
        res = client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {token}"},
                          json={"current_password": "Passw0rd!secret", "new_password": weak})
        assert res.status_code == 422, weak


def test_a_raiser_does_not_decide_their_own_record_change(client, world):
    rid = _record(client, world)
    db = client.db_factory()
    from app.models_qms import Record, STAGE_STORED
    from datetime import datetime
    record = db.get(Record, rid)
    record.stage, record.filled_at = STAGE_STORED, datetime.utcnow()
    db.commit()
    db.close()
    res = client.post("/api/record-change-requests", json={
        "record_id": rid, "reason": "Typo in the operator", "assigned_to_id": world["ids"]["po"]})
    assert res.status_code == 403  # a Process Owner does not choose who decides


def test_a_new_format_request_cannot_name_its_raiser_as_coordinator(client, world):
    _login(client, world["names"]["po"])
    res = client.post("/api/change-requests/", json={
        "kind": "new_format", "team_id": world["team_id"], "qms_coordinator_id": world["ids"]["po"],
        "title": "A form of my own", "reason": "Testing", "proposed_change": "A new sheet"})
    assert res.status_code == 400


def test_every_response_carries_the_standard_protections(client, world):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "SAMEORIGIN"


def test_a_reading_is_a_finite_number_or_refused(client, world):
    _login(client, world["names"]["po"])
    rec = client.post("/api/records/call", json={"format_id": world["format_id"]}).json()
    bore = next(v for v in rec["values"] if v["label"] == "Bore diameter")
    for bad in ("NaN", "Infinity", "1e309", "abc", "12,5"):
        res = client.put(f"/api/records/{rec['id']}/values", json={"values": [{"id": bore["id"], "value": bad}]})
        assert res.status_code == 400, (bad, res.text)
        assert "takes a number" in _detail(res)
    ok = client.put(f"/api/records/{rec['id']}/values", json={"values": [{"id": bore["id"], "value": "25.05"}]})
    assert ok.status_code == 200 and next(v for v in ok.json()["values"] if v["id"] == bore["id"])["in_spec"] is True
