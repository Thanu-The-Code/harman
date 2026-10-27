"""
The client's "Record filling & Record Approval Process Flow", box by box.

Every test here names the box of the chart it defends. If one of these fails,
the product has stopped matching the process the client signed off, which is a
different and more serious thing than an ordinary regression.

The two that matter most:

  * `test_d1_no_branch_returns_to_cft_and_turns_red` - the chart's reject arrow
    loops back to the joint review. A generic approval engine would end the
    process here, and getting that wrong would silently drop records.
  * `test_b5_nok_raises_flag_to_overall_process_owner` - the N-ok flag has to
    overtake the queue rather than wait its turn.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Document, User
from app.models_qms import GREEN, NOT_OK, OK, RED, YELLOW, Notification
from app.services import change_request_service as dcr
from app.services import format_service as fmts
from app.services import record_service as recs
from app.services import workflow_service as wf


# --------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _user(db, username, **kwargs):
    user = User(
        username=username,
        email=f"{username}@harman.example",
        full_name=username.replace("_", " ").title(),
        is_active=True,
        is_admin=kwargs.pop("is_admin", False),
        department=kwargs.pop("department", "Quality"),
        job_title=kwargs.pop("job_title", None),
        can_approve=kwargs.pop("can_approve", True),
        can_sign=kwargs.pop("can_sign", True),
        **kwargs,
    )
    user.set_password("secret")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def people(db):
    """The four responsibilities the chart names, plus two CFT members."""
    return {
        "po": _user(db, "process_owner"),
        "opo": _user(db, "overall_process_owner"),
        "cft1": _user(db, "cft_one"),
        "cft2": _user(db, "cft_two"),
        "qms": _user(db, "qms_coordinator"),
        "admin": _user(db, "admin", is_admin=True),
    }


@pytest.fixture
def team(db):
    fmts.ensure_teams(db)
    from app.models_qms import QualityTeam
    return db.query(QualityTeam).filter(QualityTeam.code == "PQ").first()


def _format(db, people, team, *, frequency="daily", activate=True, code="QF-PQ-001"):
    """A realistic in-process inspection format with two specified readings."""
    fmt = fmts.create_format(db, people["admin"], {
        "code": code,
        "title": "In-process dimensional check",
        "team_id": team.id,
        "frequency": frequency,
        "work_instruction_ref": "WI-PQ-014",
        "work_instruction": "Measure per WI-PQ-014, three parts per shift.",
        "cft_target_days": 3,
        "process_owner_id": people["po"].id,
        "overall_process_owner_id": people["opo"].id,
        "qms_coordinator_id": people["qms"].id,
        "cft_member_ids": [people["cft1"].id, people["cft2"].id],
        "fields": [
            {"label": "Bore diameter", "field_type": "number", "unit": "mm",
             "spec_min": 24.9, "spec_max": 25.1},
            {"label": "Surface finish", "field_type": "number", "unit": "Ra",
             "spec_max": 1.6},
            {"label": "Operator", "field_type": "text"},
        ],
    })
    if activate:
        fmts.activate(db, fmt, people["admin"])
    return fmt


def _document(db, name="record.pdf"):
    doc = Document(
        filename=name, original_filename=name, file_hash=name,
        file_path=f"/tmp/{name}", file_size=2048, mime_type="application/pdf",
        title="Filled record",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _fill(db, record, people, *, bore="25.0", finish="0.8"):
    return recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": bore},
        {"label": "Surface finish", "value": finish},
        {"label": "Operator", "value": "R. Kumar"},
    ])


def _submit(db, fmt, people, **fill_kwargs):
    record = recs.call_format(db, fmt, people["po"])
    _fill(db, record, people, **fill_kwargs)
    return recs.submit(db, record, people["po"], document=_document(db, f"{record.number}.pdf"))


def _approve(db, record, actor, *, sign=True, comment=""):
    """Approve whatever step is currently waiting, as `actor`."""
    workflow = wf.load(db, record.workflow_id)
    step = wf.current_step(workflow)
    assert step is not None, "nothing is waiting for a decision"
    signature = {"dataUrl": "data:image/png;base64,iVBORw0KGgo=", "name": actor.full_name} \
        if sign else None
    wf.decide(db, workflow, step, actor, "approve", comment=comment, signature=signature)
    db.refresh(record)
    return recs.on_step_decided(db, record, step, "approve", actor)


def _kinds(db):
    return [n.kind for n in db.query(Notification).all()]


# ------------------------------------------------------------------ B1, B2


def test_b1_blank_format_is_stored_with_a_frequency_and_revision(db, people, team):
    """B1 - blank formats live on the server, filled at a stated frequency."""
    fmt = _format(db, people, team, frequency="monthly")

    assert fmt.status == fmts.ACTIVE
    assert fmt.frequency == "monthly"
    assert fmt.revision == "00"
    assert fmt.work_instruction_ref == "WI-PQ-014"
    assert len(fmt.fields) == 3
    assert fmt.team.code == "PQ"


def test_b1_a_format_missing_a_responsibility_cannot_start_an_approval(db, people, team):
    """
    Responsibilities may be left off the format and chosen on each record
    instead. What must not happen is a record going into a chain that nobody
    is on - so without them, submission is refused and says what is missing.
    """
    fmt = fmts.create_format(db, people["admin"], {
        "code": "QF-PQ-099", "title": "Half-built", "team_id": team.id,
        "frequency": "daily",
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 5}],
    })
    fmts.activate(db, fmt, people["admin"])
    assert fmt.status == fmts.ACTIVE

    record = recs.call_format(db, fmt, people["po"])
    recs.save_values(db, record, people["po"], [{"label": "Reading", "value": "3"}])
    with pytest.raises(wf.WorkflowError) as caught:
        recs.submit(db, record, people["po"], document=_document(db))

    message = str(caught.value)
    assert "Process Owner" in message
    assert "CFT" in message


def test_b2_process_owner_calls_the_format_for_the_current_period(db, people, team):
    """B2 - calling a format raises an empty record for the right period."""
    fmt = _format(db, people, team, frequency="daily")
    record = recs.call_format(db, fmt, people["po"])

    today = datetime.utcnow()
    assert record.period_key == f"{today.year:04d}-{today.month:02d}-{today.day:02d}"
    assert record.stage == recs.STAGE_FILLING
    assert record.rag_status == YELLOW
    assert record.format_revision == "00"
    # A row is waiting for every field, carrying its own copy of the spec.
    assert len(record.values) == 3
    assert record.values[0].spec_min == 24.9


def test_b2_only_the_process_owner_may_call_a_format(db, people, team):
    fmt = _format(db, people, team)
    with pytest.raises(recs.RecordError) as caught:
        recs.call_format(db, fmt, people["cft1"])
    assert "Process Owner" in str(caught.value)


def test_b2_a_draft_format_cannot_be_filled(db, people, team):
    fmt = _format(db, people, team, activate=False, code="QF-PQ-002")
    with pytest.raises(recs.RecordError):
        recs.call_format(db, fmt, people["po"])


# ---------------------------------------------------------------- B3, B4, B5


def test_b3_filling_evaluates_every_reading_against_its_specification(db, people, team):
    """B3/B5 - ok or N-ok is arithmetic, not opinion."""
    fmt = _format(db, people, team)
    record = recs.call_format(db, fmt, people["po"])
    _fill(db, record, people, bore="25.0", finish="0.8")

    bore, finish, operator = record.values
    assert bore.in_spec is True
    assert finish.in_spec is True
    # A free-text field carries no specification, so it cannot be out of one.
    assert operator.in_spec is None
    assert record.observation_status == OK


def test_b3_submitting_notifies_the_process_owner(db, people, team):
    """B3 condition - trigger email notification to Process Owner for approval."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)

    sent = db.query(Notification).filter(
        Notification.kind == "record.submitted").all()
    assert len(sent) == 1
    assert sent[0].to_user_id == people["po"].id
    assert record.number in sent[0].subject


