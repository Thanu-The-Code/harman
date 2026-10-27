"""
The record lifecycle: boxes B2 through B8 of the client's process flow.

This module owns everything the generic approval engine has no concept of:
which period a record covers, whether its observations were ok or N-ok, the
traffic light shown in Tracking, the flag raised to the Overall Process Owner,
and where an approved record is finally filed.

The approval chain itself is deliberately *not* reimplemented here. It is an
ApprovalWorkflow built by `workflow_service.build_qms_chain`, so My Tasks,
Tracking, signatures, escalation and the audit trail all work on a record
exactly as they do on any other document. What this module does is decide when
the chain starts, react when it moves, and hold the QMS meaning of each stage.

The one rule worth stating twice: **a rejection at the final decision does not
end the process.** The chart's "No" branch loops back up to the CFT band, so
`send_back_for_reverification` reopens the joint review and turns the record
red. A record is only ever finished by being stored (B8).
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import func, or_, true
from sqlalchemy.orm import Session, joinedload, selectinload

from ..models import (
    ApprovalStep,
    ApprovalWorkflow,
    Document,
    DocumentFolder,
    User,
)
from ..models_qms import (
    GREEN,
    NOT_OK,
    OK,
    RED,
    STAGE_CANCELLED,
    STAGE_CFT,
    STAGE_FILLING,
    STAGE_FINAL,
    STAGE_OPO,
    STAGE_PO,
    STAGE_STORED,
    YELLOW,
    Format,
    QualityTeam,
    Record,
    RecordEvent,
    RecordFieldValue,
)
from ..utils import ist
from . import approval_people, format_service, notification_service as notify
from . import workflow_service as wf
import json


class RecordError(ValueError):
    """The request is not allowed by the rules of the record process."""


# --------------------------------------------------------------- B2: call it


def call_format(db: Session, fmt: Format, actor: User, *,
                when: Optional[datetime] = None,
                entry_mode: str = "digital") -> Record:
    """
    B2 - "Process Owner will call the format which is being to be filled."

    Creates an empty record for the current period, pre-loaded with a row for
    every field on the format and the specification each must meet. Nothing is
    approved and nobody is notified yet; that happens at submission, because a
    half-filled form is not something to interrupt anyone about.
    """
    if fmt.status != format_service.ACTIVE:
        raise RecordError(
            f"Format {fmt.code} is {fmt.status}. Only an active format can be filled."
        )

    if not (actor.is_admin or format_service.open_to(db, fmt, actor)
            or fmt.process_owner_id == actor.id
            or actor.has_permission("records.fill")):
        raise RecordError(
            "Only this format's Process Owner, or somebody permitted to fill "
            f"records, may call it. The Process Owner is {_name(fmt.process_owner)}."
        )

    when = when or datetime.utcnow()
    period = format_service.period_for(fmt.frequency, when)

    if entry_mode not in ("digital", "hardcopy"):
        entry_mode = "digital"

    record = Record(
        number=_next_number(db, fmt, when),
        format_id=fmt.id,
        format_revision=fmt.revision,
        team_id=fmt.team_id,
        period_key=period["key"],
        period_label=period["label"],
        period_start=period["start"],
        period_end=period["end"],
        entry_mode=entry_mode,
        stage=STAGE_FILLING,
        rag_status=YELLOW,
        filled_by=actor.id,
    )
    db.add(record)
    db.flush()

    # The specification is copied onto the record, not referenced. A revision
    # of the format next year must not change what this record was measured
    # against.
    for field in fmt.fields:
        db.add(RecordFieldValue(
            record_id=record.id,
            field_id=field.id,
            order_index=field.order_index,
            label=field.label,
            field_type=field.field_type,
            unit=field.unit,
            spec_min=field.spec_min,
            spec_max=field.spec_max,
            spec_text=field.spec_text,
            layout_key=field.layout_key,
        ))

    _event(db, record, actor, "called",
           f"{_name(actor)} called {fmt.code} rev {fmt.revision} for "
           f"{period['label']}")
    db.commit()
    db.refresh(record)
    logger.info(f"Record {record.number} raised against {fmt.code} rev {fmt.revision}")
    return record


# --------------------------------------------------------------- B3: fill it


def save_values(db: Session, record: Record, actor: User, values: list[dict]) -> Record:
    """
    B3 - "Record to be filled as per Inspection/Process work Instruction."

    Each value is judged against the specification copied onto its row when the
    format was called, so ok / N-ok is decided by arithmetic rather than by
    opinion. Saving is not submitting: this can be called as often as the
    person filling it likes.
    """
    # Readings are editable while the record is being filled, and again while
    # it is back with the CFT for re-verification. The chart's "No" branch
    # returns through "Record to be stored ... with status ok/N-ok", so a
    # record that has come back is expected to have its readings and its status
    # restated - that is the point of sending it back.
    amending = record.stage == STAGE_CFT and (record.reverify_count or 0) > 0
    if record.stage != STAGE_FILLING and not amending:
        raise RecordError(
            "This record has been submitted and its readings can no longer be "
            "changed. The final decision can send it back to the CFT, which "
            "reopens it for correction."
        )

    by_id = {v.id: v for v in record.values}
    by_key = {v.layout_key: v for v in record.values if v.layout_key}
    by_label = {v.label.strip().lower(): v for v in record.values}

    for raw in values or []:
        row = (by_id.get(raw.get("id"))
               or by_key.get(raw.get("layout_key"))
               or by_label.get(str(raw.get("label", "")).strip().lower()))
        if not row:
            continue
        row.value = _as_text(raw.get("value"))
        row.numeric_value = _as_float(raw.get("value"))
        if row.field_type == "number" and row.value and row.numeric_value is None:
            raise RecordError(
                f"'{row.label}' takes a number, such as 12.5. '{row.value[:40]}' is not one.")
        row.remark = (raw.get("remark") or "").strip() or None
        row.in_spec = evaluate(row)

    record.filled_by = record.filled_by or actor.id
    record.filled_at = datetime.utcnow()

    was = record.observation_status
    _apply_observation_status(record)

    if amending:
        # Somebody corrected a record that the CFT is re-verifying. Every CFT
        # decision from before the correction is cleared: a member who agreed
        # with the old readings has not seen the new ones, and letting their
        # answer stand would close the review on a version nobody re-read.
        if record.workflow:
            wf.reset_cft_answers(db, record.workflow)
        _event(db, record, actor, "amended",
               f"{_name(actor)} corrected the readings during re-verification; "
               "the CFT has been asked to look again",
               record.nok_summary)

        # The correction may have created, or cleared, an out-of-specification
        # finding. Either way the flag has to follow the readings.
        if record.observation_status == NOT_OK and not record.nok_flagged_at:
            db.commit()
            raise_nok_flag(db, record, actor)
            db.refresh(record)
            return record
        if record.observation_status == OK and was == NOT_OK and record.nok_flagged_at:
            record.nok_cleared_at = record.nok_cleared_at or datetime.utcnow()
            _event(db, record, actor, "nok_cleared",
                   "The corrected readings are within specification; the N-ok "
                   "flag no longer applies")

    refresh_status(record)
    db.commit()
    db.refresh(record)
    return record


def evaluate(row: RecordFieldValue) -> Optional[bool]:
    """
    Was this reading within specification?

    None when the row carries no specification to judge against - a free-text
    observation, a name, a batch number. Those are recorded but they cannot be
    out of spec, and treating a blank limit as a failed check would make every
    record N-ok.
    """
    has_numeric_spec = row.spec_min is not None or row.spec_max is not None
    has_text_spec = bool(row.spec_text)

    if not has_numeric_spec and not has_text_spec:
        return None

    if has_numeric_spec:
        if row.numeric_value is None:
            # A required numeric reading that was left blank cannot be called
            # conforming. It is not yet a failure either, but the record is not
            # finished, and `missing_required` is what reports that.
            return None
        if row.spec_min is not None and row.numeric_value < row.spec_min:
            return False
        if row.spec_max is not None and row.numeric_value > row.spec_max:
            return False
        return True

    given = (row.value or "").strip().lower()
    if not given:
        return None
    return given == row.spec_text.strip().lower()


def spec_label(row: RecordFieldValue) -> str:
    """
    How a reading's specification reads to a person.

    Public because the API layer renders it too, and two spellings of the same
    limit - one in an email, one on screen - is how a disagreement about what
    the limit *is* starts.
    """
    return _spec_text(row)


def log_event(db: Session, record: Record, actor: Optional[User], kind: str,
              summary: str, detail: Optional[str] = None) -> None:
    """Add a line to a record's trail from outside this module."""
    _event(db, record, actor, kind, summary, detail)


