"""Document digitisation: turn an Excel workbook, PDF or image of a form into template
elements, and read values from a filled copy.

    formats/            one handler per document format, resolved through a registry
    template.py         page layout -> builder elements (task_data)
    grid_interpreter.py ruled grids (Excel and OCR alike) -> fields, sections, tables
    extract.py          values from a filled scan, cell by cell
    engine.py           the PaddleOCR pipeline (only loaded for PDF / image)

The HTTP side is app/routers/ocr.py (/api/ocr/*). Excel needs only requirements.txt;
PDF and image need requirements-ocr.txt.
"""
