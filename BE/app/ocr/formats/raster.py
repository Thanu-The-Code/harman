"""Formats read by turning pages into images and running OCR: PDF and photos/scans."""
from abc import abstractmethod

from ..extract import extract
from ..loader import image_pages, pdf_pages
from ..pipeline import analyze, document_json
from ..template import build_template
from .base import Digitizer, FormatHandler, FormReader, TemplateBuilder, UploadedFile, ValueExtractor


class RasterHandler(FormatHandler, TemplateBuilder, ValueExtractor, Digitizer, FormReader):
    """Shared OCR pipeline; subclasses only say how to get page images out of the bytes."""

    def __init__(self, recognize=None):
        self._recognize = recognize  # injectable OCR engine (tests, other engines)

    @abstractmethod
    def load_pages(self, data: bytes) -> list:
        """-> list of BGR page images"""

    def _analyze(self, file: UploadedFile):
        return analyze(file.data, file.filename, recognize=self._recognize, page_loader=self.load_pages)

    def build_template(self, file):
        pages, images = self._analyze(file)
        return {**build_template(pages), "document": document_json(pages, images)}

    def extract(self, file, task_data):
        pages, images = self._analyze(file)
        return {**extract(task_data, pages, images, self._recognize), "document": document_json(pages, images)}

    def digitize(self, file):
        return document_json(*self._analyze(file))

    def read_form(self, file):
        pages, images = self._analyze(file)  # OCR once, use it twice
        template = build_template(pages, filled=True)
        values = extract(template["task_data"], pages, images, self._recognize)
        return {**template, **values, "document": document_json(pages, images)}


class PdfHandler(RasterHandler):
    key = "pdf"
    label = "PDF"
    extensions = (".pdf",)
    mime_types = ("application/pdf",)

    def sniff(self, data):
        return data[:5] == b"%PDF-"

    def load_pages(self, data):
        return pdf_pages(data)


class ImageHandler(RasterHandler):
    key = "image"
    label = "Image"
    extensions = (".png", ".jpg", ".jpeg")
    mime_types = ("image/png", "image/jpeg")

    def sniff(self, data):
        return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"

    def load_pages(self, data):
        return image_pages(data)