def missing_required(record: Record) -> list[str]:
    """Which fields still have to be filled before this can be submitted."""
    missing = []
    for row in record.values:
        # An entry placed on a designed form (it has a layout key) is required
        # when its field says so - form_layout.to_fields decides that: a field
        # switched to Required or carrying limits, a table cell marked Required
        # or a number cell with limits. A ✓ / ✗ cell of a monthly check sheet is
        # judged when filled but not required: a daily record fills one day.
        # A classic field list keeps the rule that an entry with a
        # specification is required (there is no point specifying a limit for
        # a reading nobody has to take).
        has_spec = (row.spec_min is not None or row.spec_max is not None
                    or bool(row.spec_text))
        if row.layout_key and row.field is not None:
            needs_value = bool(row.field.required)
        else:
            needs_value = has_spec
        if needs_value and not (row.value or "").strip():
            missing.append(row.label)
    return missing


def _apply_observation_status(record: Record) -> None:
    """B5 - ok, or N-ok with the offending readings named."""
    failures = [r for r in record.values if r.in_spec is False]
    judged = [r for r in record.values if r.in_spec is not None]

    if not judged:
        record.observation_status = None
        record.nok_summary = None
        return

    if failures:
        record.observation_status = NOT_OK
        record.nok_summary = "; ".join(
            f"{r.label}: {r.value or '-'}"
            + (f" {r.unit}" if r.unit else "")
            + f" (spec {_spec_text(r)})"
            for r in failures
        )[:2000]
    else:
        record.observation_status = OK
        record.nok_summary = None


def _spec_text(row: RecordFieldValue) -> str:
    if row.spec_text:
        return row.spec_text
    if row.spec_min is not None and row.spec_max is not None:
        return f"{_num(row.spec_min)} to {_num(row.spec_max)}"
    if row.spec_min is not None:
        return f"min {_num(row.spec_min)}"
    if row.spec_max is not None:
        return f"max {_num(row.spec_max)}"
    return "-"


def _num(value: float) -> str:
    return f"{value:g}"


# ------------------------------------------------------- B3/B4: submit it


