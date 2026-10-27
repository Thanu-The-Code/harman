"""
Answering an approval from a link in an email.

The only part of the product reachable without signing in, so it is written to
be narrow rather than convenient. A token opens exactly one step on one record
for one person; it grants no session, no access to any other record, and no
route into the rest of the system. Everything it will not let you do is decided
by `approval_link_service`, checked against the live state of the step at the
moment the link is opened.

The decisions themselves go through the ordinary services - `workflow_service`
and `record_service` - and not through anything written specially for this
route. That is the point: a decision taken from an email has to be the same
decision, with the same rules, the same audit trail and the same consequences,
as one taken by somebody signed in. A second implementation would eventually
disagree with the first, and the process would depend on which door you came
through.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalWorkflow
from ..models_qms import Record
from ..services import approval_link_service as links
from ..services import record_service as recs
from ..services import workflow_service as wf

router = APIRouter()


class DecisionPayload(BaseModel):
    # approve | object | return | send_back
    #
    # Named for what happens to the record rather than for a generic verdict.
    # There is no "reject": a quality record is never thrown away, and the
    # negative answer differs by step - an objection carried to the final
    # decision, a return for correction, or a send back to the CFT.
    action: str
    comment: str = ""
    signature: Optional[dict] = None


def _client(request: Request) -> str:
    """Where the decision was taken from, for the audit trail."""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    host = forwarded or (request.client.host if request.client else "unknown")
    agent = (request.headers.get("user-agent") or "")[:120]
    return f"{host} · {agent}".strip(" ·")


def _readings(record: Record) -> list[dict]:
    """The filled values, with their limits, for showing on the page."""
    return [
        {
            "label": value.label,
            "value": value.value,
            "unit": value.unit,
            "specification": value.spec_text or _limits(value),
            "in_spec": value.in_spec,
            "remark": value.remark,
        }
        for value in sorted(record.values, key=lambda v: v.order_index or 0)
    ]


def _limits(value) -> str:
    """The limits as they would be printed on the paper form."""
    if value.spec_min is not None and value.spec_max is not None:
        return f"{value.spec_min} to {value.spec_max}"
    if value.spec_max is not None:
        return f"max {value.spec_max}"
    if value.spec_min is not None:
        return f"min {value.spec_min}"
    return ""


@router.get("/{token}")
def open_link(token: str, db: Session = Depends(get_db)):
    """
    Everything the approval page needs, or why it cannot be answered.

    A refusal is a 200 with `ok: false` rather than an error status. The person
    holding this link is not a client that can handle a 410 — they are somebody
    who opened an email — and the page has to be able to explain what happened
    in a sentence rather than showing a browser error.
    """
    try:
        link = links.resolve(db, token)
        step = links.step_of(db, link)
    except links.LinkError as exc:
        return {"ok": False, "reason": str(exc)}

    record = db.query(Record).filter(Record.id == link.record_id).first()
    if not record:
        return {"ok": False,
                "reason": "The record this link pointed at no longer exists."}

    workflow = (db.query(ApprovalWorkflow)
                .filter(ApprovalWorkflow.id == link.workflow_id).first())
    fmt = record.format
    stage = step.qms_stage

    # What the negative answer does here. Named for the consequence, because
    # somebody answering from their phone should not have to know the process
    # to know what a button will do.
    if stage == "cft_review":
        negative = {"action": "object", "label": "Raise an objection",
                    "note": "Your objection is recorded and carried to whoever "
                            "takes the final decision. The review still finishes "
                            "once everybody has answered."}
    elif stage == "final_decision":
        negative = {"action": "send_back", "label": "Send back to the CFT",
                    "note": "The record returns to the joint review to be "
                            "re-verified. Nothing is lost."}
    else:
        negative = {"action": "return", "label": "Return for correction",
                    "note": "The readings unlock so they can be corrected and "
                            "submitted again."}

    return {
        "ok": True,
        "record": {
            "id": record.id,
            "number": record.number,
            "period": record.period_label,
            "stage": record.stage,
            "observation": record.observation_status,
            "nok_summary": record.nok_summary,
            "filled_by": (record.filler.full_name or record.filler.username
                          if record.filler else None),
            "document_id": record.document_id,
        },
        "format": {
            "code": fmt.code if fmt else "",
            "title": fmt.title if fmt else "",
            "revision": fmt.revision if fmt else "",
            "work_instruction_ref": fmt.work_instruction_ref if fmt else None,
        } if fmt else None,
        "readings": _readings(record),
        "step": {
            "name": step.name,
            "order": (step.order_index or 0) + 1,
            "total": len(workflow.steps) if workflow else 1,
            "requires_signature": bool(step.requires_signature),
            "stage": stage,
            "due_at": step.due_date,
        },
        "asked_of": {
            "name": link.user.full_name or link.user.username,
            "email": link.user.email,
        },
        "negative": negative,
        "expires_at": link.expires_at,
    }


@router.post("/{token}")
def decide_by_link(token: str, payload: DecisionPayload, request: Request,
                   db: Session = Depends(get_db)):
    """
    Record the decision, through the same services a signed-in person uses.

    The link is spent only after the decision is committed. Spending it first
    would lose the answer if the decision were then refused, and leave somebody
    holding a dead link and an unanswered approval.
    """
    try:
        link = links.resolve(db, token)
        step = links.step_of(db, link)
    except links.LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    record = db.query(Record).filter(Record.id == link.record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="That record no longer exists.")

    workflow = (db.query(ApprovalWorkflow)
                .filter(ApprovalWorkflow.id == link.workflow_id).first())
    person = link.user
    action = (payload.action or "").strip().lower()
    comment = (payload.comment or "").strip()

    if step.requires_signature and action == "approve" and not payload.signature:
        raise HTTPException(
            status_code=400,
            detail="This step has to be signed. Draw your signature and try again.")

    try:
        if action == "approve":
            if step.qms_stage == "cft_review":
                recs.record_cft_opinion(db, record, person, agrees=True, comment=comment)
            else:
                wf.decide(db, workflow, step, person, "approve",
                          comment=comment, signature=payload.signature,
                          ip_address=(request.client.host if request.client else None))
                # The engine moves the chain; the record moves its own stage and
                # fires the next trigger the process asks for. Skipping this is
                # how a decision taken from an email would quietly differ from
                # the same decision taken by somebody signed in - the approval
                # would land, and the Overall Process Owner would never be told.
                try:
                    recs.on_step_decided(db, record, step, "approve", person)
                except Exception as exc:  # never lose a valid decision
                    logger.error(
                        f"{record.number} could not follow its chain after an "
                        f"approval from a link: {exc}")

        elif action == "object":
            if not comment:
                raise HTTPException(
                    status_code=400,
                    detail="An objection needs a reason. Say what is wrong with it.")
            recs.record_cft_opinion(db, record, person, agrees=False, comment=comment)

        elif action == "return":
            if not comment:
                raise HTTPException(
                    status_code=400,
                    detail="Say what has to be corrected before returning it.")
            recs.return_for_correction(db, record, person, comment)

        elif action == "send_back":
            if not comment:
                raise HTTPException(
                    status_code=400,
                    detail="Say why it has to be re-verified before sending it back.")
            recs.send_back_for_reverification(db, record, person, comment)

        else:
            raise HTTPException(status_code=400, detail="That is not a decision.")

    except HTTPException:
        raise
    except (recs.RecordError, wf.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Could not record a decision from link {link.id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="The decision could not be recorded. Try again, or sign in "
                   "and answer it from My Approvals.")

    links.spend(db, link, action, _client(request))
    db.refresh(record)

    return {
        "ok": True,
        "action": action,
        "record": record.number,
        "stage": record.stage,
        "message": {
            "approve": "Thank you — your approval has been recorded.",
            "object": "Your objection has been recorded and will be shown to "
                      "whoever takes the final decision.",
            "return": "The record has been returned for correction.",
            "send_back": "The record has gone back to the CFT to be re-verified.",
        }.get(action, "Your decision has been recorded."),
    }
