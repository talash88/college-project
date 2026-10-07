"""knowledge_repository

Revision ID: 012
Revises: 011
Create Date: 2026-10-07 00:00:00.000000

Step 12: institutional Knowledge Repository fed ONLY by real verified solved
problems (CLOSED + mentor-approved final solution + reporter-confirmed
RESOLVED). Does not modify migrations 001-011.

Tables:
- knowledge_entries: publication snapshot of one closed problem (one official
  active entry per source problem via unique problem_id).
- knowledge_entry_skills: Skill taxonomy rows referenced by an entry.
- knowledge_embeddings: 384-dim pgvector embedding of the entry text.

Also adds problem_work_attachments.is_knowledge_shareable (default False):
only final-solution evidence explicitly flagged shareable may be published.

Note: ALTER TYPE ... ADD VALUE was verified to run inside this project's
transactional migrations on the target PostgreSQL.

"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

NEW_EVENT_VALUES = [
    "KNOWLEDGE_ENTRY_PUBLISHED",
    "KNOWLEDGE_PUBLICATION_FAILED",
    "KNOWLEDGE_ENTRY_ARCHIVED",
    "KNOWLEDGE_ENTRY_REPUBLISHED",
]

PUBLICATION_STATUSES = "'PENDING', 'PUBLISHED', 'FAILED', 'ARCHIVED'"
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

    op.execute("CREATE SEQUENCE IF NOT EXISTS knowledge_entry_number_seq START 1")

    op.create_table(
        "knowledge_entries",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entry_number", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("problem_summary", sa.Text(), nullable=False),
        sa.Column("final_category", sa.String(50), nullable=True),
        sa.Column("location_summary", sa.String(500), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("solution_summary", sa.Text(), nullable=False),
        sa.Column("work_performed", sa.Text(), nullable=False),
        sa.Column("testing_performed", sa.Text(), nullable=True),
        sa.Column("deployment_notes", sa.Text(), nullable=True),
        sa.Column("known_limitations", sa.Text(), nullable=True),
        sa.Column("resolution_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("team_names", JSONB(), nullable=False, server_default="[]"),
        sa.Column("mentor_name", sa.String(200), nullable=True),
        sa.Column("mentor_designation", sa.String(200), nullable=True),
        sa.Column("evidence_files", JSONB(), nullable=False, server_default="[]"),
        sa.Column("publication_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source_solution_submission_id", UUID(as_uuid=True), nullable=False
        ),
        sa.Column("source_text_hash", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_solution_submission_id"],
            ["problem_solution_submissions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id", name="uq_knowledge_entries_problem_id"),
        sa.UniqueConstraint("public_id", name="uq_knowledge_entries_public_id"),
        sa.CheckConstraint(
            f"publication_status IN ({PUBLICATION_STATUSES})",
            name="ck_knowledge_entries_status",
        ),
        sa.CheckConstraint(
            "char_length(title) >= 5", name="ck_knowledge_entries_title_min"
        ),
    )
    op.create_index("ix_knowledge_entries_problem_id", "knowledge_entries", ["problem_id"])
    op.create_index(
        "ix_knowledge_entries_status", "knowledge_entries", ["publication_status"]
    )
    op.create_index(
        "ix_knowledge_entries_published_at", "knowledge_entries", ["published_at"]
    )
    op.create_index(
        "ix_knowledge_entries_category", "knowledge_entries", ["final_category"]
    )

    op.create_table(
        "knowledge_entry_skills",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=True), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_entry_id"], ["knowledge_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_entry_id", "skill_id", name="uq_knowledge_entry_skills_pair"
        ),
    )
    op.create_index(
        "ix_knowledge_entry_skills_entry_id", "knowledge_entry_skills", ["knowledge_entry_id"]
    )
    op.create_index(
        "ix_knowledge_entry_skills_skill_id", "knowledge_entry_skills", ["skill_id"]
    )

    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_version", sa.String(100), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_entry_id"], ["knowledge_entries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_entry_id", name="uq_knowledge_embeddings_entry_id"
        ),
    )
    op.create_index(
        "ix_knowledge_embeddings_entry_id", "knowledge_embeddings", ["knowledge_entry_id"]
    )

    op.add_column(
        "problem_work_attachments",
        sa.Column(
            "is_knowledge_shareable",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("problem_work_attachments", "is_knowledge_shareable")
    op.drop_table("knowledge_embeddings")
    op.drop_table("knowledge_entry_skills")
    op.drop_table("knowledge_entries")
    op.execute("DROP SEQUENCE IF EXISTS knowledge_entry_number_seq")
    # problem_event_type values are append-only by design; not removed here.
