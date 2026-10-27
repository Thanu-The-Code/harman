from app.ocr.shapes import detect

from .synthetic import draw_form


def test_detects_form_structure():
    s = detect(draw_form())
    assert len(s["boxes"]) == 2  # email box, address box
    assert len(s["grids"]) == 1
    grid = s["grids"][0]
    assert (grid["n_rows"], grid["n_cols"]) == (3, 3)
    assert len(s["hlines"]) == 4  # name, dob, phone, signature
    ticks = [t for t in s["checkboxes"] if t["kind"] == "checkbox"]
    assert len(ticks) == 2
    assert all(t["fill"] < 0.1 for t in ticks)


def test_tick_is_seen_as_filled():
    s = detect(draw_form(filled=True))
    fills = sorted(t["fill"] for t in s["checkboxes"] if t["kind"] == "checkbox")
    assert len(fills) == 2
    assert fills[0] < 0.1 <= fills[1]
