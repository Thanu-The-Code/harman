"""
Taking in the scanned sheet a record is filled from.

This is the whole of B3's hard-copy route: a Process Owner photographs the form
they filled at the end of a shift, and the page has to be stored, read, and kept
where the record can point at it.

It replaces a general-purpose capture pipeline that also asked a language model
to guess the document's title, correspondent and date, and pushed an embedding
into a vector store so the page could be found by semantic search. None of that
is in the process flow, and for a quality record none of it is wanted: the
record already knows what it is, who filled it and which period it belongs to,
because a person said so on a released format. A guess would only compete with
the truth.

What is left is deliberately small - hash, store, read - because everything that
matters about the sheet is decided afterwards, by `record_extraction` matching
what the page says against the format's own fields, and by a human confirming
each one.
"""
from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Document
from .file_utils import calculate_file_hash, get_file_info

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:  # libmagic is optional; the extension map covers us
    MAGIC_AVAILABLE = False

EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".text": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


class EvidenceError(Exception):
    """The sheet could not be taken in, with a reason worth showing somebody."""


def mime_type_of(path: Path) -> str:
    """The file's type, by content where libmagic is installed, else by name."""
    if MAGIC_AVAILABLE:
        try:
            return magic.Magic(mime=True).from_file(str(path))
        except Exception as exc:
            logger.debug(f"libmagic could not read {path.name}: {exc}")

    suffix = path.suffix.lower()
    if suffix in EXTENSION_TYPES:
        return EXTENSION_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


# A photographed or scanned sheet arrives as a picture; it is kept as a PDF of that picture,
# because the approval signatures are stamped onto the record's document - a PDF.
IMAGE_SCANS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def _unreadable_pdf(path: Path) -> Optional[str]:
    """Why this PDF cannot be a hard copy, or None.

    Checked before anything is stored: the approval signatures are stamped onto
    it, so a renamed text file, an empty file or a password-protected PDF would
    be approved and then fail to open for every reviewer.
    """
    from PyPDF2 import PdfReader
    from PyPDF2.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return "That PDF is password-protected. Scan or save it again without a password."
        if not reader.pages:
            return "That PDF has no pages."
    except (PdfReadError, ValueError, OSError, KeyError, TypeError) as exc:
        logger.info(f"{path.name} is not a readable PDF: {exc}")
        return "That file is not a readable PDF. It may be damaged, empty or a different kind of file."
    return None


def content_refusal(path: Path) -> Optional[str]:
    """Why the file itself cannot be a hard copy (an unreadable or locked PDF), or None.

    Checked on every upload, before it is matched to a document already on file:
    an earlier upload of the same bad file must not be attached for it.
    """
    return _unreadable_pdf(path) if path.suffix.lower() == ".pdf" else None


def scan_types(settings) -> list[str]:
    """
    What a record's hard copy may be: a scan or photo of the sheet, of the
    types the settings allow. Not any document type: the approval signatures
    are stamped onto the hard copy, which needs a PDF or a picture made into one.
    """
    return [ext for ext in settings.allowed_extensions_list if f".{ext}" in {".pdf"} | IMAGE_SCANS]


def scan_refusal(filename: str, settings) -> Optional[str]:
    """Why a file of this name cannot be a hard copy, or None if it can."""
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    allowed = scan_types(settings)
    if suffix not in allowed:
        return (f"A '{suffix or 'file without a type'}' file cannot be the hard copy. Attach a scan or "
                "photo of the filled sheet: " + ", ".join(allowed) + ".")
    return None


def _acceptable(path: Path, settings) -> Optional[str]:
    """Why this file cannot be taken in, or None if it can."""
    refusal = scan_refusal(path.name, settings)
    if refusal:
        return refusal
    if path.stat().st_size > settings.max_file_size_bytes:
        return "That file is too large."
    return None


