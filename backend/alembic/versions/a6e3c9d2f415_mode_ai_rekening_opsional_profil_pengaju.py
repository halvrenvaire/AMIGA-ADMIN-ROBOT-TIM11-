"""mode baca AI, rekening opsional, profil pengaju, token AI

Revision ID: a6e3c9d2f415
Revises: d4f1a7c3e2b9
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a6e3c9d2f415'
down_revision: Union[str, Sequence[str], None] = 'd4f1a7c3e2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dokumen lama tetap ITEMIZED (rincian per barang) dan tanpa rekening di voucher; data rekening lama tetap tersimpan
    op.add_column('documents', sa.Column('extraction_mode', sa.String(20), nullable=False, server_default='ITEMIZED'))
    op.add_column('documents', sa.Column('include_account', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('documents', sa.Column('submitter_signature_png', sa.LargeBinary(), nullable=True))
    op.add_column('users', sa.Column('submitter_profile', postgresql.JSONB(), nullable=False, server_default='{}'))
    op.add_column('extractions', sa.Column('ai_input_tokens', sa.Integer(), nullable=True))
    op.add_column('extractions', sa.Column('ai_output_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('extractions', 'ai_output_tokens')
    op.drop_column('extractions', 'ai_input_tokens')
    op.drop_column('users', 'submitter_profile')
    op.drop_column('documents', 'submitter_signature_png')
    op.drop_column('documents', 'include_account')
    op.drop_column('documents', 'extraction_mode')
