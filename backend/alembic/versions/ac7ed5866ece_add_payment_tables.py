"""add payment tables

Revision ID: ac7ed5866ece
Revises: c4a5b6d7e8f9
Create Date: 2026-09-09 13:03:15.368594
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac7ed5866ece'
down_revision: Union[str, None] = 'c4a5b6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='disconnected'),
        sa.Column('environment', sa.String(length=20), nullable=False, server_default='sandbox'),
        sa.Column('client_id_encrypted', sa.Text(), nullable=True),
        sa.Column('client_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('webhook_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('merchant_reference', sa.String(length=255), nullable=True),
        sa.Column('last_event_id', sa.String(length=255), nullable=True),
        sa.Column('last_event_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('connected_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'provider', name='uq_payment_connection_store_provider'),
    )
    op.create_index('ix_payment_connections_organization_id', 'payment_connections', ['organization_id'])
    op.create_index('ix_payment_connections_store_id', 'payment_connections', ['store_id'])
    op.create_index('ix_payment_connections_provider', 'payment_connections', ['provider'])
    op.create_index('ix_payment_connections_status', 'payment_connections', ['status'])

    op.create_table(
        'payment_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('provider_transaction_id', sa.String(length=255), nullable=True),
        sa.Column('merchant_reference', sa.String(length=255), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('payment_method', sa.String(length=50), nullable=False),
        sa.Column('customer_phone', sa.String(length=50), nullable=True),
        sa.Column('provider_status', sa.String(length=100), nullable=True),
        sa.Column('provider_error_code', sa.String(length=100), nullable=True),
        sa.Column('provider_error_message', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('reversed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_payment_txn_org_idempotency'),
    )
    op.create_index('ix_payment_transactions_organization_id', 'payment_transactions', ['organization_id'])
    op.create_index('ix_payment_transactions_store_id', 'payment_transactions', ['store_id'])
    op.create_index('ix_payment_transactions_order_id', 'payment_transactions', ['order_id'])
    op.create_index('ix_payment_transactions_provider', 'payment_transactions', ['provider'])
    op.create_index('ix_payment_transactions_status', 'payment_transactions', ['status'])
    op.create_index('ix_payment_txn_provider_txn_id', 'payment_transactions', ['provider', 'provider_transaction_id'])


def downgrade() -> None:
    op.drop_table('payment_transactions')
    op.drop_table('payment_connections')