def submit(db: Session, record: Record, actor: User,
           document: Optional[Document] = None,
           approval_overrides: Optional[dict[str, list[str]]] = None) -> Record:
    """
    Close the filling stage and open the approval chain.

    Triggers, in the order the chart puts them:
      - the chain is built from the format, so the four responsibilities are
        never chosen by hand (B4, B4 condition, B6, B7);
      - a notification goes to the Process Owner that a record is waiting on
        them (B3 condition);
      - if anything was N-ok, the flag is raised to the Overall Process Owner
        immediately rather than waiting for the chain to reach them (B5
        condition) - the whole point of a flag is that it overtakes the queue.
    """
    if record.stage != STAGE_FILLING:
        raise RecordError("This record has already been submitted.")

    fmt = record.format
    # who reviews it: an eligible person per role, and never the same person twice over
    try:
        chosen = approval_people.validate_overrides(db, fmt, approval_overrides)
    except approval_people.ApprovalPeopleError as exc:
        raise RecordError(str(exc)) from exc
    if chosen:
        record.approval_overrides = json.dumps(chosen)
    if document is not None:
        record.document_id = document.id

    # A record with nothing on it is not a record. Everything short of that
    # goes forward: an incomplete one is still evidence of what was measured,
    # and refusing it only sends the readings back onto a scrap of paper until
    # somebody "does it properly later".
    if not any((value.value or "").strip() for value in record.values):
        raise RecordError(
            "Nothing has been filled in yet. Enter at least one reading before "
            "submitting."
        )

    # Blanks do not block the submission, but nobody signs one without being
    # told. Counted here and carried to the approver.
    missing = missing_required(record)
    if missing:
        _event(
            db, record, actor, "submitted_incomplete",
            f"{_name(actor)} submitted the record with "
            f"{len(missing)} required reading(s) still blank: "
            + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
        )

    # The scan is optional. B3 allows the form to be filled on paper *and*
    # photographed, or filled here - requiring an attachment made the paper
    # route compulsory, which is the opposite of what the process says.
    #
    # But every later step - the approval chain, the tracking screen, the
    # viewer - is anchored to a document, and an auditor asking for the record
    # in five years wants a file, not a database row. So a record filled on
    # screen writes its own: the readings, their limits and their verdicts, on
    # one page.
    if not record.document_id:
        from .evidence_service import generated_sheet

        record.entry_mode = "digital"
        try:
            document = generated_sheet(db, record)
            record.document_id = document.id
            _event(
                db, record, actor, "generated_evidence",
                "Filled on screen. The filled form was saved as this record's "
                "evidence - there is no paper original."
            )
        except Exception as exc:      # never lose a submission over a PDF
            logger.error(f"Could not generate the form for {record.number}: {exc}")
            raise RecordError(
                "The filled form could not be saved as this record's evidence. "
                "Attach the scanned sheet instead, or try again."
            )

    _apply_observation_status(record)

    record.submitted_at = datetime.utcnow()
    record.stage = STAGE_PO

    # B5 - "Record to be stored as per given path with status ok/N-ok". The
    # record is on the server from this moment, at the path its format dictates
    # and carrying its verdict. B8 is a later and different act: committing the
    # approved record into the retention structure. Recording the path here is
    # what makes the earlier step real rather than implied.
    record.storage_path = " / ".join(
        format_service.full_storage_path(
            fmt, record.period_start or datetime.utcnow()))
    record.cft_target_date = datetime.utcnow() + timedelta(
        days=fmt.cft_target_days or 3)

    document = document or db.query(Document).filter(
        Document.id == record.document_id).first()
    workflow = wf.build_qms_chain(db, document, fmt, actor, record=record)
    record.workflow_id = workflow.id

    refresh_status(record)
    _event(db, record, actor, "submitted",
           f"{_name(actor)} submitted the record for approval"
           + (" - N-ok observations recorded" if record.observation_status == NOT_OK
              else ""))
    db.commit()
    db.refresh(record)

    # B3 condition: "Implement a trigger email notification to Process owner
    # for approval."
    notify.notify(
        db, notify.RECORD_SUBMITTED,
        to=_step_recipients(record, wf.QMS_PO, fallback=process_owners(db, record)),
        subject=f"[{record.number}] {fmt.code} is filled and needs your approval",
        body=notify.record_body(
            record,
            f"{_name(actor)} has filled {fmt.code} rev {record.format_revision} "
            f"for {record.period_label}.",
            "Please review it against the specification and approve it if it is "
            "within condition.",
        ),
        related_type="record", related_id=record.id,
        record=record, step=_awaiting(record),
    )

    if record.observation_status == NOT_OK:
        # Named separately from the N-ok flag on purpose. The flag is a task
        # for one person - the Overall Process Owner has to decide what to do -
        # while this is the plant being told an inspection failed. The client's
        # brief asks for both and they have different readers.
        # the Overall Process Owner gets the flag itself (below) - one message, the one to act on
        flagged = {p.id for p in overall_process_owners(db, record)}
        notify.notify(
            db, notify.INSPECTION_FAILED,
            to=[p for p in [*process_owners(db, record), fmt.qms_coordinator] if p and p.id not in flagged],
            subject=f"[{record.number}] inspection failed - out of specification",
            body=notify.record_body(
                record,
                f"{fmt.code} rev {record.format_revision} for "
                f"{record.period_label} was submitted with readings outside "
                "specification.",
                record.nok_summary or "See the record for which readings failed.",
            ),
            related_type="record", related_id=record.id,
        )
        raise_nok_flag(db, record, actor)

    return record


# ----------------------------------------------------- B5: the N-ok flag


def raise_nok_flag(db: Session, record: Record, actor: Optional[User]) -> Record:
    """
    B5 condition - "If filled record is having any N/ok observations flag to be
    raised to overall process owner for further action."

    Raised the moment the record is submitted, not when the chain eventually
    reaches the Overall Process Owner. A flag that waits its turn in a queue is
    not a flag.
    """
    if record.nok_flagged_at:
        return record

    fmt = record.format
    opos = overall_process_owners(db, record)
    record.nok_flagged_at = datetime.utcnow()
    record.nok_flagged_to = opos[0].id if opos else None
    record.nok_cleared_at = None
    refresh_status(record)

    _event(db, record, actor, "nok_flagged",
           f"N-ok observations flagged to {_names(opos)} "
           "for further action",
           record.nok_summary)
    db.commit()

    notify.notify(
        db, notify.RECORD_NOK_FLAGGED,
        to=_step_recipients(record, wf.QMS_OPO, fallback=opos),
        subject=f"[{record.number}] N-ok observations - action required",
        body=notify.record_body(
            record,
            f"{fmt.code} rev {record.format_revision} for {record.period_label} "
            "has been filled with observations outside specification.",
            "Out of specification:\n  " + (record.nok_summary or "-")
            + "\n\nThis flag has been raised to you for further action.",
        ),
        related_type="record", related_id=record.id,
    )
    db.refresh(record)
    return record


