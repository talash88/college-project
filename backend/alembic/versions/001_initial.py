"""Initial migration - create base tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create uuid extension for UUID primary keys
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    # Note: pgvector extension will be created in a later migration when
    # the pgvector-enabled PostgreSQL image is used.
    # For now, we prepare the schema for future vector columns.


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
