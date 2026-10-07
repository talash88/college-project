"""Notification provider abstraction (Step 11).

In-app database delivery is the real, working provider today. Email and
push providers are deliberately NOT implemented: this module defines the
seam (`NotificationProvider`) so a future SMTP/Firebase implementation can
be added without touching calling services. Nothing here fakes delivery.
"""

from typing import Protocol
from uuid import UUID


class NotificationProvider(Protocol):
    """Delivery seam for future email/push providers."""

    async def deliver(
        self,
        *,
        recipient_user_id: UUID,
        type: str,
        title: str,
        message: str,
        problem_id: UUID | None,
        related_entity_type: str | None,
        related_entity_id: UUID | None,
    ) -> None:
        """Deliver one notification. Must be honest: raise on failure."""
        ...