def clear_nok_flag(db: Session, record: Record, actor: User, note: str = "") -> Record:
    """The Overall Process Owner has acted on the flag."""
    if not record.nok_flagged_at:
        raise RecordError("No N-ok flag has been raised on this record.")
    if record.nok_cleared_at:
        return record

    if not (actor.is_admin or actor.id in overall_process_owner_ids(record)):
        raise RecordError(
            "Only the Overall Process Owner may close an N-ok flag. "
            f"That is {_names(overall_process_owners(db, record))}."
        )

    record.nok_cleared_at = datetime.utcnow()
    refresh_status(record)
    _event(db, record, actor, "nok_cleared",
           f"{_name(actor)} recorded the action taken on the N-ok observations",
           note or None)
    db.commit()
    db.refresh(record)
    return record


# --------------------------------------------------- B6 condition: the RAG


def refresh_status(record: Record) -> str:
    """
    The traffic light the chart asks Tracking to show.

        Red     needs to reverify with CFT
        Yellow  filling in progress
        Green   ok for final review

    Red is tested first and deliberately wins over everything else: a record
    that has been sent back, or that is carrying an unactioned N-ok, or that has
    run past the CFT's target date, is a problem whatever else is true of it.
    An amber light on a late record would be a lie of omission.
    """
    # Red - "Record needs to reverify with CFT": while the CFT is re-verifying it. Once the
    # CFT has agreed again it is back at the final decision, and no longer needs reverifying.
    if record.reverify_count and record.stage == STAGE_CFT:
        record.rag_status = RED
        return RED
    if record.nok_flagged_at and not record.nok_cleared_at:
        record.rag_status = RED
        return RED
    # The CFT looked and disagreed. "Needs to reverify with CFT" is the
    # legend's own description of that, so it cannot be green.
    if record.cft_objection and record.stage in (STAGE_CFT, STAGE_FINAL):
        record.rag_status = RED
        return RED
    # Naive from SQLite, tz-aware from PostgreSQL: compare both as UTC.
    target = record.cft_target_date
    if target is not None and target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    if (target and record.stage in (STAGE_CFT, STAGE_FINAL)
            and target < datetime.now(timezone.utc)):
        record.rag_status = RED
        return RED

    # Green - "Record is ok for final review". The Process Owner and the
    # Overall Process Owner have both cleared it and nothing is outstanding.
    if record.stage in (STAGE_CFT, STAGE_FINAL, STAGE_STORED):
        record.rag_status = GREEN
        return GREEN

    # Yellow - "Record filling in progress", which covers the two approvals
    # before the joint review as well as the filling itself.
    record.rag_status = YELLOW
    return YELLOW


RAG_LABELS = {
    GREEN: "Ok for final review",
    YELLOW: "Filling in progress",
    RED: "Needs to reverify with CFT",
}


def rag_label(record: Record) -> str:
    """The light's legend, saying which red it is: the chart's one red has several causes."""
    if record.rag_status != RED:
        return RAG_LABELS.get(record.rag_status, record.rag_status or "")
    if record.nok_flagged_at and not record.nok_cleared_at:
        return "N-OK not yet cleared by the Overall Process Owner"
    if record.cft_objection and record.stage in (STAGE_CFT, STAGE_FINAL):
        return "Needs to reverify with CFT: a CFT member objected"
    if record.reverify_count and record.stage == STAGE_CFT:
        return "Needs to reverify with CFT"
    return "CFT review past its target date"


# ------------------------------------------- reacting to the approval chain


def on_step_decided(db: Session, record: Record, step, action: str,
                    actor: User) -> Record:
    """
    Move the record's own stage when its approval chain moves.

    Called by the workflow router after `workflow_service.decide` has done the
    generic work. Everything QMS-specific about that decision - which stage we
    are now in, which notification the chart asks for next - is decided here so
    the engine stays generic.
    """
    workflow = record.workflow
    stage = getattr(step, "qms_stage", None)
    fmt = record.format

    if action == "approve":
        if stage == STAGE_PO:
            record.stage = STAGE_OPO
            _event(db, record, actor, "po_approved",
                   f"{_name(actor)} approved the record as within specification")
            # B4 condition: "Implement a trigger email notification to overall
            # Process owner for approval."
            notify.notify(
                db, notify.RECORD_PO_APPROVED,
                to=_step_recipients(record, wf.QMS_OPO, fallback=overall_process_owners(db, record)),
                subject=f"[{record.number}] approved by the Process Owner - your approval is needed",
                body=notify.record_body(
                    record,
                    f"{_name(actor)} has approved {fmt.code} rev "
                    f"{record.format_revision} for {record.period_label}.",
                    "Your approval is now required before the joint review opens.",
                ),
                related_type="record", related_id=record.id,
                record=record, step=_awaiting(record),
            )

        elif stage == STAGE_OPO:
            record.stage = STAGE_CFT
            record.cft_target_date = record.cft_target_date or (
                datetime.utcnow() + timedelta(days=fmt.cft_target_days or 3))
            _event(db, record, actor, "opo_approved",
                   f"{_name(actor)} approved the record; joint review opened "
                   f"with a target of {record.cft_target_date:%d %b %Y}")
            # B6: "Record Joint review trigger to CFT members with target date."
            notify.notify(
                db, notify.RECORD_CFT_REVIEW,
                to=_step_recipients(record, wf.QMS_CFT, fallback=list(fmt.cft_members or [])),
                subject=f"[{record.number}] joint review - target {record.cft_target_date:%d %b %Y}",
                body=notify.record_body(
                    record,
                    f"A joint review of {fmt.code} rev {record.format_revision} "
                    f"for {record.period_label} has been opened for the CFT.",
                    "Every CFT member must record a decision before the final "
                    "decision can be taken.",
                ),
                related_type="record", related_id=record.id,
                record=record, step=_awaiting(record),
            )

        elif stage == STAGE_CFT:
            # The step only closes once every CFT member has agreed, so
            # reaching here means the joint review as a whole has concluded.
            if workflow and wf.current_step(workflow) and \
                    getattr(wf.current_step(workflow), "qms_stage", None) == STAGE_FINAL:
                record.stage = STAGE_FINAL
                _event(db, record, actor, "cft_reviewed",
                       "The CFT completed its joint review; the final decision "
                       "is now open")

        elif stage == STAGE_FINAL:
            # B7 approved, D1 "Yes". The record is now awaiting storage (B8),
            # which is the Overall Process Owner's act, not the engine's.
            _event(db, record, actor, "final_approved",
                   f"{_name(actor)} took the final decision: approved. "
                   "Ready to be filed on the server.")

    elif action == "reject" and stage == STAGE_FINAL:
        # D1 "No". Handled by the caller through send_back_for_reverification,
        # which is the only path that respects the chart's loop.
        pass

    refresh_status(record)
    db.commit()
    db.refresh(record)
    return record


