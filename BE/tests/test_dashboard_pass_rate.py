"""The dashboard's "% within spec" is of the records that had readings to judge."""
from types import SimpleNamespace

from app.models_qms import NOT_OK, OK
from app.services.inspection_report import _pass_rate


def _records(*statuses):
    return [SimpleNamespace(observation_status=s) for s in statuses]


def test_a_record_with_nothing_to_judge_neither_passes_nor_fails():
    # two check sheets judged (one OK, one N-OK) and a change request with no limits on it
    assert _pass_rate(_records(OK, NOT_OK, None)) == 50.0


def test_with_nothing_judged_there_is_no_rate():
    assert _pass_rate(_records(None, None)) is None
    assert _pass_rate([]) is None
