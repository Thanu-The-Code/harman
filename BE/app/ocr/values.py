"""Clean OCR text into values each form element accepts."""
import html
import re
from datetime import date, datetime

from rapidfuzz import fuzz

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]
DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})


def plain(label_html):
    """Labels are stored as sanitised HTML by the builder's rich-text editor."""
    return html.unescape(re.sub(r"<[^>]+>", " ", label_html or "")).replace("\xa0", " ").strip()


NUMBERING_RE = re.compile(r"^\s*\(?(\d{1,2}|[a-zA-Z]|[ivxIVX]{1,4})[.)]\s+(?=\S)")


def strip_numbering(text):
    """'2. Nominee Details' -> 'Nominee Details', 'a) Name' -> 'Name'."""
    return NUMBERING_RE.sub("", text or "", count=1)


def clean_label(text):
    """'2. Date of Birth :-' -> 'Date of Birth'; 'Approved By: (M.R.)' -> 'Approved By (M.R.)'."""
    text = re.sub(r"\s+", " ", strip_numbering((text or "").strip()))
    text = re.sub(r"\s*[:：]\s*(?=\()", " ", text)  # a qualifier written after the colon
    return re.sub(r"[\s:：\-–_*]+$", "", text).strip()


def norm(text):
    text = plain(text).lower()
    text = re.sub(r"[^a-z0-9@.+ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text):
    text = re.sub(r"_{2,}|\.{3,}|…+", " ", text or "")
    text = re.sub(r"^[\s:：;,\-–|\"'`“”‘’]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_number(text):
    fixed = (text or "").translate(DIGIT_FIXES) if re.search(r"\d", text or "") else text or ""
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", fixed)
    return m.group(0).replace(",", "") if m else ""


def clean_phone(text):
    t = (text or "").translate(DIGIT_FIXES)
    t = re.sub(r"[^\d+\-() ]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -")
    return t if sum(ch.isdigit() for ch in t) >= 6 else ""


def clean_email(text):
    t = re.sub(r"\s+", "", text or "").strip(".,;:")
    t = t.replace("(at)", "@").replace("[at]", "@")
    m = re.search(r"[\w.+\-]+@[\w\-]+(\.[\w\-]+)+", t)
    return (m.group(0) if m else t).lower()


def _year(y):
    y = int(y)
    if y < 100:
        y += 2000 if y <= (date.today().year % 100) + 10 else 1900
    return y


def _make(y, m, d):
    year = _year(y)
    if not 1900 <= year <= 2100:
        return None  # a misread year ("202:") is better reported as unreadable than as 0202
    try:
        return date(year, int(m), int(d))
    except ValueError:
        return None


def parse_date(text, day_first=False):
    raw = (text or "").strip()
    if not raw:
        return None
    t = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", raw, flags=re.I)
    m = re.search(r"(\d{1,2})[\s\-./]*([A-Za-z]{3,9})\.?[\s\-./,]*(\d{2,4})", t)
    if m and m.group(2)[:3].lower() in MONTHS:
        return _make(m.group(3), MONTHS[m.group(2)[:3].lower()], m.group(1))
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{2,4})", t)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _make(m.group(3), MONTHS[m.group(1)[:3].lower()], m.group(2))
    digits = t.translate(DIGIT_FIXES)
    m = re.search(r"(\d{4})[\-./ ](\d{1,2})[\-./ ](\d{1,2})", digits)
    if m:
        return _make(m.group(1), m.group(2), m.group(3))
    m = re.search(r"(\d{1,2})\s*[\-./ ]\s*(\d{1,2})\s*[\-./ ]\s*(\d{2,4})", digits)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12:
            return _make(y, b, a)
        if b > 12:
            return _make(y, a, b)
        return _make(y, b, a) if day_first else _make(y, a, b)
    m = re.search(r"\b(\d{2})(\d{2})(\d{4})\b", digits)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return _make(m.group(3), b, a) if (day_first or a > 12) else _make(m.group(3), a, b)
    return None


TOKEN_RE = re.compile(r"yyyy|yy|MMMM|MMM|MM|M|dd|d|HH|H|hh|h|mm|ss|aa|a|'[^']*'")


def format_date(value, fmt):
    """Format a date/datetime using the date-fns tokens the DatePicker element uses."""
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    hour12 = value.hour % 12 or 12

    def tok(m):
        s = m.group(0)
        return {
            "yyyy": f"{value.year:04d}", "yy": f"{value.year % 100:02d}",
            "MMMM": MONTH_NAMES[value.month - 1], "MMM": MONTH_NAMES[value.month - 1][:3],
            "MM": f"{value.month:02d}", "M": str(value.month),
            "dd": f"{value.day:02d}", "d": str(value.day),
            "HH": f"{value.hour:02d}", "H": str(value.hour),
            "hh": f"{hour12:02d}", "h": str(hour12),
            "mm": f"{value.minute:02d}", "ss": f"{value.second:02d}",
            "aa": "AM" if value.hour < 12 else "PM", "a": "AM" if value.hour < 12 else "PM",
        }.get(s, s[1:-1] if s.startswith("'") else s)

    return TOKEN_RE.sub(tok, fmt)


def date_mask(element):
    """The DatePicker's formatMask (see src/form-elements/date-picker.jsx updateFormat)."""
    show_select, select_only, show_input = element.get("showTimeSelect"), element.get("showTimeSelectOnly"), element.get("showTimeInput")
    date_fmt = "" if show_select and select_only else element.get("dateFormat") or "MM/dd/yyyy"
    time_fmt = (element.get("timeFormat") or "hh:mm aa") if (show_select or show_input) else ""
    return f"{date_fmt} {time_fmt}".strip()


def match_option(text, options, threshold=70):
    """Best option for free text, or None."""
    t = norm(text)
    if not t:
        return None
    best, best_score = None, 0
    for opt in options:
        for cand in (opt.get("text"), opt.get("value")):
            c = norm(cand or "")
            if not c:
                continue
            score = 100 if c == t else fuzz.WRatio(t, c)
            if score > best_score:
                best, best_score = opt, score
    return best if best_score >= threshold else None
