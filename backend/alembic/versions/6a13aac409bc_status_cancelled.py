"""status CANCELLED

Revision ID: 6a13aac409bc
Revises: 0b35d6dc8b74
Create Date: 2026-10-15 12:07:56.964346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a13aac409bc'
down_revision: Union[str, Sequence[str], None] = '0b35d6dc8b74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Pengajuan yang dibatalkan pengaju."""
    op.execute("ALTER TYPE doc_status ADD VALUE IF NOT EXISTS 'CANCELLED'")


def downgrade() -> None:
    """PostgreSQL tidak bisa menghapus nilai enum; nilai dibiarkan."""
