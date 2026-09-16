from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest


def _write_report_page(page: pymupdf.Page, n: int) -> None:
    page.insert_text((72, 30), "ACME Corp - Confidential", fontsize=8)
    page.insert_text((72, 90), f"Section {n}. Overview", fontsize=16)
    y = 120
    for i in range(8):
        page.insert_text(
            (72, y),
            f"Paragraph {n}-{i} about quarterly results and outlook for the business.",
            fontsize=11,
        )
        y += 15
    rows = [["Year", "Revenue", "Profit"], ["2023", "4.2", "0.9"], ["2024", "5.1", "1.2"]]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            rect = pymupdf.Rect(72 + c * 100, 300 + r * 20, 72 + (c + 1) * 100, 300 + (r + 1) * 20)
            page.draw_rect(rect, color=(0, 0, 0))
            page.insert_text((rect.x0 + 5, rect.y1 - 6), value, fontsize=10)
    page.insert_text((290, 800), f"Page {n}", fontsize=8)


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Build a small report-like PDF: running header/footer, heading, paragraphs, table."""

    def build(
        name: str = "report.pdf",
        *,
        pages: int = 2,
        blank_pages: int = 0,
        metadata: dict[str, str] | None = None,
        **save_kwargs,
    ) -> Path:
        doc = pymupdf.open()
        for n in range(1, pages + 1):
            _write_report_page(doc.new_page(), n)
        for _ in range(blank_pages):
            doc.new_page()
        if metadata:
            doc.set_metadata(metadata)
        path = tmp_path / name
        doc.save(path, **save_kwargs)
        doc.close()
        return path

    return build
