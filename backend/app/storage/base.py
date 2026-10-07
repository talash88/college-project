"""Attachment storage abstraction.

Local filesystem storage for development; the `AttachmentStorage` protocol
allows an S3/Cloudinary backend to replace it without touching services.
Raw files are never stored in PostgreSQL.
"""

from typing import Protocol


class AttachmentStorage(Protocol):
    async def save(self, stored_filename: str, data: bytes) -> None:
        """Persist file bytes under a server-generated name."""
        ...

    async def delete(self, stored_filename: str) -> None:
        """Remove a stored file; missing files are ignored."""
        ...


MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def sanitize_filename(name: str) -> str:
    """Strip paths and unsafe characters; never used for the storage path."""
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    safe = "".join(c if (c.isalnum() or c in ("-", "_", ".", " ", "(")) else "_" for c in base)
    safe = safe.strip().strip(".")[:200]
    return safe or "upload"


def sniff_mime(data: bytes) -> str | None:
    """Detect JPEG/PNG/WEBP/PDF from magic bytes. Returns None if unknown."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    return None
