"""Normalizar jerarquia RBAC de 4 roles, banderas modulares y administracion delegada (RF22)

Revision ID: c3d4e5f6a702
Revises: b2c3d4e5f601
Create Date: 2026-10-18 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores de revision Alembic
revision = 'c3d4e5f6a702'
down_revision = 'b2c3d4e5f601'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Banderas de permisos modulares y campos de administracion delegada en tabla usuarios
    op.add_column('usuarios', sa.Column('can_use_ai', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('usuarios', sa.Column('can_export', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('usuarios', sa.Column('can_ingest', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('usuarios', sa.Column('espacio_id', sa.Integer(), nullable=True))
    op.add_column('usuarios', sa.Column('created_by_user_id', sa.Integer(), nullable=True))

    # Claves foraneas en usuarios
    op.create_foreign_key('fk_usuarios_espacio_id', 'usuarios', 'espacios', ['espacio_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_usuarios_created_by', 'usuarios', 'usuarios', ['created_by_user_id'], ['id'])

    # 2. Normalizacion de roles institucionales en tabla roles
    conn = op.get_bind()

    # Actualizar o insertar Admin_Sistema
    conn.execute(sa.text("""
        IF EXISTS (SELECT 1 FROM roles WHERE nombre = 'SuperAdmin')
            UPDATE roles 
            SET nombre = 'Admin_Sistema', 
                descripcion = 'SuperAdmin técnico global con control total de la plataforma y administración de usuarios',
                rate_limit_quota = '1000/day'
            WHERE nombre = 'SuperAdmin';
        ELSE IF NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Admin_Sistema')
            INSERT INTO roles (nombre, descripcion, rate_limit_quota)
            VALUES ('Admin_Sistema', 'SuperAdmin técnico global con control total de la plataforma y administración de usuarios', '1000/day');
    """))

    # Actualizar o insertar Director_Recinto
    conn.execute(sa.text("""
        IF EXISTS (SELECT 1 FROM roles WHERE nombre = 'Directivo')
            UPDATE roles 
            SET nombre = 'Director_Recinto', 
                descripcion = 'Jefatura de espacio físico asignado con administración delegada de analistas y guardias',
                rate_limit_quota = '500/day'
            WHERE nombre = 'Directivo';
        ELSE IF NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Director_Recinto')
            INSERT INTO roles (nombre, descripcion, rate_limit_quota)
            VALUES ('Director_Recinto', 'Jefatura de espacio físico asignado con administración delegada de analistas y guardias', '500/day');
    """))

    # Insertar Analista_Consulta
    conn.execute(sa.text("""
        IF NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Analista_Consulta')
            INSERT INTO roles (nombre, descripcion, rate_limit_quota)
            VALUES ('Analista_Consulta', 'Decanos, directores de carrera y analistas con acceso a dashboards y modelos analíticos', '200/day');
    """))

    # Asegurar Guardia_Seguridad
    conn.execute(sa.text("""
        IF NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'Guardia_Seguridad')
            INSERT INTO roles (nombre, descripcion, rate_limit_quota)
            VALUES ('Guardia_Seguridad', 'Operador en terreno para monitoreo operativo de aforos y tránsito en su recinto asignado', '50/day');
        ELSE
            UPDATE roles 
            SET descripcion = 'Operador en terreno para monitoreo operativo de aforos y tránsito en su recinto asignado',
                rate_limit_quota = '50/day'
            WHERE nombre = 'Guardia_Seguridad';
    """))

    # 3. Asignar permisos por omision a cuentas existentes
    # Admin_Sistema: can_use_ai=1, can_export=1, can_ingest=1
    conn.execute(sa.text("""
        UPDATE u
        SET u.can_use_ai = 1, u.can_export = 1, u.can_ingest = 1
        FROM usuarios u
        JOIN usuarios_roles ur ON u.id = ur.usuario_id
        JOIN roles r ON ur.rol_id = r.id
        WHERE r.nombre = 'Admin_Sistema';
    """))

    # Director_Recinto: can_use_ai=1, can_export=1, can_ingest=1, espacio_id=1 por defecto
    conn.execute(sa.text("""
        UPDATE u
        SET u.can_use_ai = 1, u.can_export = 1, u.can_ingest = 1, u.espacio_id = ISNULL(u.espacio_id, 1)
        FROM usuarios u
        JOIN usuarios_roles ur ON u.id = ur.usuario_id
        JOIN roles r ON ur.rol_id = r.id
        WHERE r.nombre = 'Director_Recinto';
    """))

    # Guardia_Seguridad: espacio_id=1 por defecto
    conn.execute(sa.text("""
        UPDATE u
        SET u.can_use_ai = 0, u.can_export = 0, u.can_ingest = 0, u.espacio_id = ISNULL(u.espacio_id, 1)
        FROM usuarios u
        JOIN usuarios_roles ur ON u.id = ur.usuario_id
        JOIN roles r ON ur.rol_id = r.id
        WHERE r.nombre = 'Guardia_Seguridad';
    """))


def downgrade() -> None:
    op.drop_constraint('fk_usuarios_created_by', 'usuarios', type_='foreignkey')
    op.drop_constraint('fk_usuarios_espacio_id', 'usuarios', type_='foreignkey')
    op.drop_column('usuarios', 'created_by_user_id')
    op.drop_column('usuarios', 'espacio_id')
    op.drop_column('usuarios', 'can_ingest')
    op.drop_column('usuarios', 'can_export')
    op.drop_column('usuarios', 'can_use_ai')
