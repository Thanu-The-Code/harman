"""
Turning a paper inspection format into a template somebody can release.

`record_extraction` reads a sheet that has *already been filled* and offers the
values back. This is the other half of the same idea, one step earlier: read the
**blank** format - the hard copy the client has been photocopying for years -
and propose the template itself. The characteristics become fields, the
specification column becomes the limits that decide ok from N-ok, and the code
and revision printed in the corner become the template's own.

Why it is worth doing at all: a plant has hundreds of these, and typing one in
by hand is twenty minutes of transcription per format with a typo budget nobody
wants to spend on specification limits. PP-Structure hands back the table as a
table, so the pairing of "Bore diameter" with "24.90-25.10" is not a guess.

**Proposals, never facts.** Nothing here writes to the database. Every field
comes back with the row it was read from and a confidence, and a person edits
and saves it in the template editor exactly as if they had typed it. An OCR
engine that reads a tolerance of 0.05 as 0.06 must never be able to put a wrong
limit into a released format - the limits are what the whole approval chain
rests on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Optional

from loguru import logger

from .paddle_ocr import StructuredDocument, table_rows

# What the label column is called on the formats this product has seen. A
# quality department names it whatever its own procedure names it, so the list
# is deliberately generous - the cost of a wrong guess is a person editing one
# field, and the cost of no guess is them typing all twelve.
LABEL_HEADINGS = {
    "characteristic", "characteristics", "parameter", "parameters", "description",
    "check", "checks", "checkpoint", "check point", "item", "items", "inspection item",
    "dimension", "dimensions", "feature", "attribute", "particulars", "control item",
    "test", "property", "criteria", "criterion", "point",
}

SPEC_HEADINGS = {
    "specification", "specifications", "spec", "specs", "standard", "standards",
    "limit", "limits", "tolerance", "tolerances", "requirement", "requirements",
    "acceptance", "acceptance criteria", "range", "nominal", "target",
}

UNIT_HEADINGS = {"unit", "units", "uom"}

# Columns that hold what somebody *wrote* rather than what the format asks for.
# On a blank they are empty; on a filled copy they carry last shift's readings,
# and either way they are not part of the template.
VALUE_HEADINGS = {
    "reading", "readings", "observation", "observations", "observed", "value",
    "values", "actual", "measured", "result", "results", "finding", "findings",
    "remark", "remarks", "status", "judgement", "judgment", "ok/notok", "sign",
    "signature", "verified", "checked by", "by",
}

# A row numbering column, which is furniture rather than a reading.
SERIAL_HEADINGS = {"sr", "sr.", "sr no", "sr.no", "s.no", "sno", "sl", "sl no",
                   "no", "no.", "#", "serial"}

# Words that mean "this line is judged by eye, not measured". A characteristic
# specified as OK becomes a three-way choice rather than a free-text box, which
# is what the client's own forms print: OK / Not OK / NA.
JUDGEMENT_WORDS = {
    "ok", "okay", "ok/notok", "ok / not ok", "present", "yes", "conforming",
    "conform", "satisfactory", "sat", "good", "acceptable", "pass", "passed",
    "available", "done", "complete", "clean", "correct",
}

JUDGEMENT_OPTIONS = ["OK", "Not OK", "NA"]

# The details printed above the readings - Plant, Line, Shift, Part No. They
# are part of the format and worth capturing, but they are context rather than
# measurements, so they are proposed as optional text and nothing is judged by
# them.
DETAIL_MAX_WORDS = 5

# Key-value furniture in the page header: "Format:QF-PQ-001", "Rev:00".
FACT_PATTERNS = {
    "code": r"(?:format|document|doc|form)\s*(?:no|number|code)?\s*[:.\-]\s*([A-Z0-9][A-Z0-9\-/]{2,})",
    "revision": r"\brev(?:ision)?\s*(?:no)?\s*[:.\-]?\s*([A-Z0-9][A-Z0-9.\-]{0,7})\b",
    "work_instruction_ref": r"(?:work\s*instruction|w\.?i\.?)\s*(?:no|ref)?\s*[:.\-]\s*([A-Z0-9][A-Z0-9\-/]{2,})",
}

# A line that is page furniture rather than the format's name.
TITLE_NOISE = re.compile(
    r"^(harman|page\s|quality management system|confidential|uncontrolled|"
    r"format\s*[:.]|rev\s*[:.]|doc\w*\s*[:.]|work instruction)", re.I)


@dataclass
class ProposedField:
    """One line of the paper format, as this module read it."""

    label: str
    field_type: str = "text"
    unit: Optional[str] = None
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None
    spec_text: Optional[str] = None
    options: Optional[list[str]] = None
    required: bool = True
    # What it was read from, so a reviewer can check it against the scan
    # without hunting for the line.
    source: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "field_type": self.field_type,
            "unit": self.unit,
            "spec_min": self.spec_min,
            "spec_max": self.spec_max,
            "spec_text": self.spec_text,
            "options": self.options,
            "required": self.required,
            "source": self.source,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class ProposedFormat:
    """A whole template, proposed. Nothing here has been saved."""

    title: str = ""
    code: Optional[str] = None
    revision: Optional[str] = None
    work_instruction_ref: Optional[str] = None
    fields: list[ProposedField] = dc_field(default_factory=list)

    engine: str = ""
    pages: int = 0
    mean_confidence: Optional[float] = None
    # What the reader could not do, said plainly. A person about to release a
    # template needs to know the difference between "there were three
    # characteristics" and "no table was recognised at all".
    notes: list[str] = dc_field(default_factory=list)
    text: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "code": self.code,
            "revision": self.revision,
            "work_instruction_ref": self.work_instruction_ref,
            "fields": [f.to_dict() for f in self.fields],
            "engine": self.engine,
            "pages": self.pages,
            "mean_confidence": (round(self.mean_confidence, 3)
                                if self.mean_confidence is not None else None),
            "notes": self.notes,
            "text": self.text,
        }


# --------------------------------------------------------------- public API


def propose(document: StructuredDocument) -> ProposedFormat:
    """Read a scanned blank format and propose the template it describes."""
    out = ProposedFormat(
        engine=document.engine,
        pages=document.pages,
        mean_confidence=document.mean_confidence,
        text=document.text,
    )

    flat = document.text or ""
    out.title = _title(document, flat)
    facts = _facts(flat)
    out.code = facts.get("code")
    out.revision = facts.get("revision")
    out.work_instruction_ref = facts.get("work_instruction_ref")

    confidence = document.mean_confidence or 0.0
    seen: set[str] = set()

    for table in document.tables:
        rows = [r for r in table_rows(table.html) if any(c.strip() for c in r)]
        if not rows:
            continue
        head = _heading_row(rows)
        if head is None:
            # No recognisable heading. The first column is still the most
            # likely label on any form laid out left to right, so the table is
            # read as label-then-specification rather than skipped.
            out.notes.append(
                "A table was read but its column headings were not recognised. "
                "Its first column has been taken as the characteristic and its "
                "second as the specification - check both.")
            columns = {"label": 0, "spec": 1 if len(rows[0]) > 1 else None,
                       "unit": None}
            body = rows
        else:
            columns = _columns(rows[head])
            body = rows[head + 1:]
            # Anything above the heading is the format's own detail block.
            for detail in _details(rows[:head]):
                if _key(detail.label) not in seen:
                    seen.add(_key(detail.label))
                    detail.confidence = confidence
                    out.fields.append(detail)

        if columns["label"] is None:
            continue

        for row in body:
            proposed = _field_from(row, columns, confidence)
            if not proposed:
                continue
            key = _key(proposed.label)
            if key in seen:
                continue
            seen.add(key)
            out.fields.append(proposed)

    if not document.tables:
        out.notes.append(
            "No table was recognised on this page, so no characteristics could "
            "be read. A photograph taken square to the page, with the ruled "
            "table filling the frame, reads best.")
    elif not out.fields:
        out.notes.append(
            "A table was recognised but no characteristic could be read from "
            "its rows.")

    if not out.code:
        out.notes.append("No format code was found on the page - give it one.")

    logger.info("format_extraction: proposed %d field(s) from %s",
                len(out.fields), document.engine)
    return out


# ------------------------------------------------------------------ reading


def _key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (label or "").lower())


def _title(document: StructuredDocument, flat: str) -> str:
    """
    The format's name.

    PP-Structure marks a title region when it finds one; when it does not, the
    first line that is not page furniture is the best answer available, which
    on every sheet seen so far is the name printed across the top.
    """
    for region in document.regions:
        if region.kind == "title" and region.text.strip():
            return _tidy(region.text.strip().splitlines()[0])

    for line in flat.splitlines():
        line = line.strip()
        if not line or TITLE_NOISE.match(line):
            continue
        if len(line) < 4 or line.count("|") > 1:
            continue
        return _tidy(line)
    return ""


def _tidy(text: str) -> str:
    """Sentence case for something the page shouted in capitals."""
    text = re.sub(r"\s+", " ", text or "").strip(" :.-")
    if text and text == text.upper() and len(text) > 4:
        return text.capitalize()
    return text


def _facts(flat: str) -> dict:
    """Code, revision and work instruction, wherever on the page they are."""
    found: dict[str, str] = {}
    for name, pattern in FACT_PATTERNS.items():
        match = re.search(pattern, flat, re.I)
        if match:
            found[name] = match.group(1).strip(" :.-")
    return found


def _heading_row(rows: list[list[str]]) -> Optional[int]:
    """
    Which row names the columns.

    Not always the first: the sheets this was built against print a block of
    plant and shift details above the readings, inside the same ruled table.
    """
    for index, row in enumerate(rows[:8]):
        cells = [c.strip().lower().rstrip(".:") for c in row]
        if any(c in LABEL_HEADINGS for c in cells) and \
           any(c in SPEC_HEADINGS | VALUE_HEADINGS for c in cells):
            return index
    return None


def _columns(heading: list[str]) -> dict:
    """Which column is the label, the specification and the unit."""
    found = {"label": None, "spec": None, "unit": None}
    for index, cell in enumerate(heading):
        name = cell.strip().lower().rstrip(".:")
        if found["label"] is None and name in LABEL_HEADINGS:
            found["label"] = index
        elif found["spec"] is None and name in SPEC_HEADINGS:
            found["spec"] = index
        elif found["unit"] is None and name in UNIT_HEADINGS:
            found["unit"] = index

    if found["label"] is None:
        # A heading was recognised by its specification column alone. The
        # label is then the first column that is not the serial number.
        for index, cell in enumerate(heading):
            if cell.strip().lower().rstrip(".:") not in SERIAL_HEADINGS:
                found["label"] = index
                break
    return found


def _field_from(row: list[str], columns: dict, confidence: float) -> Optional[ProposedField]:
    """One body row of the readings table, as a field."""
    label_at = columns["label"]
    if label_at is None or label_at >= len(row):
        return None

    label, unit = _split_unit(row[label_at])
    if not label or len(label) < 2:
        return None
    # A row that is only a number is the serial column bleeding through.
    if re.fullmatch(r"[\d.\s]+", label):
        return None

    if columns["unit"] is not None and columns["unit"] < len(row):
        unit = row[columns["unit"]].strip() or unit

    spec = ""
    if columns["spec"] is not None and columns["spec"] < len(row):
        spec = row[columns["spec"]].strip()

    proposed = ProposedField(
        label=label, unit=unit or None,
        source=" | ".join(c for c in row if c.strip()),
        confidence=confidence,
    )
    _apply_spec(proposed, spec)
    return proposed


def _details(rows: list[list[str]]) -> list[ProposedField]:
    """
    The block above the readings: Plant, Line, Shift, Part No.

    Part of the format and worth filling in, but nothing here is measured
    against anything, so they are proposed as optional text and judged by
    nobody.
    """
    out: list[ProposedField] = []
    for row in rows:
        for cell in row:
            cell = cell.strip()
            if not cell or ":" not in cell:
                continue
            name = cell.split(":", 1)[0].strip()
            if not name or len(name.split()) > DETAIL_MAX_WORDS:
                continue
            if _key(name) in {"date", "dated"}:
                out.append(ProposedField(label=_spaced(name), field_type="date",
                                         required=False, source=cell))
                continue
            out.append(ProposedField(label=_spaced(name), field_type="text",
                                     required=False, source=cell))
    return out


def _spaced(name: str) -> str:
    """"PartNo" as the page ran it together, given its space back."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()


