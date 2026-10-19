"""logo klien di kop voucher (feedback owner)

Revision ID: c7d2e9f4a1b6
Revises: b3e8f1a2c4d5
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d2e9f4a1b6'
down_revision: Union[str, Sequence[str], None] = 'b3e8f1a2c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('logo_png', sa.LargeBinary(), nullable=True))
    op.add_column('clients', sa.Column('logo_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'logo_updated_at')
    op.drop_column('clients', 'logo_png')
