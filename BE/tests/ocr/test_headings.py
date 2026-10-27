"""Heading repairs and the suggested title of a template made from a document."""
from app.ocr.headings import column_texts, number_runs
from app.ocr.title import suggest_title


def _row(*texts):
    return [{"text": t} for t in texts]


def test_a_misread_run_of_day_numbers_is_renumbered():
    # what OCR made of 1..31 under "Result" on the client's IFC check sheet
    read = ["I", "2", "5", "4", "3", "7", "", "a", "a", "10", "11", "v", "15", "14", "13", "19",
            "17", "13", "13", "M", "21", "22", "25", "24", "22", "20", "27", "23", "23", "B", "51"]
    header = [[{"text": "Check point"}, {"text": "Result", "colspan": 31}] + [{"covered": True}] * 30,
              [{"covered": True}] + _row(*read)]
    number_runs(header)
    assert [c["text"] for c in header[1][1:]] == [str(i) for i in range(1, 32)]
    assert header[0][0]["text"] == "Check point"  # words are left as they are

    columns = column_texts([{"text": "x"}] * 32, header)
    assert (columns[0]["text"], columns[7]["text"], columns[7]["title"]) == ("Check point", "7", "Result 7")


def test_numbers_that_are_not_a_count_are_left_alone():
    sizes = _row("10", "20", "30", "40", "50", "60", "70", "80", "90")
    assert [c["text"] for c in number_runs([sizes])[0]] == ["10", "20", "30", "40", "50", "60", "70", "80", "90"]

    short = _row("1", "2", "3", "5", "5")  # too short a run to tell
    assert [c["text"] for c in number_runs([short])[0]] == ["1", "2", "3", "5", "5"]

    words = _row("OK", "NG", "Yes", "No", "N/A", "OK", "NG", "Yes", "No")
    assert [c["text"] for c in number_runs([words])[0]] == ["OK", "NG", "Yes", "No", "N/A", "OK", "NG", "Yes", "No"]


def test_the_title_is_the_text_that_names_the_document():
    def text(element, content):
        return {"element": element, "content": content}

    check_sheet = [text("Header", "PART NAME"), text("Label", "Tuner Assy"),
                   text("Label", "DAILY INITIAL FLOW MANAGEMENT CONTROL ITEMS MONITORING CHECKSHEET")]
    assert suggest_title(check_sheet) == "DAILY INITIAL FLOW MANAGEMENT CONTROL ITEMS MONITORING CHECKSHEET"

    request = [text("Header", "Harman International India Pvt. Ltd."), text("Label", "Dept.:"),
               text("Label", "Document Creation / Change Request")]
    assert suggest_title(request) == "Document Creation / Change Request"

    assert suggest_title([text("Header", "DAILY CHECKLIST"), text("Label", "Document No.:- HPU/QA/DC/01")]) == "DAILY CHECKLIST"
    assert suggest_title([{"element": "TextInput", "label": "Name"}]) is None
