"""
The approval route, and the migration table that has to keep up with it.

The route is what turns "who approves this" from a hard-coded chain into
something a plant can state. These tests defend the two things that make it
safe to do that: the process document is what you get when you say nothing, and
a route that could not work is refused before the template is released rather
than discovered by a supervisor waiting on an approval.
"""
import ast
import json
from pathlib import Path

import pytest

from app.services import approval_route as routes

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class FakePerson:
    def __init__(self, name, active=True):
        self.id = name.lower().replace(" ", ".")
        self.full_name = name
        self.username = self.id
        self.is_active = active


class FakeFormat:
    """Enough of a template for the route to be resolved against."""

    def __init__(self, po=None, opo=None, qms=None, cft=(), route=None, days=3):
        self.process_owner = po
        self.overall_process_owner = opo
        self.qms_coordinator = qms
        self.process_owner_id = po.id if po else None
        self.overall_process_owner_id = opo.id if opo else None
        self.qms_coordinator_id = qms.id if qms else None
        self.cft_members = list(cft)
        self.approval_route = route
        self.cft_target_days = days


def staffed(**kwargs):
    return FakeFormat(
        po=FakePerson("Ravi Kumar"),
        opo=FakePerson("Sunita Iyer"),
        qms=FakePerson("Mohammed Shaikh"),
        cft=[FakePerson("Anil Deshmukh"), FakePerson("Priya Nair")],
        **kwargs,
    )


# --------------------------------------------------------------- the default


def test_a_template_with_no_route_follows_the_process_document():
    """The specified process is the default, not one option among several."""
    steps = routes.parse(None)

    assert [s["stage"] for s in steps] == [
        routes.STAGE_PO, routes.STAGE_OPO, routes.STAGE_CFT, routes.STAGE_FINAL]
    assert [s["order"] for s in steps] == [1, 2, 3, 4]


def test_the_joint_review_needs_everybody_and_the_others_do_not():
    """
    The chart calls the CFT review *joint*. One member agreeing does not
    conclude it, while every other step is addressed to a single named person.
    """
    steps = {s["stage"]: s for s in routes.parse(None)}

    assert steps[routes.STAGE_CFT]["mode"] == routes.ALL_OF
    for stage in (routes.STAGE_PO, routes.STAGE_OPO, routes.STAGE_FINAL):
        assert steps[stage]["mode"] == routes.ANY_OF


def test_the_default_route_carries_the_cft_target_date():
    """B6 gives the joint review a target date, and it comes from the template."""
    steps = {s["stage"]: s for s in routes.parse(None, cft_target_days=7)}
    assert steps[routes.STAGE_CFT]["days"] == 7


def test_the_default_is_normalised_like_any_other_route():
    """
    Every step reaches a caller in one shape.

    The default used to be handed back exactly as written, without the `order`
    the cleaner adds - so a screen that had only ever seen a custom route
    worked, and the same screen on a standard template died on a missing key.
    """
    for step in routes.parse(None):
        assert set(step) == {"name", "stage", "addressed_to", "people_ids",
                             "mode", "requires_signature", "days", "order"}


# ---------------------------------------------------------- a route of one's own


def test_a_stored_route_replaces_the_default():
    stored = json.dumps([
        {"name": "Line supervisor check", "addressed_to": "people",
         "people_ids": ["s.rao"], "requires_signature": False, "days": 1},
        {"name": "Process Owner approval", "stage": "po_approval",
         "addressed_to": "process_owner", "requires_signature": True, "days": 2},
    ])
    steps = routes.parse(stored)

    assert [s["name"] for s in steps] == ["Line supervisor check",
                                          "Process Owner approval"]
    assert steps[1]["days"] == 2


def test_a_route_that_cannot_be_read_falls_back_to_the_process():
    """
    A broken configuration must not stop a shift being recorded.

    The safe answer to an unreadable route is the specified process, not no
    process at all.
    """
    assert len(routes.parse("{ not json at all")) == 4
    assert len(routes.parse(json.dumps({"not": "a list"}))) == 4
    assert len(routes.parse(json.dumps([]))) == 4


def test_a_nameless_step_is_dropped_rather_than_stalling_the_chain():
    stored = json.dumps([
        {"name": "", "addressed_to": "process_owner"},
        {"name": "Real step", "addressed_to": "process_owner",
         "requires_signature": True},
    ])
    steps = routes.parse(stored)
    assert [s["name"] for s in steps] == ["Real step"]


