"""Format-independent parts of filling a form: label matching, typing raw text into the
value each element accepts, and the answers/report every extractor returns."""
import re

from rapidfuzz import fuzz

from . import values as v

NO_VALUE = {
    "Header", "Paragraph", "Label", "LineBreak", "Image", "HyperLink", "Download", "Camera",
    "FileUpload", "TwoColumnRow", "ThreeColumnRow", "MultiColumnRow", "FieldSet",
}


def prefix_score(label, text):
    """How well `label` matches `text` or the start of it (labels are often followed by values)."""
    a, t = v.norm(v.strip_numbering(v.plain(label))), v.norm(v.strip_numbering(text))
    if len(a) < 2 or not t:
        return 0.0
    best = fuzz.ratio(a, t)
    for k in (len(a) - 1, len(a), len(a) + 1):
        if 0 < k <= len(t) and (k == len(t) or not t[k - 1:k + 1].isalnum()):
            best = max(best, fuzz.ratio(a, t[:k]))
    return best


def label_cut(text_full, label):
    """Index in text just after the label (and its colon); skips '2.'-style numbering."""
    text = v.strip_numbering(text_full)
    off = len(text_full) - len(text)
    plain_label = v.strip_numbering(v.plain(label))
    colon = max(text.find(":"), text.find("："))
    if 0 < colon <= len(plain_label) + 4:
        return off + colon + 1
    target = v.norm(plain_label)
    best_k, best = len(plain_label), -1
    for k in range(max(1, len(plain_label) - 3), min(len(text), len(plain_label) + 4) + 1):
        score = fuzz.ratio(target, v.norm(text[:k]))
        if score > best:
            best_k, best = k, score
    return off + best_k


def typed_value(e, raw):
    """Raw text -> the value this element's answer_data expects (None if unusable)."""
    kind = e.get("element")
    text = v.clean_text(raw)
    label = v.plain(e.get("label", ""))
    if label and prefix_score(label, text) >= 90 and len(v.norm(text)) > len(v.norm(label)):
        text = v.clean_text(text[label_cut(text, label):])
    if not text:
        return None
    if (e.get("ocr") or {}).get("comb"):
        text = re.sub(r"[\s|\[\]]+", "", text)  # one character per printed box
    if kind == "EmailInput":
        return v.clean_email(text) or None
    if kind == "PhoneNumber":
        return v.clean_phone(text) or None
    if kind == "NumberInput":
        return v.clean_number(text) or None
    if kind == "DatePicker":
        mask = v.date_mask(e)
        parsed = v.parse_date(text, day_first=mask.lower().startswith("d"))
        return v.format_date(parsed, mask) if parsed else None
    if kind == "Dropdown":
        opt = v.match_option(text, e.get("options") or [])
        return opt.get("value") if opt else None
    if kind == "Tags":
        picked = []
        for piece in [p for p in text.replace(";", ",").split(",") if p.strip()]:
            opt = v.match_option(piece, e.get("options") or [])
            if opt and opt.get("value") not in picked:
                picked.append(opt.get("value"))
        return picked or None
    if kind == "Rating":
        n = v.clean_number(text)
        return max(0, min(5, round(float(n)))) if n else None
    if kind == "Range":
        n = v.clean_number(text)
        if not n:
            return None
        lo, hi = int(e.get("min_value", 0)), int(e.get("max_value", 100))
        return max(lo, min(hi, int(round(float(n)))))
    if kind == "TextArea":
        return "\n".join(v.clean_text(x) for x in raw.splitlines() if v.clean_text(x)) or text
    return text


def display_order(task_data):
    """Elements in the order the form shows them: column-row children right after their row."""
    by_id = {e.get("id"): e for e in task_data}
    out = []
    for e in task_data:
        if e.get("parentId"):
            continue
        out.append(e)
        out.extend(by_id[c] for c in e.get("childItems") or [] if c in by_id)
    placed = {id(e) for e in out}
    return out + [e for e in task_data if id(e) not in placed]


def value_fields(task_data):
    return [e for e in display_order(task_data) if e.get("field_name") and e.get("element") not in NO_VALUE]


class ResultRecorder:
    """Collects answer_data plus a per-field report (value, confidence, how it was found)."""

    def __init__(self):
        self.answers = {}
        self.report = []

    def record(self, e, value, conf, method):
        if value is not None and value != [] and value != "":
            self.answers[e["field_name"]] = value
        else:
            value, method = None, "none"
        display = value
        if e["element"] == "Signature" and value:
            display = "[signature image]"
        elif e["element"] in ("Checkboxes", "RadioButtons") and value is not None:
            names = {o["key"]: o.get("text", "") for o in e.get("options") or []}
            display = ", ".join(names.get(k, k) for k in value) or "(none ticked)"
        elif e["element"] == "Dropdown" and value is not None:
            display = next((o.get("text", value) for o in e.get("options") or [] if o.get("value") == value), value)
        self.report.append({
            "id": e["id"],
            "field_name": e["field_name"],
            "label": v.plain(e.get("label", "")) or e.get("text", ""),
            "element": e["element"],
            "value": display,
            "confidence": round(float(conf), 3),
            "method": method,
        })
