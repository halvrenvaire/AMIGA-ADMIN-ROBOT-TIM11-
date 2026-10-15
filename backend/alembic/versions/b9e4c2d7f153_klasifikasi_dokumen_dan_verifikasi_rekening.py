"""klasifikasi dokumen dan verifikasi rekening vendor

Revision ID: b9e4c2d7f153
Revises: a8d3f1c6e027
Create Date: 2026-10-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e4c2d7f153'
down_revision: Union[str, Sequence[str], None] = 'a8d3f1c6e027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for code in ('RECEIPT_NOT_INVOICE', 'NEEDS_MANUAL_REVIEW', 'ACCOUNT_MISMATCH'):
        op.execute(f"ALTER TYPE issue_code ADD VALUE IF NOT EXISTS '{code}'")
    op.add_column('vendors', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vendors', sa.Column('verified_by', sa.UUID(), nullable=True))
    op.create_foreign_key('vendors_verified_by_fkey', 'vendors', 'users', ['verified_by'], ['id'])
    op.add_column('vendors', sa.Column('bank_updated_by', sa.UUID(), nullable=True))
    op.create_foreign_key('vendors_bank_updated_by_fkey', 'vendors', 'users', ['bank_updated_by'], ['id'])


def downgrade() -> None:
    """Nilai enum tidak bisa dihapus di PostgreSQL; dibiarkan."""
    op.drop_constraint('vendors_bank_updated_by_fkey', 'vendors', type_='foreignkey')
    op.drop_column('vendors', 'bank_updated_by')
    op.drop_constraint('vendors_verified_by_fkey', 'vendors', type_='foreignkey')
    op.drop_column('vendors', 'verified_by')
    op.drop_column('vendors', 'verified_at')