def _store(path: Path, document_id: str, settings) -> Path:
    """
    Move the file to where it will live, and answer with where that is.

    Filed by the day it arrived, under the document's own id. The id prefix is
    what stops two sheets photographed on the same phone, both called
    `IMG_0042.jpg`, from overwriting one another.

    This is *not* B8. B8 is the record's filing path - team, format, year,
    month, day - which `folder_service` builds from the format's frequency and
    a person commits to when they file the record. This is only where the bytes
    sit on disk.
    """
    target = Path(settings.storage_folder) / "evidence" / datetime.now().strftime("%Y-%m-%d")
    target.mkdir(parents=True, exist_ok=True)

    destination = target / f"{document_id}_{path.name}"
    path.replace(destination)
    return destination


def _keep_structure(document: Document, structured) -> None:
    """
    Keep what the engine recovered, alongside the plain text.

    Only PaddleOCR returns real regions; the other engines return a single text
    block. Storing that costs nothing and keeps every sheet the same shape for
    whatever reads it later - which is what lets `record_extraction` work
    against one structure rather than four.
    """
    try:
        document.ocr_engine = structured.engine
        document.ocr_confidence = structured.mean_confidence
        if structured.tables or len(structured.regions) > 1:
            document.layout_json = json.dumps(structured.to_dict())
            document.structured_html = structured.html
            logger.info(
                f"{document.original_filename}: kept {len(structured.regions)} "
                f"region(s) including {len(structured.tables)} table(s)")
    except Exception as exc:  # never lose a sheet over its layout
        logger.warning(f"Could not store the recovered layout: {exc}")


def _as_pdf(path: Path) -> Path:
    """The picture as a PDF beside it: one page per frame (a multi-page TIFF), upright
    (a phone photo's EXIF rotation applied), sized from its resolution - or as an A4
    sheet when the picture does not say."""
    from PIL import Image, ImageOps, ImageSequence

    out = path.with_suffix(".pdf")
    with Image.open(path) as picture:
        pages = [ImageOps.exif_transpose(frame.copy()).convert("RGB") for frame in ImageSequence.Iterator(picture)]
        dpi = (picture.info.get("dpi") or (0, 0))[0]
    first = pages[0]
    if not dpi or dpi < 50:
        long_side_inches = 11.69  # A4
        dpi = max(first.size) / long_side_inches
    first.save(out, "PDF", resolution=float(dpi), save_all=True, append_images=pages[1:])
    return out


