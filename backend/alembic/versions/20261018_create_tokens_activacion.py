"""Crear tabla tokens_activacion para ciclo Zero-Plaintext (RF27)

Revision ID: d4e5f6a7b803
Revises: c3d4e5f6a702
Create Date: 2026-10-18 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores de revision Alembic
revision: str = 'd4e5f6a7b803'
down_revision: Union[str, None] = 'c3d4e5f6a702'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tokens_activacion',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('tipo_token', sa.String(length=30), nullable=False, server_default='ACTIVACION_INICIAL'),
        sa.Column('expira_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('utilizado', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('fecha_utilizacion', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_solicitante', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_tokens_activacion_usuario_id', 'tokens_activacion', ['usuario_id'])
    op.create_index('ix_tokens_activacion_token_hash', 'tokens_activacion', ['token_hash'])


def downgrade() -> None:
    op.drop_index('ix_tokens_activacion_token_hash', table_name='tokens_activacion')
    op.drop_index('ix_tokens_activacion_usuario_id', table_name='tokens_activacion')
    op.drop_table('tokens_activacion')
