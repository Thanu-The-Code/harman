"""
Approvers chosen at submission hold the role on that record (B15).

A format may leave its Process Owner and Overall Process Owner to be chosen when
a record is submitted. The people chosen then approve the steps - and equally
return the record, send it back, close its N-ok flag and file it. People who
merely sit on the format, or anybody else, may not.
"""
from tests.test_qms_api import _current_step, _decide, _login, client, world  # noqa: F401


def _open_format(client, world):
    """A released format that names nobody: roles are chosen per record."""
    _login(client, world["names"]["admin"])
    made = client.post("/api/formats/", json={
        "code": "QF-PQ-OPEN", "title": "Roles chosen at submission", "frequency": "per_event",
        "team_id": world["team_id"],
        "fields": [{"label": "Reading", "field_type": "number", "spec_min": 1, "spec_max": 5}],
    }).json()
    assert client.post(f"/api/formats/{made['id']}/publish-without-approval").status_code == 200
    return made["id"]


def _submit(client, world, format_id, reading, *, po="cft1", opo="cft2"):
    """`cft1` fills it and takes the Process Owner role; `cft2` is chosen as OPO."""
    _login(client, world["names"][po])
    record = client.post("/api/records/call", json={"format_id": format_id}).json()
    client.put(f"/api/records/{record['id']}/values",
               json={"values": [{"id": record["values"][0]["id"], "value": reading}]})
    overrides = {"process_owner": [world["ids"][po]], "overall_process_owner": [world["ids"][opo]],
                 "cft_members": [world["ids"]["qms"]]}
    submitted = client.post(f"/api/records/{record['id']}/submit", json={"approval_overrides": overrides})
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


def test_the_chosen_overall_process_owner_is_flagged_and_alone_clears_it(client, world):
    record = _submit(client, world, _open_format(client, world), "9")  # out of spec
    assert record["nok_open"] is True
    assert record["nok_flagged_to"]["id"] == world["ids"]["cft2"]

    _login(client, world["names"]["opo"])  # the OPO of *other* formats
    refused = client.post(f"/api/records/{record['id']}/nok/clear", json={"note": "seen"})
    assert refused.status_code in (400, 403), refused.text

    _login(client, world["names"]["cft2"])
    assert client.get(f"/api/records/{record['id']}").json()["can"]["clear_nok"] is True
    cleared = client.post(f"/api/records/{record['id']}/nok/clear", json={"note": "Contained, re-measured"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["nok_open"] is False


def test_the_chosen_people_return_send_back_and_file(client, world):
    format_id = _open_format(client, world)

    # the chosen Process Owner may return it for correction
    record = _submit(client, world, format_id, "3")
    _login(client, world["names"]["cft1"])
    assert client.get(f"/api/records/{record['id']}").json()["can"]["return_for_correction"] is True
    returned = client.post(f"/api/records/{record['id']}/return", json={"reason": "Re-measure"})
    assert returned.status_code == 200, returned.text
    assert returned.json()["stage"] == "filling"

    # a fresh one goes all the way through
    record = _submit(client, world, format_id, "3")
    wf_id = record["workflow_id"]
    for who, sign in (("cft1", True), ("cft2", True), ("qms", False)):
        _login(client, world["names"][who])
        step = _current_step(client, wf_id)
        assert _decide(client, wf_id, step["id"], "approve", sign=sign).status_code == 200

    # the final decision belongs to the chosen Process Owner: sending it back works
    _login(client, world["names"]["cft1"])
    assert client.get(f"/api/records/{record['id']}").json()["can"]["send_back"] is True
    back = client.post(f"/api/records/{record['id']}/reverify", json={"reason": "Check the gauge"})
    assert back.status_code == 200, back.text
    assert back.json()["stage"] == "cft_review"

    _login(client, world["names"]["qms"])
    step = _current_step(client, wf_id)
    assert _decide(client, wf_id, step["id"], "approve", sign=False).status_code == 200
    _login(client, world["names"]["cft1"])
    step = _current_step(client, wf_id)
    assert _decide(client, wf_id, step["id"], "approve").status_code == 200

    # only the chosen OPO files it
    _login(client, world["names"]["opo"])
    assert client.post(f"/api/records/{record['id']}/store").status_code in (400, 403)
    _login(client, world["names"]["cft2"])
    assert client.get(f"/api/records/{record['id']}").json()["can"]["store"] is True
    stored = client.post(f"/api/records/{record['id']}/store")
    assert stored.status_code == 200, stored.text
    assert stored.json()["stage"] == "stored"
