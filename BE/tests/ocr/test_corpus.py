"""Regression on the harder two-page bank form (handwriting font, comb boxes, radios, grid)."""
import copy

import pytest

from app.ocr.extract import extract
from app.ocr.pipeline import analyze
from app.ocr.template import build_template

from . import corpus
from .eval_e2e import check_template, score


@pytest.fixture(scope="module")
def template():
    pages, _ = analyze(corpus.to_pdf(corpus.draw()), "blank.pdf")
    return build_template(pages)["task_data"]


def test_template_matches_expected_structure(template):
    problems, extra, opts, table = check_template(template)
    assert problems == [] and extra == []
    assert opts["Account Type"] == ["Savings", "Current", "Fixed Deposit"]
    assert opts["Services Required"] == ["Debit Card", "Cheque Book", "Net Banking", "SMS Alerts"]
    assert [c["text"] for c in table["columns"]] == ["Nominee Name", "Relationship", "Age", "Share (%)"]
    pan = next(e for e in template if e.get("label") == "PAN Number")
    assert pan["ocr"].get("comb") is True


@pytest.mark.parametrize("kind", ["clean", "phone_photo"])
@pytest.mark.parametrize("mode", ["zone", "label"])
def test_extraction(template, kind, mode):
    form = copy.deepcopy(template)
    if mode == "label":
        for e in form:
            e.pop("ocr", None)
            for o in e.get("options") or []:
                o.pop("ocr", None)
    pages = [corpus.degrade(p, kind, seed=i) for i, p in enumerate(corpus.draw(filled=True))]
    result = extract(form, *analyze(corpus.to_pdf(pages), f"{kind}.pdf"))
    wrong = {f: v for f, v in score(form, result).items() if v[0] != "ok"}
    assert wrong == {}
