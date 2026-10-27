import json
from types import SimpleNamespace

from PyPDF2 import PdfReader

from app.services import evidence_service


class _Database:
    def add(self, _item):
        pass

    def commit(self):
        pass

    def refresh(self, _item):
        pass


def test_generated_sheet_uses_filled_excel_grid_and_landscape_page(tmp_path, monkeypatch):
    excel = {
        "rows": 2,
        "cols": 12,
        "columnWidths": [100, *([48] * 11)],
        "rowHeights": [30, 50],
        "metaRows": [{"label": "PART NO.", "value": "AX-42"}],
        "cells": {
            "0:0": {
                "value": "Inspection result",
                "colSpan": 12,
                "rowSpan": 1,
                "style": {"bold": True, "align": "center", "background": "#dbeafe"},
            },
            "1:0": {"value": "Diameter", "style": {"bold": True}},
            "1:1": {"value": "24.9 mm", "style": {"align": "center"}},
        },
    }
    layout = [{
        "element": "CustomElement",
        "key": "TableGrid",
        "field_name": "table_grid",
        "label": "Inspection Sheet",
        "layoutType": "excel",
        "excel": {**excel, "cells": {**excel["cells"], "1:1": {
            "value": "",
            "style": {"align": "center"},
        }}},
    }]
    filled_excel = {
        **excel,
        "cells": {
            **excel["cells"],
            "1:1": {"value": "25.02 mm", "style": {"align": "center"}},
        },
    }
    record = SimpleNamespace(
        number="REC-2026-001",
        format=SimpleNamespace(
            layout=json.dumps(layout),
            title="Inspection Form",
            code="QF-001",
        ),
        format_revision="01",
        period_label="September 2026",
        values=[SimpleNamespace(
            id="value-1",
            label="Inspection Sheet",
            value=json.dumps({"excel": filled_excel, "columns": [], "rows": []}),
        )],
    )
    monkeypatch.setattr(
        evidence_service,
        "get_settings",
        lambda _db=None: SimpleNamespace(storage_folder=str(tmp_path)),
    )

    document = evidence_service.generated_sheet(_Database(), record)
    pdf = PdfReader(document.file_path)
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    assert "PART NO." in text
    assert "AX-42" in text
    assert "Inspection result" in text
    assert "Diameter" in text
    assert "25.02 mm" in text
    assert "&nbsp;" not in text
    assert pdf.pages[0].mediabox.width > pdf.pages[0].mediabox.height