def test_b3_a_half_filled_record_goes_forward_with_the_blanks_named(db, people, team):
    """
    A blank reading is a warning, not a wall.

    Refusing the submission left whoever filled the form with nowhere to put
    what they had measured, which is how readings end up on a scrap of paper
    until somebody "does it properly later". It goes forward - and the record
    carries what is missing, by name, so nobody approves it unknowingly.
    """
    fmt = _format(db, people, team)
    record = recs.call_format(db, fmt, people["po"])
    recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": "25.0"},
    ])

    recs.submit(db, record, people["po"], document=_document(db))

    assert record.stage == recs.STAGE_PO
    warned = [e for e in record.events if e.kind == "submitted_incomplete"]
    assert len(warned) == 1
    assert "Surface finish" in warned[0].summary


def test_b3_a_record_with_nothing_on_it_is_still_refused(db, people, team):
    """The one thing that is not a record: an empty one."""
    fmt = _format(db, people, team)
    record = recs.call_format(db, fmt, people["po"])

    with pytest.raises(recs.RecordError) as caught:
        recs.submit(db, record, people["po"], document=_document(db))
    assert "Nothing has been filled in" in str(caught.value)
    assert record.stage == recs.STAGE_FILLING


def test_b3_a_record_filled_on_screen_needs_no_scan(db, people, team):
    """
    B3 allows the form to be filled on paper or at the terminal. Demanding an
    attachment made the paper route compulsory - so the record now writes its
    own evidence, and every later step still has the document it hangs on.
    """
    fmt = _format(db, people, team)
    record = recs.call_format(db, fmt, people["po"])
    recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": "25.0"},
        {"label": "Surface finish", "value": "0.9"},
    ])

    recs.submit(db, record, people["po"])          # no document

    assert record.stage == recs.STAGE_PO
    assert record.entry_mode == "digital"
    assert record.document_id, "the filled form should have become the evidence"
    assert [e for e in record.events if e.kind == "generated_evidence"]


def test_b4_process_owner_approval_notifies_the_overall_process_owner(db, people, team):
    """B4 condition - trigger email notification to overall Process owner."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    assert record.stage == recs.STAGE_PO

    record = _approve(db, record, people["po"])

    assert record.stage == recs.STAGE_OPO
    sent = db.query(Notification).filter(
        Notification.kind == "record.po_approved").all()
    assert len(sent) == 1
    assert sent[0].to_user_id == people["opo"].id


def test_b5_nok_raises_flag_to_overall_process_owner(db, people, team):
    """
    B5 condition - an N-ok observation raises a flag to the Overall Process
    Owner *immediately*, rather than waiting for the chain to reach them.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people, bore="25.9")   # spec is 24.9 to 25.1

    assert record.observation_status == NOT_OK
    assert "Bore diameter" in record.nok_summary
    assert record.nok_flagged_at is not None
    assert record.nok_flagged_to == people["opo"].id

    # The flag went out while the record is still only at the first approval.
    assert record.stage == recs.STAGE_PO
    flagged = db.query(Notification).filter(
        Notification.kind == "record.nok_flagged").all()
    assert len(flagged) == 1
    assert flagged[0].to_user_id == people["opo"].id


def test_b5_an_open_nok_flag_makes_the_record_red(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people, finish="3.2")   # spec is max 1.6
    assert record.observation_status == NOT_OK
    assert record.rag_status == RED


def test_b5_only_the_overall_process_owner_may_close_an_nok_flag(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people, bore="30.0")

    with pytest.raises(recs.RecordError):
        recs.clear_nok_flag(db, record, people["po"], "looked at it")

    recs.clear_nok_flag(db, record, people["opo"], "Tool changed, parts quarantined.")
    assert record.nok_cleared_at is not None


# ---------------------------------------------------------------- B6 and RAG


