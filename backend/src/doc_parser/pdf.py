"""PDF parsing with pymupdf4llm.

pymupdf4llm (with the bundled pymupdf-layout model) classifies each region of a page
(title, section-header, text, table, page-header, page-footer, ...) and renders the
page as Markdown. We keep the per-page layout boxes so later layers can chunk by
section and cite page numbers.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymupdf
import pymupdf4llm

from doc_parser.base import DocumentParser, ParseLimits
from doc_parser.errors import (
    CorruptDocumentError,
    EncryptedDocumentError,
    NoExtractableTextError,
    TooManyPagesError,
    UnsupportedFormatError,
)
from doc_parser.models import (
    Block,
    DocumentMetadata,
    Page,
    ParsedDocument,
    ParserInfo,
    SourceInfo,
    TocEntry,
)

# The PDF spec allows junk before the header, but it must appear within the first 1024 bytes.
_PDF_MAGIC = b"%PDF-"
_MAGIC_WINDOW = 1024


class PdfParser(DocumentParser):
    name = "pymupdf4llm"
    media_type = "application/pdf"
    extensions = frozenset({".pdf"})

    def __init__(
        self,
        limits: ParseLimits | None = None,
        *,
        include_page_headers: bool = False,
        include_page_footers: bool = False,
        ocr: bool = False,
    ) -> None:
        super().__init__(limits)
        # OCR is off by default: it is ~100x slower per page. When on, pymupdf4llm
        # OCRs only the pages its own decision model finds to need it.
        self.ocr = ocr
        # Running headers/footers ("Confidential", "Page 3 of 40") repeat on every page.
        # They add noise to retrieval and break content hashing, so they're dropped by default.
        self.include_page_headers = include_page_headers
        self.include_page_footers = include_page_footers

    def _parse(self, path: Path, source: SourceInfo) -> ParsedDocument:
        _check_pdf_magic(path)
        started = time.perf_counter()

        try:
            doc = pymupdf.open(path, filetype="pdf")
        except (pymupdf.FileDataError, RuntimeError) as exc:
            raise CorruptDocumentError(f"{path.name} could not be opened: {exc}") from exc

        with doc:
            if doc.needs_pass:
                raise EncryptedDocumentError(f"{path.name} is password protected")
            if doc.page_count == 0:
                raise CorruptDocumentError(f"{path.name} has no pages")
            if doc.page_count > self.limits.max_pages:
                raise TooManyPagesError(
                    f"{path.name} has {doc.page_count} pages; limit is {self.limits.max_pages}"
                )

            # Read these before conversion: pymupdf4llm normalizes page rotation in place.
            metadata = _read_metadata(doc)
            page_sizes = [(page.rect.width, page.rect.height) for page in doc]

            try:
                page_chunks = pymupdf4llm.to_markdown(
                    doc,
                    page_chunks=True,
                    use_ocr=self.ocr,  # OCRs only pages that need it; off = warn instead
                    header=self.include_page_headers,
                    footer=self.include_page_footers,
                    show_progress=False,
                )
            except Exception as exc:
                raise CorruptDocumentError(f"{path.name} failed to convert: {exc}") from exc

        markdown, pages, blocks, warnings = _assemble(page_chunks, page_sizes)
        if not markdown.strip():
            hint = "" if self.ocr else "; retry with ocr=True"
            raise NoExtractableTextError(f"{path.name} has no extractable text{hint}")

        return ParsedDocument(
            source=source,
            parser=ParserInfo(
                name=self.name,
                version=pymupdf4llm.__version__,
                options={
                    "layout": True,
                    "ocr": self.ocr,
                    "include_page_headers": self.include_page_headers,
                    "include_page_footers": self.include_page_footers,
                },
            ),
            metadata=metadata,
            markdown=markdown,
            pages=pages,
            blocks=blocks,
            warnings=warnings,
            parse_seconds=round(time.perf_counter() - started, 3),
        )


def _check_pdf_magic(path: Path) -> None:
    with path.open("rb") as f:
        head = f.read(_MAGIC_WINDOW)
    if _PDF_MAGIC not in head:
        raise UnsupportedFormatError(f"{path.name} has a .pdf extension but is not a PDF")


def _assemble(
    page_chunks: list[dict], page_sizes: list[tuple[float, float]]
) -> tuple[str, list[Page], list[Block], list[str]]:
    """Concatenate per-page Markdown and shift layout box offsets to document offsets."""
    parts: list[str] = []
    pages: list[Page] = []
    blocks: list[Block] = []
    warnings: list[str] = []
    offset = 0

    for index, chunk in enumerate(page_chunks):
        number = chunk["metadata"]["page_number"]
        text = chunk["text"]
        # Keep a blank line between pages so the last line of one page and the first line
        # of the next never merge. Appending (not stripping) keeps box offsets valid.
        if text and not text.endswith("\n\n"):
            text += "\n" if text.endswith("\n") else "\n\n"

        for box in chunk["page_boxes"]:
            start, end = box["pos"]
            if end <= start:  # boxes excluded from the output (e.g. dropped headers)
                continue
            blocks.append(
                Block(
                    kind=box["class"],
                    page=number,
                    start=offset + start,
                    end=offset + end,
                    bbox=tuple(round(v, 2) for v in box["bbox"]),
                )
            )

        has_text = bool(text.strip())
        if not has_text:
            warnings.append(f"page {number}: no extractable text (scanned image or blank page)")

        width, height = page_sizes[index]
        pages.append(
            Page(
                number=number,
                start=offset,
                end=offset + len(text),
                width=round(width, 2),
                height=round(height, 2),
                has_text=has_text,
            )
        )
        parts.append(text)
        offset += len(text)

    return "".join(parts), pages, blocks, warnings


def _read_metadata(doc: pymupdf.Document) -> DocumentMetadata:
    info = doc.metadata or {}

    def clean(key: str) -> str | None:
        value = (info.get(key) or "").strip()
        return value or None

    return DocumentMetadata(
        page_count=doc.page_count,
        title=clean("title"),
        author=clean("author"),
        subject=clean("subject"),
        keywords=clean("keywords"),
        creator=clean("creator"),
        producer=clean("producer"),
        created_at=parse_pdf_date(info.get("creationDate")),
        modified_at=parse_pdf_date(info.get("modDate")),
        toc=[
            TocEntry(level=level, title=title.strip(), page=page)
            for level, title, page in doc.get_toc(simple=True)
        ],
    )


_PDF_DATE = re.compile(
    r"^(?:D:)?(?P<year>\d{4})(?P<month>\d{2})?(?P<day>\d{2})?"
    r"(?P<hour>\d{2})?(?P<minute>\d{2})?(?P<second>\d{2})?"
    r"(?:(?P<tz>[Zz+\-])(?P<tz_hour>\d{2})?'?(?P<tz_minute>\d{2})?'?)?"
)


def parse_pdf_date(value: str | None) -> str | None:
    """Convert a PDF date string (e.g. "D:20240131093000+05'30'") to ISO 8601."""
    if not value:
        return None
    match = _PDF_DATE.match(value.strip())
    if not match:
        return None

    parts = match.groupdict()
    try:
        tz = None
        if parts["tz"] in ("Z", "z"):
            tz = timezone.utc
        elif parts["tz"] in ("+", "-"):
            delta = timedelta(
                hours=int(parts["tz_hour"] or 0), minutes=int(parts["tz_minute"] or 0)
            )
            tz = timezone(delta if parts["tz"] == "+" else -delta)
        parsed = datetime(
            int(parts["year"]),
            int(parts["month"] or 1),
            int(parts["day"] or 1),
            int(parts["hour"] or 0),
            int(parts["minute"] or 0),
            int(parts["second"] or 0),
            tzinfo=tz,
        )
    except ValueError:
        return None
    return parsed.isoformat()
