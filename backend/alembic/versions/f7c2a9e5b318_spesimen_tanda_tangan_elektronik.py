"""spesimen tanda tangan elektronik

Revision ID: f7c2a9e5b318
Revises: e5b1c7d24a90
Create Date: 2026-10-15 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c2a9e5b318'
down_revision: Union[str, Sequence[str], None] = 'e5b1c7d24a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ('users', 'signatories'):
        op.add_column(table, sa.Column('signature_png', sa.LargeBinary(), nullable=True))
        op.add_column(table, sa.Column('signature_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in ('users', 'signatories'):
        op.drop_column(table, 'signature_updated_at')
        op.drop_column(table, 'signature_png')
