from app.db.base import session_scope
from app.models.geo import Facility
from sqlalchemy import select

with session_scope() as db:
    items = db.scalars(select(Facility).where(Facility.layer_key == "accommodation")).all()

    print("Facilities:", len(items))

    for x in items:
        print(x.name, "capacity:", getattr(x, "capacity", "MISSING"), "occupied:", getattr(x, "occupied", "MISSING"))

    if len(items) >= 2:
        items[0].capacity = None
        items[1].capacity = 50
        items[1].occupied = 20

        print("Test data updated")
