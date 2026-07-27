"""add audio and video metadata

Revision ID: f4a71c2d9b30
Revises: 09ed19e80028
Create Date: 2026-07-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a71c2d9b30"
down_revision: Union[str, Sequence[str], None] = "09ed19e80028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "attachments",
        "duration_ms",
    )
