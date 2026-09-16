"""Document parsing: turn uploaded files into Markdown plus structural metadata."""

from doc_parser.base import DocumentParser, ParseLimits
from doc_parser.errors import (
    CorruptDocumentError,
    EncryptedDocumentError,
    FileTooLargeError,
    NoExtractableTextError,
    ParseError,
    TooManyPagesError,
    UnsupportedFormatError,
)
from doc_parser.models import Block, DocumentMetadata, Page, ParsedDocument, SourceInfo
from doc_parser.pdf import PdfParser
from doc_parser.registry import ParserRegistry, default_registry

__all__ = [
    "Block",
    "CorruptDocumentError",
    "DocumentMetadata",
    "DocumentParser",
    "EncryptedDocumentError",
    "FileTooLargeError",
    "NoExtractableTextError",
    "Page",
    "ParseError",
    "ParseLimits",
    "ParsedDocument",
    "ParserRegistry",
    "PdfParser",
    "SourceInfo",
    "TooManyPagesError",
    "UnsupportedFormatError",
    "default_registry",
]
