"""saluran pengajuan dan isian perbaikan PIC di documents

Revision ID: d3a8f61b2c47
Revises: b7e2d4c91a05
Create Date: 2026-10-14 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd3a8f61b2c47'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4c91a05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('channel', sa.String(length=30), nullable=True))
    op.add_column('documents', sa.Column('pic_overrides', postgresql.JSONB(astext_type=sa.Text()),
                                         server_default='{}', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'pic_overrides')
    op.drop_column('documents', 'channel')