def test_b6_cft_joint_review_is_addressed_to_every_member_with_a_target_date(db, people, team):
    """B6 - the review is joint, so one member agreeing does not conclude it."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])

    assert record.stage == recs.STAGE_CFT
    assert record.cft_target_date is not None

    workflow = wf.load(db, record.workflow_id)
    cft = wf.qms_step(workflow, wf.QMS_CFT)
    assert cft.status == wf.CURRENT
    assert cft.approval_mode == wf.ALL_OF
    assert {a.id for a in cft.assignees} == {people["cft1"].id, people["cft2"].id}

    invites = db.query(Notification).filter(
        Notification.kind == "record.cft_review").all()
    assert {n.to_user_id for n in invites} == {people["cft1"].id, people["cft2"].id}


def test_b6_one_cft_member_does_not_close_the_joint_review(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])

    _approve(db, record, people["cft1"], sign=False)

    workflow = wf.load(db, record.workflow_id)
    cft = wf.qms_step(workflow, wf.QMS_CFT)
    assert cft.status == wf.CURRENT, "the joint review closed on one voice"
    assert [u.id for u in wf.outstanding(cft)] == [people["cft2"].id]


def test_b6_rag_is_yellow_while_filling_and_green_once_ready_for_review(db, people, team):
    """B6 condition - the three colours the chart names."""
    fmt = _format(db, people, team)

    record = recs.call_format(db, fmt, people["po"])
    assert record.rag_status == YELLOW, "filling in progress"

    _fill(db, record, people)
    record = recs.submit(db, record, people["po"], document=_document(db))
    assert record.rag_status == YELLOW, "still in the two approvals"

    record = _approve(db, record, people["po"])
    assert record.rag_status == YELLOW

    record = _approve(db, record, people["opo"])
    assert record.rag_status == GREEN, "ok for final review"


def test_b6_a_missed_cft_target_date_turns_the_record_red(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    assert record.rag_status == GREEN

    record.cft_target_date = datetime.utcnow() - timedelta(days=1)
    recs.refresh_status(record)
    assert record.rag_status == RED


# ------------------------------------------------------------- B7 and D1


def test_b7_final_decision_opens_only_after_the_whole_cft_has_answered(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)

    assert record.stage == recs.STAGE_FINAL
    workflow = wf.load(db, record.workflow_id)
    final = wf.qms_step(workflow, wf.QMS_FINAL)
    assert final.status == wf.CURRENT
    assert [a.id for a in final.assignees] == [people["po"].id]


def test_d1_no_branch_returns_to_cft_and_turns_red(db, people, team):
    """
    D1 "No" - the chart's reject arrow loops back up to the CFT band.

    The record must survive, the joint review must reopen with every previous
    CFT decision cleared, and the traffic light must go red. Terminating the
    workflow here - which is what a generic approval engine does on a reject -
    would silently lose the record.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)
    assert record.stage == recs.STAGE_FINAL

    record = recs.send_back_for_reverification(
        db, record, people["po"], "Bore readings disagree with the gauge log.")

    assert record.stage == recs.STAGE_CFT, "the record left the process entirely"
    assert record.reverify_count == 1
    assert record.rag_status == RED

    workflow = wf.load(db, record.workflow_id)
    assert workflow.status == wf.ACTIVE, "the workflow was terminated"

    cft = wf.qms_step(workflow, wf.QMS_CFT)
    assert cft.status == wf.CURRENT
    # Last round's approvals must not count towards this one.
    assert cft.decisions == []
    assert {u.id for u in wf.outstanding(cft)} == {people["cft1"].id, people["cft2"].id}

    told = db.query(Notification).filter(
        Notification.kind == "record.reverify").all()
    assert {n.to_user_id for n in told} == {people["cft1"].id, people["cft2"].id}


