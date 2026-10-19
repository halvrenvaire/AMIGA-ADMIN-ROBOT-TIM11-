"""kategori pengajuan voucher pengeluaran

Revision ID: da9b4276d328
Revises: 22a5edb97ab1
Create Date: 2026-10-19 14:52:34.734221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da9b4276d328'
down_revision: Union[str, Sequence[str], None] = '22a5edb97ab1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Jenis permintaan teks bebas lama dipetakan ke kategori baru (feedback owner)."""
    op.execute("""
        UPDATE documents SET request_type = CASE
            WHEN request_type IN ('Voucher Pengeluaran Vendor', 'Voucher Pengeluaran Reimburse', 'Lainnya') THEN request_type
            WHEN lower(coalesce(request_type, '')) LIKE '%reimburs%' THEN 'Voucher Pengeluaran Reimburse'
            WHEN request_type IS NULL OR lower(request_type) LIKE '%vendor%' THEN 'Voucher Pengeluaran Vendor'
            ELSE 'Lainnya' END
    """)


def downgrade() -> None:
    """Nilai lama tidak dikembalikan (pemetaan satu arah)."""
