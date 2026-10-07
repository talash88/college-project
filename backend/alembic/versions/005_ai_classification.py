"""ai_classification

Revision ID: 005
Revises: 004
Create Date: 2026-09-27 00:00:00.000000

Step 5: problem classification audit table + classification_status cache
column on problems. Does not modify migrations 001-004.

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

CLASSIFICATION_STATUSES = [
    "NOT_RUN",
    "PROCESSING",
    "COMPLETED",
    "LOW_CONFIDENCE",
    "FAILED",
]


def upgrade() -> None:
    op.execute(
        "CREATE TYPE problem_classification_status AS ENUM ("
        + ", ".join(f"'{s}'" for s in CLASSIFICATION_STATUSES)
        + ")"
    )

    op.create_table(
        "problem_classifications",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("predicted_category", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *CLASSIFICATION_STATUSES,
                name="problem_classification_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("requires_manual_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_category", sa.String(50), nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_problem_classifications"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_problem_classifications_problem_id",
        "problem_classifications",
        ["problem_id"],
        unique=False,
    )
    op.create_index(
        "ix_problem_classifications_created_at",
        "problem_classifications",
        ["created_at"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_classifications_confidence_range",
        "problem_classifications",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )

    op.add_column(
        "problems",
        sa.Column(
            "classification_status",
            postgresql.ENUM(
                *CLASSIFICATION_STATUSES,
                name="problem_classification_status",
                create_type=False,
            ),
            nullable=False,
            server_default="NOT_RUN",
        ),
    )


def downgrade() -> None:
    op.drop_column("problems", "classification_status")
    op.drop_table("problem_classifications")
    op.execute("DROP TYPE IF EXISTS problem_classification_status")
