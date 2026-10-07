"""notifications_verification

Revision ID: 011
Revises: 010
Create Date: 2026-10-01 00:00:00.000000

Step 11: solution submission + mentor review + reporter verification +
verified closure + in-app notifications. Does not modify migrations
001-010.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL.

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "SOLUTION_SUBMITTED",
    "MENTOR_CHANGES_REQUESTED",
    "MENTOR_SOLUTION_APPROVED",
    "REPORTER_VERIFICATION_REQUESTED",
    "REPORTER_CONFIRMED_RESOLUTION",
    "REPORTER_REJECTED_RESOLUTION",
    "PROBLEM_RESOLVED",
    "PROBLEM_CLOSED",
]

SOLUTION_STATUSES = "'SUBMITTED', 'CHANGES_REQUESTED', 'MENTOR_APPROVED', 'REPORTER_REJECTED', 'VERIFIED'"
REVIEW_DECISIONS = "'APPROVED', 'CHANGES_REQUESTED'"
VERIFICATION_DECISIONS = "'RESOLVED', 'NOT_RESOLVED'"


def upgrade() -> None:
    # problem_event_type values are append-only: ADD VALUE cannot be rolled
    # back, so only add labels missing on this database (downgrade-safe).
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'problem_event_type'"
            )
        ).all()
    }
    for value in NEW_EVENT_VALUES:
        if value not in existing:
            op.execute(f"ALTER TYPE problem_event_type ADD VALUE '{value}'")

    op.create_table(
        "problem_solution_submissions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("solution_summary", sa.String(2000), nullable=False),
        sa.Column("root_cause", sa.String(2000), nullable=False),
        sa.Column("work_performed", sa.Text(), nullable=False),
        sa.Column("testing_performed", sa.Text(), nullable=True),
        sa.Column("deployment_notes", sa.Text(), nullable=True),
        sa.Column("limitations", sa.Text(), nullable=True),
        sa.Column("evidence_attachment_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("readiness_override_reason", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column(
            "submitted_at",
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
        sa.PrimaryKeyConstraint("id", name="pk_problem_solution_submissions"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["problem_assignments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_solution_submissions_problem_id", "problem_solution_submissions", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_solution_submissions_assignment_id",
        "problem_solution_submissions",
        ["assignment_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_solution_status", "problem_solution_submissions", f"status IN ({SOLUTION_STATUSES})"
    )
    op.create_check_constraint(
        "ck_solution_revision_positive", "problem_solution_submissions", "revision_number >= 1"
    )
    op.create_check_constraint(
        "ck_solution_summary_min",
        "problem_solution_submissions",
        "char_length(solution_summary) >= 10",
    )
    op.create_check_constraint(
        "ck_solution_root_cause_min",
        "problem_solution_submissions",
        "char_length(root_cause) >= 10",
    )
    op.create_check_constraint(
        "ck_solution_work_min",
        "problem_solution_submissions",
        "char_length(work_performed) >= 20",
    )

    op.create_table(
        "mentor_solution_reviews",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("solution_submission_id", UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("review_comment", sa.String(2000), nullable=True),
        sa.Column("is_admin_override", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mentor_solution_reviews"),
        sa.ForeignKeyConstraint(
            ["solution_submission_id"], ["problem_solution_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["mentor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_solution_reviews_submission_id",
        "mentor_solution_reviews",
        ["solution_submission_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_review_decision", "mentor_solution_reviews", f"decision IN ({REVIEW_DECISIONS})"
    )

    op.create_table(
        "problem_resolution_verifications",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("solution_submission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reporter_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_resolution_verifications"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["solution_submission_id"], ["problem_solution_submissions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_verifications_problem_id", "problem_resolution_verifications", ["problem_id"], unique=False
    )
    op.create_check_constraint(
        "ck_verification_decision",
        "problem_resolution_verifications",
        f"decision IN ({VERIFICATION_DECISIONS})",
    )

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=True),
        sa.Column("related_entity_type", sa.String(50), nullable=True),
        sa.Column("related_entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_notifications_recipient_id", "notifications", ["recipient_user_id"], unique=False
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_notifications_problem_id", "notifications", ["problem_id"], unique=False)


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("problem_resolution_verifications")
    op.drop_table("mentor_solution_reviews")
    op.drop_table("problem_solution_submissions")
    # problem_event_type values are append-only by design; not removed here.
