"""Track committed asset changes for cross-process report cache invalidation.

Revision ID: 0003_report_revision
Revises: 0002_users
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_report_revision"
down_revision = "0002_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.execute("INSERT INTO report_revision (id, version) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("report_revision")