def test_dump_returns_nothing_for_an_empty_route():
    """Storing nothing is how somebody says 'go back to the standard process'."""
    assert routes.dump([]) is None
    assert routes.dump(None) is None


# -------------------------------------------------------------- what it refuses


def test_a_route_nobody_signs_is_refused():
    """A quality record that nobody signed is not a quality record."""
    steps = routes.parse(json.dumps([
        {"name": "A look over", "addressed_to": "process_owner",
         "requires_signature": False},
    ]))
    found = routes.problems(steps, staffed())

    assert any("signature" in p for p in found)


def test_a_step_addressed_to_nobody_is_refused():
    """
    A step with no assignee stalls forever, and says nothing on screen while it
    does. It has to be caught when the template is released.
    """
    steps = routes.parse(json.dumps([
        {"name": "Nobody's step", "addressed_to": "people", "people_ids": [],
         "requires_signature": True},
    ]))
    found = routes.problems(steps, staffed())

    assert any("not addressed to anybody" in p for p in found)


def test_a_step_addressed_to_an_unnamed_role_is_refused():
    unstaffed = FakeFormat(po=None, opo=None, qms=None, cft=[])
    found = routes.problems(routes.parse(None), unstaffed)

    assert any("Process Owner, who is not named" in p for p in found)
    assert any("Overall Process Owner, who is not named" in p for p in found)
    assert any("CFT, which has no members" in p for p in found)


def test_a_properly_staffed_default_route_has_no_problems():
    assert routes.problems(routes.parse(None), staffed()) == []


# ------------------------------------------------------------ who it reaches


def test_a_role_step_resolves_to_whoever_holds_the_role_now():
    """
    Addressing a role rather than a person is what lets the route survive
    somebody leaving: name the new Process Owner once and every step follows.
    """
    fmt = staffed()
    steps = {s["stage"]: s for s in routes.parse(None)}

    assert routes.assignees_for(steps[routes.STAGE_PO], fmt) == [fmt.process_owner_id]
    assert routes.assignees_for(steps[routes.STAGE_CFT], fmt) == [
        m.id for m in fmt.cft_members]


def test_a_named_step_resolves_to_the_people_on_it():
    steps = routes.parse(json.dumps([
        {"name": "Two named people", "addressed_to": "people",
         "people_ids": ["a.sharma", "r.kumar"], "requires_signature": True},
    ]))
    assert routes.assignees_for(steps[0], staffed()) == ["a.sharma", "r.kumar"]


def test_describe_says_who_a_step_will_actually_reach():
    fmt = staffed()
    steps = {s["stage"]: s for s in routes.parse(None)}

    assert routes.describe(steps[routes.STAGE_PO], fmt) == "Ravi Kumar"
    assert "Anil Deshmukh" in routes.describe(steps[routes.STAGE_CFT], fmt)
    assert routes.describe(
        steps[routes.STAGE_PO],
        FakeFormat(po=None)) == "nobody yet"


# ------------------------------------------------- the migration table itself


def test_no_table_is_listed_twice_in_the_migration_table():
    """
    A duplicate key in a dict literal silently replaces the first one.

    `ADDITIONS` was written with two "formats" entries, and Python kept only
    the second - so every column in the first was never added, the server
    started healthy, and the first request touching one of them returned a 500.
    Nothing warns about this, so it is asserted here instead.
    """
    source = (REPOSITORY_ROOT / "app" / "utils" / "schema_migrations.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)

    additions = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and getattr(node.target, "id", None) == "ADDITIONS"
    )

    tables = [key.value for key in additions.keys if isinstance(key, ast.Constant)]
    duplicates = {name for name in tables if tables.count(name) > 1}

    assert not duplicates, (
        f"these tables are listed twice, so the earlier block never runs: "
        f"{sorted(duplicates)}")


@pytest.mark.parametrize("table, column", [
    ("formats", "approval_route"),
    ("users", "quality_team_id"),
])
def test_columns_added_after_the_first_release_are_in_the_migration_table(table, column):
    """
    Every column added to a model has to be added to the migration table too.

    `create_all` builds new tables but never adds a column to one that already
    exists, so an installation that upgrades by pulling and restarting gets a
    server that starts and then fails on the first query touching the column -
    including sign-in.
    """
    from app.utils.schema_migrations import ADDITIONS

    assert column in ADDITIONS.get(table, {})
