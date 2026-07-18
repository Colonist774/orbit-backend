"""encrypt message content

Revision ID: 0a10b07b399f
Revises: 1ad8078c5a09
Create Date: 2026-07-17 21:48:07.040227
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0a10b07b399f"
down_revision: Union[str, Sequence[str], None] = "1ad8078c5a09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM messages")

    op.add_column(
        "messages",
        sa.Column(
            "ciphertext",
            sa.Text(),
            nullable=False,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "iv",
            sa.String(length=24),
            nullable=False,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "key_version",
            sa.Integer(),
            nullable=False,
        ),
    )

    op.drop_column(
        "messages",
        "content",
    )


def downgrade() -> None:
    op.execute("DELETE FROM messages")

    op.add_column(
        "messages",
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
    )

    op.drop_column(
        "messages",
        "key_version",
    )

    op.drop_column(
        "messages",
        "iv",
    )

    op.drop_column(
        "messages",
        "ciphertext",
    )