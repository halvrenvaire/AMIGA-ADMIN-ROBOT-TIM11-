"""peran ganda: tabel user_roles menggantikan kolom users.role

Revision ID: b7e2d4c91a05
Revises: a5a345fe32b3
Create Date: 2026-10-14 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7e2d4c91a05'
down_revision: Union[str, Sequence[str], None] = 'a5a345fe32b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tipe enum user_role sudah dibuat di skema awal; dipakai ulang tanpa CREATE TYPE
user_role = postgresql.ENUM(
    'PIC_KLIEN', 'INTAKE_SUPPORT', 'FINANCE_REVIEWER', 'SERVICE_LEAD', 'SYSTEM_ADMIN',
    name='user_role', create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_roles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', user_role, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'role')
    )
    # Pindahkan peran tunggal yang sudah ada
    op.execute("INSERT INTO user_roles (user_id, role) SELECT id, role FROM users")
    op.drop_column('users', 'role')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('role', user_role, nullable=True))
    # Peran ganda tidak bisa disimpan di satu kolom: ambil satu peran per pengguna
    op.execute("""
        UPDATE users u SET role = r.role
        FROM (SELECT DISTINCT ON (user_id) user_id, role FROM user_roles ORDER BY user_id, role) r
        WHERE r.user_id = u.id
    """)
    op.alter_column('users', 'role', nullable=False)
    op.drop_table('user_roles')
