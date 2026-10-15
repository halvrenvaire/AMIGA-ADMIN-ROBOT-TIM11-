"""kode kendala NOT_AN_INVOICE

Revision ID: 0b35d6dc8b74
Revises: 04b0de42b387
Create Date: 2026-10-15 08:50:47.080504

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b35d6dc8b74'
down_revision: Union[str, Sequence[str], None] = '04b0de42b387'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """PDF yang dinilai AI bukan invoice."""
    op.execute("ALTER TYPE issue_code ADD VALUE IF NOT EXISTS 'NOT_AN_INVOICE'")


def downgrade() -> None:
    """PostgreSQL tidak bisa menghapus nilai enum; nilai dibiarkan."""
