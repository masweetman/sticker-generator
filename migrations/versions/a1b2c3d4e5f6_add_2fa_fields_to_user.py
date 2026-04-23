"""add 2FA fields to user

Revision ID: a1b2c3d4e5f6
Revises: 67bda19b7e32
Create Date: 2026-04-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '67bda19b7e32'
branch_labels = None
depends_on = None


def upgrade():
    # Use direct op.add_column (SQLite native ALTER TABLE ADD COLUMN)
    # to avoid Alembic batch-mode circular dependency bug with server_default.
    op.add_column('user', sa.Column('two_factor_enabled', sa.Boolean(),
                                    nullable=False, server_default=sa.false()))
    op.add_column('user', sa.Column('two_factor_secret', sa.String(length=64),
                                    nullable=True))


def downgrade():
    # SQLite does not support DROP COLUMN before 3.35;
    # batch mode is safe for downgrade (no server_default ordering issue).
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('two_factor_secret')
        batch_op.drop_column('two_factor_enabled')
