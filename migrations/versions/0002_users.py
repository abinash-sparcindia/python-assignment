"""Add user accounts for authenticated API access.

Revision ID: 0002_users
Revises: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_users"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('surveyor', 'administrator')", name="ck_users_role"),
    )


def downgrade() -> None:
    op.drop_table("users")
