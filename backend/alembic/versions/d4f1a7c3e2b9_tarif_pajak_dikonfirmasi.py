"""tarif pajak PPh 21, 23, 4 ayat 2 dikonfirmasi (Tahap 5)

Revision ID: d4f1a7c3e2b9
Revises: c7d2e9f4a1b6
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd4f1a7c3e2b9'
down_revision: Union[str, Sequence[str], None] = 'c7d2e9f4a1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PPH26_OLD = ("Pembayaran ke pihak luar negeri. 20% atau sesuai tax treaty (P3B) bila ada SKD.")
PPH26_NEW = ("Pembayaran ke pihak luar negeri. 20% atau sesuai tax treaty (P3B) bila ada SKD. "
             "Belum dikonfirmasi: owner menulis \"Ppn 26 (luar negeri)\", artinya PPh 26 atau PPN luar negeri.")


def upgrade() -> None:
    # Keputusan tim 20 Okt 2026: tarif awal PPh 21, 23, dan 4 ayat 2 sudah benar (Tanpa potongan selalu 0%)
    op.execute("UPDATE tax_rates SET needs_confirmation = false WHERE code IN ('NONE', 'PPH21', 'PPH23', 'PPH4_2')")
    op.execute(f"UPDATE tax_rates SET description = $${PPH26_NEW}$$ WHERE code = 'PPH26' AND description = $${PPH26_OLD}$$")


def downgrade() -> None:
    op.execute("UPDATE tax_rates SET needs_confirmation = true WHERE code IN ('NONE', 'PPH21', 'PPH23', 'PPH4_2')")
    op.execute(f"UPDATE tax_rates SET description = $${PPH26_OLD}$$ WHERE code = 'PPH26' AND description = $${PPH26_NEW}$$")
