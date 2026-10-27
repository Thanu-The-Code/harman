"""Contracts every document format plugs into.

A format handler declares which files it accepts and implements only the capabilities it
supports (interface segregation): building a template, filling values, digitizing as-is,
reading a filled copy as a form, writing values back into the document.
The HTTP layer depends on these abstractions, never on a concrete format (dependency inversion),
so a new format is a new handler class plus one registry entry (open/closed).
"""
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..errors import UnsupportedFile, UnsupportedFormat  # noqa: F401  (re-exported)


@dataclass(frozen=True)
class UploadedFile:
    data: bytes
    filename: str = ""

    @property
    def extension(self):
        return os.path.splitext(self.filename or "")[1].lower()


class TemplateBuilder(ABC):
    @abstractmethod
    def build_template(self, file: UploadedFile) -> dict:
        """-> {"task_data": [...], "stats": {...}, "document": {...}}"""


class ValueExtractor(ABC):
    @abstractmethod
    def extract(self, file: UploadedFile, task_data: list) -> dict:
        """-> {"answers": {...}, "fields": [...], "alignment": [...], "document": {...}}"""


class Digitizer(ABC):
    @abstractmethod
    def digitize(self, file: UploadedFile) -> dict:
        """-> {"pages": [...], "text": "..."}"""


class FormReader(ABC):
    @abstractmethod
    def read_form(self, file: UploadedFile) -> dict:
        """A filled-in document as a form plus its values, in one pass.

        -> {"task_data", "stats", "answers", "fields", "alignment", "document"}
        """


class FormExporter(ABC):
    @abstractmethod
    def export(self, file: UploadedFile, task_data: list, answers: dict) -> dict:
        """The document with the form's values written into it (the rest left as it was).

        -> {"filename", "media_type", "data": bytes, "written": [labels], "skipped": [{"label", "reason"}]}
        """


CAPABILITIES = {
    "template": TemplateBuilder, "extract": ValueExtractor, "digitize": Digitizer, "read_form": FormReader,
    "export": FormExporter,
}


class FormatHandler(ABC):
    """Identity of a format: its key, display name, file extensions and content sniffing."""

    key: str = ""
    label: str = ""
    extensions: tuple = ()
    mime_types: tuple = ()

    @abstractmethod
    def sniff(self, data: bytes) -> bool:
        """True if the bytes look like this format (magic number check)."""

    def accepts(self, file: UploadedFile) -> bool:
        return self.sniff(file.data) or file.extension in self.extensions

    @property
    def capabilities(self):
        return [name for name, iface in CAPABILITIES.items() if isinstance(self, iface)]

    def describe(self):
        return {
            "key": self.key,
            "label": self.label,
            "extensions": list(self.extensions),
            "mime_types": list(self.mime_types),
            "capabilities": self.capabilities,
        }
