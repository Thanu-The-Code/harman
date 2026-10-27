"""Text in columns without ruling, and fields that share a label (HPU-F-MR-04 change request)."""
from app.ocr import labels, textgrid
from app.ocr.values import clean_label

LH = 10


def _lines(*items):
    """(text, x0, y0, x1) -> line dicts one line-height tall."""
    return [{"text": t, "bbox": [x0, y0, x1, y0 + LH]} for t, x0, y0, x1 in items]


REVISION_HISTORY = _lines(
    ("Revision history", 260, 0, 340),
    ("S.No", 0, 20, 30), ("Change description", 80, 20, 200), ("Rev No", 230, 20, 270), ("Rev date", 330, 20, 380),
    ("1", 40, 35, 46), ("Initial release", 95, 35, 180), ("00", 230, 35, 245), ("01.11.2014", 330, 35, 400),
)


def test_columns_of_text_are_read_as_a_table_row_by_row():
    lines = REVISION_HISTORY
    tables = textgrid.find(range(len(lines)), lambda i: lines[i]["bbox"], LH)
    assert len(tables) == 1
    item = textgrid.table_item(tables[0], lambda i: lines[i]["bbox"], lambda i: lines[i]["text"])
    assert [c["text"] for c in item["columns"]] == ["S.No", "Change description", "Rev No", "Rev date"]
    assert item["body"] == [[{"text": "1"}, {"text": "Initial release"}, {"text": "00"}, {"text": "01.11.2014"}]]


def test_a_sentence_or_a_single_row_is_not_a_table():
    lines = _lines(
        ("Prepared by", 0, 0, 60), ("the quality", 64, 0, 120), ("team", 124, 0, 150),  # words, not columns
        ("Format No.: HPU/F/MR/04", 0, 40, 120), ("Rev No. :00", 200, 40, 260), ("Rev Date : 01.11.2014", 320, 40, 420),
    )
    assert textgrid.find(range(len(lines)), lambda i: lines[i]["bbox"], LH) == []


def _field(label, x, y, page=0):
    return {"element": "Signature", "field_name": f"signature_{x}_{y}", "label": label,
            "ocr": {"page": page, "label_bbox": [x, y, x + 0.1, y + 0.02]}}


def test_repeated_labels_are_named_after_the_field_above():
    fields = [
        _field("Requester Name", 0.0, 0.10), _field("Req.HOD Name", 0.3, 0.10), _field("Approved By (M.R.)", 0.6, 0.10),
        _field("Requester Sign", 0.0, 0.13), _field("Sign", 0.3, 0.13), _field("Sign", 0.6, 0.13),
    ]
    labels.disambiguate(fields)
    assert [f["label"] for f in fields[3:]] == ["Requester Sign", "Sign – Req.HOD Name", "Sign – Approved By (M.R.)"]


def test_repeated_labels_with_nothing_above_are_numbered():
    fields = [_field("Remarks", 0.0, 0.1), _field("Remarks", 0.0, 0.1, page=1), {"element": "Header", "static": True, "content": "Remarks"}]
    labels.disambiguate(fields)
    assert [f["label"] for f in fields[:2]] == ["Remarks", "Remarks (2)"]


def test_a_qualifier_after_the_colon_stays_with_the_label():
    assert clean_label("Approved By:\n(M.R.)") == "Approved By (M.R.)"
    assert clean_label("2. Date of Birth :-") == "Date of Birth"
