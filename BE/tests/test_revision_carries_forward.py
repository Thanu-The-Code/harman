"""
A revision is the old template plus the requested change.

Everything a change request is silent about has to survive it. That sounds
obvious and is exactly the kind of thing that quietly stops being true as a
template grows new parts: the form's design and its approval route were both
added after `new_revision` was written, and neither was carried across - so
executing a change request handed the plant a plainer, differently-approved
form than the one they had asked to amend, with nothing to say so.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, User
from app.models_qms import Format, QualityTeam
from app.services import format_service as fmts
from app.services import form_layout as layouts


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'revisions.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def designed(db):
    """A released template with a designed sheet and a route of its own."""
    team = QualityTeam(code="PQ", name="Process Quality")
    owner = User(username="r.kumar", email="r.kumar@harman.example",
                 full_name="Ravi Kumar", is_active=True,
                 can_approve=True, can_sign=True)
    owner.set_password("Harman@2026")
    db.add_all([team, owner])
    db.commit()

    template = fmts.create_format(db, owner, {
        "code": "QF-PQ-900",
        "title": "Carry-forward check",
        "team_id": team.id,
        "frequency": "daily",
        "process_owner_id": owner.id,
        "overall_process_owner_id": owner.id,
        "qms_coordinator_id": owner.id,
        "layout": layouts.starter("Carry-forward check"),
        "approval_route": [
            {"name": "Line supervisor check", "addressed_to": "people",
             "people_ids": [owner.id], "mode": "any",
             "requires_signature": False, "days": 1},
            {"name": "Process Owner approval", "stage": "po_approval",
             "addressed_to": "process_owner", "mode": "any",
             "requires_signature": True, "days": 2},
        ],
    })
    template.cft_members = [owner]
    db.commit()
    return template, owner


def test_the_next_revision_keeps_the_form_design(db, designed):
    """
    The sheet somebody drew has to survive a change request.

    Without this the plant asks for one tolerance to be widened and gets back a
    form that has lost its letterhead, its checklist and its ruled table.
    """
    template, owner = designed
    before = layouts.parse(template.layout)
    assert before, "the fixture should have a designed sheet"

    successor = fmts.new_revision(db, template, owner, {})

    after = layouts.parse(successor.layout)
    assert [b["kind"] for b in after] == [b["kind"] for b in before]
    assert successor.revision == "01"
    assert template.status == fmts.SUPERSEDED


def test_the_next_revision_keeps_the_approval_route(db, designed):
    """A revision must not silently revert to the standard four steps."""
    from app.services import approval_route as routes

    template, owner = designed
    successor = fmts.new_revision(db, template, owner, {})

    steps = routes.parse(successor.approval_route, successor.cft_target_days)
    assert [s["name"] for s in steps] == [
        "Line supervisor check", "Process Owner approval"]
    assert successor.approval_route, "the custom route must be stored, not defaulted"


def test_a_request_may_still_replace_the_design(db, designed):
    """Carrying forward is the default, not a refusal to change anything."""
    template, owner = designed

    successor = fmts.new_revision(db, template, owner, {
        "layout": [{
            "kind": "fields",
            "title": "Just one entry",
            "fields": [{"label": "Coolant temperature", "type": "number",
                        "spec_min": 18, "spec_max": 24}],
        }],
    })

    after = layouts.parse(successor.layout)
    assert [b["kind"] for b in after] == ["fields"]
    # And the fields follow the new design, because the layout owns them.
    assert [f.label for f in successor.fields] == ["Coolant temperature"]
    assert successor.fields[0].spec_max == 24


def test_the_specification_survives_when_the_request_is_silent(db, designed):
    """The readings and their limits come across unchanged."""
    template, owner = designed
    before = [(f.label, f.spec_min, f.spec_max) for f in template.fields]

    successor = fmts.new_revision(db, template, owner, {})

    assert [(f.label, f.spec_min, f.spec_max) for f in successor.fields] == before


def test_the_old_revision_is_left_exactly_as_it_was(db, designed):
    """
    Records already filled point at the old row and must keep reporting its
    revision. That is the whole reason revisions exist rather than edits.
    """
    template, owner = designed
    original_layout = template.layout
    original_route = template.approval_route

    fmts.new_revision(db, template, owner, {
        "layout": [{"kind": "fields", "title": "Something else",
                    "fields": [{"label": "Anything", "type": "text"}]}],
    })

    assert template.layout == original_layout
    assert template.approval_route == original_route
    assert template.revision == "00"
