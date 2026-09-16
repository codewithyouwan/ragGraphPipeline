import json

import pytest

from doc_parser import UnsupportedFormatError, default_registry
from doc_parser.cli import main
from doc_parser.storage import META_FILE


def test_registry_rejects_unknown_extension(tmp_path):
    path = tmp_path / "notes.docx"
    path.write_bytes(b"PK")
    with pytest.raises(UnsupportedFormatError, match=r"supported: \.pdf"):
        default_registry().for_path(path)


def test_registry_matches_extension_case_insensitively(tmp_path):
    assert default_registry().for_path(tmp_path / "REPORT.PDF").name == "pymupdf4llm"


def test_cli_writes_output_and_skips_duplicates(make_pdf, tmp_path, capsys):
    source = make_pdf()
    copy = tmp_path / "copy-of-report.pdf"
    copy.write_bytes(source.read_bytes())
    out = tmp_path / "parsed"

    assert main([str(source), "--out", str(out)]) == 0
    [doc_dir] = out.iterdir()
    assert "# Section 1. Overview" in (doc_dir / "doc.md").read_text()
    meta = json.loads((doc_dir / META_FILE).read_text())
    assert meta["source"]["filename"] == "report.pdf"
    assert meta["source"]["sha256"] == doc_dir.name
    assert "markdown" not in meta

    # Same bytes under another name: exact duplicate, not parsed again.
    assert main([str(copy), "--out", str(out)]) == 0
    assert "already parsed" in capsys.readouterr().out
    assert len(list(out.iterdir())) == 1


def test_cli_reports_failures_and_continues(make_pdf, tmp_path, capsys):
    good = make_pdf()
    bad = tmp_path / "fake.pdf"
    bad.write_text("not a pdf")
    out = tmp_path / "parsed"

    assert main([str(tmp_path), "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert "✗ fake.pdf" in captured.err
    assert f"✓ {good.name}" in captured.out
    assert "parsed 1, skipped 0, failed 1" in captured.out
