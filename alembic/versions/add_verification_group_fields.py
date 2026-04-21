"""Add verification group message tracking

Revision ID: add_verification_group_fields
Revises: 4f9840814bd0
Create Date: 2026-04-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_verification_group_fields'
down_revision: Union[str, None] = '4f9840814bd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('verification_group_message_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('verification_group_chat_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'verification_group_chat_id')
    op.drop_column('users', 'verification_group_message_id')
