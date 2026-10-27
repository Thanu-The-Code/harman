"""One label per field: two "Sign:" boxes on a form become "Sign – Req.HOD Name" and
"Sign – Approved By (M.R.)".

A reading is shown, exported and reviewed by its label, so two fields with the same
label cannot be told apart once filled in. A repeated label is qualified by the
field written above it (the person or column it belongs to), or numbered when
nothing is.
"""
from . import geometry as g

NOT_FIELDS = {"Table", "Image", "TwoColumnRow", "ThreeColumnRow", "MultiColumnRow"}


def _key(label):
    return " ".join((label or "").split()).lower()


def _box(e):
    ocr = e.get("ocr") or {}
    return ocr.get("label_bbox") or ocr.get("value_bbox")


def _above(e, fields):
    """The nearest other field directly above this one on its page."""
    box, page = _box(e), (e.get("ocr") or {}).get("page")
    if not box:
        return None
    best, best_d = None, None
    for other in fields:
        ob = _box(other)
        if other is e or not ob or (other.get("ocr") or {}).get("page") != page:
            continue
        d = box[1] - ob[3]
        if d < -0.002 or g.h_overlap(box, ob) < 0.5:
            continue
        if best_d is None or d < best_d:
            best, best_d = other, d
    return best


def disambiguate(task_data):
    """Rename repeated input labels in place; returns task_data."""
    fields = [e for e in task_data if e.get("field_name") and not e.get("static") and e.get("element") not in NOT_FIELDS]
    groups = {}
    for e in fields:
        if _key(e.get("label")):
            groups.setdefault(_key(e["label"]), []).append(e)
    renamed = {}  # worked out before any label changes, so the result does not depend on order
    for same in groups.values():
        if len(same) < 2:
            continue
        for e in same:
            above = _above(e, fields)
            if above is not None and _key(above.get("label")) not in ("", _key(e["label"])):
                renamed[id(e)] = f"{e['label']} – {above['label']}"
    for e in fields:
        e["label"] = renamed.get(id(e), e.get("label"))
    taken = set()
    for e in fields:
        label, n = e.get("label") or "", 2
        if not _key(label):
            continue
        while _key(e["label"]) in taken:
            e["label"], n = f"{label} ({n})", n + 1
        taken.add(_key(e["label"]))
    return task_data
