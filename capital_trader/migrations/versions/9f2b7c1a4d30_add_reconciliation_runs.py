"""add reconciliation runs

Revision ID: 9f2b7c1a4d30
Revises: 2511bca9ec79
Create Date: 2026-09-20 00:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f2b7c1a4d30"
down_revision: Union[str, Sequence[str], None] = "2511bca9ec79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reconciliation_runs_status"), "reconciliation_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reconciliation_runs_status"), table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
