"""auto tax option on document

Revision ID: c9e4a8b2d1f7
Revises: b8d2e4f6a713
Create Date: 2026-10-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e4a8b2d1f7'
down_revision: Union[str, Sequence[str], None] = 'b8d2e4f6a713'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('auto_tax', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    op.drop_column('documents', 'auto_tax')
