"""Schema invariants independent of API and ingestion behavior."""

from datetime import date

from sqlalchemy import select

from utility_assets.models import Asset, Visit


def test_asset_visit_cascade(db_session):
    asset = Asset(
        asset_id="PL-0001",
        name="Test pole",
        asset_type="pole",
        latitude=20.3,
        longitude=85.8,
        elevation_m=None,
        surveyed_on=date(2026, 9, 1),
        surveyor="Anita Das",
        status="active",
        condition_score=5,
        attributes={"height_m": 9},
    )
    asset.visits.append(
        Visit(surveyed_on=date(2026, 9, 1), surveyor="Anita Das", condition_score=5)
    )
    db_session.add(asset)
    db_session.commit()

    db_session.delete(asset)
    db_session.commit()

    assert db_session.scalar(select(Visit.id)) is None
