"""Supported document formats.

To add a format: write a FormatHandler subclass implementing the capabilities it supports
(TemplateBuilder / ValueExtractor / Digitizer / FormReader / FormExporter) and add it to AVAILABLE. To switch formats on
or off without code changes, set DOC_FORMATS (e.g. "pdf,image" disables Excel).

PDF and image need the OCR extra (requirements-ocr.txt: PaddleOCR, OpenCV). Without it those two
are left out of the default set, and naming them in DOC_FORMATS is an error that says what to install.
"""
import logging
import os

from .base import (  # noqa: F401
    Digitizer, FormatHandler, FormExporter, FormReader, TemplateBuilder, UnsupportedFile, UnsupportedFormat,
    UploadedFile, ValueExtractor,
)
from .excel import ExcelHandler
from .registry import FormatRegistry

log = logging.getLogger("ocr")

AVAILABLE = {"excel": ExcelHandler}
OCR_UNAVAILABLE = None  # why PDF / image are missing, if they are

try:  # the raster route imports OpenCV (and PaddleOCR when a page is read)
    from .raster import ImageHandler, PdfHandler

    AVAILABLE = {"pdf": PdfHandler, "image": ImageHandler, **AVAILABLE}
except ImportError as exc:  # pragma: no cover - depends on what is installed
    OCR_UNAVAILABLE = f"{exc}. Install requirements-ocr.txt to read PDFs and images."
    log.info("OCR formats unavailable: %s", OCR_UNAVAILABLE)

DEFAULT_FORMATS = ",".join(AVAILABLE)


def build_registry(enabled=None, **handler_kwargs):
    """Registry of the enabled formats (comma-separated keys; default from DOC_FORMATS)."""
    keys = [k.strip() for k in (enabled or os.environ.get("DOC_FORMATS") or DEFAULT_FORMATS).split(",") if k.strip()]
    unknown = [k for k in keys if k not in AVAILABLE]
    if unknown:
        hint = f" ({OCR_UNAVAILABLE})" if OCR_UNAVAILABLE and set(unknown) & {"pdf", "image"} else ""
        raise ValueError(
            f"Unknown document format(s): {', '.join(unknown)}. Available: {', '.join(AVAILABLE)}{hint}"
        )
    registry = FormatRegistry()
    for key in keys:
        handler_cls = AVAILABLE[key]
        kwargs = handler_kwargs.get(key, {})
        registry.register(handler_cls(**kwargs))
    return registry