def test_d1_a_reverified_record_can_complete_the_second_time(db, people, team):
    """The loop is a loop, not a trap: the record can still reach storage."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)
    record = recs.send_back_for_reverification(db, record, people["po"], "Re-check.")

    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)
    assert record.stage == recs.STAGE_FINAL

    record = _approve(db, record, people["po"])
    workflow = wf.load(db, record.workflow_id)
    assert workflow.status == wf.APPROVED

    record = recs.store(db, record, people["opo"])
    assert record.stage == recs.STAGE_STORED


def test_d1_only_the_process_owner_may_send_a_record_back(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)

    with pytest.raises(recs.RecordError):
        recs.send_back_for_reverification(db, record, people["cft1"], "no")


# -------------------------------------------------------------------- B8


def _run_to_final_approval(db, fmt, people, **fill_kwargs):
    record = _submit(db, fmt, people, **fill_kwargs)
    record = _approve(db, record, people["po"])
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)
    record = _approve(db, record, people["cft2"], sign=False)
    return _approve(db, record, people["po"])


def test_b8_daily_record_is_filed_in_a_date_wise_folder(db, people, team):
    """B8 condition - date wise/month wise folders, driven by frequency."""
    fmt = _format(db, people, team, frequency="daily")
    record = _run_to_final_approval(db, fmt, people)

    record = recs.store(db, record, people["opo"])

    now = datetime.utcnow()
    assert record.stage == recs.STAGE_STORED
    assert record.storage_path == (
        f"Records / {team.name} / {fmt.code} / {now:%Y} / {now:%m-%b} / {now:%d}")
    assert record.storage_folder_id is not None
    # The evidence moved with the record.
    assert record.document.folder_id == record.storage_folder_id


def test_b8_monthly_record_stops_at_the_month_folder(db, people, team):
    fmt = _format(db, people, team, frequency="monthly", code="QF-PQ-010")
    record = _run_to_final_approval(db, fmt, people)
    record = recs.store(db, record, people["opo"])

    now = datetime.utcnow()
    assert record.storage_path == (
        f"Records / {team.name} / {fmt.code} / {now:%Y} / {now:%m-%b}")


def test_b8_storage_is_the_overall_process_owners_act(db, people, team):
    fmt = _format(db, people, team)
    record = _run_to_final_approval(db, fmt, people)
    with pytest.raises(recs.RecordError) as caught:
        recs.store(db, record, people["cft1"])
    assert "Overall Process Owner" in str(caught.value)


def test_b8_an_unapproved_record_cannot_be_filed(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    with pytest.raises(recs.RecordError) as caught:
        recs.store(db, record, people["opo"])
    assert "not been fully approved" in str(caught.value)


def test_b8_a_record_with_an_open_nok_flag_cannot_be_filed(db, people, team):
    """An N-ok flag is "for further action"; filing it unactioned would bury it."""
    fmt = _format(db, people, team)
    record = _run_to_final_approval(db, fmt, people, bore="26.5")
    assert record.observation_status == NOT_OK

    with pytest.raises(recs.RecordError) as caught:
        recs.store(db, record, people["opo"])
    assert "N-ok flag" in str(caught.value)

    recs.clear_nok_flag(db, record, people["opo"], "Batch quarantined, tool reset.")
    record = recs.store(db, record, people["opo"])
    assert record.stage == recs.STAGE_STORED


# ---------------------------------------------------------------- D2 and B9


def test_b9_change_request_notifies_the_qms_coordinator(db, people, team):
    """B9 condition 1 - change request filed, mail trigger to QMS coordinator."""
    fmt = _format(db, people, team)
    request = dcr.create(db, people["po"], {
        "kind": dcr.CHANGE_EXISTING,
        "format_id": fmt.id,
        "title": "Widen the bore tolerance",
        "reason": "Process capability study shows the current band is too tight.",
        "proposed_change": "Change bore diameter spec to 24.8 - 25.2 mm.",
    })

    assert request.number.startswith("DCR-")
    assert request.status == dcr.SUBMITTED
    assert request.qms_coordinator_id == people["qms"].id

    sent = db.query(Notification).filter(
        Notification.kind == "dcr.submitted").all()
    assert len(sent) == 1
    assert sent[0].to_user_id == people["qms"].id


def test_b9_an_active_format_cannot_be_edited_outside_change_control(db, people, team):
    """
    The chart routes every change through B9. If a format could still be edited
    directly, that control would be a formality.
    """
    fmt = _format(db, people, team)
    with pytest.raises(fmts.FormatError) as caught:
        fmts.update_format(db, fmt, people["admin"], {"title": "Sneaky edit"})
    assert "change request" in str(caught.value)


def test_b9_only_the_qms_coordinator_may_approve_a_change_request(db, people, team):
    fmt = _format(db, people, team)
    request = dcr.create(db, people["po"], {
        "kind": dcr.CHANGE_EXISTING, "format_id": fmt.id,
        "title": "Change", "reason": "Because.", "proposed_change": "Something.",
    })
    with pytest.raises(dcr.ChangeRequestError) as caught:
        dcr.decide(db, request, people["po"], "approve")
    assert "QMS Coordinator" in str(caught.value)


def test_b9_approval_then_execution_creates_the_next_revision(db, people, team):
    """B9 condition 2 - approved before execution, then trigger to Process Owner."""
    fmt = _format(db, people, team)
    request = dcr.create(db, people["po"], {
        "kind": dcr.CHANGE_EXISTING, "format_id": fmt.id,
        "title": "Widen the bore tolerance",
        "reason": "Capability study.",
        "proposed_change": "24.8 to 25.2 mm.",
    })

    dcr.decide(db, request, people["qms"], "approve", "Agreed at the quality meeting.")
    assert request.status == dcr.APPROVED

    successor = dcr.execute(db, request, people["qms"], {
        "fields": [
            {"label": "Bore diameter", "field_type": "number", "unit": "mm",
             "spec_min": 24.8, "spec_max": 25.2},
            {"label": "Surface finish", "field_type": "number", "unit": "Ra",
             "spec_max": 1.6},
            {"label": "Operator", "field_type": "text"},
        ],
    })

    assert successor.revision == "01"
    assert successor.revision_of == fmt.id
    assert successor.status == fmts.DRAFT, "a new revision must be released deliberately"
    assert fmt.status == fmts.SUPERSEDED
    assert request.status == dcr.IMPLEMENTED
    assert request.resulting_format_id == successor.id
    # The responsibilities and the CFT carried forward.
    assert successor.process_owner_id == people["po"].id
    assert {m.id for m in successor.cft_members} == {people["cft1"].id, people["cft2"].id}
    assert "dcr.decided" in _kinds(db)


def test_b9_execution_is_refused_before_approval(db, people, team):
    fmt = _format(db, people, team)
    request = dcr.create(db, people["po"], {
        "kind": dcr.CHANGE_EXISTING, "format_id": fmt.id,
        "title": "Change", "reason": "Because.", "proposed_change": "Something.",
    })
    with pytest.raises(dcr.ChangeRequestError) as caught:
        dcr.execute(db, request, people["qms"])
    assert "approved" in str(caught.value)


def test_b9_a_new_format_request_creates_a_brand_new_format(db, people, team):
    request = dcr.create(db, people["po"], {
        "kind": dcr.NEW_FORMAT,
        "team_id": team.id,
        "qms_coordinator_id": people["qms"].id,
        "title": "Leak test record",
        "reason": "New product line has a leak test with no record format.",
        "proposed_change": "Create QF-PQ-020 with pressure and hold time.",
    })
    dcr.decide(db, request, people["qms"], "approve")

    created = dcr.execute(db, request, people["qms"], {
        "code": "QF-PQ-020",
        "frequency": "weekly",
        "process_owner_id": people["po"].id,
        "overall_process_owner_id": people["opo"].id,
        "cft_member_ids": [people["cft1"].id],
        "fields": [{"label": "Pressure", "field_type": "number", "unit": "bar",
                    "spec_min": 2.0, "spec_max": 2.5}],
    })

    assert created.code == "QF-PQ-020"
    assert created.revision == "00"
    assert created.status == fmts.DRAFT
    assert request.status == dcr.IMPLEMENTED


def test_a_record_keeps_the_revision_it_was_filled_against(db, people, team):
    """History cannot be rewritten by a later revision."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    assert record.format_revision == "00"

    request = dcr.create(db, people["po"], {
        "kind": dcr.CHANGE_EXISTING, "format_id": fmt.id,
        "title": "Change", "reason": "Because.", "proposed_change": "Something.",
    })
    dcr.decide(db, request, people["qms"], "approve")
    dcr.execute(db, request, people["qms"])

    db.refresh(record)
    assert record.format_revision == "00"
    assert record.values[0].spec_min == 24.9, "the old record was re-measured"


