"""add generated columns for extracted fields

Revision ID: 20250314_generated_columns
Revises: 20250118_01
Create Date: 2025-03-14

"""
from alembic import op

revision = '20250314_generated_columns'
down_revision = '20250118_01'
branch_labels = None
depends_on = None


def upgrade():
    stmts = [
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS thread_id_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'thread_id')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS type_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'type')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS category_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'category')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS person_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'person')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS metric_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'metric')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS subject_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'subject')) STORED",
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_extracted TEXT GENERATED ALWAYS AS ((ai_understanding->>'source')) STORED",
        (
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS value_extracted NUMERIC GENERATED ALWAYS AS ("
            "CASE WHEN (ai_understanding->>'value') ~ '^-?\\d+(?:\\.\\d+)?$'"
            " THEN (ai_understanding->>'value')::numeric ELSE NULL END) STORED"
        ),
    ]
    for stmt in stmts:
        op.execute(stmt)


def downgrade():
    stmts = [
        "ALTER TABLE memories DROP COLUMN IF EXISTS value_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS source_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS subject_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS metric_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS person_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS category_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS type_extracted",
        "ALTER TABLE memories DROP COLUMN IF EXISTS thread_id_extracted",
    ]
    for stmt in stmts:
        op.execute(stmt)
