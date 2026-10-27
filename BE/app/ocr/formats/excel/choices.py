"""Tick boxes typed as text: "☐ Yes ☐ No", "Married: [ ] Yes [x] No", or a lone "☐" in a cell.

Shared by the template side (which options a cell offers) and the filling side (which are ticked).
"""
import re

EMPTY_BOXES = "☐□▢❏❑"
TICKED_BOXES = "☑☒▣✅"
EMPTY_RADIOS = "○◯◦"
FILLED_RADIOS = "●◉⦿"
FILLED_SQUARE = "■"  # a ticked box in some forms, but also a common bullet
EMPTY = EMPTY_BOXES + EMPTY_RADIOS
GLYPHS = EMPTY_BOXES + TICKED_BOXES + EMPTY_RADIOS + FILLED_RADIOS + FILLED_SQUARE
MAX_OPTION_WORDS = 6

_BRACKETS = [
    (re.compile(r"\[\s*\]"), "☐"),
    (re.compile(r"\[\s*[xX✓✔√]\s*\]"), "☑"),
    (re.compile(r"\(\s*\)"), "○"),
    (re.compile(r"\(\s*[xX•●✓✔]\s*\)"), "●"),
]


def _normalize(text):
    for pattern, glyph in _BRACKETS:
        text = pattern.sub(glyph, text)
    return text


def kind_of(glyph):
    return "radio" if glyph in EMPTY_RADIOS + FILLED_RADIOS else "checkbox"


def is_ticked(glyph):
    return glyph in TICKED_BOXES + FILLED_RADIOS + FILLED_SQUARE


def lone_glyph(text):
    """The glyph if the cell holds nothing but one tick box ("☐", "☑", "[ ]"), else None."""
    t = _normalize((text or "").strip())
    return t if len(t) == 1 and t in GLYPHS else None


def glyph_for(kind, checked):
    if kind == "radio":
        return "●" if checked else "○"
    return "☑" if checked else "☐"


def set_ticks(text, states):
    """Re-tick the tick boxes in a cell's text: states {option index: checked}; others unchanged.

    'Married: ☐ Yes ☐ No', {1: True} -> 'Married: ☐ Yes ☑ No'. A lone box becomes ☑ / ☐.
    """
    t = _normalize((text or "").strip())
    if len(t) == 1 and t in GLYPHS:
        return glyph_for(kind_of(t), states.get(0, is_ticked(t)))
    out, n = [], 0
    for ch in t:
        if ch in GLYPHS:
            if n in states:
                ch = glyph_for(kind_of(ch), states[n])
            n += 1
        out.append(ch)
    return "".join(out)


def glyph_options(text):
    """'Married: ☐ Yes ☑ No' -> ('Married:', [{"text": "Yes", "checked": False, "kind": "checkbox"}, ...]).

    None when the text is not a set of tick boxes. A filled square alone is read as a bullet,
    not a ticked box, unless an empty box sits beside it.
    """
    t = _normalize((text or "").strip())
    marks = [i for i, ch in enumerate(t) if ch in GLYPHS]
    if not marks or len(t) == 1:
        return None
    if not any(t[i] in EMPTY + TICKED_BOXES for i in marks):
        return None
    options = []
    for n, i in enumerate(marks):
        end = marks[n + 1] if n + 1 < len(marks) else len(t)
        caption = " ".join(t[i + 1:end].strip(" \t\n:-–/,;").split())
        if len(caption.split()) > MAX_OPTION_WORDS:
            return None  # a sentence after a bullet, not an option
        options.append({"text": caption, "checked": is_ticked(t[i]), "kind": kind_of(t[i])})
    if not any(o["text"] for o in options):
        return None
    return t[:marks[0]].strip(), options
