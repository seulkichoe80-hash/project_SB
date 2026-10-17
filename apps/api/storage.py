import hashlib
import os
import re
from pathlib import Path
from .errors import DomainError


class LocalOriginalStore:
    """UUID-only keys; exclusive writes, never overwrites or deletes originals."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not re.fullmatch(r'[0-9a-f]{32}', key):
            raise DomainError('invalid_storage_key', 400)
        path = self.root / key
        if path.is_symlink() or path.resolve().parent != self.root:
            raise DomainError('unsafe_storage_path', 409)
        return path

    def write(self, key: str, data: bytes):
        with self.path(key).open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # OS administrators can bypass permissions. Reads verify hashes as well.
        self.path(key).chmod(0o444)

    def read(self, key: str, expected_hash: str) -> bytes:
        try:
            data = self.path(key).read_bytes()
        except OSError:
            raise DomainError('original_unavailable', 409) from None
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise DomainError('original_integrity_failure', 409)
        return data

