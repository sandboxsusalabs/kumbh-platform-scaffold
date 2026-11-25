"""Interactive GIS map: layers, facilities, nearest search, status updates, routing."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_roles
from app.core.security import Principal
from app.db.base import get_db
from app.models.geo import FACILITY_CATEGORIES, Facility, MapLayer, ZoneDensity
from app.schemas import FacilityOut, FacilityStatusIn, LayerOut, NearbyOut, RouteOut
from app.services import audit, events
from app.services.geo import nearest_facilities, plan_route

router = APIRouter(prefix="/map", tags=["map"])

WALK_MPS = 1.25
FIELD_ROLES = ("officer", "supervisor", "control_room", "agency_admin", "admin", "volunteer")


@router.get("/layers", response_model=List[LayerOut], summary="Map layers and their data owners")
def layers(db: Session = Depends(get_db)) -> List[LayerOut]:
    stmt = select(MapLayer).where(MapLayer.is_visible.is_(True)).order_by(MapLayer.sort_order)
    return [LayerOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("/facilities", response_model=List[FacilityOut], summary="Facilities by category or layer")
def facilities(
    category: Optional[str] = Query(default=None, description=f"one of {', '.join(FACILITY_CATEGORIES)}"),
    layer_key: Optional[str] = None,
    zone_code: Optional[str] = None,
    facility_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db),
) -> List[FacilityOut]:
    stmt = select(Facility)
    if category:
        stmt = stmt.where(Facility.category == category)
    if layer_key:
        stmt = stmt.where(Facility.layer_key == layer_key)
    if zone_code:
        stmt = stmt.where(Facility.zone_code == zone_code)
    if facility_status:
        stmt = stmt.where(Facility.status == facility_status)
    stmt = stmt.limit(limit)
    return [FacilityOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("/nearby", response_model=List[NearbyOut],
            summary="Nearest toilet, water, medical, police or food from my location")
def nearby(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    category: Optional[str] = Query(default=None, description="omit for all categories"),
    radius_m: int = Query(default=1500, ge=50, le=10000),
    only_open: bool = True,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
) -> List[NearbyOut]:
    """Distance is computed on the sphere; PostGIS takes over in production."""
    pairs = nearest_facilities(db, lat=lat, lon=lon, radius_m=radius_m,
                               category=category, only_open=only_open, limit=limit)
    return [
        NearbyOut(
            facility=FacilityOut.model_validate(facility),
            distance_m=round(distance, 1),
            walk_minutes=max(1, round(distance / (WALK_MPS * 60))),
        )
        for facility, distance in pairs
    ]


@router.get("/facilities/{facility_id}", response_model=FacilityOut, summary="One facility")
def get_facility(facility_id: str, db: Session = Depends(get_db)) -> FacilityOut:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
    return FacilityOut.model_validate(facility)


@router.patch("/facilities/{facility_id}/status", response_model=FacilityOut,
              summary="Field app: mark a toilet, water point or parking lot open/closed/full")
def set_facility_status(
    facility_id: str,
    payload: FacilityStatusIn,
    request: Request,
    principal: Principal = Depends(require_roles(*FIELD_ROLES)),
    db: Session = Depends(get_db),
) -> FacilityOut:
    facility = db.get(Facility, facility_id)
    if facility is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")

    # An officer may only touch facilities in their own agency's layer, unless admin.
    if principal.role not in {"admin", "control_room"} and principal.agency:
        if facility.owner_agency != principal.agency:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"layer owned by {facility.owner_agency}")

    facility.status = payload.status
    if payload.occupied is not None:
        facility.occupied = payload.occupied
    facility.updated_by = principal.subject
    db.commit()
    db.refresh(facility)

    events.publish_sync(events.TOPIC_FACILITY, facility.id, {
        "facility_id": facility.id, "status": facility.status,
        "category": facility.category, "lat": facility.lat, "lon": facility.lon,
        "updated_by": principal.subject,
    })
    audit.record(db, principal, "facility.status", object_type="facility",
                 object_id=facility.id, ip=client_ip(request),
                 status=payload.status, note=payload.note)
    return FacilityOut.model_validate(facility)


@router.get("/route", response_model=RouteOut, summary="Walking or vehicle route avoiding red zones")
def route(
    from_lat: float = Query(ge=-90, le=90),
    from_lon: float = Query(ge=-180, le=180),
    to_lat: float = Query(ge=-90, le=90),
    to_lon: float = Query(ge=-180, le=180),
    mode: str = Query(default="walk", pattern="^(walk|vehicle)$"),
    db: Session = Depends(get_db),
) -> RouteOut:
    """Closures and red-density zones come from the control room's live state."""
    blocked = db.scalars(
        select(ZoneDensity).where(
            (ZoneDensity.level == "red") | (ZoneDensity.is_closed.is_(True))
        )
    ).all()
    avoid = [(z.centroid_lat, z.centroid_lon) for z in blocked
             if z.centroid_lat is not None and z.centroid_lon is not None]
    plan = plan_route((from_lat, from_lon), (to_lat, to_lon), avoid=avoid, mode=mode)
    plan["avoided_zones"] = len(avoid)
    return RouteOut(**plan)
