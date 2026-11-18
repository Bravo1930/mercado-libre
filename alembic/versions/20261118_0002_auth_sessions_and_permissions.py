"""Migración de Autenticación, Sesiones Activas, Recuperación y Permisos Multi-Empresa.

Revision ID: 20261118_0002
Revises: 20261117_0001
Create Date: 2026-11-18 00:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20261118_0002'
down_revision: Union[str, None] = '20261117_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Campos de auditoría de login en users
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Campos de control de acceso modular en company_users
    op.add_column('company_users', sa.Column('role', sa.String(length=50), server_default='operator', nullable=False))
    op.add_column('company_users', sa.Column('permissions_json', sa.Text(), nullable=True))
    op.add_column('company_users', sa.Column('restricted_modules_json', sa.Text(), nullable=True))
    op.add_column('company_users', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.create_index('ix_company_users_lookup', 'company_users', ['company_id', 'user_id', 'is_active'])

    # 3. Tabla user_sessions (Trazabilidad y revocación de JWT)
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_jti', sa.String(length=64), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.Column('device_info', sa.String(length=100), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    )
    op.create_index(op.f('ix_user_sessions_token_jti'), 'user_sessions', ['token_jti'], unique=True)
    op.create_index(op.f('ix_user_sessions_is_revoked'), 'user_sessions', ['is_revoked'])
    op.create_index(op.f('ix_user_sessions_expires_at'), 'user_sessions', ['expires_at'])
    op.create_index('ix_user_sessions_active', 'user_sessions', ['user_id', 'is_revoked', 'expires_at'])

    # 4. Tabla password_reset_tokens (Recuperación criptográfica)
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_reset_tokens_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_password_reset_tokens')),
    )
    op.create_index(op.f('ix_password_reset_tokens_token_hash'), 'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_password_reset_tokens_is_used'), 'password_reset_tokens', ['is_used'])
    op.create_index('ix_pwd_reset_active', 'password_reset_tokens', ['token_hash', 'is_used', 'expires_at'])

    # 5. Permitir company_id nullable en audit_logs para registrar eventos de autenticación
    op.alter_column('audit_logs', 'company_id', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column('audit_logs', 'company_id', existing_type=sa.UUID(), nullable=False)
    op.drop_table('password_reset_tokens')
    op.drop_table('user_sessions')
    op.drop_index('ix_company_users_lookup', table_name='company_users')
    op.drop_column('company_users', 'is_active')
    op.drop_column('company_users', 'restricted_modules_json')
    op.drop_column('company_users', 'permissions_json')
    op.drop_column('company_users', 'role')
    op.drop_column('users', 'last_login_at')
