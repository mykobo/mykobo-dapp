"""add nonces table

Revision ID: add_nonces_table
Revises: 8eb63c6edb24
Create Date: 2025-10-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_nonces_table'
down_revision = '8eb63c6edb24'
branch_labels = None
depends_on = None


def upgrade():
    # Create nonces table
    op.create_table('nonces',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('nonce', sa.String(length=255), nullable=False),
    sa.Column('wallet_address', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='dapp'
    )
    with op.batch_alter_table('nonces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dapp_nonces_nonce'), ['nonce'], unique=True)
        batch_op.create_index(batch_op.f('ix_dapp_nonces_wallet_address'), ['wallet_address'], unique=False)
        batch_op.create_index(batch_op.f('ix_dapp_nonces_expires_at'), ['expires_at'], unique=False)


def downgrade():
    with op.batch_alter_table('nonces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dapp_nonces_expires_at'))
        batch_op.drop_index(batch_op.f('ix_dapp_nonces_wallet_address'))
        batch_op.drop_index(batch_op.f('ix_dapp_nonces_nonce'))

    op.drop_table('nonces', schema='dapp')
