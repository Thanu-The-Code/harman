"""Excel workbooks (.xlsx, .xlsm, .xls): exact cell structure, no OCR needed."""
from ... import textgrid
from ...grid_interpreter import GridInterpreter
from ...template import assemble
import os

from ..base import Digitizer, FormatHandler, FormExporter, FormReader, TemplateBuilder, ValueExtractor
from .fill import ExcelFiller
from .layout import SheetLayout
from .workbook import is_xls, is_xlsx, read_workbook
from .writer import write_workbook

MEDIA_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
}


class ExcelHandler(FormatHandler, TemplateBuilder, ValueExtractor, Digitizer, FormReader, FormExporter):
    key = "excel"
    label = "Excel"
    extensions = (".xlsx", ".xlsm", ".xls")
    mime_types = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroEnabled.12",
        "application/vnd.ms-excel",
    )

    def sniff(self, data):
        return is_xlsx(data) or is_xls(data)

    @staticmethod
    def _layouts(file):
        layouts = [SheetLayout(sh) for sh in read_workbook(file.data)]
        # Workbooks often contain a small lookup sheet or an accidental second sheet.
        # Do not turn those auxiliary cells into an extra page in the form designer.
        return [
            layout for layout in layouts
            if any(cell.boxed or cell.image for cell in layout.grid().cells)
        ]

    @staticmethod
    def _document(layouts):
        pages = [layout.document_page(i) for i, layout in enumerate(layouts)]
        return {"pages": pages, "text": "\n\n".join(p["text"] for p in pages)}

    @staticmethod
    def _template(layouts, filled=False):
        pages = []
        for layout in layouts:
            if not layout.grid().cells:
                continue
            interpreter = GridInterpreter(layout.grid(), text_size=layout.text_size, filled=filled)
            grid = layout.grid()
            # Excel is already a positioned grid. Keeping the complete sheet as one table
            # prevents irregular forms from being reflowed into unrelated fields/tables.
            items = [interpreter._table_item(0, 0, grid.n_rows, 0, grid.n_cols)]
            pages.append({"items": items, "width": layout.width, "height": layout.height,
                          "line_height": layout.line_height, "sheet": layout.sheet.name})
        return assemble(pages, preserve_geometry=True)

    def build_template(self, file):
        layouts = self._layouts(file)
        return {**self._template(layouts), "document": self._document(layouts)}

    def read_form(self, file):
        sheets = read_workbook(file.data)
        layouts = [SheetLayout(sh) for sh in sheets]
        template = self._template(layouts, filled=True)
        values = ExcelFiller(template["task_data"], sheets).run()
        return {**template, **values, "document": self._document(layouts)}

    def extract(self, file, task_data):
        sheets = read_workbook(file.data)
        result = ExcelFiller(task_data, sheets).run()
        return {**result, "document": self._document([SheetLayout(sh) for sh in sheets])}

    def digitize(self, file):
        return self._document(self._layouts(file))

    def export(self, file, task_data, answers):
        data, plan = write_workbook(file.data, task_data, answers)
        stem, ext = os.path.splitext(os.path.basename(file.filename or ""))
        ext = ext.lower() if ext.lower() in MEDIA_TYPES else (".xls" if is_xls(file.data) else ".xlsx")
        return {
            "filename": f"{stem or 'form'}-filled{ext}",
            "media_type": MEDIA_TYPES[ext],
            "data": data,
            "written": plan.written,
            "skipped": plan.skipped,
        }
