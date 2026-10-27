from datetime import date

from app.ocr import values as v


def test_parse_date_formats():
    assert v.parse_date("14/03/1992") == date(1992, 3, 14)  # day > 12 decides
    assert v.parse_date("03/04/1992", day_first=True) == date(1992, 4, 3)
    assert v.parse_date("03/04/1992") == date(1992, 3, 4)
    assert v.parse_date("1992-03-14") == date(1992, 3, 14)
    assert v.parse_date("14 Mar 1992") == date(1992, 3, 14)
    assert v.parse_date("March 14, 1992") == date(1992, 3, 14)
    assert v.parse_date("l4/O3/1992") == date(1992, 3, 14)  # OCR digit confusions
    assert v.parse_date("not a date") is None


def test_format_date_uses_date_fns_tokens():
    assert v.format_date(date(1992, 3, 14), "MM/dd/yyyy") == "03/14/1992"
    assert v.format_date(date(1992, 3, 4), "d MMM yyyy") == "4 Mar 1992"


def test_date_mask_matches_datepicker():
    assert v.date_mask({"dateFormat": "MM/dd/yyyy"}) == "MM/dd/yyyy"
    assert v.date_mask({"dateFormat": "MM/dd/yyyy", "timeFormat": "hh:mm aa", "showTimeSelect": True}) == "MM/dd/yyyy hh:mm aa"


def test_cleaners():
    assert v.clean_number("Rs. 1,25,000/-") == "125000"
    assert v.clean_phone("Ph: +91 98765 43210") == "+91 98765 43210"
    assert v.clean_email("Priya.Sharma @ example.com") == "priya.sharma@example.com"
    assert v.clean_text(": ____ John  Smith") == "John Smith"
    assert v.plain("<strong>Full&nbsp;Name</strong>") == "Full Name"


def test_match_option():
    opts = [{"text": "Male", "value": "male"}, {"text": "Female", "value": "female"}]
    assert v.match_option("FEMALE", opts)["value"] == "female"
    assert v.match_option("xyz", opts) is None