# ---------------------------------------------------------------- periods


@pytest.mark.parametrize("frequency,expected_tail", [
    ("daily", 3),
    ("weekly", 2),   # a week is not filed under a month; it can straddle two
    ("monthly", 2),
    ("quarterly", 2),
    ("yearly", 1),
])
def test_storage_depth_follows_the_frequency(db, people, team, frequency, expected_tail):
    """
    A daily check earns a folder per day; a yearly one would be absurd there.
    """
    fmt = fmts.create_format(db, people["admin"], {
        "code": f"QF-X-{frequency[:3].upper()}", "title": "X", "team_id": team.id,
        "frequency": frequency,
    })
    assert len(fmts.storage_segments(fmt)) == expected_tail


def test_period_keys_are_distinct_per_period(db):
    when = datetime(2026, 9, 1, 10, 30)
    assert fmts.period_for("daily", when)["key"] == "2026-09-01"
    assert fmts.period_for("monthly", when)["key"] == "2026-09"
    assert fmts.period_for("quarterly", when)["key"] == "2026-Q3"
    assert fmts.period_for("yearly", when)["key"] == "2026"
    assert fmts.period_for("weekly", when)["key"] == "2026-W36"



def test_periods_and_folders_follow_the_plants_calendar_not_utc(db, people, team):
    """02:15 on 1 October in India is still 30 September in UTC; the check is October's."""
    when = datetime(2026, 9, 30, 20, 45)  # stored UTC
    daily = fmts.period_for("daily", when)
    assert (daily["key"], daily["label"]) == ("2026-10-01", "01 Oct 2026")
    # the bounds stay naive UTC, like every stored timestamp: midnight IST is 18:30 UTC
    assert (daily["start"], daily["end"]) == (datetime(2026, 9, 30, 18, 30), datetime(2026, 10, 1, 18, 30))
    assert fmts.period_for("monthly", when)["key"] == "2026-10"
    assert fmts.period_for("per_event", when)["label"] == "01 Oct 2026 02:15"
    fmt = fmts.create_format(db, people["admin"], {"code": "QF-X-IST", "title": "X", "team_id": team.id, "frequency": "daily"})
    assert fmts.storage_segments(fmt, when) == ["2026", "10-Oct", "01"]
    assert fmts.storage_segments(fmt, daily["start"]) == ["2026", "10-Oct", "01"]  # filed by the period's start


# ------------------------------------------------------------ notifications


def test_every_notification_is_recorded_even_with_no_mail_server(db, people, team):
    """
    The chart asks for the trigger; an auditor asks for evidence it fired. With
    no SMTP host configured the row still exists, marked so.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    _approve(db, record, people["po"])

    rows = db.query(Notification).all()
    assert rows, "no trail at all"
    assert {"record.submitted", "record.po_approved"} <= set(_kinds(db))
    assert all(r.status in ("skipped", "queued", "sent", "failed") for r in rows)


def test_notification_email_has_styled_html_and_plain_text_alternatives():
    from app.config import Settings
    from app.models_qms import Notification
    from app.services.notification_service import EMAIL_BRAND, SMTPNotificationChannel

    notification = Notification(
        kind="record.submitted",
        subject="Review required",
        body="Review <script>alert('unsafe')</script>\n"
             "Open https://example.com/track?a=1&b=2.",
        to_email="owner@example.com",
    )
    message = SMTPNotificationChannel()._compose(
        Settings(
            smtp_from="factory@example.com",
            smtp_from_name="Quality Records",
        ),
        notification,
    )

    assert message["From"].startswith(f"{EMAIL_BRAND} ")
    assert "Quality Records" not in message["From"]
    assert message.get_content_type() == "multipart/alternative"
    assert message.get_body(preferencelist=("plain",)).get_content().startswith(
        "Review <script>"
    )
    html_body = message.get_body(preferencelist=("html",)).get_content()
    assert EMAIL_BRAND in html_body
    assert "Quality Records" not in html_body
    assert "background-color:#17365d" in html_body
    assert "&lt;script&gt;" in html_body
    assert "<script>" not in html_body
    assert 'href="https://example.com/track?a=1&amp;b=2"' in html_body


def test_notification_service_accepts_an_alternate_delivery_channel(db, people):
    class UnconfiguredChannel:
        def is_available(self, settings):
            return False

        def unavailable_reason(self, settings):
            return "Push delivery is not configured."

        def send_batch(self, notifications, settings):
            raise AssertionError("Unavailable channels must not send.")

    rows = recs.notify.notify(
        db,
        recs.notify.RECORD_SUBMITTED,
        to=people["po"],
        subject="Approval required",
        body="Please review the record.",
        channel=UnconfiguredChannel(),
    )

    assert len(rows) == 1
    assert rows[0].status == "skipped"
    assert rows[0].error == "Push delivery is not configured."


def test_notification_service_records_alternate_channel_delivery(
    db, people
):
    from app.services.notification_service import (
        DeliveryResult,
        NotificationDeliveryService,
        NotificationService,
    )

    class AvailableChannel:
        def is_available(self, settings):
            return True

        def unavailable_reason(self, settings):
            return "Push delivery is not configured."

        def send_batch(self, notifications, settings):
            return [DeliveryResult(row.id) for row in notifications]

    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    delivery = NotificationDeliveryService(
        AvailableChannel(),
        session_factory=sessionmaker(bind=db.get_bind()),
        thread_factory=InlineThread,
    )
    service = NotificationService(
        channel=AvailableChannel(),
        delivery_service=delivery,
    )

    rows = service.notify(
        db,
        recs.notify.RECORD_SUBMITTED,
        to=people["po"],
        subject="Approval required",
        body="Please review the record.",
        channel=AvailableChannel(),
    )

    db.refresh(rows[0])
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None


def test_approval_link_is_not_embedded_in_email_body(db, people, team):
    """Email notifications should not include one-time approval links."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    workflow = wf.load(db, record.workflow_id)
    step = wf.current_step(workflow)
    assert step is not None

    rows = recs.notify.notify(
        db,
        recs.notify.RECORD_SUBMITTED,
        to=fmt.process_owner,
        subject="Approval required",
        body="Body text",
        related_type="record",
        related_id=record.id,
        record=record,
        step=step,
        send=False,
    )

    body = rows[0].body or ""
    assert "Answer it here - this link is yours and works once" not in body
    assert "http://127.0.0.1:8000/approve/" not in body


