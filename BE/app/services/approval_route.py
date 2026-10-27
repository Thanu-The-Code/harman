"""
The route a record takes to get approved.

The process document specifies four steps in a fixed order - the Process Owner,
the Overall Process Owner, the CFT joint review, then the final decision - and
that is what a template gets unless somebody deliberately says otherwise. This
module is the "otherwise": it reads, validates and normalises a route stored on
a template, and hands back the flowchart's own chain when there is none.

Two rules are not negotiable, whatever route is defined:

  * A route must end in a decision somebody signs. A record that nobody signed
    is not a quality record, and every route therefore has at least one signed
    step or it is refused.
  * A step must be addressed to somebody. A step with no assignee stalls
    forever, and a chain that silently stalls is worse than one that refuses to
    start - so `problems()` reports it before the template can be released.

Stage tags matter beyond naming. `record_service` reads them to know which step
is the CFT review (so an objection is recorded rather than a rejection) and
which is the final decision (so "No" sends the record back up the chart rather
than ending it). A custom route keeps those meanings by tagging its steps.
"""
from __future__ import annotations

import json
from typing import Optional

from loguru import logger

# The stages the record process understands. A custom step may carry no stage
# at all - an extra verification a plant has added - and the process treats it
# as an ordinary approval.
STAGE_PO = "po_approval"
STAGE_OPO = "opo_approval"
STAGE_CFT = "cft_review"
STAGE_FINAL = "final_decision"

STAGES = {
    STAGE_PO: "Process Owner approval",
    STAGE_OPO: "Overall Process Owner approval",
    STAGE_CFT: "CFT joint review",
    STAGE_FINAL: "Final decision",
}

ANY_OF, ALL_OF = "any", "all"
MODES = (ANY_OF, ALL_OF)

# What a person picks from when addressing a step. Naming a *role* rather than
# a person means the route survives somebody leaving: the template names the
# new Process Owner once and every route step addressed to that role follows.
ROLE_PROCESS_OWNER = "process_owner"
ROLE_OVERALL_PROCESS_OWNER = "overall_process_owner"
ROLE_CFT = "cft_members"
ROLE_QMS_COORDINATOR = "qms_coordinator"
ROLE_PEOPLE = "people"          # named individuals, chosen on the route itself

ROLE_LABELS = {
    ROLE_PROCESS_OWNER: "The Process Owner",
    ROLE_OVERALL_PROCESS_OWNER: "The Overall Process Owner",
    ROLE_CFT: "Every CFT member",
    ROLE_QMS_COORDINATOR: "The QMS Coordinator",
    ROLE_PEOPLE: "Named people",
}


def _normalised(steps: list[dict]) -> list[dict]:
    """Every step through the same cleaner, so callers see one shape.

    The default route used to be handed back exactly as written here, without
    the `order` the cleaner adds - so a caller that had never seen a custom
    route worked and one that had did not.
    """
    return [s for s in (_clean_step(item, at) for at, item in enumerate(steps)) if s]


def default_route(cft_target_days: int = 3) -> list[dict]:
    """
    The four steps of the process document.

    This is what a template gets when it says nothing about its route, and what
    the route editor opens on. The CFT step is the only "all": the chart calls
    the review *joint*, so one member agreeing does not conclude it.
    """
    days = max(1, int(cft_target_days or 3))
    return [
        {
            "name": "Process Owner approval",
            "stage": STAGE_PO,
            "addressed_to": ROLE_PROCESS_OWNER,
            "people_ids": [],
            "mode": ANY_OF,
            "requires_signature": True,
            "days": 1,
        },
        {
            "name": "Overall Process Owner approval",
            "stage": STAGE_OPO,
            "addressed_to": ROLE_OVERALL_PROCESS_OWNER,
            "people_ids": [],
            "mode": ANY_OF,
            "requires_signature": True,
            "days": 1,
        },
        {
            "name": "CFT joint review",
            "stage": STAGE_CFT,
            "addressed_to": ROLE_CFT,
            "people_ids": [],
            "mode": ALL_OF,
            "requires_signature": False,
            "days": days,
        },
        {
            "name": "Final decision",
            "stage": STAGE_FINAL,
            "addressed_to": ROLE_PROCESS_OWNER,
            "people_ids": [],
            "mode": ANY_OF,
            "requires_signature": True,
            "days": 1,
        },
    ]


