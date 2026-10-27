"""
Turning a scanned format back into a filled record.

This is why the structure was worth keeping. A quality record is a table: rows
of labelled readings with their values beside them. Flattened into a wall of
text, "Bore diameter 25.02 0.8 Ra R. Kumar" is a guess about which number
belongs to which line. Kept as a table, the pairing is not a guess at all.

So when a Process Owner photographs a filled sheet, this module matches the
recognised table rows against the format's own field labels and offers the
values back as suggestions. Nobody has to retype a form they have already
filled once on paper.

**Suggestions, never facts.** Every value is offered with the confidence and
the row it came from, and nothing is written to the record until a person has
looked at it. An OCR engine that reads 25.02 as 26.02 must not be able to
silently put an out-of-specification reading into a quality record - the whole
point of B4 is that a person confirms it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from .paddle_ocr import StructuredDocument, table_rows

# Below this the two labels are not the same line, whatever the arithmetic says.
MIN_SIMILARITY = 0.62

# Words that appear in a scanned label but carry no meaning when matching:
# units and column furniture the format's own label does not repeat.
NOISE = {
    "value", "values", "reading", "readings", "result", "results", "observed",
    "observation", "actual", "measured", "spec", "specification", "limit",
    "limits", "min", "max", "unit", "units", "sr", "no", "s", "n", "sl",
    "remark", "remarks", "check", "checked", "nom", "nominal",
}


@dataclass
class Suggestion:
    """One reading the scan appears to contain."""

    label: str                       # the format's own label
    value: str                       # what the scan said
    source_label: str = ""           # the label as it appeared on the sheet
    confidence: float = 0.0          # 0..1, how sure the match is
    row: int = 0
    in_spec: Optional[bool] = None   # judged once the value is a number

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "value": self.value,
            "source_label": self.source_label,
            "confidence": round(self.confidence, 3),
            "row": self.row,
            "in_spec": self.in_spec,
        }


def _normalise(text: str) -> list[str]:
    """A label reduced to the words that actually identify it."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    kept = [w for w in words if w not in NOISE and not w.isdigit()]
    return kept or words


def similarity(a: str, b: str) -> float:
    """
    How alike two labels are, as words rather than characters.

    Word overlap rather than edit distance because OCR mangles characters but
    rarely loses whole words: "Bore diameter" read as "Bore diarneter" should
    still match, and "Surface finish" should not match "Bore diameter" merely
    because they share letters.
    """
    from difflib import SequenceMatcher

    left, right = set(_normalise(a)), set(_normalise(b))
    if not left or not right:
        return 0.0

    by_word = len(left & right) / len(left | right)

    # And by characters, which is what rescues a word OCR mangled outright:
    # "diarneter" shares no whole word with "diameter" but almost every letter.
    # Discounted slightly so a genuine word match always outranks a lucky
    # spelling coincidence.
    by_chars = SequenceMatcher(None, " ".join(sorted(left)),
                               " ".join(sorted(right))).ratio() * 0.9

    return max(by_word, by_chars)


NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def _first_number(text: str) -> Optional[str]:
    match = NUMBER.search(text or "")
    if not match:
        return None
    return match.group(0).replace(",", ".")


# How a specification announces itself in a cell: a limit word, a tolerance
# sign, or a range. Most formats put one between the label and the reading.
SPEC_WORDS = re.compile(
    r"\b(max|min|maximum|minimum|nom|nominal|spec|tol|tolerance|limit|ref|"
    r"upto|up\s*to)\b", re.I)
RANGE = re.compile(r"\d\s*(?:-|–|—|to|\.\.|~)\s*\d", re.I)
TOLERANCE = re.compile(r"[±+]\s*/?\s*-?\s*\d")