def return_for_correction(db: Session, record: Record, actor: User,
                          reason: str) -> Record:
    """
    B4 - the record was not found to be within specification condition.

    The chart draws no exit here, because the answer is not to discard the
    record: it is to correct it and run the approval again. The record goes
    back to filling with its readings unlocked, and resubmitting builds a fresh
    chain from the format.
    """
    if record.stage not in (STAGE_PO, STAGE_OPO):
        raise RecordError(
            "Only a record still with the Process Owner or the Overall Process "
            "Owner can be returned for correction. Once the joint review has "
            "opened, the final decision is what sends it back."
        )

    # Whoever the record is currently with, and nobody else. The workflow API
    # already checks this through `can_act`, but the record API is a second
    # door onto the same act and has to hold the same line.
    allowed = (
        actor.is_admin
        or (record.stage == STAGE_PO and actor.id in process_owner_ids(record))
        or (record.stage == STAGE_OPO and actor.id in overall_process_owner_ids(record))
    )
    if not allowed:
        holders = (process_owners(db, record) if record.stage == STAGE_PO
                   else overall_process_owners(db, record))
        raise RecordError(
            "This record is with " + _names(holders)
            + ", and only they can return it for correction."
        )

    if not (reason or "").strip():
        raise RecordError("Say what has to be corrected.")

    if record.workflow:
        wf.return_for_correction(db, record.workflow, actor, reason)

    record.stage = STAGE_FILLING
    record.workflow_id = None
    record.submitted_at = None
    refresh_status(record)
    _event(db, record, actor, "returned",
           f"{_name(actor)} returned the record to be corrected", reason)
    db.commit()

    notify.notify(
        db, notify.RECORD_SUBMITTED,
        to=record.filler or process_owners(db, record),
        subject=f"[{record.number}] returned for correction",
        body=notify.record_body(
            record,
            f"{_name(actor)} has returned this record to be corrected.",
            f"Reason given: {reason}\n\nCorrect the readings and submit it again.",
        ),
        related_type="record", related_id=record.id,
    )
    db.refresh(record)
    return record


def record_cft_opinion(db: Session, record: Record, actor: User, agrees: bool,
                       comment: str = "") -> Record:
    """
    B6 - one CFT member's answer, agreement or objection.

    An objection does not stop the record. It is carried to the final decision,
    which is the chart's only decision point, and it turns the record red -
    the legend's own words for that colour are "needs to reverify with CFT",
    which is exactly what an unresolved objection means.
    """
    if record.stage != STAGE_CFT:
        raise RecordError("This record is not in the CFT joint review.")
    if not record.workflow:
        raise RecordError("This record has no approval chain.")

    step = wf.qms_step(record.workflow, wf.QMS_CFT)
    if not step:
        raise RecordError("This record's chain has no joint review.")

    try:
        wf.record_cft_opinion(db, record.workflow, step, actor, agrees, comment)
    except wf.WorkflowError as exc:
        raise RecordError(str(exc))

    db.refresh(record)
    objections = wf.cft_objections(record.workflow)
    record.cft_objection = "; ".join(
        f"{(d.user.full_name or d.user.username) if d.user else 'A member'}: "
        f"{d.comment or d.reason or 'objected'}"
        for d in objections
    )[:2000] or None

    # The joint review closes only when everybody has answered, so reaching the
    # final decision here means the CFT has concluded.
    current = wf.current_step(record.workflow)
    if current and current.qms_stage == wf.QMS_FINAL:
        record.stage = STAGE_FINAL
        _event(db, record, actor, "cft_reviewed",
               "The CFT completed its joint review"
               + (f" with {len(objections)} objection"
                  + ("" if len(objections) == 1 else "s") if objections else ""))

    refresh_status(record)
    db.commit()
    db.refresh(record)
    return record


# ------------------------------------------------- D1 "No": back to the CFT


