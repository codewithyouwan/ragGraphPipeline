"""Errors raised while parsing documents.

Every error derives from ParseError so callers (CLI now, ingestion workers later)
can catch one type and record a clear, user-facing reason for the failure.
"""


class ParseError(Exception):
    """Base class for all document parsing failures."""


class UnsupportedFormatError(ParseError):
    """No parser handles this file, or its content doesn't match its extension."""


class FileTooLargeError(ParseError):
    """The file exceeds the configured size limit."""


class TooManyPagesError(ParseError):
    """The document exceeds the configured page limit."""


class EncryptedDocumentError(ParseError):
    """The document is password protected."""


class CorruptDocumentError(ParseError):
    """The file could not be opened or read by the parsing library."""


class NoExtractableTextError(ParseError):
    """The document has no text layer (e.g. a scanned PDF while OCR is disabled)."""
