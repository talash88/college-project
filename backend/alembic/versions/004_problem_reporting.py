"""problem_reporting

Revision ID: 004
Revises: 003
Create Date: 2026-09-27 00:00:00.000000

Step 4: campus problem reporting tables (problems, attachments, activity,
comments, ticket counters). Does not modify migrations 001, 002 or 003.

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

PROBLEM_STATUSES = [
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "ASSIGNED",
    "IN_PROGRESS",
    "AWAITING_VERIFICATION",
    "RESOLVED",
    "CLOSED",
    "REJECTED",
    "DUPLICATE",
    "WITHDRAWN",
]
PROBLEM_EVENTS = [
    "SUBMITTED",
    "EDITED",
    "STATUS_CHANGED",
    "ATTACHMENT_ADDED",
    "ATTACHMENT_REMOVED",
    "COMMENT_ADDED",
]


def upgrade() -> None:
    op.execute(
        "CREATE TYPE problem_status AS ENUM (" + ", ".join(f"'{s}'" for s in PROBLEM_STATUSES) + ")"
    )
    op.execute(
        "CREATE TYPE problem_event_type AS ENUM ("
        + ", ".join(f"'{e}'" for e in PROBLEM_EVENTS)
        + ")"
    )

    op.create_table(
        "ticket_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("year", name="pk_ticket_counters"),
    )

    op.create_table(
        "problems",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reporter_id", UUID(as_uuid=True), nullable=False),
        sa.Column("location_text", sa.String(300), nullable=False),
        sa.Column("building", sa.String(150), nullable=True),
        sa.Column("area", sa.String(150), nullable=True),
        sa.Column("affected_people_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(*PROBLEM_STATUSES, name="problem_status", create_type=False),
            nullable=False,
            server_default="SUBMITTED",
        ),
        sa.Column("predicted_category", sa.String(100), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("priority_score", sa.Float(), nullable=True),
        sa.Column("priority_level", sa.String(20), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problems"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("ticket_number", name="uq_problems_ticket_number"),
    )
    op.create_index("ix_problems_ticket_number", "problems", ["ticket_number"], unique=True)
    op.create_index("ix_problems_reporter_id", "problems", ["reporter_id"], unique=False)
    op.create_index("ix_problems_status", "problems", ["status"], unique=False)
    op.create_index("ix_problems_created_at", "problems", ["created_at"], unique=False)
    op.create_check_constraint("ck_problems_title_min", "problems", "char_length(title) >= 5")
    op.create_check_constraint(
        "ck_problems_description_min", "problems", "char_length(description) >= 20"
    )
    op.create_check_constraint(
        "ck_problems_affected_positive",
        "problems",
        "affected_people_count IS NULL OR affected_people_count >= 1",
    )

    op.create_table(
        "problem_attachments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_attachments"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stored_filename", name="uq_problem_attachments_stored_filename"),
    )
    op.create_index(
        "ix_problem_attachments_problem_id", "problem_attachments", ["problem_id"], unique=False
    )
    op.create_check_constraint(
        "ck_problem_attachments_size_positive", "problem_attachments", "size_bytes > 0"
    )

    op.create_table(
        "problem_activities",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "event_type",
            postgresql.ENUM(*PROBLEM_EVENTS, name="problem_event_type", create_type=False),
            nullable=False,
        ),
        sa.Column("old_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=True),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_activities"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_problem_activities_problem_id", "problem_activities", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_problem_activities_created_at", "problem_activities", ["created_at"], unique=False
    )

    op.create_table(
        "problem_comments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_comments"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_problem_comments_problem_id", "problem_comments", ["problem_id"], unique=False
    )
    op.create_check_constraint(
        "ck_problem_comments_content_nonempty",
        "problem_comments",
        "char_length(content) >= 1",
    )


def downgrade() -> None:
    op.drop_table("problem_comments")
    op.drop_table("problem_activities")
    op.drop_table("problem_attachments")
    op.drop_table("problems")
    op.drop_table("ticket_counters")
    op.execute("DROP TYPE IF EXISTS problem_event_type")
    op.execute("DROP TYPE IF EXISTS problem_status")
