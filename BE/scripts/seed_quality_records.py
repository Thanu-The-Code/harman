#!/usr/bin/env python
"""
Seed the record process with something real to look at.

Creates the three dedicated quality teams, the people the process names, and
three released formats - one per team, at three different frequencies, so the
date- and month-wise folder behaviour is visible rather than described. Then it
runs a handful of records through, on purpose leaving one of each interesting
state behind:

    a record filed on the server, all green            (the happy path)
    a record carrying an open N-ok flag                (red, blocked at B8)
    a record sent back for CFT re-verification         (red, the D1 "No" loop)
    a record still being filled                        (yellow)
    a change request waiting on the QMS Coordinator    (B9)

Everything is idempotent by code, so running it twice does not produce two of
anything. Passwords are printed at the end; change them before this is anywhere
near a real network.

    python scripts/seed_quality_records.py
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import SessionLocal, init_db          # noqa: E402
from app.models import Document, Role, User             # noqa: E402
from app.models_qms import Format, QualityTeam          # noqa: E402
from app.services import change_request_service as dcr  # noqa: E402
from app.services import format_service as fmts         # noqa: E402
from app.services import record_service as recs         # noqa: E402
from app.services import workflow_service as wf         # noqa: E402
from app.services.role_service import apply_role, ensure_standard_roles  # noqa: E402
from app.services.template_folder_service import ensure_folder_path    # noqa: E402

PASSWORD = "Harman@2026"

SIGNATURE = {
    "dataUrl": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    ),
    "method": "draw",
}

# username -> (full name, job title, department, quality team code)
#
# The department and the team are deliberately separate. Anil Deshmukh works in
# Manufacturing and sits on the Process Quality cross-functional review; a
# single field could not say both, and the review would have had to be staffed
# by guessing.
PEOPLE = {
    "r.kumar":    ("Ravi Kumar", "Process Owner - Machining", "Process Quality", "PQ"),
    "a.sharma":   ("Aryan Sharma", "Process Owner - Assembly", "Process Quality", "PQ"),
    "s.iyer":     ("Sunita Iyer", "Head of Process Quality", "Process Quality", "PQ"),
    "a.deshmukh": ("Anil Deshmukh", "Manufacturing Engineer", "Manufacturing", "PQ"),
    "p.nair":     ("Priya Nair", "Quality Engineer", "Process Quality", "PQ"),
    "m.shaikh":   ("Mohammed Shaikh", "QMS Coordinator", "Quality Assurance", None),
    "k.reddy":    ("Kavitha Reddy", "Process Owner - Incoming", "Supplier Quality", "SQ"),
    "d.varma":    ("Deepak Varma", "Head of Supplier Quality", "Supplier Quality", "SQ"),
}


# Every person seeded here approves and signs somewhere in the process. That
# authority has to come from a role: on every start-up
# `role_service.remove_legacy_roles` re-derives can_approve / can_sign from the
# user's role permissions, so a user without a role would lose both at the next
# restart.
#
# The permissions are deliberately narrower than the Roles screen's
# "approvals.approve" capability. That capability also grants `records.store`,
# and the "records.fill" capability grants `records.fill`; both let the holder
# fill or file *any* format's records, not just the ones they are named on. The
# seeded people act only where a format names them, so they get what their
# legacy "signatory" account type granted, and nothing more.
APPROVER_ROLE = "Quality Approver"
APPROVER_PERMISSIONS = ["documents.approve", "documents.read", "documents.sign", "formats.read"]


def approver_role(db) -> Role:
    role = db.query(Role).filter(Role.name == APPROVER_ROLE).first()
    if role:
        return role
    role = Role(
        name=APPROVER_ROLE,
        description="Reviews, approves and signs quality records on the formats "
                    "that name them.",
        permissions=json.dumps(APPROVER_PERMISSIONS),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    print(f"  + role {APPROVER_ROLE}")
    return role


def person(db, username: str) -> User:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        # Databases seeded before the role existed: give the person the role so
        # their authority survives the next restart.
        if not existing.is_admin and not existing.roles:
            existing.roles = [approver_role(db)]
            existing.can_approve = True
            existing.can_sign = True
            db.commit()
        return existing

    full_name, job_title, department, team_code = PEOPLE[username]
    team = (db.query(QualityTeam).filter(QualityTeam.code == team_code).first()
            if team_code else None)
    user = User(
        username=username,
        email=f"{username}@harman.example",
        full_name=full_name,
        job_title=job_title,
        department=department,
        quality_team_id=team.id if team else None,
        is_active=True,
        can_approve=True,
        can_sign=True,
        account_type="signatory",
    )
    user.set_password(PASSWORD)
    user.roles = [approver_role(db)]
    db.add(user)
    db.commit()
    db.refresh(user)
    apply_role(db, user)
    print(f"  + {full_name} ({username})")
    return user


def team(db, code: str) -> QualityTeam:
    return db.query(QualityTeam).filter(QualityTeam.code == code).first()


def format_for(db, admin, spec: dict) -> Format:
    existing = (
        db.query(Format)
        .filter(Format.code == spec["code"], Format.status.in_([fmts.DRAFT, fmts.ACTIVE]))
        .first()
    )
    if existing:
        return existing

    created = fmts.create_format(db, admin, spec)
    fmts.activate(db, created, admin)
    print(f"  + {created.code} rev {created.revision} - {created.title} "
          f"({fmts.FREQUENCY_LABELS[created.frequency]})")
    return created


def draw_sheet(record) -> bytes:
    """
    A filled sheet for one record, as a PDF.

    Drawn from the record's own values so the paper and the screen agree - an
    auditor comparing the two in a demonstration should find the same numbers,
    and a reading marked N-ok on screen should be marked N-ok here.
    """
    from PIL import Image, ImageDraw, ImageFont

    def font(size, bold=False):
        for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
                     else ("arial.ttf", "DejaVuSans.ttf")):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    ink, rule, bad = (28, 28, 32), (90, 90, 98), (150, 20, 20)
    page = Image.new("RGB", (1240, 1750), "white")
    draw = ImageDraw.Draw(page)
    fmt = record.format

    draw.text((70, 70), "HARMAN", font=font(30, True), fill=ink)
    draw.text((70, 118), fmt.title if fmt else record.number,
              font=font(20, True), fill=ink)
    draw.text((70, 148),
              f"{fmt.code if fmt else ''}   Rev {record.format_revision or ''}"
              f"   {record.period_label or ''}",
              font=font(15), fill=rule)
    draw.line([(70, 182), (1170, 182)], fill=rule, width=3)

    y = 220
    draw.text((70, y), "Characteristic", font=font(15, True), fill=ink)
    draw.text((560, y), "Specification", font=font(15, True), fill=ink)
    draw.text((840, y), "Reading", font=font(15, True), fill=ink)
    draw.text((1030, y), "Remark", font=font(15, True), fill=ink)
    y += 28
    draw.line([(70, y), (1170, y)], fill=rule, width=2)
    y += 14

    for value in sorted(record.values, key=lambda v: v.order_index or 0):
        out = value.in_spec is False
        limits = ""
        if value.spec_min is not None and value.spec_max is not None:
            limits = f"{value.spec_min} - {value.spec_max}"
        elif value.spec_max is not None:
            limits = f"max {value.spec_max}"
        elif value.spec_min is not None:
            limits = f"min {value.spec_min}"

        draw.text((70, y), (value.label or "")[:46], font=font(15), fill=ink)
        draw.text((560, y), limits, font=font(15), fill=rule)
        draw.text((840, y), str(value.value or "-"), font=font(15),
                  fill=bad if out else ink)
        draw.text((1030, y), "N-OK" if out else ("OK" if limits else ""),
                  font=font(15), fill=bad if out else ink)
        y += 34

    if record.nok_summary:
        y += 24
        draw.text((70, y), "Observations", font=font(15, True), fill=ink)
        y += 26
        for line in str(record.nok_summary)[:300].split(";"):
            draw.text((70, y), line.strip()[:88], font=font(14), fill=bad)
            y += 24

    draw.line([(70, 1560), (560, 1560)], fill=rule, width=2)
    draw.text((70, 1570), "Filled by", font=font(13), fill=rule)
    draw.line([(660, 1560), (1170, 1560)], fill=rule, width=2)
    draw.text((660, 1570), "Verified by", font=font(13), fill=rule)

    buffer = io.BytesIO()
    page.save(buffer, "PDF", resolution=150)
    return buffer.getvalue()


def evidence(db, record) -> Document:
    """
    The scanned sheet a record was filled from.

    A real file, written to storage, because the alternative - a row pointing
    at a path nothing wrote - gives a 404 the first time anybody presses "View
    the sheet", which on sample data is the first thing they will do.
    """
    import hashlib
    from pathlib import Path

    from app.config import get_settings

    pdf = draw_sheet(record)

    folder = Path(get_settings().storage_folder) / "evidence" / "seed"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record.number}.pdf"
    path.write_bytes(pdf)

    doc = Document(
        filename=f"{record.number}.pdf",
        original_filename=f"{record.number}.pdf",
        file_hash=hashlib.sha256(pdf).hexdigest(),
        file_path=str(path),
        file_size=len(pdf),
        mime_type="application/pdf",
        title=f"{record.number} - {record.format.title}",
        ocr_status="completed",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def fill(db, record, owner, values: dict):
    recs.save_values(db, record, owner, [
        {"label": label, "value": value} for label, value in values.items()
    ])


def approve(db, record, actor, sign=True):
    """Approve whatever step is waiting, and let the record follow its chain."""
    workflow = wf.load(db, record.workflow_id)
    step = wf.current_step(workflow)
    if not step:
        return record
    wf.decide(db, workflow, step, actor, "approve",
              signature=dict(SIGNATURE, name=actor.full_name) if sign else None)
    db.refresh(record)
    return recs.on_step_decided(db, record, step, "approve", actor)


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        print("\nSetting up the record process\n" + "=" * 46)

        fmts.ensure_teams(db)
        ensure_standard_roles(db)

        admin = db.query(User).filter(User.is_admin.is_(True)).first()
        if not admin:
            # A brand new database. Create the administrator here rather than
            # sending somebody back to the sign-in page first: this script
            # already creates seven accounts with a known password, and making
            # them do it in two passes to get an eighth helps nobody.
            admin = User(
                username="admin",
                email="admin@harman.example",
                full_name="System Administrator",
                job_title="Administrator",
                department="Quality Assurance",
                is_active=True,
                is_admin=True,
                can_approve=True,
                can_sign=True,
                account_type="administrator",
            )
            admin.set_password(PASSWORD)
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print("\nAdministrator")
            print("  + System Administrator (admin)")

        print("\nPeople")
        po = person(db, "r.kumar")
        # The second person in the demonstration: he receives the approval
        # email, opens the link, and answers from his own account while the
        # administrator watches the status change on Tracking.
        aryan = person(db, "a.sharma")
        opo = person(db, "s.iyer")
        cft_a = person(db, "a.deshmukh")
        cft_b = person(db, "p.nair")
        qms = person(db, "m.shaikh")
        sq_po = person(db, "k.reddy")
        sq_opo = person(db, "d.varma")

        pq, sq, cq = team(db, "PQ"), team(db, "SQ"), team(db, "CQ")

        # Folders of the Resources library, offered when a template is created
        # (Template Builder -> Create Template). Empty until templates are filed in them.
        print("\nTemplate folders")
        for folder in (
            "Teams / Process Quality / Audit Reports",
            "Teams / Process Quality / Procedures",
            "Teams / Process Quality / Work Instructions",
            "Teams / Process Quality / Quality Standards",
            "Teams / Process Quality / Inspection Logs",
            "Teams / Supplier Quality / Incoming Inspection",
            "Teams / Customer Quality / Customer Audits",
        ):
            ensure_folder_path(db, folder, created_by=admin.id)
            print(f"  + {folder}")
        db.commit()

        print("\nFormats")
        daily = format_for(db, admin, {
            "code": "QF-PQ-001",
            "title": "In-process dimensional check",
            "description": "Three parts per shift off the CNC line.",
            "team_id": pq.id,
            "frequency": "daily",
            "work_instruction_ref": "WI-PQ-014",
            "work_instruction": (
                "Measure three consecutive parts at the start of each shift with "
                "the calibrated bore gauge. Record every reading, not the average."
            ),
            "cft_target_days": 3,
            "process_owner_id": po.id,
            "overall_process_owner_id": opo.id,
            "qms_coordinator_id": qms.id,
            "cft_member_ids": [cft_a.id, cft_b.id],
            "fields": [
                {"label": "Bore diameter", "field_type": "number", "unit": "mm",
                 "spec_min": 24.90, "spec_max": 25.10},
                {"label": "Surface finish", "field_type": "number", "unit": "Ra",
                 "spec_max": 1.6},
                {"label": "Run-out", "field_type": "number", "unit": "mm",
                 "spec_max": 0.05},
                {"label": "Gauge serial", "field_type": "text"},
                {"label": "Operator", "field_type": "text"},
            ],
        })

        weekly = format_for(db, admin, {
            "code": "QF-SQ-002",
            "title": "Incoming material inspection",
            "description": "Goods-in check against the supplier certificate.",
            "team_id": sq.id,
            "frequency": "weekly",
            "work_instruction_ref": "WI-SQ-007",
            "work_instruction": (
                "Check one carton per delivery against the mill certificate. "
                "Any mismatch is an N-ok, whatever the quantity."
            ),
            "cft_target_days": 5,
            "process_owner_id": sq_po.id,
            "overall_process_owner_id": sq_opo.id,
            "qms_coordinator_id": qms.id,
            "cft_member_ids": [cft_b.id, po.id],
            "fields": [
                {"label": "Certificate matches batch", "field_type": "text",
                 "spec_text": "Yes"},
                {"label": "Hardness", "field_type": "number", "unit": "HRC",
                 "spec_min": 58, "spec_max": 62},
                {"label": "Visual damage", "field_type": "text", "spec_text": "None"},
                {"label": "Inspector", "field_type": "text"},
            ],
        })

        format_for(db, admin, {
            "code": "QF-CQ-003",
            "title": "Customer complaint containment review",
            "description": "Monthly review of every open containment action.",
            "team_id": cq.id,
            "frequency": "monthly",
            "work_instruction_ref": "WI-CQ-002",
            "cft_target_days": 7,
            "process_owner_id": po.id,
            "overall_process_owner_id": opo.id,
            "qms_coordinator_id": qms.id,
            "cft_member_ids": [cft_a.id, cft_b.id],
            "fields": [
                {"label": "Open complaints", "field_type": "number", "spec_max": 5},
                {"label": "Containment verified", "field_type": "text",
                 "spec_text": "Yes"},
                {"label": "Reviewed by", "field_type": "text"},
            ],
        })

        if db.query(recs.Record).count():
            print("\nRecords already exist; leaving them alone.")
            _summary(db)
            return 0

        print("\nRecords")

        # 1 · the happy path, all the way to the server.
        good = recs.call_format(db, daily, po)
        fill(db, good, po, {
            "Bore diameter": "25.02", "Surface finish": "0.8", "Run-out": "0.02",
            "Gauge serial": "BG-4471", "Operator": "R. Kumar",
        })
        good = recs.submit(db, good, po, document=evidence(db, good))
        good = approve(db, good, po)
        good = approve(db, good, opo)
        approve(db, good, cft_a, sign=False)
        good = approve(db, good, cft_b, sign=False)
        good = approve(db, good, po)
        good = recs.store(db, good, opo)
        print(f"  + {good.number}  green, filed at {good.storage_path}")

        # 2 · an N-ok observation, flagged and still open.
        bad = recs.call_format(db, daily, po)
        fill(db, bad, po, {
            "Bore diameter": "25.34", "Surface finish": "2.1", "Run-out": "0.03",
            "Gauge serial": "BG-4471", "Operator": "R. Kumar",
        })
        bad = recs.submit(db, bad, po, document=evidence(db, bad))
        print(f"  + {bad.number}  red, N-ok flagged to {opo.full_name}")

        # 3 · the chart's "No" branch: sent back to the CFT.
        sent_back = recs.call_format(db, weekly, sq_po)
        fill(db, sent_back, sq_po, {
            "Certificate matches batch": "Yes", "Hardness": "60",
            "Visual damage": "None", "Inspector": "K. Reddy",
        })
        sent_back = recs.submit(db, sent_back, sq_po,
                                document=evidence(db, sent_back))
        sent_back = approve(db, sent_back, sq_po)
        sent_back = approve(db, sent_back, sq_opo)
        approve(db, sent_back, cft_b, sign=False)
        sent_back = approve(db, sent_back, po, sign=False)
        sent_back = recs.send_back_for_reverification(
            db, sent_back, sq_po,
            "Hardness readings do not match the mill certificate attached. "
            "Re-verify with the CFT before this is accepted.")
        print(f"  + {sent_back.number}  red, back with the CFT for re-verification")

        # 4 · one still being filled.
        drafting = recs.call_format(db, daily, po)
        fill(db, drafting, po, {"Bore diameter": "24.98", "Operator": "R. Kumar"})
        print(f"  + {drafting.number}  yellow, still being filled")

        # 5 · a change request waiting on the QMS Coordinator.
        request = dcr.create(db, po, {
            "kind": dcr.CHANGE_EXISTING,
            "format_id": daily.id,
            "title": "Widen the bore diameter tolerance",
            "reason": (
                "A capability study over 300 parts puts Cpk at 0.94 against the "
                "current band. The process is stable; the band is too tight."
            ),
            "current_state": "Bore diameter 24.90 - 25.10 mm.",
            "proposed_change": "Bore diameter 24.85 - 25.15 mm.",
            "justification": "Capability study CS-2026-11, agreed at the "
                             "quality meeting of 18 August.",
        })
        print(f"  + {request.number}  waiting on {qms.full_name}")

        _summary(db)
        return 0
    finally:
        db.close()


def _summary(db) -> None:
    stats = recs.stats(db)
    print("\n" + "=" * 46)
    print(f"  green {stats['green']}   yellow {stats['yellow']}   red {stats['red']}"
          f"   ({stats['nok_open']} N-ok flag(s) open)")
    print("\nSign in as any of these to see their part of the process:")
    print(f"  {'admin':<12} {PASSWORD:<14} System Administrator - builds and releases formats")
    for username, (full_name, job_title, _department, _team) in PEOPLE.items():
        print(f"  {username:<12} {PASSWORD:<14} {full_name} - {job_title}")
    print("\nChange these passwords before this reaches a real network.\n")


if __name__ == "__main__":
    raise SystemExit(main())
