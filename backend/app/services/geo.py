"""Geo helpers: nearest-facility search and crowd-aware routing.

On PostgreSQL/PostGIS the bbox + distance work moves into SQL (see the GiST index in
the migration). On SQLite the same query runs in Python over a bbox-prefiltered set, so
tests and local dev need no PostGIS.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.geo import Facility, ZoneDensity

EARTH_RADIUS_M = 6371000.0

# Density thresholds that turn an occupancy ratio into the app's traffic light.
AMBER_RATIO = 0.60
RED_RATIO = 0.85


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bbox(lat: float, lon: float, radius_m: float) -> Tuple[float, float, float, float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(0.15, math.cos(math.radians(lat))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def level_for_ratio(ratio: float) -> str:
    if ratio >= RED_RATIO:
        return "red"
    if ratio >= AMBER_RATIO:
        return "amber"
    return "green"


def nearest_facilities(
    db: Session,
    *,
    lat: float,
    lon: float,
    radius_m: float = 1500,
    category: str | None = None,
    layer_key: str | None = None,
    only_open: bool = False,
    limit: int = 20,
) -> List[Tuple[Facility, float]]:
    min_lat, max_lat, min_lon, max_lon = bbox(lat, lon, radius_m)
    stmt = select(Facility).where(
        and_(Facility.lat.between(min_lat, max_lat), Facility.lon.between(min_lon, max_lon))
    )
    if category:
        stmt = stmt.where(Facility.category == category)
    if layer_key:
        stmt = stmt.where(Facility.layer_key == layer_key)
    if only_open:
        stmt = stmt.where(Facility.status == "open")

    scored = [(f, haversine_m(lat, lon, f.lat, f.lon)) for f in db.scalars(stmt).all()]
    scored = [pair for pair in scored if pair[1] <= radius_m]
    scored.sort(key=lambda pair: pair[1])
    return scored[:limit]


def densest_zones(db: Session, limit: int = 5) -> List[ZoneDensity]:
    stmt = select(ZoneDensity).order_by(ZoneDensity.occupancy_ratio.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def plan_route(
    start: Tuple[float, float],
    end: Tuple[float, float],
    avoid: Sequence[Tuple[float, float]] = (),
    mode: str = "walk",
) -> dict:
    """Routing stub.

    Production calls the routing engine (OSRM/Valhalla) with live closures and red
    zones as `exclude` polygons. Until that endpoint exists this returns a
    straight-line plan with a detour around each avoided zone, clearly flagged as a
    stub so no one mistakes it for a real walking route.
    """
    speed_mps = 1.25 if mode == "walk" else 6.0
    waypoints = [start]
    total = 0.0
    current = start

    for zone in avoid:
        total += haversine_m(*current, *zone)
        # Step sideways from the zone by ~120 m to represent the detour.
        detour = (zone[0] + 0.0011, zone[1] + 0.0011)
        total += haversine_m(*zone, *detour)
        waypoints.append(zone)
        waypoints.append(detour)
        current = detour

    total += haversine_m(*current, *end)
    waypoints.append(end)

    return {
        "mode": mode,
        "engine": "stub",
        "note": "Straight-line plan. Set ROUTING_ENGINE_URL for real turn-by-turn routing.",
        "distance_m": round(total, 1),
        "duration_s": round(total / speed_mps),
        "waypoints": [{"lat": round(p[0], 6), "lon": round(p[1], 6)} for p in waypoints],
        "avoided_zones": len(avoid),
    }


def iter_ring(centre: Tuple[float, float], radius_m: float, points: int = 24) -> Iterable[Tuple[float, float]]:
    """Helper for drawing closure rings in the dashboard map."""
    lat, lon = centre
    for i in range(points):
        angle = 2 * math.pi * i / points
        dlat = (radius_m * math.cos(angle)) / 111_320.0
        dlon = (radius_m * math.sin(angle)) / (111_320.0 * math.cos(math.radians(lat)))
        yield lat + dlat, lon + dlon
