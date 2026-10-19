"""tarif pajak (Tahap 4 feedback owner)

Revision ID: b3e8f1a2c4d5
Revises: 0d4aa4ac8523
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b3e8f1a2c4d5'
down_revision: Union[str, Sequence[str], None] = '0d4aa4ac8523'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Isi awal memakai aturan umum; semuanya ditandai "perlu dikonfirmasi konsultan pajak"
DEFAULT_RATES = [
    ("NONE", "Tanpa potongan", "Pembelian barang biasa, reimburse karyawan, atau tagihan yang tidak dipotong PPh.",
     0, 0, 0),
    ("PPH23", "PPh 23", "Jasa oleh badan usaha (konsultan, sewa alat/kendaraan, perbaikan, kebersihan, dll.). "
     "Tanpa NPWP: dua kali lipat.", 2, 4, 1),
    ("PPH21", "PPh 21 (non final)", "Honor atau jasa oleh orang pribadi bukan pegawai. Isi awal: 50% x tarif "
     "terendah Pasal 17 (5%) = 2,5%; tanpa NPWP 20% lebih tinggi.", 2.5, 3, 2),
    ("PPH4_2", "PPh 4 ayat 2 (final)", "Sewa tanah/bangunan (10%). Jasa konstruksi memakai tarif lain sesuai "
     "kualifikasi; ubah tarif per invoice bila perlu.", 10, 10, 3),
    ("PPH26", "PPh 26 (luar negeri)", "Pembayaran ke pihak luar negeri. 20% atau sesuai tax treaty (P3B) bila "
     "ada SKD.", 20, 20, 4),
]


def upgrade() -> None:
    table = op.create_table(
        'tax_rates',
        sa.Column('code', sa.String(length=20), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rate_npwp', sa.Numeric(6, 3), nullable=False),
        sa.Column('rate_no_npwp', sa.Numeric(6, 3), nullable=False),
        sa.Column('position', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('needs_confirmation', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(table, [
        {"code": c, "name": n, "description": d, "rate_npwp": r1, "rate_no_npwp": r2, "position": p}
        for c, n, d, r1, r2, p in DEFAULT_RATES
    ])


def downgrade() -> None:
    op.drop_table('tax_rates')
