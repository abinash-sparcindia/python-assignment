"""Initial asset, visit and seed schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.String(length=7), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("surveyed_on", sa.Date(), nullable=False),
        sa.Column("surveyor", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("condition_score", sa.Integer(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.CheckConstraint("condition_score BETWEEN 0 AND 10", name="ck_assets_condition_score"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_assets_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_assets_longitude"),
    )
    op.create_index("ix_assets_type_status", "assets", ["asset_type", "status"])
    op.create_index("ix_assets_surveyor", "assets", ["surveyor"])
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id", sa.String(length=7), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("surveyed_on", sa.Date(), nullable=False),
        sa.Column("surveyor", sa.String(length=120), nullable=False),
        sa.Column("condition_score", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_visits_asset_date", "visits", ["asset_id", "surveyed_on"])
    op.create_table(
        "seed_runs",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("seed_runs")
    op.drop_index("ix_visits_asset_date", table_name="visits")
    op.drop_table("visits")
    op.drop_index("ix_assets_surveyor", table_name="assets")
    op.drop_index("ix_assets_type_status", table_name="assets")
    op.drop_table("assets")
