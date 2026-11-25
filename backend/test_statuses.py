from app.db.base import session_scope
from app.models.geo import Facility
from sqlalchemy import select

with session_scope() as db:
    items = db.scalars(select(Facility).where(Facility.layer_key == "accommodation")).all()
    print("Before:", [(x.name, x.status) for x in items])
    if len(items) >= 2:
        items[0].status = "closed"
        items[1].status = "full"
        print("After:", [(x.name, x.status) for x in items])
