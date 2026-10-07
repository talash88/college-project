"""recommendations

Revision ID: 008
Revises: 007
Create Date: 2026-09-28 00:00:00.000000

Step 8: student team + faculty mentor recommendations (advisory only).
New tables team_recommendations, team_recommendation_members,
mentor_recommendations + per-problem team/mentor recommendation statuses.
Does not modify migrations 001-007.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL.

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "TEAM_RECOMMENDATION_COMPLETED",
    "MENTOR_RECOMMENDATION_COMPLETED",
]
RECOMMENDATION_STATUSES = (
    "'NOT_RUN', 'PROCESSING', 'COMPLETED', "
    "'NO_ELIGIBLE_CANDIDATES', 'INSUFFICIENT_DATA', 'FAILED'"
)


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
        "team_recommendations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("skill_coverage_score", sa.Float(), nullable=False),
        sa.Column("proficiency_score", sa.Float(), nullable=False),
        sa.Column("availability_score", sa.Float(), nullable=False),
        sa.Column("workload_score", sa.Float(), nullable=False),
        sa.Column("verified_skill_score", sa.Float(), nullable=False),
        sa.Column("domain_score", sa.Float(), nullable=False),
        sa.Column("coverage_percent", sa.Float(), nullable=False),
        sa.Column("team_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="COMPLETED"),
        sa.Column("missing_skills", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_team_recommendations"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_team_recommendations_problem_id", "team_recommendations", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_team_recommendations_run_id", "team_recommendations", ["run_id"], unique=False
    )
    op.create_index(
        "ix_team_recommendations_created_at",
        "team_recommendations",
        ["created_at"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_team_recommendations_score_range",
        "team_recommendations",
        "score >= 0 AND score <= 100",
    )
    op.create_check_constraint(
        "ck_team_recommendations_coverage_range",
        "team_recommendations",
        "coverage_percent >= 0 AND coverage_percent <= 100",
    )

    op.create_table(
        "team_recommendation_members",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("individual_score", sa.Float(), nullable=False),
        sa.Column("covered_skills", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reason_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_team_recommendation_members"),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["team_recommendations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_team_rec_members_recommendation_id",
        "team_recommendation_members",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        "ix_team_rec_members_user_id", "team_recommendation_members", ["user_id"], unique=False
    )
    op.create_check_constraint(
        "ck_team_rec_members_score_range",
        "team_recommendation_members",
        "individual_score >= 0 AND individual_score <= 100",
    )

    op.create_table(
        "mentor_recommendations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("mentor_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("specialization_score", sa.Float(), nullable=False),
        sa.Column("skill_match_score", sa.Float(), nullable=False),
        sa.Column("category_score", sa.Float(), nullable=False),
        sa.Column("availability_score", sa.Float(), nullable=False),
        sa.Column("workload_score", sa.Float(), nullable=False),
        sa.Column("semantic_similarity", sa.Float(), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("reason_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mentor_recommendations"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mentor_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_mentor_recommendations_problem_id",
        "mentor_recommendations",
        ["problem_id"],
        unique=False,
    )
    op.create_index(
        "ix_mentor_recommendations_run_id",
        "mentor_recommendations",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_mentor_recommendations_created_at",
        "mentor_recommendations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_mentor_recommendations_mentor_user_id",
        "mentor_recommendations",
        ["mentor_user_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_mentor_recommendations_score_range",
        "mentor_recommendations",
        "score >= 0 AND score <= 100",
    )
    op.create_check_constraint(
        "ck_mentor_recommendations_semantic_range",
        "mentor_recommendations",
        "semantic_similarity >= 0 AND semantic_similarity <= 1",
    )

    op.add_column(
        "problems",
        sa.Column(
            "team_recommendation_status", sa.String(30), nullable=False, server_default="NOT_RUN"
        ),
    )
    op.add_column(
        "problems",
        sa.Column(
            "mentor_recommendation_status",
            sa.String(30),
            nullable=False,
            server_default="NOT_RUN",
        ),
    )
    op.create_check_constraint(
        "ck_problems_team_rec_status",
        "problems",
        f"team_recommendation_status IN ({RECOMMENDATION_STATUSES})",
    )
    op.create_check_constraint(
        "ck_problems_mentor_rec_status",
        "problems",
        f"mentor_recommendation_status IN ({RECOMMENDATION_STATUSES})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_problems_mentor_rec_status", "problems", type_="check")
    op.drop_constraint("ck_problems_team_rec_status", "problems", type_="check")
    op.drop_column("problems", "mentor_recommendation_status")
    op.drop_column("problems", "team_recommendation_status")
    op.drop_table("mentor_recommendations")
    op.drop_table("team_recommendation_members")
    op.drop_table("team_recommendations")
    # problem_event_type values are append-only by design; not removed here.
