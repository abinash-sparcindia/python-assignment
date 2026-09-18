"""Persistent asset, visit and seed state."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from utility_assets.db import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint("condition_score BETWEEN 0 AND 10", name="ck_assets_condition_score"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_assets_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_assets_longitude"),
        Index("ix_assets_type_status", "asset_type", "status"),
        Index("ix_assets_surveyor", "surveyor"),
    )

    asset_id: Mapped[str] = mapped_column(String(7), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    surveyed_on: Mapped[date] = mapped_column(Date, nullable=False)
    surveyor: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    condition_score: Mapped[int] = mapped_column(Integer, nullable=False)
    attributes: Mapped[Any] = mapped_column(JSON, nullable=False)
    visits: Mapped[list["Visit"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (Index("ix_visits_asset_date", "asset_id", "surveyed_on"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(
        String(7), ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False
    )
    surveyed_on: Mapped[date] = mapped_column(Date, nullable=False)
    surveyor: Mapped[str] = mapped_column(String(120), nullable=False)
    condition_score: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    asset: Mapped[Asset] = relationship(back_populates="visits")


class SeedRun(Base):
    __tablename__ = "seed_runs"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReportRevision(Base):
    __tablename__ = "report_revision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('surveyor', 'administrator')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