def send_back_for_reverification(db: Session, record: Record, actor: User,
                                 reason: str) -> Record:
    """
    The chart's "No" branch, and the reason this module exists.

    A rejection at the final decision does not terminate the process. The arrow
    goes back up to the CFT band, so the joint review reopens with a fresh
    target date, the record turns red, and the count of how many times this has
    happened goes up by one. Nobody has to raise a new record, and nothing that
    was already agreed is lost.
    """
    if record.stage not in (STAGE_FINAL, STAGE_CFT):
        raise RecordError(
            "Only a record at the final decision can be sent back for "
            "re-verification."
        )
    if not (reason or "").strip():
        raise RecordError("Say why the record has to go back to the CFT.")

    fmt = record.format
    if not (actor.is_admin or actor.id in process_owner_ids(record)):
        raise RecordError(
            "The final decision belongs to the Process Owner. "
            f"That is {_names(process_owners(db, record))}."
        )

    record.reverify_count = (record.reverify_count or 0) + 1
    record.stage = STAGE_CFT
    # Last round's objections belong to last round. The CFT is being asked a
    # fresh question and their answers to it are what count now.
    record.cft_objection = None
    record.cft_target_date = datetime.utcnow() + timedelta(
        days=fmt.cft_target_days or 3)

    if record.workflow:
        wf.reopen_cft_review(db, record.workflow, actor, reason)

    refresh_status(record)
    _event(db, record, actor, "reverify",
           f"{_name(actor)} sent the record back to the CFT for re-verification "
           f"(round {record.reverify_count})", reason)
    db.commit()

    notify.notify(
        db, notify.RECORD_REVERIFY,
        to=_step_recipients(record, wf.QMS_CFT, fallback=list(fmt.cft_members or [])),
        subject=f"[{record.number}] sent back for CFT re-verification",
        body=notify.record_body(
            record,
            f"The final decision on {fmt.code} rev {record.format_revision} for "
            f"{record.period_label} was not to approve, and the record has come "
            "back to the CFT.",
            f"Reason given: {reason}\n\nPlease re-verify and record your "
            "decision again.",
        ),
        related_type="record", related_id=record.id,
    )
    db.refresh(record)
    return record


# ------------------------------------------------------------ B8: store it


def store(db: Session, record: Record, actor: User) -> Record:
    """
    B8 - "Records to be stored on server for further storage", into the
    date-wise / month-wise folders derived from the format's frequency.

    The act belongs to the Overall Process Owner in the chart, and it is gated
    on the chain being fully approved: a record cannot be filed as a completed
    quality record while somebody in the chain has not yet agreed to it.
    """
    fmt = record.format

    if not (actor.is_admin or actor.id in overall_process_owner_ids(record)
            or actor.has_permission("records.store")):
        raise RecordError(
            "Filing an approved record on the server is the Overall Process "
            f"Owner's act. That is {_names(overall_process_owners(db, record))}."
        )

    if record.stage == STAGE_STORED:
        return record

    # Two people - or one person and an impatient second click - must not file
    # the same record twice and build the folder chain twice. Whoever moves the
    # record out of its current stage first wins; the other is told it is done.
    from sqlalchemy import update as _update

    claimed = db.execute(
        _update(Record)
        .where(Record.id == record.id, Record.stage != STAGE_STORED)
        .values(stage=STAGE_STORED)
    ).rowcount
    if not claimed:
        db.expire_all()
        db.refresh(record)
        return record

    workflow = record.workflow
    if not workflow or workflow.status not in (wf.APPROVED, wf.PUBLISHED):
        raise RecordError(
            "This record has not been fully approved yet, so it cannot be "
            "filed. The final decision has to be taken first."
        )

    if record.nok_flagged_at and not record.nok_cleared_at:
        raise RecordError(
            "The N-ok flag on this record has not been closed. Record the "
            "action taken before filing it."
        )

    folder = _ensure_storage_folder(db, fmt, record)
    record.storage_folder_id = folder.id if folder else None
    record.storage_path = " / ".join(
        format_service.full_storage_path(fmt, record.period_start or record.created_at))
    record.stage = STAGE_STORED
    record.stored_at = datetime.utcnow()
    record.stored_by = actor.id

    # The evidence moves with the record, so the folder tree and the record
    # never disagree about where the document is.
    if record.document_id and folder:
        document = db.query(Document).filter(Document.id == record.document_id).first()
        if document:
            document.folder_id = folder.id

    refresh_status(record)
    _event(db, record, actor, "stored",
           f"{_name(actor)} filed the record at {record.storage_path}")
    db.commit()

    notify.notify(
        db, notify.RECORD_STORED,
        to=[*process_owners(db, record), *overall_process_owners(db, record)],
        subject=f"[{record.number}] filed on the server",
        body=notify.record_body(
            record,
            f"{fmt.code} rev {record.format_revision} for {record.period_label} "
            "has completed the process and been filed.",
            f"Stored at: {record.storage_path}",
        ),
        related_type="record", related_id=record.id,
    )

    # The same moment, said to the person who filled it rather than to the
    # people who own the format: their inspection is finished and there is
    # nothing left for them to do with it.
    if record.filler and record.filled_by not in (
            process_owner_ids(record) | overall_process_owner_ids(record)):
        notify.notify(
            db, notify.INSPECTION_COMPLETED,
            to=record.filler,
            subject=f"[{record.number}] inspection completed and filed",
            body=notify.record_body(
                record,
                f"The inspection you filled on {fmt.code} for "
                f"{record.period_label} has been approved and filed.",
                f"Stored at: {record.storage_path}",
            ),
            related_type="record", related_id=record.id,
        )

    db.refresh(record)
    return record


def _ensure_storage_folder(db: Session, fmt: Format, record: Record):
    """
    Build the date/month folder chain on demand, creating only what is missing.

    Folders are shared, not per-user: a quality record filed by one person has
    to be findable by the auditor who was never given a personal folder.
    """
    when = record.period_start or record.created_at or datetime.utcnow()
    segments = format_service.full_storage_path(fmt, when)

    parent = None
    for name in segments:
        query = db.query(DocumentFolder).filter(
            DocumentFolder.name == name,
            DocumentFolder.user_id.is_(None),
        )
        query = (query.filter(DocumentFolder.parent_id == parent.id) if parent
                 else query.filter(DocumentFolder.parent_id.is_(None)))
        folder = query.first()
        if not folder:
            folder = DocumentFolder(
                name=name,
                parent_id=parent.id if parent else None,
                user_id=None,
                description=(
                    f"Quality records - {fmt.code}" if parent is None else None),
            )
            db.add(folder)
            db.flush()
        parent = folder
    return parent


# ------------------------------------------------------------------ queries


