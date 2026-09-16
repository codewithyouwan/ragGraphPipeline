import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Hash a file in fixed-size pieces so memory use doesn't grow with file size."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
