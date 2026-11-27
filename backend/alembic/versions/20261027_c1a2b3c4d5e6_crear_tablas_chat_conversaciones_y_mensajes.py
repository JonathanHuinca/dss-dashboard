"""crear_tablas_chat_conversaciones_y_mensajes

Revision ID: c1a2b3c4d5e6
Revises: 8ead4fe84114
Create Date: 2026-10-27 10:50:00.000000-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'c1a2b3c4d5e6'
down_revision = '8ead4fe84114'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_conversaciones',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('espacio_id', sa.Integer(), nullable=False),
        sa.Column('titulo', sa.String(length=255), nullable=False),
        sa.Column('creada_en', mssql.DATETIME2(), nullable=False),
        sa.Column('actualizada_en', mssql.DATETIME2(), nullable=False),
        sa.Column('archivada', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('eliminada_en', mssql.DATETIME2(), nullable=True),
        sa.ForeignKeyConstraint(['espacio_id'], ['espacios.id'], ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_chat_conversaciones_usuario_actualizada',
        'chat_conversaciones',
        ['usuario_id', 'actualizada_en'],
        unique=False
    )

    op.create_table(
        'chat_mensajes',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('conversacion_id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('rol', sa.String(length=20), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('herramienta', sa.String(length=100), nullable=True),
        sa.Column('argumentos_json', sa.Text(), nullable=True),
        sa.Column('modelo', sa.String(length=100), nullable=True),
        sa.Column('creado_en', mssql.DATETIME2(), nullable=False),
        sa.ForeignKeyConstraint(['conversacion_id'], ['chat_conversaciones.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_chat_mensajes_conversacion_creado',
        'chat_mensajes',
        ['conversacion_id', 'creado_en'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_chat_mensajes_conversacion_creado', table_name='chat_mensajes')
    op.drop_table('chat_mensajes')
    op.drop_index('ix_chat_conversaciones_usuario_actualizada', table_name='chat_conversaciones')
    op.drop_table('chat_conversaciones')
