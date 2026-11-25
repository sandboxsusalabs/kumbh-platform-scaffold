from app.db.base import session_scope
from app.models.geo import ZoneDensity
from sqlalchemy import select

with session_scope() as db:
    zones = db.scalars(select(ZoneDensity).where(ZoneDensity.is_ghat == True)).all()

    print("Before:", [(z.name, z.level, z.occupancy_ratio) for z in zones])

    for z in zones:
        z.level = "green"
        z.occupancy_ratio = 0.30
        z.estimated_persons = int(z.capacity * 0.30) if z.capacity else 0
        z.inflow_per_min = 10
        z.outflow_per_min = 10
        z.is_closed = False

    print("Updated all ghat zones to low occupancy.")
    print("After:", [(z.name, z.level, z.occupancy_ratio) for z in zones])
