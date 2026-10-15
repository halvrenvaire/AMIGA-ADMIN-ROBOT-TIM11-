"""waktu selesai baca per file

Revision ID: a8d3f1c6e027
Revises: f7c2a9e5b318
Create Date: 2026-10-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d3f1c6e027'
down_revision: Union[str, Sequence[str], None] = 'f7c2a9e5b318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_files', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('document_files', 'read_at')