def get(db: Session, record_id: str) -> Optional[Record]:
    return db.query(Record).filter(Record.id == record_id).first()


def by_workflow(db: Session, workflow_id: str) -> Optional[Record]:
    return db.query(Record).filter(Record.workflow_id == workflow_id).first()


def by_document(db: Session, document_id: str) -> Optional[Record]:
    return db.query(Record).filter(Record.document_id == document_id).first()


def list_records(db: Session, *, team_id: Optional[str] = None,
                 format_id: Optional[str] = None,
                 stage: Optional[str] = None,
                 rag: Optional[str] = None,
                 observation: Optional[str] = None,
                 mine_for: Optional[User] = None,
                 limit: int = 200) -> list[Record]:
    q = db.query(Record)
    if team_id:
        q = q.filter(Record.team_id == team_id)
    if format_id:
        q = q.filter(Record.format_id == format_id)
    if stage:
        q = q.filter(Record.stage == stage)
    if rag:
        q = q.filter(Record.rag_status == rag)
    if observation:
        q = q.filter(Record.observation_status == observation)
    if mine_for is not None:
        q = q.filter(Record.filled_by == mine_for.id)
    return q.order_by(Record.created_at.desc()).limit(max(1, min(limit, 1000))).all()


def involving(db: Session, user: User, *, limit: int = 500) -> list[Record]:
    """
    Every record this person has a stake in.

    "Mine" on the register means the narrower thing - records I filled - and
    that is the right answer to that question. It is the wrong one for My
    Forms, where an approver who has never filled anything would see an empty
    screen while records sat waiting on their signature.

    A person has a stake in a record if they filled it, if they are named on
    any step of its approval chain, or if they hold one of the four
    responsibilities on the format it was raised against. Those are the three
    ways the process can put a record in front of somebody.
    """
    records = (
        db.query(Record)
        .order_by(Record.created_at.desc())
        .limit(1000)
        .all()
    )

    def has_stake(record: Record) -> bool:
        if record.filled_by == user.id:
            return True

        fmt = record.format
        if fmt is not None:
            if user.id in (fmt.process_owner_id, fmt.overall_process_owner_id,
                           fmt.qms_coordinator_id):
                return True
            if any(m.id == user.id for m in (fmt.cft_members or [])):
                return True

        workflow = record.workflow
        if workflow is not None:
            for step in workflow.steps or []:
                if any(a.id == user.id for a in (step.assignees or [])):
                    return True
        return False

    return [r for r in records if has_stake(r)][:max(1, min(limit, 1000))]


def _my_documents_scope(user: User):
    """SQL scope shared by the My Documents rows, badges, and filters."""
    if user.is_admin:
        return true()
    return or_(
        Record.filled_by == user.id,
        Record.format.has(or_(
            Format.process_owner_id == user.id,
            Format.overall_process_owner_id == user.id,
            Format.qms_coordinator_id == user.id,
            Format.cft_members.any(User.id == user.id),
        )),
        Record.workflow.has(
            ApprovalWorkflow.steps.any(
                ApprovalStep.assignees.any(User.id == user.id)
            )
        ),
    )