def test_the_full_happy_path_end_to_end(db, people, team):
    """Start to END, in the order the chart draws it."""
    fmt = _format(db, people, team)                              # B1
    record = recs.call_format(db, fmt, people["po"])             # B2
    _fill(db, record, people)                                    # B3
    record = recs.submit(db, record, people["po"],
                         document=_document(db))
    record = _approve(db, record, people["po"])                  # B4
    assert record.observation_status == OK                       # B5
    record = _approve(db, record, people["opo"])
    _approve(db, record, people["cft1"], sign=False)             # B6
    record = _approve(db, record, people["cft2"], sign=False)
    record = _approve(db, record, people["po"])                  # B7 / D1 yes
    record = recs.store(db, record, people["opo"])               # B8

    assert record.stage == recs.STAGE_STORED
    assert record.rag_status == GREEN
    assert record.storage_path.startswith(f"Records / {team.name} / {fmt.code} / ")

    kinds = _kinds(db)
    for expected in ("record.submitted", "record.po_approved",
                     "record.cft_review", "record.stored"):
        assert expected in kinds, f"{expected} never fired"


# ===========================================================================
# The branches the chart implies but does not draw a box for.
#
# The record process has exactly one decision point - the final decision - and
# no exit that discards a record. Everything below defends that: a disagreeing
# CFT member, a Process Owner who finds a record out of specification, and a
# correction made while a record is back for re-verification all have to leave
# the record alive and moving.
# ===========================================================================


def _reach_cft(db, fmt, people, **fill_kwargs):
    """Submitted, both approvals given, the joint review open."""
    record = _submit(db, fmt, people, **fill_kwargs)
    record = _approve(db, record, people["po"])
    return _approve(db, record, people["opo"])


def _reach_final(db, fmt, people, **fill_kwargs):
    """The whole CFT has agreed; the final decision is waiting."""
    record = _reach_cft(db, fmt, people, **fill_kwargs)
    _approve(db, record, people["cft1"], sign=False)
    return _approve(db, record, people["cft2"], sign=False)


def test_a_cft_objection_does_not_end_the_process(db, people, team):
    """
    B6 into B7 - "Final Decision require from CFT".

    A member who disagrees is giving the final decision something to weigh, not
    rejecting the record. Ending the workflow here would strand it at a stage
    the chart has no exit from.
    """
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)

    record = recs.record_cft_opinion(
        db, record, people["cft1"], agrees=False,
        comment="Readings disagree with the gauge log.")

    workflow = wf.load(db, record.workflow_id)
    assert workflow.status == wf.ACTIVE, "an objection ended the process"
    assert wf.current_step(workflow).qms_stage == wf.QMS_CFT
    assert [u.id for u in wf.outstanding(wf.current_step(workflow))] == [people["cft2"].id]
    assert record.rag_status == RED, "an objection must not read as ok for review"


def test_the_joint_review_concludes_once_everybody_has_answered(db, people, team):
    """An objection counts as an answer; it does not hold the review open."""
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)

    recs.record_cft_opinion(db, record, people["cft1"], agrees=False,
                            comment="Gauge log disagrees.")
    record = recs.record_cft_opinion(db, record, people["cft2"], agrees=True)

    workflow = wf.load(db, record.workflow_id)
    assert wf.current_step(workflow).qms_stage == wf.QMS_FINAL
    assert record.stage == recs.STAGE_FINAL


def test_the_objection_is_carried_to_the_final_decision(db, people, team):
    """A final decision taken without the CFT's words is not one "from CFT"."""
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)

    recs.record_cft_opinion(db, record, people["cft1"], agrees=False,
                            comment="Bore readings disagree with the gauge log.")
    record = recs.record_cft_opinion(db, record, people["cft2"], agrees=True)

    assert record.cft_objection
    assert "gauge log" in record.cft_objection.lower()


def test_an_objected_record_can_still_be_approved_and_filed(db, people, team):
    """The final decision is the Process Owner's; an objection informs it."""
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)
    recs.record_cft_opinion(db, record, people["cft1"], agrees=False, comment="Doubtful.")
    record = recs.record_cft_opinion(db, record, people["cft2"], agrees=True)

    record = _approve(db, record, people["po"])
    record = recs.store(db, record, people["opo"])
    assert record.stage == recs.STAGE_STORED


def test_an_objection_must_say_what_it_is(db, people, team):
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)
    with pytest.raises(recs.RecordError):
        recs.record_cft_opinion(db, record, people["cft1"], agrees=False, comment="")


# --------------------------------------------------- B4's other outcome


