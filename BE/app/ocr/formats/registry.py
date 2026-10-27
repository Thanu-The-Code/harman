"""Registry of enabled document formats; the API resolves every upload through it."""
from .base import CAPABILITIES, UnsupportedFormat, UploadedFile


class FormatRegistry:
    def __init__(self, handlers=()):
        self._handlers = {}
        for h in handlers:
            self.register(h)

    def register(self, handler):
        if not handler.key:
            raise ValueError("handler needs a key")
        if handler.key in self._handlers:
            raise ValueError(f"format '{handler.key}' already registered")
        self._handlers[handler.key] = handler
        return self

    def unregister(self, key):
        self._handlers.pop(key, None)
        return self

    def get(self, key):
        return self._handlers.get(key)

    def handlers(self):
        return list(self._handlers.values())

    def describe(self):
        return [h.describe() for h in self._handlers.values()]

    def extensions(self):
        return [ext for h in self._handlers.values() for ext in h.extensions]

    def resolve(self, file: UploadedFile, capability=None):
        """The handler for this file: content sniffing first, then the file extension."""
        handler = next((h for h in self._handlers.values() if h.sniff(file.data)), None)
        if handler is None:
            handler = next((h for h in self._handlers.values() if file.extension in h.extensions), None)
        if handler is None:
            allowed = ", ".join(sorted(self.extensions())) or "none"
            raise UnsupportedFormat(f"Unsupported file type. Supported: {allowed}")
        if capability and not isinstance(handler, CAPABILITIES[capability]):
            raise UnsupportedFormat(f"{handler.label} files cannot be used to {capability}")
        return handler