def list_my_documents(
    db: Session,
    user: User,
    tab: str,
    q: Optional[str],
    team_id: Optional[str],
    page: int,
    page_size: int,
) -> tuple[list[Record], int, dict[str, int], list[dict[str, str]]]:
    """Fetch one My Documents page and its scoped tab badges and departments."""
    visible_stages = (STAGE_FILLING, STAGE_PO, STAGE_OPO, STAGE_CFT, STAGE_FINAL)
    tab_stages = (
        (STAGE_PO, STAGE_OPO, STAGE_CFT, STAGE_FINAL)
        if tab == "verification"
        else (STAGE_FILLING,)
    )
    scope = _my_documents_scope(user)
    # a draft is the person filling it's own: the approvers named on the format see it
    # once it is submitted, not while it is being written
    draft_scope = true() if user.is_admin else or_(
        Record.filled_by == user.id, Record.format.has(Format.process_owner_id == user.id))

    def filtered_query(*, apply_team: bool = True):
        query = db.query(Record).join(Record.format).filter(
            scope,
            Record.stage.in_(visible_stages),
            or_(Record.stage != STAGE_FILLING, draft_scope),
        )
        if q:
            term = f"%{q.strip()}%"
            query = query.filter(
                Format.title.ilike(term) | Record.number.ilike(term)
            )
        if apply_team and team_id:
            query = query.filter(Record.team_id == team_id)
        return query

    counts: dict[str, int] = {}
    for name, stages in (
        ("verification", (STAGE_PO, STAGE_OPO, STAGE_CFT, STAGE_FINAL)),
        ("draft", (STAGE_FILLING,)),
    ):
        counts[name] = filtered_query().filter(Record.stage.in_(stages)).count()

    departments = [
        {"id": department_id, "name": name}
        for department_id, name in (
            db.query(QualityTeam.id, QualityTeam.name)
            .join(Record, Record.team_id == QualityTeam.id)
            .join(Record.format)
            .filter(scope, Record.stage.in_(visible_stages))
            .distinct()
            .order_by(QualityTeam.name)
            .all()
        )
    ]

    latest_event = (
        db.query(func.max(RecordEvent.created_at))
        .filter(RecordEvent.record_id == Record.id)
        .correlate(Record)
        .scalar_subquery()
    )
    last_update = func.coalesce(Record.updated_at, latest_event, Record.created_at)
    records = (
        filtered_query()
        .filter(Record.stage.in_(tab_stages))
        .options(
            joinedload(Record.format),
            joinedload(Record.team),
            selectinload(Record.workflow)
            .selectinload(ApprovalWorkflow.steps)
            .joinedload(ApprovalStep.decider),
            selectinload(Record.workflow)
            .selectinload(ApprovalWorkflow.steps)
            .selectinload(ApprovalStep.assignees),
            selectinload(Record.workflow)
            .selectinload(ApprovalWorkflow.steps)
            .selectinload(ApprovalStep.decisions),
            selectinload(Record.events),
        )
        .order_by(last_update.desc(), Record.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    total = counts[tab]
    return records, total, counts, departments


def refresh_all_statuses(db: Session) -> int:
    """
    Re-evaluate every open record's traffic light.

    Needed because one of the red conditions is the passage of time: a record
    whose CFT target date went by overnight has to be red in the morning even
    though nobody touched it. Called by the Tracking screen.
    """
    changed = 0
    open_records = db.query(Record).filter(
        Record.stage.notin_([STAGE_STORED, STAGE_CANCELLED])).all()
    for record in open_records:
        before = record.rag_status
        if refresh_status(record) != before:
            changed += 1
    if changed:
        db.commit()
    return changed


def stats(db: Session, *, team_id: Optional[str] = None) -> dict:
    """The counts every QMS screen puts at the top, computed once."""
    q = db.query(Record)
    if team_id:
        q = q.filter(Record.team_id == team_id)

    def count(**filters) -> int:
        sub = q
        for column, value in filters.items():
            sub = sub.filter(getattr(Record, column) == value)
        return sub.count()

    return {
        "total": q.count(),
        "green": count(rag_status=GREEN),
        "yellow": count(rag_status=YELLOW),
        "red": count(rag_status=RED),
        "ok": count(observation_status=OK),
        "not_ok": count(observation_status=NOT_OK),
        "filling": count(stage=STAGE_FILLING),
        "po_approval": count(stage=STAGE_PO),
        "opo_approval": count(stage=STAGE_OPO),
        "cft_review": count(stage=STAGE_CFT),
        "final_decision": count(stage=STAGE_FINAL),
        "stored": count(stage=STAGE_STORED),
        "nok_open": q.filter(Record.nok_flagged_at.isnot(None),
                             Record.nok_cleared_at.is_(None)).count(),
    }


# ------------------------------------------------------------------ helpers


def _next_number(db: Session, fmt: Format, when: datetime) -> str:
    """
    A human-quotable record number: REC-QF-PQ-001-20260901-01.

    Sequential within a format and a day, because that is how somebody reads it
    out over a telephone.
    """
    stamp = ist.to_ist(when).strftime("%Y%m%d")  # the day as the plant reads it
    prefix = f"REC-{fmt.code}-{stamp}-"
    used = (
        db.query(func.count(Record.id))
        .filter(Record.number.like(f"{prefix}%"))
        .scalar()
    ) or 0
    return f"{prefix}{used + 1:02d}"


def _event(db: Session, record: Record, actor: Optional[User], kind: str,
           summary: str, detail: Optional[str] = None) -> None:
    db.add(RecordEvent(
        record_id=record.id,
        actor_id=actor.id if actor else None,
        kind=kind,
        summary=summary[:400],
        detail=(detail or None),
    ))


# ------------------------------------------- who holds each responsibility
#
# A format may leave its Process Owner / Overall Process Owner to be chosen
# when a record is submitted (`approval_overrides`). Whoever was chosen holds
# the role on that record - for the approval steps, and equally for the acts
# around them: returning, sending back, closing an N-ok flag, filing.


def _chosen_ids(record, role: str) -> list[str]:
    """The people chosen for a role when the record was submitted, if any."""
    try:
        chosen = json.loads(record.approval_overrides or "{}")
    except (TypeError, ValueError):
        return []
    return [i for i in (chosen.get(role) or []) if i]


def _role_ids(record, role: str, format_person_id: Optional[str]) -> set[str]:
    chosen = _chosen_ids(record, role)
    if chosen:
        return set(chosen)
    return {format_person_id} if format_person_id else set()


def process_owner_ids(record) -> set[str]:
    """Who is Process Owner on this record: chosen at submission, else the format's."""
    fmt = record.format
    return _role_ids(record, "process_owner", fmt.process_owner_id if fmt else None)


def overall_process_owner_ids(record) -> set[str]:
    """Who is Overall Process Owner on this record: chosen at submission, else the format's."""
    fmt = record.format
    return _role_ids(record, "overall_process_owner",
                     fmt.overall_process_owner_id if fmt else None)


def _people(db: Session, ids: set[str]) -> list[User]:
    if not ids:
        return []
    return db.query(User).filter(User.id.in_(ids)).order_by(User.full_name).all()


def process_owners(db: Session, record) -> list[User]:
    return _people(db, process_owner_ids(record))


def overall_process_owners(db: Session, record) -> list[User]:
    return _people(db, overall_process_owner_ids(record))


def _names(people: list[User]) -> str:
    return ", ".join(_name(p) for p in people) or "nobody yet"


def _step_recipients(record, qms_stage: str, *, fallback=None):
    """Who this record is currently asking to act, falling back to format owners."""
    workflow = getattr(record, "workflow", None)
    if workflow:
        for step in workflow.steps or []:
            if getattr(step, "qms_stage", None) == qms_stage and getattr(step, "assignees", None):
                return list(step.assignees)
    if fallback is None:
        return []
    if isinstance(fallback, (list, tuple, set)):
        return list(fallback)
    return [fallback]


def _awaiting(record):
    """
    The step this record is waiting on, or None.

    Used to attach a personal approval link to the trigger emails that ask for
    a decision. Read from the live workflow, so it is always the step the
    recipient is actually being asked about.
    """
    workflow = getattr(record, "workflow", None)
    if not workflow:
        return None
    for step in workflow.steps or []:
        if step.status == "current":
            return step
    return None


def _name(user: Optional[User]) -> str:
    if not user:
        return "nobody yet"
    return user.full_name or user.username


def _as_text(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value).strip() or None


def _as_float(value) -> Optional[float]:
    """A finite number, or None: "NaN" would pass every limit, "1e309" breaks the database."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
