"""Combine OCR text lines and detected shapes into one page model.

A line is {"text", "conf", "bbox", "chars"} where chars is a list of
[char, x0, x1] aligned 1:1 with text, so lines can be sliced by x position.
"""
import re
from statistics import median

from . import geometry as g

BOX_GLYPHS = set("□☐☑☒✓✔✗✘口■◻◼▢[]()|")
ROUND_GLYPHS = set("oO0○◯●◉Øø")
BLANK_RE = re.compile(r"_{3,}|\.{4,}|…{2,}|-{5,}")


def make_line(text, bbox, conf, chars=None, words=None):
    text = text or ""
    if chars is None or len(chars) != len(text):
        x0, _, x1, _ = bbox
        n = max(1, len(text))
        step = (x1 - x0) / n
        chars = [[ch, x0 + i * step, x0 + (i + 1) * step] for i, ch in enumerate(text)]
    line = {"text": text, "conf": float(conf), "bbox": [float(v) for v in bbox], "chars": chars}
    if words:
        line["words"] = words  # [token, x0, x1] with OCR's own word boxes
    return line


def sub_line(line, i, j):
    """The part of a line covering text[i:j], with surrounding whitespace trimmed."""
    chars = line["chars"][i:j]
    while chars and chars[0][0].isspace():
        chars = chars[1:]
    while chars and chars[-1][0].isspace():
        chars = chars[:-1]
    if not chars:
        return None
    text = "".join(c[0] for c in chars)
    y0, y1 = line["bbox"][1], line["bbox"][3]
    return {"text": text, "conf": line["conf"], "bbox": [chars[0][1], y0, chars[-1][2], y1], "chars": chars}


def slice_x(line, x_from, x_to):
    """The part of a line whose characters are centred within [x_from, x_to)."""
    idx = [i for i, c in enumerate(line["chars"]) if x_from <= (c[1] + c[2]) / 2 < x_to]
    if not idx:
        return None
    return sub_line(line, idx[0], idx[-1] + 1)


def _strip_glyphs(segment, left_cut, right_cut):
    """Drop box-like characters OCR produced for a checkbox next to this segment."""
    if segment is None:
        return None
    text = segment["text"]
    i, j = 0, len(text)
    if left_cut:
        while i < j and (text[i] in BOX_GLYPHS or text[i].isspace()):
            i += 1
        if i + 1 < j and text[i] in ROUND_GLYPHS and text[i + 1].isspace():
            i += 2
    if right_cut:
        while j > i and (text[j - 1] in BOX_GLYPHS or text[j - 1].isspace()):
            j -= 1
        if j - 2 > i and text[j - 1] in ROUND_GLYPHS and text[j - 2].isspace():
            j -= 2
    if i == 0 and j == len(text):
        return segment
    return sub_line(segment, i, j)


def _single_char_is_box(t, kind):
    return t in BOX_GLYPHS or t in ROUND_GLYPHS or (kind == "checkbox" and t in "DQ")


def _reads_as_letter(line, bbox, kind):
    """True when OCR read the shape at bbox as part of a word (the 'o' in 'of', 'O' in 'FORM', '%')."""
    words = line.get("words")
    if words:
        cx = (bbox[0] + bbox[2]) / 2
        for token, x0, x1 in words:
            t = token.strip()
            if not t or not x0 <= cx <= x1:
                continue
            if all(c in BOX_GLYPHS for c in t):
                return False
            if len(t) == 1:
                return not _single_char_is_box(t, kind)
            # A box glyph fused onto the option text ("□Male", "OSavings") sits at the word's left
            # edge. A round glyph only counts before a Title-case word, so "of" / "OCCUPATION" stay text.
            char_w = (x1 - x0) / len(t)
            fused = t[0] in BOX_GLYPHS and not (t[0].isascii() and t[0].isalnum())
            fused = fused or (t[0] in ROUND_GLYPHS and len(t) >= 3 and t[1].isupper() and any(c.islower() for c in t[2:]))
            return not (fused and bbox[0] <= x0 + 0.5 * char_w)
        return False  # between words: a drawn shape OCR did not read as text
    chars = line["chars"]
    idx = [i for i, c in enumerate(chars) if bbox[0] - 1 <= (c[1] + c[2]) / 2 <= bbox[2] + 1 and not c[0].isspace()]
    if not idx:
        return False
    over = [chars[i][0] for i in idx]
    if all(c in BOX_GLYPHS for c in over):
        return False  # OCR saw the box itself ("□Female")
    before = chars[idx[0] - 1][0] if idx[0] > 0 else " "
    after = chars[idx[-1] + 1][0] if idx[-1] + 1 < len(chars) else " "
    standalone = not before.isalnum() and not after.isalnum()
    return not (standalone and len(over) == 1 and _single_char_is_box(over[0], kind))