def test_a_record_not_within_specification_is_returned_not_rejected(db, people, team):
    """
    B4 - "Record to be approved by Process Owner **if found within
    specification condition**".

    The chart draws no exit for the case where it is not, because the answer is
    to correct the record, not to throw it away.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)

    record = recs.return_for_correction(
        db, record, people["po"], "Readings disagree with the gauge log.")

    assert record.stage == recs.STAGE_FILLING
    assert record.workflow_id is None
    assert record.rag_status == YELLOW


def test_a_returned_record_is_corrected_and_run_again(db, people, team):
    """The same record, not a second one raised for the same period."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    number = record.number

    recs.return_for_correction(db, record, people["po"], "Re-measure the bore.")
    _fill(db, record, people, bore="25.05")
    record = recs.submit(db, record, people["po"],
                         document=_document(db, "again.pdf"))

    assert record.number == number, "a correction must not create a new record"
    assert record.stage == recs.STAGE_PO
    assert wf.load(db, record.workflow_id).status == wf.ACTIVE


def test_a_record_cannot_be_returned_once_the_cft_has_it(db, people, team):
    """After the joint review opens, the final decision is what sends it back."""
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)
    with pytest.raises(recs.RecordError):
        recs.return_for_correction(db, record, people["po"], "too late")


# --------------------------------------- D1 "No" returns through B5


def test_a_record_sent_back_can_have_its_readings_corrected(db, people, team):
    """
    The chart's "No" branch returns through "Record to be stored ... with
    status ok/N-ok", so a record that has come back is expected to have its
    readings and its verdict restated.
    """
    fmt = _format(db, people, team)
    record = _reach_final(db, fmt, people)
    record = recs.send_back_for_reverification(
        db, record, people["po"], "Re-check against the gauge log.")

    record = recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": "25.05"},
        {"label": "Surface finish", "value": "0.9"},
        {"label": "Operator", "value": "R. Kumar"},
    ])
    assert record.values[0].value == "25.05"


def test_correcting_a_record_makes_the_cft_look_again(db, people, team):
    """A member who agreed with the old readings has not seen the new ones."""
    fmt = _format(db, people, team)
    record = _reach_final(db, fmt, people)
    recs.send_back_for_reverification(db, record, people["po"], "Re-check.")

    recs.record_cft_opinion(db, record, people["cft1"], agrees=True)
    workflow = wf.load(db, record.workflow_id)
    assert [u.id for u in wf.outstanding(wf.current_step(workflow))] == [people["cft2"].id]

    recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": "25.05"},
        {"label": "Surface finish", "value": "0.9"},
        {"label": "Operator", "value": "R. Kumar"},
    ])

    workflow = wf.load(db, record.workflow_id)
    outstanding = {u.id for u in wf.outstanding(wf.current_step(workflow))}
    assert outstanding == {people["cft1"].id, people["cft2"].id}, \
        "an approval given before the correction still counted"


def test_a_correction_that_goes_out_of_specification_raises_the_flag(db, people, team):
    """B5 follows the readings, whenever they change."""
    fmt = _format(db, people, team)
    record = _reach_final(db, fmt, people)
    recs.send_back_for_reverification(db, record, people["po"], "Re-check.")
    assert record.observation_status == OK

    record = recs.save_values(db, record, people["po"], [
        {"label": "Bore diameter", "value": "26.4"},
        {"label": "Surface finish", "value": "0.9"},
        {"label": "Operator", "value": "R. Kumar"},
    ])

    assert record.observation_status == NOT_OK
    assert record.nok_flagged_at is not None
    assert record.nok_flagged_to == people["opo"].id


def test_readings_stay_locked_while_a_record_is_in_normal_approval(db, people, team):
    """Only a send-back reopens them; an approval in flight does not."""
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    with pytest.raises(recs.RecordError):
        _fill(db, record, people, bore="25.05")


# ----------------------------------------------- the engine's own guard


def test_the_engine_refuses_to_reject_a_record_step(db, people, team):
    """
    There must be no way in that loses a record.

    The router routes every negative decision to the record process, but the
    engine is what guarantees it: a caller reaching `decide` directly could
    otherwise end the workflow and strand the record.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    workflow = wf.load(db, record.workflow_id)
    step = wf.current_step(workflow)

    with pytest.raises(wf.WorkflowError) as caught:
        wf.decide(db, workflow, step, people["po"], "reject", reason="no")
    assert "never rejected outright" in str(caught.value)
    assert wf.load(db, record.workflow_id).status == wf.ACTIVE


def test_an_ordinary_document_can_still_be_rejected(db, people, team):
    """The guard is for records only; the document spine is untouched."""
    document = _document(db, "ordinary.pdf")
    workflow = wf.create_workflow(
        db, document, people["admin"], name="Ordinary",
        steps=[{"name": "Review", "assignee_ids": [people["po"].id]}])
    step = wf.current_step(workflow)

    wf.decide(db, workflow, step, people["po"], "reject", reason="Not acceptable")
    assert wf.load(db, workflow.id).status == wf.REJECTED


# ---------------------------------------------------------- B5's path


def test_a_submitted_record_is_on_the_server_at_its_given_path(db, people, team):
    """
    B5 - "Record to be stored as per given path with status ok/N-ok".

    That is a step in its own right, before the joint review. B8 is the later
    and different act of committing an approved record to retention.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)

    assert record.storage_path, "B5 left the record with no path"
    assert record.storage_path.startswith(f"Records / {team.name} / {fmt.code} / ")
    assert record.observation_status == OK
    # It is not yet filed: that is B8, and it needs the whole chain approved.
    assert record.stored_at is None
    assert record.stage == recs.STAGE_PO


