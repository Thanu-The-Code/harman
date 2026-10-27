from app.ocr.cellgrid import CellGrid, GridCell
from app.ocr.grid_interpreter import GridInterpreter


def test_full_ruled_grid_keeps_metadata_and_data_in_one_table():
    cells = [
        GridCell(row=0, col=0, colspan=3, text="Inspection form title"),
        GridCell(row=1, col=0, text="PART NAME"),
        GridCell(row=1, col=1, text="PART NO."),
        GridCell(row=1, col=2, text="DATE"),
        GridCell(row=2, col=0, text="Tuner Assy"),
        GridCell(row=2, col=1),
        GridCell(row=2, col=2),
    ]

    items = GridInterpreter(CellGrid(cells, n_rows=3, n_cols=3)).interpret()

    assert len(items) == 1
    table = items[0]
    assert table["kind"] == "table"
    assert table["header"] == []
    assert len(table["body"]) == 3
    assert table["body"][0][0] == {"text": "Inspection form title", "colspan": 3}
    assert table["body"][1][0]["text"] == "PART NAME"
    assert table["body"][2][1] == {"input": "text"}
