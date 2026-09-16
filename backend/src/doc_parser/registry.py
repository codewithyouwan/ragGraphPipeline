from collections.abc import Iterable
from pathlib import Path

from doc_parser.base import DocumentParser, ParseLimits
from doc_parser.errors import UnsupportedFormatError
from doc_parser.models import ParsedDocument
from doc_parser.pdf import PdfParser


class ParserRegistry:
    """Picks the parser for a file by its extension."""

    def __init__(self, parsers: Iterable[DocumentParser] = ()) -> None:
        self._parsers: list[DocumentParser] = list(parsers)

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset().union(*(p.extensions for p in self._parsers))

    def for_path(self, path: str | Path) -> DocumentParser:
        path = Path(path)
        for parser in self._parsers:
            if parser.can_parse(path):
                return parser
        supported = ", ".join(sorted(self.supported_extensions)) or "none"
        raise UnsupportedFormatError(
            f"no parser for '{path.suffix or path.name}' (supported: {supported})"
        )

    def parse(self, path: str | Path, *, sha256: str | None = None) -> ParsedDocument:
        return self.for_path(path).parse(path, sha256=sha256)


def default_registry(limits: ParseLimits | None = None, **pdf_options: bool) -> ParserRegistry:
    return ParserRegistry([PdfParser(limits, **pdf_options)])