def filter_ticks(ticks, lines):
    """Drop tick-box candidates that OCR actually read as letters (e.g. an 'o' or 'D')."""
    kept = []
    for t in ticks:
        b = t["bbox"]
        is_text = False
        for line in lines:
            inter = g.intersection(b, line["bbox"])
            if inter and g.area(inter) >= 0.3 * g.area(b) and _reads_as_letter(line, b, t["kind"]):
                is_text = True
                break
        if not is_text:
            kept.append(t)
    return kept


def split_at_ticks(lines, ticks):
    out = []
    for line in lines:
        cuts = sorted(
            t["bbox"] for t in ticks
            if g.v_overlap(t["bbox"], line["bbox"]) >= 0.4 and t["bbox"][0] < line["bbox"][2] and t["bbox"][2] > line["bbox"][0]
        )
        if not cuts:
            out.append(line)
            continue
        groups = {}
        for i, c in enumerate(line["chars"]):
            xc = (c[1] + c[2]) / 2
            if any(cut[0] - 2 <= xc <= cut[2] + 2 for cut in cuts):
                continue
            slot = sum(1 for cut in cuts if cut[2] <= xc)
            groups.setdefault(slot, []).append(i)
        for slot, idx in sorted(groups.items()):
            seg = sub_line(line, idx[0], idx[-1] + 1)
            seg = _strip_glyphs(seg, left_cut=slot > 0, right_cut=slot < len(cuts))
            if seg and seg["text"].strip():
                out.append(seg)
    return out


def split_blanks(lines):
    """Turn 'Name: ________' into a label line plus a blank (write-in) region."""
    out, blanks = [], []
    for line in lines:
        matches = list(BLANK_RE.finditer(line["text"]))
        if not matches:
            out.append(line)
            continue
        pos = 0
        for m in matches:
            seg = sub_line(line, pos, m.start())
            if seg:
                out.append(seg)
            b = line["chars"][m.start():m.end()]
            blanks.append({"bbox": [b[0][1], line["bbox"][1], b[-1][2], line["bbox"][3]]})
            pos = m.end()
        seg = sub_line(line, pos, len(line["text"]))
        if seg:
            out.append(seg)
    return out, blanks


def build_page(ocr_lines, shapes):
    lines = [l for l in ocr_lines if l["text"].strip()]
    ticks = filter_ticks(shapes["checkboxes"], lines)
    lines = split_at_ticks(lines, ticks)
    lines, blanks = split_blanks(lines)
    lines = [l for l in lines if l["text"].strip(" :;,.-_|")]
    heights = [g.height(l["bbox"]) for l in lines]
    line_height = median(heights) if heights else 0.012 * shapes["height"]
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    return {
        "width": shapes["width"],
        "height": shapes["height"],
        "line_height": float(line_height),
        "lines": lines,
        "checkboxes": ticks,
        "boxes": shapes["boxes"],
        "grids": shapes["grids"],
        "hlines": shapes["hlines"],
        "blanks": blanks,
        "binary": shapes.get("binary"),
    }


def page_text(page):
    """Plain text of a page in reading order (rows top-to-bottom, left-to-right)."""
    rows = []
    for line in sorted(page["lines"], key=lambda l: (l["bbox"][1], l["bbox"][0])):
        for row in rows:
            if g.v_overlap(row[0]["bbox"], line["bbox"]) >= 0.5:
                row.append(line)
                break
        else:
            rows.append([line])
    return "\n".join("    ".join(l["text"] for l in sorted(r, key=lambda l: l["bbox"][0])) for r in rows)
