"""Parser-independent output model.

Every parser (PDF now, DOCX/HTML/... later) produces a ParsedDocument, so later
layers (hashing, chunking, citations) never depend on a specific parsing library.

All character offsets (`start`/`end`) index into `ParsedDocument.markdown`, which lets
a chunker map any span of Markdown back to pages and layout blocks.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceInfo:
    filename: str
    sha256: str  # hash of the original bytes (the original file itself is not kept)
    size_bytes: int
    media_type: str


@dataclass(frozen=True, slots=True)
class ParserInfo:
    name: str
    version: str
    options: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TocEntry:
    level: int
    title: str
    page: int


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    page_count: int
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creator: str | None = None
    producer: str | None = None
    created_at: str | None = None  # ISO 8601
    modified_at: str | None = None  # ISO 8601
    toc: list[TocEntry] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Page:
    number: int  # 1-based
    start: int
    end: int
    width: float
    height: float
    has_text: bool


@dataclass(frozen=True, slots=True)
class Block:
    kind: str  # layout class, e.g. "section-header", "text", "table", "list-item"
    page: int
    start: int
    end: int
    bbox: tuple[float, float, float, float]


@dataclass(slots=True)
class ParsedDocument:
    source: SourceInfo
    parser: ParserInfo
    metadata: DocumentMetadata
    markdown: str
    pages: list[Page]
    blocks: list[Block]
    warnings: list[str]
    parse_seconds: float

    def page_text(self, number: int) -> str:
        page = self.pages[number - 1]
        return self.markdown[page.start : page.end]

    def to_dict(self, *, include_markdown: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_markdown:
            del data["markdown"]
        return data
