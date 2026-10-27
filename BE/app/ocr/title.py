"""The title a template made from a document should start with.

A form's title is seldom the first or the biggest text on it: the top-left cell of a
check sheet says "PART NAME", the letterhead says "Harman International India Pvt.
Ltd.". The title names the document - a check sheet, a request, a report - so text
that says what kind of document it is wins, then a heading, then something title-length.
"""
from __future__ import annotations

import re

from .elements import DISPLAY
from .values import plain

_KIND = re.compile(
    r"check\s*-?\s*sheet|check\s*-?\s*list|\bform\b|\breport\b|\brequest\b|\brecord\b|\bregister\b|"
    r"\blog\b|monitoring|inspection|\baudit\b|\bsheet\b|\bplan\b|\bprocedure\b",
    re.I,
)
_NOT_TITLE = re.compile(
    r"\b(pvt|ltd|limited|inc|llp|international)\b|\brev(ision)?\b|\bdate\b|\bdoc(ument)?\s*no\b|:\s*-?\s*$",
    re.I,
)
_TEXT_ELEMENTS = ("Header", "Label", "Paragraph")


def _best(task_data: list[dict]) -> tuple[dict | None, str | None]:
    best, best_text, best_score = None, None, 0.0
    for index, element in enumerate(task_data):
        if element.get("element") not in _TEXT_ELEMENTS:
            continue
        text = " ".join(plain(element.get("content") or element.get("label") or "").split())
        if not 4 <= len(text) <= 120:
            continue
        score = 0.0
        if _KIND.search(text):
            score += 3
        if element.get("element") == "Header":
            score += 2
        if 10 <= len(text) <= 100:
            score += 1
        if _NOT_TITLE.search(text):
            score -= 3
        score -= index * 0.01  # an earlier text wins a tie
        if score > best_score:
            best, best_text, best_score = element, text, score
    return best, best_text


def suggest_title(task_data: list[dict]) -> str | None:
    """The text of the template that best reads as its title, or None."""
    return _best(task_data)[1]


def lead_with_title(task_data: list[dict]) -> None:
    """Make the title the form's heading (in place).

    A scan's biggest text is not always its title: the IFC sheet's top-left "PART NAME"
    was read as the heading and the check sheet's name as a label beside it. When the
    title says what kind of document this is, it becomes the heading and any other
    heading a bold label.
    """
    title, text = _best(task_data)
    if title is None or title.get("element") == "Header" or not _KIND.search(text or ""):
        return
    for element in task_data:
        if element.get("element") == "Header":
            element.update(element="Label", text=DISPLAY["Label"], bold=True)
    title.update(element="Header", text=DISPLAY["Header"])