def _is_specification(text: str, spec_min, spec_max) -> bool:
    """
    Is this cell the limit rather than the measurement?

    Getting this wrong is the worst failure this module can have: a
    specification read as a reading is always plausible and always within
    specification, so nobody notices it is not what was measured.

    Three signals, any of which is enough:
      - it says so         "max 1.6", "Tol ±0.05"
      - it is a range      "24.90 - 25.10"
      - it *is* the limit  the number equals this field's own spec bound
    """
    if SPEC_WORDS.search(text) or RANGE.search(text) or TOLERANCE.search(text):
        return True

    number = _first_number(text)
    if number is None:
        return False
    try:
        value = float(number)
    except ValueError:
        return False
    for bound in (spec_min, spec_max):
        if bound is not None and abs(value - float(bound)) < 1e-9:
            return True
    return False


def _value_from_row(row: list[str], label_at: int, numeric: bool,
                    spec_min=None, spec_max=None) -> str:
    """
    The cell on this row that holds the reading.

    Read left to right after the label. Cells that are specifications are
    stepped over rather than taken - see `_is_specification` for why that
    matters more than it looks.
    """
    candidates = row[label_at + 1:] or row[:label_at]
    best = ""
    for cell in candidates:
        text = (cell or "").strip()
        if not text or text in {"-", "--", "n/a", "N/A"}:
            continue
        if _is_specification(text, spec_min, spec_max):
            continue
        if numeric:
            number = _first_number(text)
            if number is not None:
                return number
            continue
        if not best:
            best = text
    return best


def suggest_values(document: StructuredDocument, fields: list) -> list[Suggestion]:
    """
    Match a scanned document's tables against a format's fields.

    `fields` are the record's own value rows - anything carrying `label`, and
    optionally `field_type`, `spec_min`, `spec_max`. Returns one suggestion per
    field that was confidently found, best match first.
    """
    if not document or not fields:
        return []

    rows: list[list[str]] = []
    for table in document.tables:
        rows.extend(table_rows(table.html))

    # A format with no ruled table still has labelled lines. Treat each line of
    # recognised text as a one-row table so those are matched too.
    if not rows:
        for region in document.regions:
            for line in (region.text or "").splitlines():
                if line.strip():
                    rows.append(re.split(r"\s{2,}|\t|:", line.strip()))

    suggestions: list[Suggestion] = []
    used_rows: set[int] = set()

    for field in fields:
        label = getattr(field, "label", None) or (
            field.get("label") if isinstance(field, dict) else None)
        if not label:
            continue

        field_type = getattr(field, "field_type", None) or (
            field.get("field_type") if isinstance(field, dict) else None) or "text"
        spec_min = getattr(field, "spec_min", None) if not isinstance(field, dict) \
            else field.get("spec_min")
        spec_max = getattr(field, "spec_max", None) if not isinstance(field, dict) \
            else field.get("spec_max")
        numeric = field_type == "number" or spec_min is not None or spec_max is not None

        best: Optional[Suggestion] = None
        for index, row in enumerate(rows):
            if index in used_rows or not row:
                continue
            for cell_at, cell in enumerate(row):
                score = similarity(label, cell)
                if score < MIN_SIMILARITY:
                    continue
                value = _value_from_row(row, cell_at, numeric,
                                        spec_min, spec_max)
                if not value:
                    continue
                if best is None or score > best.confidence:
                    best = Suggestion(label=label, value=value,
                                      source_label=(cell or "").strip(),
                                      confidence=score, row=index)

        if best is None:
            continue

        if numeric:
            number = _first_number(best.value)
            if number is None:
                continue
            best.value = number
            reading = float(number)
            if spec_min is not None and reading < float(spec_min):
                best.in_spec = False
            elif spec_max is not None and reading > float(spec_max):
                best.in_spec = False
            elif spec_min is not None or spec_max is not None:
                best.in_spec = True

        used_rows.add(best.row)
        suggestions.append(best)

    suggestions.sort(key=lambda s: -s.confidence)
    logger.info(
        f"Matched {len(suggestions)} of {len(fields)} field(s) from "
        f"{len(document.tables)} recognised table(s)"
    )
    return suggestions