def _clean_step(raw: dict, index: int) -> Optional[dict]:
    """One step, normalised. None when it is too malformed to keep."""
    if not isinstance(raw, dict):
        return None

    name = str(raw.get("name") or "").strip()
    if not name:
        return None

    stage = raw.get("stage") or None
    if stage not in STAGES and stage is not None:
        stage = None

    addressed_to = raw.get("addressed_to")
    if addressed_to not in ROLE_LABELS:
        addressed_to = ROLE_PEOPLE

    people = raw.get("people_ids")
    people = [str(p) for p in people if p] if isinstance(people, list) else []

    mode = raw.get("mode")
    if mode not in MODES:
        mode = ANY_OF

    try:
        days = max(1, int(raw.get("days") or 1))
    except (TypeError, ValueError):
        days = 1

    return {
        "name": name[:120],
        "stage": stage,
        "addressed_to": addressed_to,
        "people_ids": people,
        "mode": mode,
        "requires_signature": bool(raw.get("requires_signature")),
        "days": days,
        "order": index + 1,
    }


def parse(stored: Optional[str], cft_target_days: int = 3) -> list[dict]:
    """
    The route held on a template, or the process document's own chain.

    Never raises. A route that cannot be read is a configuration mistake, and
    the safe response to one is the specified process rather than no process at
    all - so a malformed value is logged and the default is used.
    """
    if not stored:
        return _normalised(default_route(cft_target_days))

    try:
        raw = json.loads(stored)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Could not read the approval route, using the default: {exc}")
        return _normalised(default_route(cft_target_days))

    if not isinstance(raw, list):
        return _normalised(default_route(cft_target_days))

    steps = _normalised(raw)
    return steps or _normalised(default_route(cft_target_days))


def dump(steps: list[dict]) -> Optional[str]:
    """A route ready to store. None when it is simply the default."""
    cleaned = [s for s in (_clean_step(item, at) for at, item in enumerate(steps or [])) if s]
    if not cleaned:
        return None
    return json.dumps(cleaned)


def problems(steps: list[dict], fmt, *, allow_unassigned: bool = False) -> list[str]:
    """
    What would stop this route working, in words somebody can act on.

    Checked before a template is released, because every one of these produces
    a record that stops moving with nothing on screen to say why.
    """
    found: list[str] = []

    if not steps:
        found.append("The approval route has no steps.")
        return found

    if not any(s.get("requires_signature") for s in steps):
        found.append(
            "No step on this route requires a signature. A quality record has "
            "to be signed by somebody.")

    for step in steps:
        who = step.get("addressed_to")
        label = step.get("name")

        if who == ROLE_PEOPLE and not step.get("people_ids") and not allow_unassigned:
            found.append(f"'{label}' is not addressed to anybody.")
        elif who == ROLE_PROCESS_OWNER and not fmt.process_owner_id and not allow_unassigned:
            found.append(f"'{label}' goes to the Process Owner, who is not named.")
        elif who == ROLE_OVERALL_PROCESS_OWNER and not fmt.overall_process_owner_id and not allow_unassigned:
            found.append(
                f"'{label}' goes to the Overall Process Owner, who is not named.")
        elif who == ROLE_QMS_COORDINATOR and not fmt.qms_coordinator_id and not allow_unassigned:
            found.append(f"'{label}' goes to the QMS Coordinator, who is not named.")
        elif who == ROLE_CFT and not list(fmt.cft_members or []) and not allow_unassigned:
            found.append(f"'{label}' goes to the CFT, which has no members.")

    return found


def assignees_for(step: dict, fmt) -> list[str]:
    """The user ids a step is addressed to, resolved against the template."""
    who = step.get("addressed_to")

    if who == ROLE_PROCESS_OWNER:
        return [fmt.process_owner_id] if fmt.process_owner_id else []
    if who == ROLE_OVERALL_PROCESS_OWNER:
        return ([fmt.overall_process_owner_id]
                if fmt.overall_process_owner_id else [])
    if who == ROLE_QMS_COORDINATOR:
        return [fmt.qms_coordinator_id] if fmt.qms_coordinator_id else []
    if who == ROLE_CFT:
        return [m.id for m in (fmt.cft_members or [])]
    return list(step.get("people_ids") or [])


def describe(step: dict, fmt) -> str:
    """Who this step will actually reach, for showing on the template."""
    who = step.get("addressed_to")

    if who == ROLE_PEOPLE:
        return f"{len(step.get('people_ids') or [])} named person(s)"

    holder = {
        ROLE_PROCESS_OWNER: fmt.process_owner,
        ROLE_OVERALL_PROCESS_OWNER: fmt.overall_process_owner,
        ROLE_QMS_COORDINATOR: fmt.qms_coordinator,
    }.get(who)

    if who == ROLE_CFT:
        members = list(fmt.cft_members or [])
        return (", ".join(m.full_name or m.username for m in members)
                if members else "nobody yet")

    if holder is None:
        return "nobody yet"
    return holder.full_name or holder.username
