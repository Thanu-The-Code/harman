# Document digitisation (`app/ocr`)

Turns an **Excel workbook, PDF or image** of a form into template elements for the Template Builder's
designer, fills an existing form from a filled copy (any of those formats), or digitises a document as-is.
PDFs and images are read with PaddleOCR; Excel files are read directly, and a filled form can be saved back
into its Excel workbook.

Formerly a separate service (`Template_OCR/ocr-backend`); now part of the backend: the HTTP side is
`app/routers/ocr.py`, under `/api/ocr/*` and signed in (turning a document into a template needs
template-management rights). The designer's Upload File uses `POST /api/ocr/template`.

## Setup

Excel needs only `requirements.txt`. For PDFs and images, also install the OCR extra:

```powershell
.venv\Scripts\pip install -r requirements-ocr.txt
```

The first scan downloads the PP-OCRv5 mobile models (~20 MB) to `%USERPROFILE%\.paddlex` (`~/.paddlex`).
Without the extra, `GET /api/ocr/formats` lists Excel only and says why.

## API

| Endpoint | Input (multipart) | Output |
| --- | --- | --- |
| `GET /api/ocr/health` | - | enabled formats, engine settings, `ready` once models are loaded |
| `GET /api/ocr/formats` | - | enabled formats with extensions, MIME types and capabilities (the UI builds its file chooser from this) |
| `POST /api/ocr/digitize` | `file` | `{pages, text}`: text, tick boxes, tables with positions; page images (none for Excel) |
| `POST /api/ocr/template` | `file` | `{task_data, stats, document}`: builder elements |
| `POST /api/ocr/extract` | `file`, `form` (task_data JSON) | `{answers, fields, alignment, document}`: `answers` is `answer_data` for `ReactFormGenerator`; `fields` lists each field's value, confidence and how it was found (`cell`, `zone`, `label`) |
| `POST /api/ocr/read-form` | `file` | `{task_data, stats, answers, fields, document}`: a **filled-in** document as an editable form plus the values read from it, in one pass (the library's Digitize view) |
| `POST /api/ocr/export` | `file`, `form` (task_data JSON), `answers` (answer_data JSON, `{name: value}` or `[{name, value}]`) | `{filename, media_type, data (base64), written, skipped}`: that document with the values written in (Excel) |

Errors: `400` unreadable/empty file, `413` over 25 MB, `415` file type not enabled or lacking the capability.

## Architecture

```
routers/ocr.py              HTTP only (app/routers): resolves every upload through the registry
app/ocr/formats/
  base.py                   UploadedFile; FormatHandler (identity + sniffing) and the capability
                            interfaces TemplateBuilder / ValueExtractor / Digitizer / FormReader /
                            FormExporter
  registry.py               FormatRegistry: register / unregister / resolve(file, capability)
  __init__.py               AVAILABLE handlers, build_registry() (DOC_FORMATS switches formats on/off)
  raster.py                 RasterHandler (OCR pipeline) -> PdfHandler, ImageHandler
  excel/                    ExcelHandler: workbook.py (xlsx/xls readers), package.py (pictures, Form
                            Controls, Excel 2010+ validation straight from the zip), layout.py (sheet ->
                            grid with page geometry, input styling), choices.py (typed tick boxes),
                            fill.py (values from a filled workbook), writer.py (values back into one)
app/ocr/cellgrid.py             format-neutral ruled-form model (cells with row/col spans)
app/ocr/grid_interpreter.py     CellGrid -> fields, sections, multi-row tables (shared by Excel and OCR)
app/ocr/template.py             OCR page layout -> items; assemble() items -> task_data (shared)
app/ocr/extract.py              fill from OCR'd pages (positions, labels, per-cell reading)
app/ocr/cells.py                read one ruled cell: crop, erase its borders, OCR it or classify a tick/cross
app/ocr/results.py, tables.py   shared value typing, answer reporting, table helpers
```

SOLID in practice:

- **Single responsibility**: reading files, interpreting grids, assembling elements, reading values and
  HTTP are separate modules.
- **Open/closed**: a new format is a new `FormatHandler` subclass plus one `AVAILABLE` entry; nothing else
  changes. The UI picks it up from `/api/ocr/formats`.
- **Liskov**: every handler returns the same result shapes, so callers never special-case a format.
- **Interface segregation**: a handler implements only the capabilities it supports (e.g. a text-only
  format could implement just `Digitizer`); the registry refuses other requests with `415`.
- **Dependency inversion**: the API depends on the registry and interfaces; OCR engines are injected into
  raster handlers (`PdfHandler(recognize=...)`).

### Adding or removing a format

```python
# app/ocr/formats/word.py
class WordHandler(FormatHandler, Digitizer):
    key, label, extensions = "word", "Word", (".docx",)
    def sniff(self, data): ...
    def digitize(self, file): ...

# app/ocr/formats/__init__.py
AVAILABLE = {..., "word": WordHandler}
```

Switch formats without code changes: `DOC_FORMATS=pdf,image` (Excel off), `DOC_FORMATS=excel` (no OCR models
are loaded at all), default `pdf,image,excel`.

## How it works

**Excel** (`.xlsx`, `.xlsm`, `.xls`): cell text with number formats applied (`1` with `0%` reads `100%`),
merged ranges, borders, fonts, hidden rows/columns (dropped), print area, and embedded pictures (logos)
are read. Neighbouring cells with no border between them become one box, as on paper. The grid goes
through the shared `GridInterpreter`. Every element remembers its source cell (`excel.cell` /
`excel.cells`), so a filled copy of the workbook is read exactly; column widths/row heights give each
element page positions too, so the same template can be filled from a scanned print-out.

**Which Excel cells are inputs, and what kind**: a cell is a place to fill in when it is drawn as a box
(borders) or styled as one: a background fill (not the sheet's general background colour), unlocked for
editing (when the labels are locked), or restricted by data validation. Data validation sets the input
type: a list becomes a **Dropdown** with its entries (inline, a range on a hidden sheet, a named range, or
Excel 2010+ cross-sheet lists), date/number rules a **DatePicker**/**NumberInput**; an empty cell's number
format refines a plain text input (dates, numbers). Tick boxes become **Checkboxes**/**RadioButtons**: typed
(`☐ Yes ☐ No`, `[ ] Yes`, a lone `☐` next to its caption, `○` for one-of) and Excel **Form Controls**
(check boxes, option buttons; ticked state from the control or its linked cell). Table cells get `check` /
`date` / `number` input types the same way. Formula cells are shown, never offered as inputs.

**Saving back to Excel** (`/api/ocr/export`): values go into the cells the template remembered (or, for a form
drawn in the builder or made from a scan, the cells found by labels and table headings). Only those cells,
tick boxes (glyphs, Form Controls and their linked cells) and the "recalculate formulas on open" flag change:
an `.xlsx`/`.xlsm` is edited part by part inside its zip, so formatting, logos, drop-down lists, Form
Controls, macros and formulas stay exactly as they were. Dates go into date-formatted cells as real dates;
formula cells are never overwritten. A `.xls` is written back as `.xls` (xlutils), keeping cell formatting.

**PDF / image**: pages are rendered at 200 dpi, straightened (projection-profile deskew), ruling lines,
boxes, grids and tick boxes are found with OpenCV, text with PaddleOCR. Ruled areas become a `CellGrid` and
go through the same `GridInterpreter`; free text, underlines, `____` blanks and `Label:` lines are handled
around it.

**Grid interpretation** (both routes): a heading row (optionally continued, e.g. "DATE" over 1..31) above
rows with blank cells is a **table**, with merged cells kept as row/col spans; labels next to blanks are
**fields** ("Revision Number: | OLD: | [ ]" gives "Revision Number OLD"); "Work Station : IQC" cells are
inline fields (document-control text such as "Document No.:- ..." stays static); wide single texts are
sections; the most prominent top text is the header.

**Filling from a scan**: the scan is aligned to the template by matching label text; tables are found by
their column headings; each ruled cell is then read **from its own crop** with its borders erased (page-level
OCR merges text across narrow neighbouring cells). Cells holding only a hand-drawn mark read as `✓` / `✗`.

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `DOC_FORMATS` | `pdf,image,excel` | enabled document formats |
| `OCR_DET_MODEL` | `PP-OCRv5_mobile_det` | `PP-OCRv5_server_det` is more accurate, ~3x slower on CPU |
| `OCR_REC_MODEL` | `en_PP-OCRv5_mobile_rec` | |
| `OCR_DEVICE` | `cpu` | `gpu:0` needs `paddlepaddle-gpu` instead of `paddlepaddle` |
| `OCR_MKLDNN` | `1` | oneDNN CPU acceleration |

Speed on this machine (CPU): Excel < 1 s; A4 scan ~6 s/page; dense A3 check sheets 20-40 s/page (OCR time
grows with the number of text lines; a GPU is the remedy). `paddlepaddle` is pinned to 3.1.1 because 3.2+
crashes with oneDNN on Windows.

## Tests

```powershell
.venv\Scripts\python -m pytest -q tests/ocr                     # Excel, registry, HTTP (seconds)
$env:RUN_OCR_TESTS = "1"; .venv\Scripts\python -m pytest -q tests/ocr   # also PaddleOCR on whole scans (~5 min)
.venv\Scripts\python -m tests.ocr.eval_e2e                      # HTTP evaluation over 7 scan conditions (server running)
```

- `test_formats.py`: registry routing, enabling/disabling formats, capabilities, HTTP errors.
- `test_excel.py`: the client workbooks in `tests/ocr/samples/client`: template structure, filling from filled copies by
  cell address and by labels only (`.xlsx` and `.xls`).
- `test_excel_inputs.py`: inputs marked by validation, number formats, shading, unlocking, typed tick boxes,
  Form Controls and formulas (`tests/excel_forms.py` builds the workbook), plus guards (background colour,
  everything unlocked, decorative strips, formatting dragged down 30,000 rows).
- `test_excel_export.py`: saving values back: round trips (synthetic and client workbooks, `.xlsx`/`.xls`),
  only touched parts change, Form Controls ticked/unticked, label-only templates, the endpoint.
- `test_hardening.py`: zip bombs and oversized sheets are refused; a slow document does not block other requests.
- `test_client_scans.py`: the client PDFs: templates match the Excel structure; filling from scans with
  handwriting drawn in; an Excel-built template filled from a scan.
- `test_pipeline.py`, `test_corpus.py`: synthetic forms (`tests/synthetic.py`, `tests/corpus.py`).

`samples/` holds filled copies to try in the UI (`filled_daily_check_sheet.xlsx`,
`filled_change_request.xls`, `filled_daily_check_sheet_scan.jpg`, and the synthetic forms), plus
`employee_onboarding_form.xlsx` / `filled_employee_onboarding_form.xlsx` (drop-downs, shaded inputs,
tick boxes, Form Controls).

## Limits

- Tuned for printed forms in English. Handwriting is read with lower accuracy (an occasional digit slip in
  narrow cells, e.g. 1050 -> 1051); every value carries a confidence and is reviewed before it is used.
- Ruled tables only (borderless tables come out as text). Tick boxes must be printed squares/circles.
- Fields whose labels repeat on the form ("Sign", "Sign") can only be told apart by position, so fill
  those forms with a template made from the same layout.
- Excel shapes (drawn ticks, arrows) are not read; pictures are (PNG/JPEG/GIF/BMP; EMF/WMF logos are
  skipped because browsers cannot show them). Form Control drop-downs (combo boxes) are not read; data
  validation drop-downs are.
- `.xls`: Form Controls, data validation and pictures are not readable (xlrd), and a filled `.xls` written
  back loses its pictures. Formulas in `.xls` are read as their last calculated values.
- Uploads: 25 MB; an `.xlsx` may expand to at most 300 MB and hold at most 1,000,000 stored cells.
- Template input types are guesses from label wording; adjust them in the builder.
