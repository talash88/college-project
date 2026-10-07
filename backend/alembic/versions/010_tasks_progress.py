"""tasks_progress

Revision ID: 010
Revises: 009
Create Date: 2026-09-30 00:00:00.000000

Step 10: team workspace — tasks, milestones, progress updates, work
attachments, and a cached real-progress column on problems. Does not
modify migrations 001-009.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL.

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "WORK_STARTED",
    "TASK_CREATED",
    "TASK_STARTED",
    "TASK_BLOCKED",
    "TASK_COMPLETED",
    "TASK_CANCELLED",
    "TASK_REASSIGNED",
    "TASK_UPDATED",
    "MILESTONE_CREATED",
    "MILESTONE_STARTED",
    "MILESTONE_COMPLETED",
    "MILESTONE_MISSED",
    "PROGRESS_UPDATED",
    "WORK_FILE_ADDED",
    "WORK_FILE_REMOVED",
]

TASK_STATUSES = "'TODO', 'IN_PROGRESS', 'BLOCKED', 'DONE', 'CANCELLED'"
TASK_PRIORITIES = "'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"
MILESTONE_STATUSES = "'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'MISSED', 'CANCELLED'"


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
        "problem_tasks",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="TODO"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocker_reason", sa.String(1000), nullable=True),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_problem_tasks"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["problem_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_problem_tasks_problem_id", "problem_tasks", ["problem_id"], unique=False)
    op.create_index("ix_problem_tasks_team_id", "problem_tasks", ["team_id"], unique=False)
    op.create_index(
        "ix_problem_tasks_assignee", "problem_tasks", ["assigned_to_user_id"], unique=False
    )
    op.create_index("ix_problem_tasks_status", "problem_tasks", ["status"], unique=False)
    op.create_check_constraint(
        "ck_problem_tasks_status", "problem_tasks", f"status IN ({TASK_STATUSES})"
    )
    op.create_check_constraint(
        "ck_problem_tasks_priority", "problem_tasks", f"priority IN ({TASK_PRIORITIES})"
    )
    op.create_check_constraint(
        "ck_problem_tasks_title_min", "problem_tasks", "char_length(title) >= 3"
    )

    op.create_table(
        "problem_milestones",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PLANNED"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_problem_milestones"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_problem_milestones_problem_id", "problem_milestones", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_problem_milestones_status", "problem_milestones", ["status"], unique=False
    )
    op.create_check_constraint(
        "ck_milestones_status", "problem_milestones", f"status IN ({MILESTONE_STATUSES})"
    )
    op.create_check_constraint(
        "ck_milestones_title_min", "problem_milestones", "char_length(title) >= 3"
    )

    op.create_table(
        "problem_progress_updates",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=True),
        sa.Column("progress_snapshot", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_progress_updates"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_progress_updates_problem_id", "problem_progress_updates", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_progress_updates_created_at", "problem_progress_updates", ["created_at"], unique=False
    )
    op.create_check_constraint(
        "ck_progress_summary_min", "problem_progress_updates", "char_length(summary) >= 5"
    )
    op.create_check_constraint(
        "ck_progress_snapshot_range",
        "problem_progress_updates",
        "progress_snapshot >= 0 AND progress_snapshot <= 100",
    )

    op.create_table(
        "problem_work_attachments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("is_reporter_visible", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_work_attachments"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["problem_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("storage_key", name="uq_work_attachments_storage_key"),
    )
    op.create_index(
        "ix_work_attachments_problem_id", "problem_work_attachments", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_work_attachments_task_id", "problem_work_attachments", ["task_id"], unique=False
    )
    op.create_check_constraint(
        "ck_work_attachments_size_positive", "problem_work_attachments", "size_bytes > 0"
    )

    op.add_column(
        "problems",
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_problems_progress_range", "problems", "progress_percent >= 0 AND progress_percent <= 100"
    )


def downgrade() -> None:
    op.drop_constraint("ck_problems_progress_range", "problems", type_="check")
    op.drop_column("problems", "progress_percent")
    op.drop_table("problem_work_attachments")
    op.drop_table("problem_progress_updates")
    op.drop_table("problem_milestones")
    op.drop_table("problem_tasks")
    # problem_event_type values are append-only by design; not removed here.