def _split_unit(cell: str) -> tuple[str, Optional[str]]:
    """"Bore diameter (mm)" -> ("Bore diameter", "mm")."""
    cell = re.sub(r"\s+", " ", (cell or "").strip())
    match = re.match(r"^(.*?)\s*\(([^)]{1,12})\)\s*$", cell)
    if match and match.group(1).strip():
        return match.group(1).strip(), match.group(2).strip()
    return cell, None


def _apply_spec(proposed: ProposedField, spec: str) -> None:
    """
    Read a specification cell into limits.

    The forms write it every way a machinist writes it, so all of them are
    understood and anything left over is kept as written rather than thrown
    away - a limit nobody can parse is still a limit somebody has to meet.
    """
    spec = re.sub(r"\s+", " ", (spec or "").strip())
    if not spec:
        # Nothing to judge against. Recorded, not judged - which the product
        # already understands and prints as such.
        return

    low = spec.lower()
    number = r"[-+]?\d+(?:\.\d+)?"

    # 25.00 ± 0.05
    around = re.search(rf"({number})\s*(?:±|\+/-|\+-)\s*({number})", spec)
    if around:
        middle, tolerance = float(around.group(1)), float(around.group(2))
        proposed.spec_min, proposed.spec_max = middle - tolerance, middle + tolerance
        proposed.field_type = "number"
        return

    # 24.90 - 25.10, 24.90 to 25.10
    between = re.search(rf"({number})\s*(?:-|–|to|\.\.)\s*({number})", spec, re.I)
    if between and not low.startswith(("max", "min")):
        first, second = float(between.group(1)), float(between.group(2))
        proposed.spec_min, proposed.spec_max = min(first, second), max(first, second)
        proposed.field_type = "number"
        return

    # max 1.6, <= 1.6, NMT 1.6
    upper = re.search(rf"(?:max|maximum|nmt|≤|<=|<)\s*({number})", spec, re.I)
    if upper:
        proposed.spec_max = float(upper.group(1))
        proposed.field_type = "number"
        return

    # min 0.5, >= 0.5, NLT 0.5
    lower = re.search(rf"(?:min|minimum|nlt|≥|>=|>)\s*({number})", spec, re.I)
    if lower:
        proposed.spec_min = float(lower.group(1))
        proposed.field_type = "number"
        return

    # A bare number is a target with no tolerance printed. Kept as written
    # rather than invented into limits nobody specified.
    if re.fullmatch(number, spec):
        proposed.field_type = "number"
        proposed.spec_text = spec
        return

    # Judged by eye: OK / Not OK / NA, which is what the paper prints.
    if _key(spec) in {_key(w) for w in JUDGEMENT_WORDS}:
        proposed.field_type = "select"
        proposed.options = list(JUDGEMENT_OPTIONS)
        proposed.spec_text = "OK"
        return

    proposed.spec_text = spec
