"""banyak invoice dalam satu PDF: rentang halaman per bukti

Revision ID: b8d2e4f6a713
Revises: a6e3c9d2f415
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d2e4f6a713'
down_revision: Union[str, Sequence[str], None] = 'a6e3c9d2f415'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bukti lama tetap 1 file = 1 bukti (kolom kosong = seluruh file, belum dipindai per invoice)
    op.add_column('document_files', sa.Column('upload_key', sa.String(500), nullable=True))
    op.add_column('document_files', sa.Column('page_from', sa.SmallInteger(), nullable=True))
    op.add_column('document_files', sa.Column('page_to', sa.SmallInteger(), nullable=True))
    op.add_column('document_files', sa.Column('upload_pages', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('document_files', 'upload_pages')
    op.drop_column('document_files', 'page_to')
    op.drop_column('document_files', 'page_from')
    op.drop_column('document_files', 'upload_key')
