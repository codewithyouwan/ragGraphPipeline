import hashlib

import pymupdf
import pytest

from doc_parser import (
    CorruptDocumentError,
    EncryptedDocumentError,
    FileTooLargeError,
    NoExtractableTextError,
    ParseLimits,
    PdfParser,
    TooManyPagesError,
    UnsupportedFormatError,
)
from doc_parser.pdf import parse_pdf_date


def test_converts_headings_paragraphs_and_tables(make_pdf):
    parsed = PdfParser().parse(make_pdf())

    assert "# Section 1. Overview" in parsed.markdown
    assert "Paragraph 1-0 about quarterly results" in parsed.markdown
    assert "|Year|Revenue|Profit|" in parsed.markdown
    kinds = {block.kind for block in parsed.blocks}
    assert {"section-header", "text", "table"} <= kinds


def test_source_info_hashes_original_bytes(make_pdf):
    path = make_pdf()
    parsed = PdfParser().parse(path)

    assert parsed.source.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert parsed.source.size_bytes == path.stat().st_size
    assert parsed.source.media_type == "application/pdf"
    assert parsed.parser.name == "pymupdf4llm"


def test_offsets_map_back_to_pages_and_blocks(make_pdf):
    parsed = PdfParser().parse(make_pdf(pages=3))

    assert [p.number for p in parsed.pages] == [1, 2, 3]
    assert parsed.pages[0].start == 0
    assert parsed.pages[-1].end == len(parsed.markdown)
    for prev, cur in zip(parsed.pages, parsed.pages[1:]):
        assert prev.end == cur.start

    assert "Section 2. Overview" in parsed.page_text(2)
    assert "Section 2. Overview" not in parsed.page_text(1)

    for block in parsed.blocks:
        page = parsed.pages[block.page - 1]
        assert page.start <= block.start < block.end <= page.end
    header = next(b for b in parsed.blocks if b.kind == "section-header" and b.page == 3)
    assert parsed.markdown[header.start : header.end].startswith("# Section 3. Overview")


def test_running_headers_and_footers_dropped_by_default(make_pdf):
    path = make_pdf()

    default = PdfParser().parse(path)
    assert "Confidential" not in default.markdown
    assert "Page 1" not in default.markdown

    kept = PdfParser(include_page_headers=True, include_page_footers=True).parse(path)
    assert "ACME Corp - Confidential" in kept.markdown
    assert "Page 1" in kept.markdown


def test_blank_pages_produce_warnings(make_pdf):
    parsed = PdfParser().parse(make_pdf(pages=1, blank_pages=1))

    assert [p.has_text for p in parsed.pages] == [True, False]
    assert parsed.pages[1].start == parsed.pages[1].end
    assert parsed.warnings == ["page 2: no extractable text (scanned image or blank page)"]


def test_document_without_text_is_rejected(make_pdf):
    with pytest.raises(NoExtractableTextError):
        PdfParser().parse(make_pdf(pages=0, blank_pages=2))


def test_reads_metadata(make_pdf):
    path = make_pdf(
        metadata={
            "title": " Annual Report ",
            "author": "Finance Team",
            "creationDate": "D:20240131093000+05'30'",
        }
    )
    meta = PdfParser().parse(path).metadata

    assert meta.page_count == 2
    assert meta.title == "Annual Report"
    assert meta.author == "Finance Team"
    assert meta.subject is None
    assert meta.created_at == "2024-01-31T09:30:00+05:30"


def test_encrypted_pdf_is_rejected(make_pdf):
    path = make_pdf(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    with pytest.raises(EncryptedDocumentError):
        PdfParser().parse(path)


def test_corrupt_pdf_is_rejected(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not a real pdf body")
    with pytest.raises(CorruptDocumentError):
        PdfParser().parse(path)


def test_non_pdf_with_pdf_extension_is_rejected(tmp_path):
    path = tmp_path / "notes.pdf"
    path.write_text("just some text")
    with pytest.raises(UnsupportedFormatError):
        PdfParser().parse(path)


def test_size_limit(make_pdf):
    with pytest.raises(FileTooLargeError):
        PdfParser(ParseLimits(max_file_bytes=100)).parse(make_pdf())


def test_page_limit(make_pdf):
    with pytest.raises(TooManyPagesError):
        PdfParser(ParseLimits(max_pages=2)).parse(make_pdf(pages=3))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("D:20240131093000Z", "2024-01-31T09:30:00+00:00"),
        ("D:20240131093000-08'00'", "2024-01-31T09:30:00-08:00"),
        ("D:20240131093000+05'30", "2024-01-31T09:30:00+05:30"),
        ("D:20240131", "2024-01-31T00:00:00"),
        ("20240131093000", "2024-01-31T09:30:00"),
        ("D:2024", "2024-01-01T00:00:00"),
        ("D:20241399", None),
        ("garbage", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_pdf_date(raw, expected):
    assert parse_pdf_date(raw) == expected


def _scanned_pdf(source, target):
    """Rasterize a PDF so it has images but no text layer (like a scan)."""
    scanned = pymupdf.open()
    with pymupdf.open(source) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            new = scanned.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, pixmap=pix)
    scanned.save(target)
    scanned.close()
    return target


@pytest.mark.ocr
def test_ocr_reads_scanned_pages(make_pdf, tmp_path):
    scanned = _scanned_pdf(make_pdf(pages=1), tmp_path / "scanned.pdf")

    with pytest.raises(NoExtractableTextError, match="retry with ocr=True"):
        PdfParser().parse(scanned)

    parsed = PdfParser(ocr=True).parse(scanned)
    assert "Section 1" in parsed.markdown
    assert "quarterly results" in parsed.markdown
    assert parsed.parser.options["ocr"] is True
