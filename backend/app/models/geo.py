"""Geography: map layers, facilities, crowd density and the bathing schedule.

Every layer has a named owner (`owner_agency`) and a freshness timestamp, because the
design requires that each layer stays current and that the app, dashboard and field app
never disagree about a facility's status.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime, time as time_type, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Layer keys mirror the two tables in the solution design (pages 4–5).
LAYER_KEYS = [
    "bathing_ghats", "religious", "parking", "bus_stands", "railway",
    "medical", "police", "fire", "toilets", "water", "food",
    "accommodation", "info_centres", "lost_found",
]

FACILITY_CATEGORIES = [
    "toilet", "water", "medical", "police", "food", "parking",
    "bus_stop", "railway", "fire", "accommodation", "info", "lost_found",
    "ghat", "temple", "camp",
]


class MapLayer(Base):
    __tablename__ = "map_layers"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    owner_agency: Mapped[str] = mapped_column(String(64))
    geometry_type: Mapped[str] = mapped_column(String(16), default="point")  # point | line | polygon
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Facility(Base):
    """One physical point: a toilet block, a ghat, a first-aid post, a parking lot.

    `status` is the field of record for open / closed / full / crowded. The visitor app
    reads it from here, so a change pushed from the field app reaches every phone.
    """

    __tablename__ = "facilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    layer_key: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(160))
    name_i18n: Mapped[dict] = mapped_column(JSON, default=dict)

    lat: Mapped[float] = mapped_column(Float, index=True)
    lon: Mapped[float] = mapped_column(Float, index=True)
    zone_code: Mapped[str | None] = mapped_column(String(24), index=True)

    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed | full | crowded
    capacity: Mapped[int | None] = mapped_column(Integer)
    occupied: Mapped[int | None] = mapped_column(Integer)
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=False)
    opening_hours: Mapped[str | None] = mapped_column(String(64))

    owner_agency: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ZoneDensity(Base):
    """Crowd level per ghat or zone, refreshed from CCTV counts, gate counters and
    mobile-network density. Drives the green/amber/red indicator and route avoidance."""

    __tablename__ = "zone_density"

    zone_code: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    is_ghat: Mapped[bool] = mapped_column(Boolean, default=False)
    # Centroid of the zone polygon; routing detours around this point until the
    # polygon table lands in the GIS layer.
    centroid_lat: Mapped[float | None] = mapped_column(Float)
    centroid_lon: Mapped[float | None] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(8), default="green")  # green | amber | red
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    estimated_persons: Mapped[int] = mapped_column(Integer, default=0)
    occupancy_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    inflow_per_min: Mapped[int] = mapped_column(Integer, default=0)
    outflow_per_min: Mapped[int] = mapped_column(Integer, default=0)
    one_way_flow: Mapped[str | None] = mapped_column(String(16))  # None | inward | outward
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="cctv")  # cctv | gate | network | manual
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SnanSlot(Base):
    """Bathing schedule by ghat. Shahi snan days are flagged so the app highlights them."""

    __tablename__ = "snan_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    ghat_code: Mapped[str] = mapped_column(String(24), index=True)
    ghat_name: Mapped[str] = mapped_column(String(120))
    start_time: Mapped[time_type] = mapped_column(Time)
    end_time: Mapped[time_type] = mapped_column(Time)
    is_shahi: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(240))


class WeatherSnapshot(Base):
    """Latest weather and river-level reading. Cached so weak-network clients can read it."""

    __tablename__ = "weather_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    temperature_c: Mapped[float] = mapped_column(Float)
    rain_mm: Mapped[float] = mapped_column(Float, default=0.0)
    river_level_m: Mapped[float | None] = mapped_column(Float)
    river_level_warning: Mapped[str | None] = mapped_column(String(16))  # normal | watch | danger
    condition: Mapped[str] = mapped_column(String(48), default="clear")
    source: Mapped[str] = mapped_column(String(48), default="stub")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
