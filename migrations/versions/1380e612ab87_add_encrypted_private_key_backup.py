"""add encrypted private key backup

Revision ID: 1380e612ab87
Revises: c2e1bf97f697
Create Date: 2026-07-20 23:30:30.650635

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1380e612ab87'
down_revision: Union[str, Sequence[str], None] = 'c2e1bf97f697'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_public_keys",
        sa.Column(
            "encrypted_private_key",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "user_public_keys",
        sa.Column(
            "private_key_iv",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "user_public_keys",
        sa.Column(
            "private_key_salt",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "user_public_keys",
        sa.Column(
            "private_key_kdf",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "user_public_keys",
        sa.Column(
            "private_key_iterations",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "user_public_keys",
        "private_key_iterations",
    )
    op.drop_column(
        "user_public_keys",
        "private_key_kdf",
    )
    op.drop_column(
        "user_public_keys",
        "private_key_salt",
    )
    op.drop_column(
        "user_public_keys",
        "private_key_iv",
    )
    op.drop_column(
        "user_public_keys",
        "encrypted_private_key",
    )