def ingest(db: Session, path: Path, title: str = "") -> Document:
    """
    Take in one scanned sheet and answer with the document holding it.

    Raises `EvidenceError` with something worth showing the person holding the
    scanner. The caller has already dealt with the case of a sheet that is
    somebody else's evidence, because only the caller knows which record is
    asking - so a duplicate reaching here is the same sheet arriving twice, and
    the document already on file is the right answer.
    """
    settings = get_settings(db)

    if not path.exists():
        raise EvidenceError("The scan could not be read. It may be corrupt or empty.")

    refusal = _acceptable(path, settings)
    if refusal:
        raise EvidenceError(refusal)

    # the sheet's identity is the file as it was scanned, so the same scan is still
    # recognised (and refused for a second record) after it has been turned into a PDF
    digest = calculate_file_hash(path)
    already = db.query(Document).filter(Document.file_hash == digest).first()
    if already:
        logger.info(f"{path.name} is already on file as {already.id}")
        return already

    original_name = path.name
    if path.suffix.lower() in IMAGE_SCANS:
        try:
            pdf = _as_pdf(path)
        except Exception as exc:  # an unreadable picture
            raise EvidenceError("The picture could not be read. It may be corrupt or in an unusual format.") from exc
        path.unlink(missing_ok=True)
        path = pdf

    problem = _unreadable_pdf(path)
    if problem:
        raise EvidenceError(problem)

    info = get_file_info(path)
    document = Document(
        filename=path.name,
        original_filename=original_name,
        file_hash=digest,
        file_path="",           # set once the file has been moved
        file_size=info["size"],
        mime_type=mime_type_of(path),
        title=title or path.stem,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # The hard copy is evidence, kept as it was scanned: its readings are entered on
    # screen by the Process Owner, not read off it here (the template import in
    # app/ocr is where documents are read).
    document.ocr_status = "skipped"
    document.file_path = str(_store(path, document.id, settings))
    document.processed_at = datetime.now()
    db.commit()
    db.refresh(document)
    return document


# def generated_sheet(db: Session, record) -> Document:
#     """
#     The filled form itself, as a PDF, for a record filled on screen.

#     A record filled at a terminal has no photograph behind it, and the approval
#     chain is anchored to a document - so without this a record that never
#     touched paper could not be submitted at all, which made the hard-copy route
#     compulsory. The process says the opposite: B3 allows the form to be filled
#     on paper *or* on screen.

#     So the record generates its own evidence: the readings, their limits, and
#     whether each one met them, on one page. It is deliberately plain. The
#     handsome version of this document is the record screen, which draws the
#     designed sheet and carries the signatures; this exists so the approval has
#     something to hang on and so an auditor has a file even if the product is
#     gone.
#     """
#     from io import BytesIO
#     from uuid import uuid4

#     from reportlab.lib.pagesizes import A4
#     from reportlab.lib.units import mm
#     from reportlab.pdfgen import canvas as pdf_canvas

#     fmt = record.format
#     buffer = BytesIO()
#     page = pdf_canvas.Canvas(buffer, pagesize=A4)
#     width, height = A4
#     y = height - 22 * mm

#     page.setFont("Helvetica-Bold", 13)
#     page.drawString(18 * mm, y, (fmt.title if fmt else record.number)[:70])
#     y -= 6 * mm
#     page.setFont("Helvetica", 9)
#     page.drawString(18 * mm, y, " · ".join(filter(None, [
#         f"{fmt.code} rev {record.format_revision}" if fmt else None,
#         record.period_label,
#         record.number,
#     ]))[:110])

#     y -= 4 * mm
#     page.line(18 * mm, y, width - 18 * mm, y)
#     y -= 9 * mm

#     page.setFont("Helvetica-Bold", 9)
#     for label, x in (("What was checked", 18), ("Limits", 92),
#                      ("Reading", 132), ("Verdict", 168)):
#         page.drawString(x * mm, y, label)
#     y -= 5 * mm

#     page.setFont("Helvetica", 9)
#     for value in sorted(record.values, key=lambda v: v.order_index or 0):
#         if y < 30 * mm:                      # a long form spills onto page two
#             page.showPage()
#             y = height - 22 * mm
#             page.setFont("Helvetica", 9)

#         limits = value.spec_text or ""
#         if not limits:
#             if value.spec_min is not None and value.spec_max is not None:
#                 limits = f"{value.spec_min} - {value.spec_max}"
#             elif value.spec_max is not None:
#                 limits = f"max {value.spec_max}"
#             elif value.spec_min is not None:
#                 limits = f"min {value.spec_min}"

#         verdict = ("N-ok" if value.in_spec is False
#                    else "ok" if value.in_spec is True else "")

#         page.drawString(18 * mm, y, (value.label or "")[:44])
#         page.drawString(92 * mm, y, limits[:22])
#         page.drawString(132 * mm, y,
#                         f"{value.value or '—'} {value.unit or ''}".strip()[:20])
#         page.drawString(168 * mm, y, verdict)
#         y -= 5.5 * mm

#     y -= 6 * mm
#     page.setFont("Helvetica-Oblique", 8)
#     page.drawString(18 * mm, y,
#                     "Filled on screen. No paper original exists for this record.")

#     page.showPage()
#     page.save()

#     settings = get_settings(db)
#     target = Path(settings.storage_folder) / "evidence" / "generated"
#     target.mkdir(parents=True, exist_ok=True)
#     path = target / f"{record.number}-{uuid4().hex[:8]}.pdf"
#     path.write_bytes(buffer.getvalue())

#     document = Document(
#         filename=path.name,
#         original_filename=f"{record.number}.pdf",
#         file_hash=calculate_file_hash(path),
#         file_path=str(path),
#         file_size=path.stat().st_size,
#         mime_type="application/pdf",
#         title=record.number,
#         ocr_status="skipped",
#     )
#     db.add(document)
#     db.commit()
#     db.refresh(document)
#     logger.info(f"Generated the filled form for {record.number}")
#     return document


def generated_sheet(db: Session, record) -> Document:
    """
    Generate a PDF using the saved React Form Builder layout.

    The format.layout is the source of truth:
      - Header
      - TextInput
      - TableGrid
      - other supported layout elements

    Record values are inserted into the saved layout.
    """

    from io import BytesIO
    from uuid import uuid4
    import html
    import json
    import re

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )

    fmt = record.format

    from ..services import form_layout as layouts

    layout = layouts.parse(fmt.layout) if fmt and fmt.layout else []
    has_wide_excel_grid = any(
        isinstance(item, dict)
        and (
            item.get("key") == "TableGrid"
            or item.get("field_name") == "table_grid"
            or item.get("element") == "CustomElement"
            or item.get("table_grid")
        )
        and (
            (item.get("excel") or item.get("table_grid", {}).get("excel") or {}).get("cols", 0) > 10
        )
        for item in layout
    )
    page_size = landscape(A3) if has_wide_excel_grid else A4

    # ---------------------------------------------------------
    # BASIC PDF SETUP
    # ---------------------------------------------------------

    buffer = BytesIO()

    settings = get_settings(db)

    target = (
        Path(settings.storage_folder)
        / "evidence"
        / "generated"
    )

    target.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        target
        / f"{record.number}-{uuid4().hex[:8]}.pdf"
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=page_size,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "PaperlessTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )

    subtitle_style = ParagraphStyle(
        "PaperlessSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=4 * mm,
    )

    header_style = ParagraphStyle(
        "PaperlessHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )

    label_style = ParagraphStyle(
        "PaperlessLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
    )

    value_style = ParagraphStyle(
        "PaperlessValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )

    normal_style = ParagraphStyle(
        "PaperlessNormal",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
    )

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    def clean_html(value):
        """
        Convert builder HTML such as:

            <strong>TESTER NAME</strong>

        into:

            TESTER NAME
        """

        if value is None:
            return ""

        value = str(value)

        value = html.unescape(value)

        value = re.sub(
            r"<br\s*/?>",
            "\n",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"</p\s*>",
            "\n",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"<[^>]+>",
            "",
            value,
        )

        return value.strip()

    def paragraph_text(value, style=normal_style):
        text = clean_html(value)

        if not text:
            text = " "

        text = html.escape(text)
        text = text.replace("\n", "<br/>")

        return Paragraph(
            text,
            style,
        )

    def value_for_layout_item(item):
        """
        Find the saved RecordFieldValue belonging to a layout item.
        """

        item_id = str(
            item.get("id")
            or ""
        )

        field_name = str(
            item.get("field_name")
            or ""
        )

        label = clean_html(
            item.get("label")
            or item.get("text")
            or item.get("name")
            or ""
        )

        candidates = []

        for value in record.values:
            candidates.append(value)

            value_label = clean_html(
                getattr(value, "label", "")
                or ""
            )

            if field_name and value_label == field_name:
                return value

            if label and value_label == label:
                return value

        # Last fallback: compare IDs if the model exposes one.
        for value in candidates:
            value_id = str(
                getattr(value, "id", "")
                or ""
            )

            if item_id and value_id == item_id:
                return value

        return None

    def get_value(item):
        value = value_for_layout_item(item)

        if value is None:
            return ""

        return (
            getattr(value, "value", None)
            or ""
        )

    def get_table_value(item):
        """
        Get saved TableGrid JSON from RecordValue.value.
        """

        item_id = str(item.get("id") or "")
        field_name = str(item.get("field_name") or "")
        custom_name = str(item.get("custom_name") or "")
        item_name = clean_html(
            item.get("label")
            or item.get("name")
            or ""
        )

        for value in record.values:

            value_id = str(
                getattr(value, "id", "") or ""
            )

            value_label = clean_html(
                getattr(value, "label", "") or ""
            )

            value_name = clean_html(
                getattr(value, "name", "") or ""
            )

            value_custom_name = clean_html(
                getattr(value, "custom_name", "") or ""
            )

            # Match by label/name/custom_name/field id
            matched = (
                (item_id and value_id == item_id)
                or (field_name and value_label == field_name)
                or (custom_name and value_label == custom_name)
                or (item_name and value_label == item_name)
                or (item_name and value_name == item_name)
                or (item_name and value_custom_name == item_name)
            )

            if not matched:
                continue

            raw = getattr(value, "value", None)

            if not raw:
                return None

            if isinstance(raw, dict):
                return raw

            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)

                    if isinstance(parsed, dict):
                        return parsed

                except Exception:
                    return None

        return None

    # ---------------------------------------------------------
    # LOAD SAVED BUILDER LAYOUT
    # ---------------------------------------------------------

    # Make sure layout is always a list.
    if not isinstance(layout, list):
        layout = []

    story = []

    # ---------------------------------------------------------
    # PDF HEADER
    # ---------------------------------------------------------

    if fmt:

        story.append(
            Paragraph(
                clean_html(
                    fmt.title
                    or record.number
                ),
                title_style,
            )
        )

        meta_parts = []

        if fmt.code:
            meta_parts.append(
                f"{fmt.code} rev {record.format_revision}"
            )

        if record.period_label:
            meta_parts.append(
                record.period_label
            )

        if record.number:
            meta_parts.append(
                record.number
            )

        if meta_parts:
            story.append(
                Paragraph(
                    html.escape(
                        " · ".join(meta_parts)
                    ),
                    subtitle_style,
                )
            )

        story.append(
            Spacer(
                1,
                2 * mm,
            )
        )

    # ---------------------------------------------------------
    # RENDER EACH BUILDER ELEMENT
    # ---------------------------------------------------------

    for item in layout:

        if not isinstance(item, dict):
            continue

        element = (
            item.get("element")
            or item.get("type")
            or ""
        )

        element_lower = str(
            element
        ).lower()

        # =====================================================
        # HEADER
        # =====================================================

        if element_lower == "header":

            content = (
                item.get("content")
                or item.get("text")
                or ""
            )

            text = clean_html(
                content
            )

            if text:
                story.append(
                    Paragraph(
                        html.escape(text),
                        header_style,
                    )
                )

                story.append(
                    Spacer(
                        1,
                        2 * mm,
                    )
                )

            continue

        # =====================================================
        # LABEL
        # =====================================================

        if element_lower in (
            "label",
            "paragraph",
        ):

            text = (
                item.get("content")
                or item.get("text")
                or item.get("label")
                or ""
            )

            if text:
                story.append(
                    paragraph_text(
                        text,
                        label_style,
                    )
                )

                story.append(
                    Spacer(
                        1,
                        2 * mm,
                    )
                )

            continue

        # =====================================================
        # TABLE GRID
        # =====================================================

        is_table_grid = (
            item.get("key") == "TableGrid"
            or item.get("field_name") == "table_grid"
            or str(item.get("field_name", "")).startswith("table_grid")
            or item.get("type") == "table_grid"
            or item.get("element") == "CustomElement"
            or bool(item.get("table_grid"))
        )

        if is_table_grid:

            table_definition = (
                item.get("table_grid")
                or {}
            )

            excel = (
                item.get("excel")
                or table_definition.get("excel")
                or {}
            )

            table_value = get_table_value(item)
            if table_value and isinstance(table_value.get("excel"), dict):
                excel = table_value["excel"]

            if (
                str(item.get("layoutType") or table_definition.get("layoutType") or "").lower()
                == "excel"
                and excel.get("rows")
                and excel.get("cols")
            ):
                excel_rows = max(1, int(excel.get("rows", 1)))
                excel_cols = max(1, int(excel.get("cols", 1)))
                excel_cells = excel.get("cells") or {}

                def cell_at(row_index, column_index):
                    return excel_cells.get(f"{row_index}:{column_index}") or {}

                meta_rows = excel.get("metaRows") or []
                if meta_rows:
                    meta_data = []
                    for meta in meta_rows:
                        if not isinstance(meta, dict):
                            continue
                        meta_data.append([
                            paragraph_text(meta.get("label", ""), label_style),
                            paragraph_text(meta.get("value", ""), value_style),
                        ])
                    if meta_data:
                        meta_table = Table(
                            meta_data,
                            colWidths=[35 * mm, page_size[0] - 30 * mm - 35 * mm],
                            hAlign="LEFT",
                        )
                        meta_table.setStyle(TableStyle([
                            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#7A8490")),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F6F8")),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ]))
                        story.extend([meta_table, Spacer(1, 3 * mm)])

                grid_data = []
                spans = []
                cell_styles = []
                for row_index in range(excel_rows):
                    pdf_row = []
                    for column_index in range(excel_cols):
                        cell = cell_at(row_index, column_index)
                        if cell.get("coveredBy"):
                            pdf_row.append("")
                            continue

                        style_data = cell.get("style") or {}
                        alignment = str(style_data.get("align", "left")).lower()
                        paragraph_alignment = {
                            "center": TA_CENTER,
                            "right": 2,
                        }.get(alignment, TA_LEFT)
                        cell_style = ParagraphStyle(
                            f"ExcelCell{row_index}_{column_index}",
                            parent=value_style,
                            fontName="Helvetica-Bold" if style_data.get("bold") else "Helvetica",
                            alignment=paragraph_alignment,
                        )
                        pdf_row.append(paragraph_text(cell.get("value", ""), cell_style))

                        row_span = max(1, int(cell.get("rowSpan", 1) or 1))
                        col_span = max(1, int(cell.get("colSpan", 1) or 1))
                        if row_span > 1 or col_span > 1:
                            spans.append((
                                (column_index, row_index),
                                (min(excel_cols - 1, column_index + col_span - 1),
                                 min(excel_rows - 1, row_index + row_span - 1)),
                            ))

                        background = style_data.get("background")
                        if background:
                            try:
                                cell_styles.append((
                                    "BACKGROUND",
                                    (column_index, row_index),
                                    (column_index, row_index),
                                    colors.HexColor(str(background)),
                                ))
                            except (ValueError, TypeError):
                                pass
                        vertical = str(style_data.get("verticalAlign", "middle")).upper()
                        cell_styles.append((
                            "VALIGN",
                            (column_index, row_index),
                            (column_index, row_index),
                            vertical if vertical in {"TOP", "MIDDLE", "BOTTOM"} else "MIDDLE",
                        ))
                    grid_data.append(pdf_row)

                available_width = page_size[0] - 30 * mm
                raw_widths = excel.get("columnWidths") or []
                widths = [
                    max(1, float(raw_widths[index]))
                    if index < len(raw_widths) else 100
                    for index in range(excel_cols)
                ]
                width_total = sum(widths)
                col_widths = [available_width * width / width_total for width in widths]

                raw_heights = excel.get("rowHeights") or []
                row_heights = [
                    max(12, float(raw_heights[index]) * 0.75)
                    if index < len(raw_heights) else None
                    for index in range(excel_rows)
                ]
                if any(height is None for height in row_heights):
                    row_heights = None

                excel_table = Table(
                    grid_data,
                    colWidths=col_widths,
                    rowHeights=row_heights,
                    repeatRows=0,
                    hAlign="LEFT",
                    splitByRow=1,
                )
                base_styles = [
                    ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#7A8490")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
                base_styles.extend(("SPAN", start, end) for start, end in spans)
                base_styles.extend(cell_styles)
                excel_table.setStyle(TableStyle(base_styles))
                story.extend([excel_table, Spacer(1, 5 * mm)])
                continue

            columns = (
                item.get("columns")
                or table_definition.get("columns")
                or []
            )

            saved_rows = (
                item.get("rows")
                or table_definition.get("rows")
                or []
            )

            # -------------------------------------------------
            # GET ACTUAL FILLED TABLE VALUE
            # -------------------------------------------------

            table_value = get_table_value(item)

            if table_value:

                columns = (
                    table_value.get("columns")
                    or columns
                )

                filled_rows = (
                    table_value.get("rows")
                    or []
                )

            else:
                filled_rows = saved_rows

            # -------------------------------------------------
            # TABLE TITLE
            # -------------------------------------------------

            table_title = clean_html(
                item.get("label")
                or item.get("name")
                or ""
            )

            if table_title and table_title.lower() != "table / grid":
                story.append(
                    Paragraph(
                        html.escape(table_title),
                        label_style,
                    )
                )

                story.append(
                    Spacer(
                        1,
                        2 * mm,
                    )
                )

            # -------------------------------------------------
            # TABLE HEADER
            # -------------------------------------------------

            header_row = []

            for column in columns:

                if not isinstance(
                    column,
                    dict,
                ):
                    continue

                column_name = (
                    column.get("name")
                    or column.get("label")
                    or "Column"
                )

                header_row.append(
                    paragraph_text(
                        column_name,
                        label_style,
                    )
                )

            if not header_row:
                continue

            table_data = [
                header_row
            ]

            # -------------------------------------------------
            # TABLE BODY
            # -------------------------------------------------

            for row in filled_rows:

                if not isinstance(
                    row,
                    dict,
                ):
                    continue

                cells = (
                    row.get("cells")
                    or {}
                )

                body_row = []

                for column in columns:

                    column_id = str(
                        column.get("id")
                        or ""
                    )

                    cell_value = (
                        cells.get(
                            column_id,
                            ""
                        )
                    )

                    body_row.append(
                        paragraph_text(
                            cell_value,
                            value_style,
                        )
                    )

                if body_row:
                    table_data.append(
                        body_row
                    )

            # If there are no saved rows, use
            # the layout rows as blank rows.
            if len(table_data) == 1:

                for row in saved_rows:

                    if not isinstance(
                        row,
                        dict,
                    ):
                        continue

                    cells = (
                        row.get("cells")
                        or {}
                    )

                    body_row = []

                    for column in columns:

                        column_id = str(
                            column.get("id")
                            or ""
                        )

                        body_row.append(
                            paragraph_text(
                                cells.get(
                                    column_id,
                                    ""
                                ),
                                value_style,
                            )
                        )

                    if body_row:
                        table_data.append(
                            body_row
                        )

            # -------------------------------------------------
            # COLUMN WIDTHS
            # -------------------------------------------------

            page_width = (
                A4[0]
                - 30 * mm
            )

            raw_widths = []

            for column in columns:

                try:
                    raw_widths.append(
                        max(
                            40,
                            float(
                                column.get(
                                    "width",
                                    100,
                                )
                            ),
                        )
                    )

                except Exception:
                    raw_widths.append(
                        100
                    )

            total_width = sum(
                raw_widths
            )

            if total_width <= 0:
                col_widths = None
            else:
                col_widths = [
                    page_width
                    * (
                        width
                        / total_width
                    )
                    for width in raw_widths
                ]

            # -------------------------------------------------
            # CREATE PDF TABLE
            # -------------------------------------------------

            pdf_table = Table(
                table_data,
                colWidths=col_widths,
                repeatRows=1,
                hAlign="LEFT",
            )

            pdf_table.setStyle(
                TableStyle(
                    [
                        (
                            "BACKGROUND",
                            (0, 0),
                            (-1, 0),
                            colors.HexColor(
                                "#E9EDF2"
                            ),
                        ),
                        (
                            "TEXTCOLOR",
                            (0, 0),
                            (-1, 0),
                            colors.black,
                        ),
                        (
                            "FONTNAME",
                            (0, 0),
                            (-1, 0),
                            "Helvetica-Bold",
                        ),
                        (
                            "FONTNAME",
                            (0, 1),
                            (-1, -1),
                            "Helvetica",
                        ),
                        (
                            "FONTSIZE",
                            (0, 0),
                            (-1, -1),
                            8,
                        ),
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            0.5,
                            colors.HexColor(
                                "#7A8490"
                            ),
                        ),
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "MIDDLE",
                        ),
                        (
                            "LEFTPADDING",
                            (0, 0),
                            (-1, -1),
                            5,
                        ),
                        (
                            "RIGHTPADDING",
                            (0, 0),
                            (-1, -1),
                            5,
                        ),
                        (
                            "TOPPADDING",
                            (0, 0),
                            (-1, -1),
                            5,
                        ),
                        (
                            "BOTTOMPADDING",
                            (0, 0),
                            (-1, -1),
                            5,
                        ),
                    ]
                )
            )

            story.append(
                pdf_table
            )

            story.append(
                Spacer(
                    1,
                    5 * mm,
                )
            )

            continue

        # =====================================================
        # NORMAL INPUT / FIELD
        # =====================================================

        value = get_value(
            item
        )

        label = (
            item.get("label")
            or item.get("text")
            or item.get("name")
            or ""
        )

        label = clean_html(
            label
        )

        # Ignore empty static controls
        # unless they have content.
        if not label and not value:
            continue

        field_table = Table(
            [
                [
                    paragraph_text(
                        label,
                        label_style,
                    ),
                    paragraph_text(
                        value,
                        value_style,
                    ),
                ]
            ],
            colWidths=[
                55 * mm,
                110 * mm,
            ],
        )

        field_table.setStyle(
            TableStyle(
                [
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor(
                            "#AAB2BD"
                        ),
                    ),
                    (
                        "BACKGROUND",
                        (0, 0),
                        (0, 0),
                        colors.HexColor(
                            "#F5F6F8"
                        ),
                    ),
                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "MIDDLE",
                    ),
                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        6,
                    ),
                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5,
                    ),
                ]
            )
        )

        story.append(
            field_table
        )

        story.append(
            Spacer(
                1,
                2 * mm,
            )
        )

    # ---------------------------------------------------------
    # FALLBACK IF LAYOUT DOES NOT EXIST
    # ---------------------------------------------------------

    if not layout:

        story.append(
            Paragraph(
                "No saved form layout was found.",
                normal_style,
            )
        )

        story.append(
            Spacer(
                1,
                4 * mm,
            )
        )

        for value in sorted(
            record.values,
            key=lambda v: (
                v.order_index or 0
            ),
        ):

            label = clean_html(
                value.label or ""
            )

            current_value = (
                value.value
                or ""
            )

            field_table = Table(
                [
                    [
                        paragraph_text(
                            label,
                            label_style,
                        ),
                        paragraph_text(
                            current_value,
                            value_style,
                        ),
                    ]
                ],
                colWidths=[
                    55 * mm,
                    110 * mm,
                ],
            )

            field_table.setStyle(
                TableStyle(
                    [
                        (
                            "GRID",
                            (0, 0),
                            (-1, -1),
                            0.4,
                            colors.grey,
                        ),
                    ]
                )
            )

            story.append(
                field_table
            )

    # ---------------------------------------------------------
    # FOOTER
    # ---------------------------------------------------------

    story.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    story.append(
        Paragraph(
            "Filled on screen. This PDF represents the saved form record.",
            ParagraphStyle(
                "PaperlessFooter",
                parent=styles["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=7.5,
                textColor=colors.HexColor(
                    "#666666"
                ),
            ),
        )
    )

    # ---------------------------------------------------------
    # BUILD PDF
    # ---------------------------------------------------------

    doc.build(
        story
    )

    # ---------------------------------------------------------
    # CREATE DOCUMENT RECORD
    # ---------------------------------------------------------

    document = Document(
        filename=path.name,
        original_filename=f"{record.number}.pdf",
        file_hash=calculate_file_hash(path),
        file_path=str(path),
        file_size=path.stat().st_size,
        mime_type="application/pdf",
        title=record.number,
        ocr_status="skipped",
    )

    db.add(
        document
    )

    db.commit()

    db.refresh(
        document
    )

    logger.info(
        f"Generated designed filled form for {record.number}"
    )

    return document