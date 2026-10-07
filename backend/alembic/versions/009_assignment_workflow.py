"""assignment_workflow

Revision ID: 009
Revises: 008
Create Date: 2026-09-28 00:00:00.000000

Step 9: admin review/approval workflow + real persistent teams and
transactional assignments (team + mentor + workload increments).
Does not modify migrations 001-008.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL.

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "REVIEW_STARTED",
    "PROBLEM_APPROVED",
    "PROBLEM_REJECTED",
    "TEAM_CREATED",
    "TEAM_ASSIGNED",
    "MENTOR_ASSIGNED",
    "ASSIGNMENT_CREATED",
    "ASSIGNMENT_UPDATED",
    "ASSIGNMENT_CANCELLED",
]
ASSIGNMENT_STATUSES = "'ACTIVE', 'COMPLETED', 'CANCELLED', 'REASSIGNED'"


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
        "problem_teams",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_teams"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_problem_teams_problem_id", "problem_teams", ["problem_id"], unique=False
    )
    # One active primary team per problem (DB-enforced).
    op.create_index(
        "uq_problem_teams_one_active",
        "problem_teams",
        ["problem_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "problem_team_members",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_in_team", sa.String(50), nullable=True),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name="pk_problem_team_members"),
        sa.ForeignKeyConstraint(["team_id"], ["problem_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_team_members_team_id", "problem_team_members", ["team_id"], unique=False
    )
    op.create_index(
        "ix_team_members_user_id", "problem_team_members", ["user_id"], unique=False
    )
    # No duplicate active membership per team (re-adding after removal allowed).
    op.create_index(
        "uq_team_members_one_active",
        "problem_team_members",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "problem_assignments",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_team_recommendation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_mentor_recommendation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_by", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("team_was_overridden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("mentor_was_overridden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("team_override_reason", sa.String(1000), nullable=True),
        sa.Column("mentor_override_reason", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unassigned_by", UUID(as_uuid=True), nullable=True),
        sa.Column("unassignment_reason", sa.String(1000), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_problem_assignments"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["problem_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mentor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_team_recommendation_id"], ["team_recommendations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_mentor_recommendation_id"],
            ["mentor_recommendations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["unassigned_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_assignments_problem_id", "problem_assignments", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_assignments_team_id", "problem_assignments", ["team_id"], unique=False
    )
    op.create_index(
        "ix_assignments_mentor_user_id",
        "problem_assignments",
        ["mentor_user_id"],
        unique=False,
    )
    # One active assignment per problem (DB-enforced idempotency backstop).
    op.create_index(
        "uq_assignments_one_active",
        "problem_assignments",
        ["problem_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_check_constraint(
        "ck_assignments_status",
        "problem_assignments",
        f"status IN ({ASSIGNMENT_STATUSES})",
    )

    op.add_column(
        "problems",
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "problems",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "problems",
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "problems",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "problems",
        sa.Column("rejection_reason", sa.String(1000), nullable=True),
    )
    op.create_foreign_key(
        "fk_problems_reviewed_by",
        "problems",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_problems_approved_by",
        "problems",
        "users",
        ["approved_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_problems_approved_by", "problems", type_="foreignkey")
    op.drop_constraint("fk_problems_reviewed_by", "problems", type_="foreignkey")
    op.drop_column("problems", "rejection_reason")
    op.drop_column("problems", "approved_at")
    op.drop_column("problems", "approved_by")
    op.drop_column("problems", "reviewed_at")
    op.drop_column("problems", "reviewed_by")
    op.drop_table("problem_assignments")
    op.drop_table("problem_team_members")
    op.drop_table("problem_teams")
    # problem_event_type values are append-only by design; not removed here.