def test_a_format_whose_process_owner_cannot_sign_is_not_released(db, people, team):
    """
    Its two steps are signed, so releasing it would build a chain that stops
    dead on its first step - discovered by an operator at six in the morning
    rather than by the person building the format.
    """
    people["po"].can_sign = False
    db.commit()

    fmt = fmts.create_format(db, people["admin"], {
        "code": "QF-PQ-050", "title": "Unsignable", "team_id": team.id,
        "frequency": "daily",
        "process_owner_id": people["po"].id,
        "overall_process_owner_id": people["opo"].id,
        "qms_coordinator_id": people["qms"].id,
        "cft_member_ids": [people["cft1"].id],
        "fields": [{"label": "R", "field_type": "number", "spec_max": 5}],
    })

    with pytest.raises(fmts.FormatError) as caught:
        fmts.activate(db, fmt, people["admin"])
    assert "not permitted to apply a signature" in str(caught.value)


def test_only_the_holder_may_return_a_record_for_correction(db, people, team):
    """
    The record API is a second door onto the same act as the workflow API, and
    has to hold the same line: a CFT member cannot reach past the approval
    chain and hand somebody else's record back.
    """
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)

    with pytest.raises(recs.RecordError) as caught:
        recs.return_for_correction(db, record, people["cft1"], "not mine to return")
    assert "only they can return it" in str(caught.value)

    # And the person it is actually with can.
    record = recs.return_for_correction(db, record, people["po"], "Re-measure.")
    assert record.stage == recs.STAGE_FILLING


# ===========================================================================
# Regressions found by validating the running system rather than the code.
#
# Both of these passed every unit test and failed the moment two people, or a
# leaver, were involved. They are the reason this file also exercises separate
# database sessions: a joint review is precisely where two people act at once,
# and a session's own copy of a step cannot see what the other one just did.
# ===========================================================================


def _second_session(db):
    """Another person's session on the same database."""
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=db.get_bind())()


def test_two_cft_members_answering_at_once_conclude_the_review_once(db, people, team):
    """
    Both members answered, and the review deadlocked with nothing waiting.

    Each session held a step loaded before the other acted, so both read the
    other as still outstanding and neither closed the joint review. The record
    stranded at `cft_review` with every answer in. Answers are now committed
    before the question is asked, and exactly one caller may close the step.
    """
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)

    other = _second_session(db)
    try:
        # The second member's session loads the record while the first is
        # still deciding - the ordinary case for a joint review.
        from app.models_qms import Record
        mirrored = other.query(Record).filter(Record.id == record.id).first()
        mirror_person = other.query(User).filter(
            User.id == people["cft2"].id).first()

        recs.record_cft_opinion(db, record, people["cft1"], agrees=True)
        recs.record_cft_opinion(other, mirrored, mirror_person, agrees=True)

        db.expire_all()
        workflow = wf.load(db, record.workflow_id)
        current = wf.current_step(workflow)
        assert current is not None, "the joint review deadlocked"
        assert current.qms_stage == wf.QMS_FINAL, \
            f"expected the final decision, got {current.name}"

        cft = wf.qms_step(workflow, wf.QMS_CFT)
        assert cft.status == wf.APPROVED
        assert len(cft.decisions) == 2, "an answer was recorded twice or lost"
    finally:
        other.close()


def test_a_member_cannot_answer_twice_from_a_stale_session(db, people, team):
    """`can_act` read this session's copy, which a second click does not update."""
    fmt = _format(db, people, team)
    record = _reach_cft(db, fmt, people)

    other = _second_session(db)
    try:
        from app.models_qms import Record
        mirrored = other.query(Record).filter(Record.id == record.id).first()
        same_person = other.query(User).filter(User.id == people["cft1"].id).first()

        recs.record_cft_opinion(db, record, people["cft1"], agrees=True)
        with pytest.raises(recs.RecordError):
            recs.record_cft_opinion(other, mirrored, same_person, agrees=True)
    finally:
        other.close()


def test_filing_the_same_record_twice_files_it_once(db, people, team):
    """An impatient second click must not build the folder chain twice."""
    fmt = _format(db, people, team)
    record = _run_to_final_approval(db, fmt, people)

    first = recs.store(db, record, people["opo"])
    path = first.storage_path
    folder = first.storage_folder_id

    second = recs.store(db, record, people["opo"])
    assert second.storage_path == path
    assert second.storage_folder_id == folder

    from app.models import DocumentFolder
    leaves = db.query(DocumentFolder).filter(
        DocumentFolder.id == folder).count()
    assert leaves == 1, "filing twice created a second folder"


# --------------------------------------------------- people who move on


def test_a_format_whose_process_owner_has_left_is_not_released(db, people, team):
    """
    A deactivated owner reported the format as ready. Records raised against it
    would have gone to an account that cannot act on them, and the format would
    quietly stop working with nothing on screen to say why.
    """
    fmt = _format(db, people, team, activate=False, code="QF-PQ-070")
    assert fmts.readiness(fmt) == []

    people["po"].is_active = False
    db.commit()

    problems = fmts.readiness(fmt)
    assert any("no longer active" in p for p in problems), problems
    with pytest.raises(fmts.FormatError):
        fmts.activate(db, fmt, people["admin"])


def test_a_cft_member_who_has_left_is_reported(db, people, team):
    """One inactive member would hold up every joint review."""
    fmt = _format(db, people, team, activate=False, code="QF-PQ-071")
    people["cft2"].is_active = False
    db.commit()

    problems = fmts.readiness(fmt)
    assert any("no longer active" in p and "CFT" in p for p in problems), problems


def test_an_overall_process_owner_who_has_left_is_reported(db, people, team):
    fmt = _format(db, people, team, activate=False, code="QF-PQ-072")
    people["opo"].is_active = False
    db.commit()
    assert any("Overall Process Owner" in p and "no longer active" in p
               for p in fmts.readiness(fmt))


def test_a_qms_coordinator_who_has_left_is_reported(db, people, team):
    """Change requests would have nobody to approve them."""
    fmt = _format(db, people, team, activate=False, code="QF-PQ-073")
    people["qms"].is_active = False
    db.commit()
    assert any("QMS Coordinator" in p and "no longer active" in p
               for p in fmts.readiness(fmt))
