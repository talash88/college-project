"""duplicate_detection

Revision ID: 007
Revises: 006
Create Date: 2026-09-27 00:00:00.000000

Step 7: semantic duplicate detection (problem embeddings, candidates,
clusters, members) + per-problem duplicate status/canonical link.
Does not modify migrations 001-006.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL; plus a harmless
'PROBE_EVENT_X' value from pre-flight verification remains on dev DBs.

"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "DUPLICATE_ANALYSIS_COMPLETED",
    "DUPLICATE_CONFIRMED",
    "DUPLICATE_REJECTED",
    "JOINED_DUPLICATE_CLUSTER",
    "DUPLICATE_CLUSTER_MERGED",
]
DECISION_STATUSES = "'PENDING', 'CONFIRMED_DUPLICATE', 'REJECTED', 'STALE'"
ANALYSIS_STATUSES = (
    "'NOT_RUN', 'PROCESSING', 'COMPLETED', 'FAILED', 'NO_MATCHES', 'POSSIBLE_DUPLICATES'"
)
EMBEDDING_DIM = 384


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
    op.execute("CREATE TYPE duplicate_decision_status AS ENUM (" + DECISION_STATUSES + ")")

    op.create_table(
        "problem_embeddings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_problem_embeddings"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "problem_id", "model_version", name="uq_problem_embeddings_problem_version"
        ),
    )
    op.create_index(
        "ix_problem_embeddings_problem_id", "problem_embeddings", ["problem_id"], unique=False
    )

    op.create_table(
        "problem_duplicate_candidates",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by_problem_id", UUID(as_uuid=True), nullable=True),
        sa.Column("semantic_similarity", sa.Float(), nullable=False),
        sa.Column("location_score", sa.Float(), nullable=True),
        sa.Column("category_support_score", sa.Float(), nullable=True),
        sa.Column("final_match_score", sa.Float(), nullable=False),
        sa.Column(
            "decision_status",
            postgresql.ENUM(
                "PENDING",
                "CONFIRMED_DUPLICATE",
                "REJECTED",
                "STALE",
                name="duplicate_decision_status",
                create_type=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("embedding_version", sa.String(100), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_problem_duplicate_candidates"),
        sa.ForeignKeyConstraint(["source_problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_problem_id"], ["problems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "source_problem_id",
            "candidate_problem_id",
            name="uq_duplicate_candidates_pair",
        ),
    )
    op.create_index(
        "ix_duplicate_candidates_source",
        "problem_duplicate_candidates",
        ["source_problem_id"],
        unique=False,
    )
    op.create_index(
        "ix_duplicate_candidates_candidate",
        "problem_duplicate_candidates",
        ["candidate_problem_id"],
        unique=False,
    )
    op.create_index(
        "ix_duplicate_candidates_status",
        "problem_duplicate_candidates",
        ["decision_status"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_duplicate_candidates_no_self",
        "problem_duplicate_candidates",
        "source_problem_id != candidate_problem_id",
    )
    op.create_check_constraint(
        "ck_duplicate_candidates_similarity_range",
        "problem_duplicate_candidates",
        "semantic_similarity >= 0 AND semantic_similarity <= 1",
    )
    op.create_check_constraint(
        "ck_duplicate_candidates_match_range",
        "problem_duplicate_candidates",
        "final_match_score >= 0 AND final_match_score <= 1",
    )

    op.execute("CREATE SEQUENCE duplicate_cluster_number_seq START 1")
    op.create_table(
        "duplicate_clusters",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("nextval('duplicate_cluster_number_seq')"),
            unique=True,
        ),
        sa.Column("cluster_number", sa.String(20), nullable=True),
        sa.Column("canonical_problem_id", UUID(as_uuid=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_duplicate_clusters"),
        sa.ForeignKeyConstraint(["canonical_problem_id"], ["problems.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("cluster_number", name="uq_duplicate_clusters_number"),
    )
    op.create_index(
        "ix_duplicate_clusters_canonical",
        "duplicate_clusters",
        ["canonical_problem_id"],
        unique=False,
    )

    op.create_table(
        "duplicate_cluster_members",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("is_canonical", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id", name="pk_duplicate_cluster_members"),
        sa.ForeignKeyConstraint(["cluster_id"], ["duplicate_clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("problem_id", name="uq_cluster_members_problem"),
    )
    op.create_index(
        "ix_cluster_members_cluster_id",
        "duplicate_cluster_members",
        ["cluster_id"],
        unique=False,
    )
    # One canonical member per cluster (partial unique index).
    op.create_index(
        "uq_cluster_members_one_canonical",
        "duplicate_cluster_members",
        ["cluster_id"],
        unique=True,
        postgresql_where=sa.text("is_canonical"),
    )

    op.add_column(
        "problems",
        sa.Column("duplicate_status", sa.String(20), nullable=False, server_default="NOT_RUN"),
    )
    op.add_column(
        "problems",
        sa.Column("canonical_problem_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_problems_canonical_problem",
        "problems",
        "problems",
        ["canonical_problem_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_problems_duplicate_status", "problems", f"duplicate_status IN ({ANALYSIS_STATUSES})"
    )


def downgrade() -> None:
    op.drop_constraint("ck_problems_duplicate_status", "problems", type_="check")
    op.drop_constraint("fk_problems_canonical_problem", "problems", type_="foreignkey")
    op.drop_column("problems", "canonical_problem_id")
    op.drop_column("problems", "duplicate_status")
    op.drop_table("duplicate_cluster_members")
    op.drop_table("duplicate_clusters")
    op.execute("DROP SEQUENCE IF EXISTS duplicate_cluster_number_seq")
    op.drop_table("problem_duplicate_candidates")
    op.drop_table("problem_embeddings")
    op.execute("DROP TYPE IF EXISTS duplicate_decision_status")
    # problem_event_type values are append-only by design; not removed here.
