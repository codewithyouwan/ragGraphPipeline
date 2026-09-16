"""Parse local files into Markdown + metadata.

    uv run doc-parser path/to/file.pdf path/to/folder --out data/parsed
"""

import argparse
import sys
from pathlib import Path

from doc_parser.base import ParseLimits
from doc_parser.errors import ParseError
from doc_parser.hashing import sha256_file
from doc_parser.registry import ParserRegistry, default_registry
from doc_parser.storage import document_dir, is_parsed, save_parsed


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    registry = default_registry(
        ParseLimits(max_file_bytes=int(args.max_mb * 1_048_576), max_pages=args.max_pages),
        include_page_headers=args.keep_headers,
        include_page_footers=args.keep_footers,
    )

    files = _collect_files(args.paths, registry)
    if not files:
        print("no supported files found", file=sys.stderr)
        return 1

    parsed = skipped = failed = 0
    for path in files:
        try:
            sha256 = sha256_file(path)
            if not args.force and is_parsed(args.out, sha256):
                skipped += 1
                print(f"= {path.name}: already parsed → {document_dir(args.out, sha256)}")
                continue

            result = registry.parse(path, sha256=sha256)
            target = save_parsed(args.out, result)
        except ParseError as exc:
            failed += 1
            print(f"✗ {path.name}: {exc}", file=sys.stderr)
            continue

        parsed += 1
        print(
            f"✓ {path.name} → {target} "
            f"({result.metadata.page_count} pages, {len(result.markdown):,} chars, "
            f"{result.parse_seconds:.2f}s)"
        )
        for warning in result.warnings:
            print(f"    ! {warning}")

    print(f"\nparsed {parsed}, skipped {skipped}, failed {failed}")
    return 1 if failed else 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc-parser", description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="files or folders to parse")
    parser.add_argument(
        "--out", type=Path, default=Path("data/parsed"), help="output root (default: data/parsed)"
    )
    parser.add_argument("--force", action="store_true", help="re-parse files already parsed")
    parser.add_argument("--max-mb", type=float, default=50, help="max file size in MB (default: 50)")
    parser.add_argument("--max-pages", type=int, default=500, help="max pages (default: 500)")
    parser.add_argument("--keep-headers", action="store_true", help="keep running page headers")
    parser.add_argument("--keep-footers", action="store_true", help="keep running page footers")
    return parser


def _collect_files(paths: list[Path], registry: ParserRegistry) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                sorted(
                    p
                    for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in registry.supported_extensions
                )
            )
        elif path.is_file():
            files.append(path)  # unsupported explicit files fail with a clear message later
        else:
            print(f"✗ {path}: not found", file=sys.stderr)
    return files


if __name__ == "__main__":
    sys.exit(main())
