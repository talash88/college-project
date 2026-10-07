"""users_profiles_skills

Revision ID: 002
Revises: 001
Create Date: 2026-09-25 22:42:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE user_role AS ENUM ('REPORTER', 'SOLVER', 'MENTOR', 'ADMIN')")
    op.execute("CREATE TYPE department AS ENUM ('Computer Science & Engineering', 'Information Technology', 'Electronics', 'Electrical', 'Mechanical', 'Civil', 'Administration', 'Other')")
    op.execute("CREATE TYPE availability_status AS ENUM ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')")
    op.execute("CREATE TYPE skill_category AS ENUM ('Software Development', 'AI / Data', 'Infrastructure / Networking', 'Hardware / Campus Technical', 'Design', 'General')")
    op.execute("CREATE TYPE proficiency_level AS ENUM ('1', '2', '3', '4', '5')")

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),  # Use String, constraint via check
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_users'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_email_lower', 'users', ['email'], unique=False, postgresql_ops={'email': 'text_pattern_ops'})
    op.create_check_constraint('ck_users_role', 'users', "role IN ('REPORTER', 'SOLVER', 'MENTOR', 'ADMIN')")

    # Create student_profiles table
    op.create_table(
        'student_profiles',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_identifier', sa.String(50), nullable=False),
        sa.Column('department', sa.String(50), nullable=False),  # Use String, constraint via check
        sa.Column('academic_year', sa.Integer(), nullable=False),
        sa.Column('semester', sa.Integer(), nullable=True),
        sa.Column('bio', sa.String(2000), nullable=True),
        sa.Column('availability_status', sa.String(20), nullable=False, server_default='AVAILABLE'),
        sa.Column('current_workload', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_workload', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_student_profiles'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_student_profiles_user_id'),
        sa.UniqueConstraint('student_identifier', name='uq_student_profiles_student_identifier'),
    )
    op.create_index('ix_student_profiles_department', 'student_profiles', ['department'], unique=False)
    op.create_index('ix_student_profiles_availability', 'student_profiles', ['availability_status'], unique=False)
    op.create_index('ix_student_profiles_student_identifier', 'student_profiles', ['student_identifier'], unique=True)
    op.create_check_constraint('ck_student_profiles_current_workload_nonneg', 'student_profiles', 'current_workload >= 0')
    op.create_check_constraint('ck_student_profiles_max_workload_pos', 'student_profiles', 'max_workload > 0')
    op.create_check_constraint('ck_student_profiles_workload_valid', 'student_profiles', 'current_workload <= max_workload')
    op.create_check_constraint('ck_student_profiles_department', 'student_profiles', "department IN ('Computer Science & Engineering', 'Information Technology', 'Electronics', 'Electrical', 'Mechanical', 'Civil', 'Administration', 'Other')")
    op.create_check_constraint('ck_student_profiles_availability', 'student_profiles', "availability_status IN ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')")

    # Create faculty_profiles table
    op.create_table(
        'faculty_profiles',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('employee_identifier', sa.String(50), nullable=False),
        sa.Column('department', sa.String(50), nullable=False),
        sa.Column('designation', sa.String(100), nullable=False),
        sa.Column('specialization', sa.String(500), nullable=False),
        sa.Column('bio', sa.String(2000), nullable=True),
        sa.Column('availability_status', sa.String(20), nullable=False, server_default='AVAILABLE'),
        sa.Column('current_workload', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_workload', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_faculty_profiles'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_faculty_profiles_user_id'),
        sa.UniqueConstraint('employee_identifier', name='uq_faculty_profiles_employee_identifier'),
    )
    op.create_index('ix_faculty_profiles_department', 'faculty_profiles', ['department'], unique=False)
    op.create_index('ix_faculty_profiles_availability', 'faculty_profiles', ['availability_status'], unique=False)
    op.create_index('ix_faculty_profiles_employee_identifier', 'faculty_profiles', ['employee_identifier'], unique=True)
    op.create_check_constraint('ck_faculty_profiles_current_workload_nonneg', 'faculty_profiles', 'current_workload >= 0')
    op.create_check_constraint('ck_faculty_profiles_max_workload_pos', 'faculty_profiles', 'max_workload > 0')
    op.create_check_constraint('ck_faculty_profiles_workload_valid', 'faculty_profiles', 'current_workload <= max_workload')
    op.create_check_constraint('ck_faculty_profiles_department', 'faculty_profiles', "department IN ('Computer Science & Engineering', 'Information Technology', 'Electronics', 'Electrical', 'Mechanical', 'Civil', 'Administration', 'Other')")
    op.create_check_constraint('ck_faculty_profiles_availability', 'faculty_profiles', "availability_status IN ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')")

    # Create skills table
    op.create_table(
        'skills',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('normalized_name', sa.String(100), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_skills'),
        sa.UniqueConstraint('normalized_name', name='uq_skills_normalized_name'),
    )
    op.create_index('ix_skills_category', 'skills', ['category'], unique=False)
    op.create_index('ix_skills_is_active', 'skills', ['is_active'], unique=False)
    op.create_index('ix_skills_normalized_name', 'skills', ['normalized_name'], unique=True)
    op.create_check_constraint('ck_skills_category', 'skills', "category IN ('Software Development', 'AI / Data', 'Infrastructure / Networking', 'Hardware / Campus Technical', 'Design', 'General')")

    # Create user_skills table
    op.create_table(
        'user_skills',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('skill_id', UUID(as_uuid=True), nullable=False),
        sa.Column('proficiency_level', sa.Integer(), nullable=False),
        sa.Column('years_experience', sa.Integer(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name='pk_user_skills'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'skill_id', name='uq_user_skills_user_skill'),
    )
    op.create_index('ix_user_skills_user_id', 'user_skills', ['user_id'], unique=False)
    op.create_index('ix_user_skills_skill_id', 'user_skills', ['skill_id'], unique=False)
    op.create_index('ix_user_skills_proficiency', 'user_skills', ['proficiency_level'], unique=False)
    op.create_check_constraint('ck_user_skills_proficiency_range', 'user_skills', 'proficiency_level BETWEEN 1 AND 5')
    op.create_check_constraint('ck_user_skills_years_exp_nonneg', 'user_skills', 'years_experience >= 0')

    # Enable pgvector extension (will work with pgvector image)
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS vector')
    op.drop_table('user_skills')
    op.drop_table('skills')
    op.drop_table('faculty_profiles')
    op.drop_table('student_profiles')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS proficiency_level")
    op.execute("DROP TYPE IF EXISTS skill_category")
    op.execute("DROP TYPE IF EXISTS availability_status")
    op.execute("DROP TYPE IF EXISTS department")
    op.execute("DROP TYPE IF EXISTS user_role")
