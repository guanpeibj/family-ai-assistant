"""add household and member tables

Revision ID: 20250923_households
Revises: 20250314_generated_columns
Create Date: 2025-09-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20250923_households'
down_revision = '20250314_generated_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'family_households',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index('ix_family_households_slug', 'family_households', ['slug'], unique=True)

    op.create_table(
        'family_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('household_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('member_key', sa.String(length=128), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('relationship', sa.String(length=64), nullable=True),
        sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['household_id'], ['family_households.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('household_id', 'member_key', name='uq_family_member_household_key'),
    )
    op.create_index('ix_family_members_household_id', 'family_members', ['household_id'])

    op.create_table(
        'family_member_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('member_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(['member_id'], ['family_members.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('member_id', 'user_id', name='uq_family_member_user'),
    )
    op.create_index('ix_family_member_accounts_member_id', 'family_member_accounts', ['member_id'])
    op.create_index('ix_family_member_accounts_user_id', 'family_member_accounts', ['user_id'])


def downgrade():
    op.drop_index('ix_family_member_accounts_user_id', table_name='family_member_accounts')
    op.drop_index('ix_family_member_accounts_member_id', table_name='family_member_accounts')
    op.drop_table('family_member_accounts')

    op.drop_index('ix_family_members_household_id', table_name='family_members')
    op.drop_table('family_members')

    op.drop_index('ix_family_households_slug', table_name='family_households')
    op.drop_table('family_households')
