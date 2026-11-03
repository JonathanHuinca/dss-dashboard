"""Add chat_audit_logs table

Revision ID: a7f8e91d2c3b
Revises: d55f159711e2
Create Date: 2026-10-09 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'a7f8e91d2c3b'
down_revision = 'd55f159711e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('prompt_text', sa.Text(), nullable=False),
        sa.Column('dataset_tipo', sa.String(length=50), nullable=True),
        sa.Column('modelo_utilizado', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_time_ms', sa.Float(), nullable=True),
        sa.Column('timestamp', mssql.DATETIME2(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_audit_logs_usuario_id'), 'chat_audit_logs', ['usuario_id'], unique=False)
    op.create_index(op.f('ix_chat_audit_logs_dataset_tipo'), 'chat_audit_logs', ['dataset_tipo'], unique=False)
    op.create_index(op.f('ix_chat_audit_logs_timestamp'), 'chat_audit_logs', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_chat_audit_logs_timestamp'), table_name='chat_audit_logs')
    op.drop_index(op.f('ix_chat_audit_logs_dataset_tipo'), table_name='chat_audit_logs')
    op.drop_index(op.f('ix_chat_audit_logs_usuario_id'), table_name='chat_audit_logs')
    op.drop_table('chat_audit_logs')
