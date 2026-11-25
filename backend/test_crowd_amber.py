from app.db.base import session_scope
from app.models.geo import ZoneDensity
from sqlalchemy import select

with session_scope() as db:
    zones = db.scalars(select(ZoneDensity).where(ZoneDensity.is_ghat == True)).all()

    if zones:
        z = zones[0]
        z.level = "amber"
        z.occupancy_ratio = 0.65
        z.estimated_persons = int(z.capacity * 0.65) if z.capacity else 0
        z.inflow_per_min = 100
        z.outflow_per_min = 50
        z.is_closed = False

        print("Updated:", z.name, z.level, z.occupancy_ratio)
    else:
        print("No ghat zones found")
