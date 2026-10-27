"""
What the acceptance test's roles track found, kept found: the flood of
"inspection pending" for per-event forms, a dashboard deaf to its date range,
overdue approvals missing from the list, and drafts shown to their approvers.
"""
from datetime import datetime, timedelta

from app.models_qms import Notification
from app.services import inspection_report as report
from app.services import record_service as recs

from tests.test_qms_record_workflow import _format, _submit, db, people, team  # noqa: F401  (fixtures)


def test_a_per_event_form_is_never_missed(db, people, team):
    """Its period is the moment it is raised: there is no period to have missed, and no flood."""
    _format(db, people, team, frequency="per_event", code="QF-PQ-090")
    for _ in range(3):
        report.sweep_pending(db)
    assert not report.missed_periods(db)
    assert db.query(Notification).filter(Notification.kind == "inspection.pending").count() == 0


def test_the_dashboard_follows_the_range_asked_for(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people)
    record.submitted_at = datetime.utcnow() - timedelta(days=20)
    db.commit()
    assert report.dashboard(db, days=7, period=None)["totals"]["total"] == 0
    assert report.dashboard(db, days=30, period=None)["totals"]["total"] == 1


def test_a_draft_is_its_fillers_not_its_approvers(db, people, team):
    fmt = _format(db, people, team)
    recs.call_format(db, fmt, people["po"])
    mine = recs.list_my_documents(db, people["po"], "draft", None, None, 1, 10)[0]
    theirs = recs.list_my_documents(db, people["opo"], "draft", None, None, 1, 10)[0]
    assert len(mine) == 1 and theirs == []


def test_each_red_says_why(db, people, team):
    fmt = _format(db, people, team)
    record = _submit(db, fmt, people, bore="26.5")  # out of specification
    assert record.rag_status == recs.RED
    assert recs.rag_label(record) == "N-OK not yet cleared by the Overall Process Owner"


def test_a_template_without_a_process_owner_is_filled_by_its_own_team(db, people, team):
    from app.models_qms import QualityTeam
    from app.services import format_service as fmts

    other = db.query(QualityTeam).filter(QualityTeam.code == "SQ").first()
    people["po"].quality_team_id = team.id
    people["opo"].quality_team_id = other.id  # somebody of another team
    db.commit()
    fmt = fmts.create_format(db, people["admin"], {
        "code": "QF-PQ-091", "title": "Owner chosen per record", "team_id": team.id, "frequency": "daily",
        "fields": [{"label": "Reading", "field_type": "number", "spec_max": 5}]})
    fmts.activate(db, fmt, people["admin"])
    assert fmt in fmts.callable_by(db, people["po"])
    assert fmt not in fmts.callable_by(db, people["opo"])
