"""priority_and_skills

Revision ID: 006
Revises: 005
Create Date: 2026-09-27 00:00:00.000000

Step 6: explainable priority analyses, pgvector skill embeddings,
required-skill analyses + matches, and per-problem analysis status caches.
Does not modify migrations 001-005.

"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

ANALYSIS_STATUSES = "'NOT_RUN', 'PROCESSING', 'COMPLETED', 'LOW_CONFIDENCE', 'FAILED'"
PRIORITY_LEVELS = "'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"
MATCH_TYPES = "'EXACT', 'SEMANTIC', 'HYBRID'"
EMBEDDING_DIM = 384


def upgrade() -> None:
    op.create_table(
        "problem_priority_analyses",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("priority_level", sa.String(10), nullable=True),
        sa.Column("severity_component", sa.Float(), nullable=False),
        sa.Column("affected_people_component", sa.Float(), nullable=False),
        sa.Column("age_component", sa.Float(), nullable=False),
        sa.Column("category_component", sa.Float(), nullable=False),
        sa.Column("duplicate_component", sa.Float(), nullable=False),
        sa.Column("component_details", JSONB, nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recalculation_reason", sa.String(500), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_priority_analyses"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_priority_analyses_problem_id", "problem_priority_analyses", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_priority_analyses_created_at",
        "problem_priority_analyses",
        ["created_at"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_priority_score_range",
        "problem_priority_analyses",
        "score IS NULL OR (score >= 0 AND score <= 100)",
    )
    op.create_check_constraint(
        "ck_priority_status", "problem_priority_analyses", f"status IN ({ANALYSIS_STATUSES})"
    )
    op.create_check_constraint(
        "ck_priority_level", "problem_priority_analyses", f"priority_level IN ({PRIORITY_LEVELS})"
    )

    op.create_table(
        "skill_embeddings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_skill_embeddings"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("skill_id", "model_version", name="uq_skill_embeddings_skill_version"),
    )
    op.create_index("ix_skill_embeddings_skill_id", "skill_embeddings", ["skill_id"], unique=False)

    op.create_table(
        "problem_skill_analyses",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("recalculation_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_skill_analyses"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_skill_analyses_problem_id", "problem_skill_analyses", ["problem_id"], unique=False
    )
    op.create_index(
        "ix_skill_analyses_created_at", "problem_skill_analyses", ["created_at"], unique=False
    )
    op.create_check_constraint(
        "ck_skill_analysis_status", "problem_skill_analyses", f"status IN ({ANALYSIS_STATUSES})"
    )

    op.create_table(
        "problem_required_skills",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_required_skills"),
        sa.ForeignKeyConstraint(["analysis_id"], ["problem_skill_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("analysis_id", "skill_id", name="uq_required_skills_analysis_skill"),
    )
    op.create_index(
        "ix_required_skills_problem_id", "problem_required_skills", ["problem_id"], unique=False
    )
    op.create_check_constraint(
        "ck_required_skills_score_range",
        "problem_required_skills",
        "score >= 0 AND score <= 1",
    )
    op.create_check_constraint(
        "ck_required_skills_match_type",
        "problem_required_skills",
        f"match_type IN ({MATCH_TYPES})",
    )

    op.add_column(
        "problems",
        sa.Column(
            "priority_status",
            sa.String(20),
            nullable=False,
            server_default="NOT_RUN",
        ),
    )
    op.add_column(
        "problems",
        sa.Column(
            "required_skills_status",
            sa.String(20),
            nullable=False,
            server_default="NOT_RUN",
        ),
    )
    op.create_check_constraint(
        "ck_problems_priority_status", "problems", f"priority_status IN ({ANALYSIS_STATUSES})"
    )
    op.create_check_constraint(
        "ck_problems_skills_status",
        "problems",
        f"required_skills_status IN ({ANALYSIS_STATUSES})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_problems_skills_status", "problems", type_="check")
    op.drop_constraint("ck_problems_priority_status", "problems", type_="check")
    op.drop_column("problems", "required_skills_status")
    op.drop_column("problems", "priority_status")
    op.drop_table("problem_required_skills")
    op.drop_table("problem_skill_analyses")
    op.drop_table("skill_embeddings")
    op.drop_table("problem_priority_analyses")
    # vector extension stays: enabled in 002, may serve future steps.
