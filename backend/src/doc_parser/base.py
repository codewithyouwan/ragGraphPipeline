from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from doc_parser.errors import FileTooLargeError, ParseError
from doc_parser.hashing import sha256_file
from doc_parser.models import ParsedDocument, SourceInfo


@dataclass(frozen=True, slots=True)
class ParseLimits:
    max_file_bytes: int = 50 * 1024 * 1024
    max_pages: int = 500


class DocumentParser(ABC):
    """Base class for format-specific parsers.

    `parse` runs the checks shared by every format (file exists, size limit, hashing)
    and then delegates to `_parse`. To support a new format, subclass this, set the
    class attributes, implement `_parse`, and register it in `registry.default_registry`.
    """

    name: ClassVar[str]
    media_type: ClassVar[str]
    extensions: ClassVar[frozenset[str]]

    def __init__(self, limits: ParseLimits | None = None) -> None:
        self.limits = limits or ParseLimits()

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def parse(self, path: str | Path, *, sha256: str | None = None) -> ParsedDocument:
        """Parse a file. Pass `sha256` if the caller already hashed the file."""
        path = Path(path)
        if not path.is_file():
            raise ParseError(f"{path} is not a file")

        size = path.stat().st_size
        if size > self.limits.max_file_bytes:
            raise FileTooLargeError(
                f"{path.name} is {size / 1_048_576:.1f} MB; "
                f"limit is {self.limits.max_file_bytes / 1_048_576:.1f} MB"
            )

        source = SourceInfo(
            filename=path.name,
            sha256=sha256 or sha256_file(path),
            size_bytes=size,
            media_type=self.media_type,
        )
        return self._parse(path, source)

    @abstractmethod
    def _parse(self, path: Path, source: SourceInfo) -> ParsedDocument: ...
