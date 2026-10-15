"""pemilik dan data riwayat percakapan

Revision ID: e5b1c7d24a90
Revises: 6a13aac409bc
Create Date: 2026-10-15 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5b1c7d24a90'
down_revision: Union[str, Sequence[str], None] = '6a13aac409bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversation_messages', sa.Column('user_id', sa.UUID(), nullable=True))
    op.add_column('conversation_messages', sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f('ix_conversation_messages_user_id'), 'conversation_messages', ['user_id'], unique=False)
    op.create_foreign_key('conversation_messages_user_id_fkey', 'conversation_messages', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('conversation_messages_user_id_fkey', 'conversation_messages', type_='foreignkey')
    op.drop_index(op.f('ix_conversation_messages_user_id'), table_name='conversation_messages')
    op.drop_column('conversation_messages', 'data')
    op.drop_column('conversation_messages', 'user_id')
