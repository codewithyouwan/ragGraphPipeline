"""Local storage for parsed documents.

Layout (one directory per unique source file, named by the SHA-256 of its bytes):

    <root>/<sha256>/
        doc.md      # Markdown
        meta.json   # source, parser, metadata, pages, blocks, warnings

Keying by content hash makes re-parsing the same file a no-op: exact duplicate
detection (layer L0 in docs/PLAN.md). meta.json is written last and is the
completion marker, so a crash mid-write never looks like a finished parse.
"""

import json
import os
from pathlib import Path

from doc_parser.models import ParsedDocument

MARKDOWN_FILE = "doc.md"
META_FILE = "meta.json"


def document_dir(root: Path, sha256: str) -> Path:
    return root / sha256


def is_parsed(root: Path, sha256: str) -> bool:
    return (document_dir(root, sha256) / META_FILE).is_file()


def save_parsed(root: Path, parsed: ParsedDocument) -> Path:
    target = document_dir(root, parsed.source.sha256)
    target.mkdir(parents=True, exist_ok=True)
    _write_atomic(target / MARKDOWN_FILE, parsed.markdown)
    _write_atomic(
        target / META_FILE,
        json.dumps(parsed.to_dict(include_markdown=False), indent=2, ensure_ascii=False),
    )
    return target


def _write_atomic(path: Path, content: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
