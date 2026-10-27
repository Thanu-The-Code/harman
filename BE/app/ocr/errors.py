class UnsupportedFile(ValueError):
    """The file claims a supported type but its content cannot be read."""


class UnsupportedFormat(ValueError):
    """No enabled handler accepts this file, or the handler lacks the requested capability."""
