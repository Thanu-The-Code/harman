"""One paper form, whichever way it arrives (scan, PDF, workbook), becomes the same template."""
import pytest

from app.ocr.elements import static_element
from app.ocr.formats import UploadedFile, build_registry
from app.ocr.tables import normalize_legend
from app.ocr.title import lead_with_title
from app.ocr.values import plain

from . import client_samples as cs

needs_samples = pytest.mark.skipif(not cs.available(), reason="client samples (tests/ocr/samples/client) not present")


def _excel(key):
    ext = cs.EXCEL_EXT[key]
    return build_registry("excel").get("excel").build_template(UploadedFile(cs.read(key, ext), "x" + ext))["task_data"]


@needs_samples
def test_a_label_running_over_the_empty_cell_beside_it_is_one_label():
    # "Requester Sign:" in a narrow column A covers B26 on paper; B26 is not a second box
    labels = [plain(e["label"]) for e in _excel("change") if e["element"] in ("Signature", "TextInput", "DatePicker")]
    assert "Requester Sign (2)" not in labels
    assert {"Revision Number OLD", "Revision Number NEW"} <= set(labels)
    assert labels.count("Date of Revision") == 1 and "Date of Revision (3)" not in labels


@needs_samples
def test_a_row_wholly_inside_merged_cells_is_not_a_row_of_the_form():
    table = next(e for e in _excel("ifc") if e["element"] == "Table")
    assert len(table["rows"]) == 26  # as the scan of the same sheet reads it
    assert not any(all(c.get("covered") for c in row["cells"]) for row in table["rows"])
    assert len(table["excel"]["cells"]) == len(table["rows"])  # each row still finds its cells


def test_the_title_becomes_the_heading():
    corner, title = static_element("Header", "PART NAME"), static_element("Label", "DAILY INITIAL FLOW MONITORING CHECKSHEET")
    lead_with_title([corner, title])
    assert (corner["element"], corner["bold"], title["element"]) == ("Label", True, "Header")


def test_a_heading_that_is_not_a_document_title_stays():
    header, note = static_element("Header", "Harman International"), static_element("Label", "Shift 1")
    lead_with_title([header, note])
    assert (header["element"], note["element"]) == ("Header", "Label")


def test_a_check_sheet_key_shows_the_marks_it_is_filled_with():
    assert [normalize_legend(t) for t in ("V OK", "√ OK", "× NOT OK", "x not ok")] == ["✓ OK", "✓ OK", "✗ NOT OK", "✗ NOT OK"]
    assert [normalize_legend(t) for t in ("OK", "Note: OK", "A OK")] == ["OK", "Note: OK", "A OK"]
