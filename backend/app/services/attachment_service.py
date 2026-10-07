"""Problem attachment file handling (Step 4)."""

from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ProblemEventType
from app.models.problem import ProblemAttachment
from app.models.user import User
from app.repositories.problem_repository import ActivityRepository, AttachmentRepository
from app.services.auth_service import AuthError
from app.services.problem_service import ProblemService
from app.storage.base import sanitize_filename, sniff_mime
from app.storage.local import LocalAttachmentStorage, resolve_storage_dir

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


class AttachmentService:
    def __init__(self, session: AsyncSession, problems: ProblemService):
        self.session = session
        self.problems = problems
        self.attachments = AttachmentRepository(session)
        self.activities = ActivityRepository(session)
        self.storage = LocalAttachmentStorage(resolve_storage_dir(settings.STORAGE_DIR))
        self.max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
        self.max_count = settings.MAX_ATTACHMENTS_PER_PROBLEM
        self.allowed = set(settings.ALLOWED_ATTACHMENT_MIME_TYPES)

    async def _read_limited(self, upload: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > self.max_bytes:
                raise AuthError(413, f"File too large (max {settings.MAX_ATTACHMENT_SIZE_MB} MB)")
            chunks.append(chunk)
        return b"".join(chunks)

    async def add(self, user: User, problem_id: UUID, upload: UploadFile) -> ProblemAttachment:
        problem = await self.problems.require_modifiable(user, problem_id)
        existing = await self.attachments.count_for_problem(problem.id)
        if existing >= self.max_count:
            raise AuthError(409, f"At most {self.max_count} attachments per report")

        declared = (upload.content_type or "").split(";")[0].strip().lower()
        if declared not in self.allowed:
            raise AuthError(415, f"Unsupported file type: {declared or 'unknown'}")

        data = await self._read_limited(upload)
        if not data:
            raise AuthError(422, "Uploaded file is empty")
        sniffed = sniff_mime(data)
        if sniffed != declared:
            raise AuthError(415, "File content does not match its declared type")

        original = sanitize_filename(upload.filename or "upload")
        stored = self.storage.build_stored_filename(declared)
        await self.storage.save(stored, data)
        try:
            attachment = await self.attachments.create(
                problem_id=problem.id,
                original_filename=original,
                stored_filename=stored,
                mime_type=declared,
                size_bytes=len(data),
                uploaded_by=user.id,
            )
            await self.activities.log(
                problem_id=problem.id,
                event_type=ProblemEventType.ATTACHMENT_ADDED,
                actor_user_id=user.id,
                message=f"Attachment added: {original}",
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await self.storage.delete(stored)
            raise
        return attachment

    async def remove(self, user: User, problem_id: UUID, attachment_id: UUID) -> None:
        problem = await self.problems.require_modifiable(user, problem_id)
        attachment = await self.attachments.get(attachment_id)
        if attachment is None or attachment.problem_id != problem.id:
            raise AuthError(404, "Attachment not found")
        stored = attachment.original_filename
        stored_key = attachment.stored_filename
        await self.attachments.delete(attachment)
        await self.activities.log(
            problem_id=problem.id,
            event_type=ProblemEventType.ATTACHMENT_REMOVED,
            actor_user_id=user.id,
            message=f"Attachment removed: {stored}",
        )
        await self.session.commit()
        await self.storage.delete(stored_key)
