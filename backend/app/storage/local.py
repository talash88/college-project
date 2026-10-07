import asyncio
from pathlib import Path
from uuid import uuid4

from app.storage.base import MIME_EXTENSION


def resolve_storage_dir(configured: str) -> Path:
    """Resolve the storage dir; relative paths anchor at the backend/ directory."""
    path = Path(configured)
    if not path.is_absolute():
        backend_root = Path(__file__).resolve().parent.parent.parent
        path = backend_root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


class LocalAttachmentStorage:
    """Filesystem storage. Filenames are server-generated UUIDs; the resolved
    path is always contained in the storage root (no traversal possible)."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def build_stored_filename(self, mime_type: str) -> str:
        ext = MIME_EXTENSION.get(mime_type, ".bin")
        return f"{uuid4().hex}{ext}"

    def _resolve(self, stored_filename: str) -> Path:
        # Only a bare filename is ever accepted; anything else is rejected.
        if (
            "/" in stored_filename
            or "\\" in stored_filename
            or stored_filename != Path(stored_filename).name
        ):
            raise ValueError("Invalid stored filename")
        return self.root / stored_filename

    async def save(self, stored_filename: str, data: bytes) -> None:
        target = self._resolve(stored_filename)
        await asyncio.to_thread(target.write_bytes, data)

    async def delete(self, stored_filename: str) -> None:
        try:
            target = self._resolve(stored_filename)
        except ValueError:
            return
        try:
            await asyncio.to_thread(target.unlink, True)
        except FileNotFoundError:
            pass
