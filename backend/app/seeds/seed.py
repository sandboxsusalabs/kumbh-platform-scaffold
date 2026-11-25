"""Demo data for local runs and the pilot.

Coordinates are approximate demo points around Har Ki Pauri, Haridwar, so distance and
"nearest" behave realistically in dev. The real layer data comes from each owning agency
(see docs/architecture.md) and is loaded by the GIS data-collection task in phase 1.

Run:  python -m app.seeds.seed
"""
from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app.db.base import create_all, session_scope
from app.models.comms import Alert
from app.models.geo import Facility, MapLayer, SnanSlot, WeatherSnapshot, ZoneDensity
from app.models.identity import Officer

LAYERS = [
    ("bathing_ghats", "Bathing ghats", "mela_admin", 1),
    ("religious", "Temples and akharas", "mela_admin", 2),
    ("parking", "Parking", "traffic_police", 3),
    ("bus_stands", "Temporary bus stands", "transport", 4),
    ("railway", "Railway stations", "railways", 5),
    ("medical", "Medical facilities", "health", 6),
    ("police", "Police and help desks", "police", 7),
    ("fire", "Fire stations", "fire", 8),
    ("toilets", "Public toilets", "municipal", 9),
    ("water", "Drinking water", "jal_sansthan", 10),
    ("food", "Food distribution", "mela_admin", 11),
    ("accommodation", "Camps and dharamshalas", "mela_admin", 12),
    ("info_centres", "Information centres", "mela_admin", 13),
    ("lost_found", "Lost and found", "police", 14),
]

# (layer, category, name, lat, lon, zone, status, owner, accessible)
FACILITIES = [
    ("bathing_ghats", "ghat", "Har Ki Pauri", 29.9562, 78.1707, "Z1", "open", "mela_admin", False),
    ("bathing_ghats", "ghat", "Kushavart Ghat", 29.9538, 78.1690, "Z2", "open", "mela_admin", False),
    ("bathing_ghats", "ghat", "Asthi Pravah Ghat", 29.9512, 78.1676, "Z3", "open", "mela_admin", True),
    ("religious", "temple", "Mansa Devi Temple", 29.9641, 78.1748, "Z6", "open", "mela_admin", False),
    ("religious", "camp", "Akhara camp — Sector 4", 29.9595, 78.1665, "Z4", "open", "mela_admin", True),
    ("parking", "parking", "Pant Deep parking", 29.9602, 78.1755, "Z4", "open", "traffic_police", False),
    ("parking", "parking", "Bhupatwala parking", 29.9725, 78.1910, "Z5", "open", "traffic_police", True),
    ("bus_stands", "bus_stop", "Temporary bus stand — Sector 2", 29.9490, 78.1720, "Z5", "open", "transport", True),
    ("railway", "railway", "Haridwar Junction", 29.9476, 78.1633, "Z5", "open", "railways", True),
    ("medical", "medical", "First-aid post — Har Ki Pauri", 29.9566, 78.1701, "Z1", "open", "health", False),
    ("medical", "medical", "First-aid post — Sector 4", 29.9598, 78.1660, "Z4", "open", "health", True),
    ("medical", "medical", "Base hospital camp — Bhupatwala", 29.9721, 78.1902, "Z5", "open", "health", True),
    ("police", "police", "Police outpost — Har Ki Pauri", 29.9558, 78.1706, "Z1", "open", "police", False),
    ("police", "police", "Police outpost — Sector 4", 29.9601, 78.1655, "Z4", "open", "police", False),
    ("fire", "fire", "Fire point — Sector 3", 29.9520, 78.1690, "Z3", "open", "fire", False),
    ("toilets", "toilet", "Toilet block — Har Ki Pauri north", 29.9571, 78.1712, "Z1", "open", "municipal", True),
    ("toilets", "toilet", "Toilet block — Kushavart", 29.9538, 78.1694, "Z2", "full", "municipal", False),
    ("toilets", "toilet", "Toilet block — Sector 4", 29.9597, 78.1668, "Z4", "open", "municipal", True),
    ("water", "water", "Jal station — Clock Tower", 29.9549, 78.1699, "Z2", "open", "jal_sansthan", False),
    ("water", "water", "Jal station — Pant Deep", 29.9602, 78.1755, "Z4", "open", "jal_sansthan", False),
    ("water", "water", "Jal station — Sector 2", 29.9495, 78.1718, "Z5", "open", "jal_sansthan", True),
    ("food", "food", "Annakshetra — Sector 3", 29.9520, 78.1680, "Z3", "open", "mela_admin", True),
    ("food", "food", "Langar — Sector 5", 29.9610, 78.1642, "Z5", "open", "mela_admin", True),
    ("accommodation", "accommodation", "Dharamshala — Sector 4", 29.9605, 78.1650, "Z4", "open", "mela_admin", True),
    ("accommodation", "camp", "Tent city — Sector 5", 29.9630, 78.1620, "Z5", "open", "mela_admin", True),
    ("info_centres", "info", "Help desk — Har Ki Pauri", 29.9560, 78.1710, "Z1", "open", "mela_admin", True),
    ("lost_found", "lost_found", "Lost and found centre — Mela office", 29.9585, 78.1668, "Z4", "open", "police", True),
]

# (code, name, is_ghat, capacity, persons, centroid)
ZONES = [
    ("Z1", "Har Ki Pauri", True, 40000, 37200, (29.9562, 78.1707)),
    ("Z2", "Kushavart Ghat", True, 22000, 14800, (29.9538, 78.1690)),
    ("Z3", "Asthi Pravah Ghat", True, 12000, 4300, (29.9512, 78.1676)),
    ("Z4", "Sector 4 — camps and akharas", False, 25000, 12100, (29.9600, 78.1660)),
    ("Z5", "Sector 5 — parking and transit", False, 18000, 5400, (29.9680, 78.1830)),
    ("Z6", "Mansa Devi approach", False, 15000, 9600, (29.9641, 78.1748)),
]

SNAN = [
    ("Z1", "Har Ki Pauri", time(4, 0), time(9, 0), True, "Shahi snan — akhara processions"),
    ("Z2", "Kushavart Ghat", time(5, 30), time(11, 0), False, None),
    ("Z3", "Asthi Pravah Ghat", time(5, 30), time(12, 0), False, None),
]

# Dev-only officer. MFA secret is a placeholder — rotate before any real deployment.
DEV_OFFICERS = [
    ("CR-001", "Control Room Duty Officer", "9000000001", "control_room", "admin", None, "JBSWY3DPEHPK3PXP"),
    ("MH-014", "Health Supervisor", "9000000002", "supervisor", "health", "Z1", "JBSWY3DPEHPK3PXP"),
    ("MC-021", "Sanitation Officer", "9000000003", "officer", "municipal", "Z2", "JBSWY3DPEHPK3PXP"),
    ("AD-001", "Mela Administrator", "9000000004", "admin", "admin", None, "JBSWY3DPEHPK3PXP"),
]


def seed() -> dict:
    create_all()
    counts = {"layers": 0, "facilities": 0, "zones": 0, "snan": 0, "officers": 0, "alerts": 0}

    with session_scope() as db:
        for key, name, owner, order in LAYERS:
            if db.get(MapLayer, key) is None:
                db.add(MapLayer(key=key, name=name, owner_agency=owner, sort_order=order))
                counts["layers"] += 1

        for layer, category, name, lat, lon, zone, status, owner, accessible in FACILITIES:
            exists = db.scalars(
                select(Facility).where(Facility.name == name, Facility.category == category)
            ).first()
            if exists is None:
                db.add(Facility(
                    layer_key=layer, category=category, name=name, lat=lat, lon=lon,
                    zone_code=zone, status=status, owner_agency=owner, is_accessible=accessible,
                ))
                counts["facilities"] += 1

        for code, name, is_ghat, capacity, persons, centroid in ZONES:
            if db.get(ZoneDensity, code) is None:
                ratio = persons / capacity if capacity else 0.0
                level = "red" if ratio >= 0.85 else "amber" if ratio >= 0.60 else "green"
                db.add(ZoneDensity(
                    zone_code=code, name=name, is_ghat=is_ghat, capacity=capacity,
                    estimated_persons=persons, occupancy_ratio=round(ratio, 3), level=level,
                    centroid_lat=centroid[0], centroid_lon=centroid[1],
                    inflow_per_min=120, outflow_per_min=90,
                ))
                counts["zones"] += 1

        today = date.today()
        if not db.scalars(select(SnanSlot).limit(1)).first():
            for zone, ghat_name, start, end, shahi, note in SNAN:
                db.add(SnanSlot(date=today, ghat_code=zone, ghat_name=ghat_name,
                                start_time=start, end_time=end, is_shahi=shahi, note=note))
                counts["snan"] += 1

        if not db.scalars(select(WeatherSnapshot).limit(1)).first():
            db.add(WeatherSnapshot(temperature_c=18.5, rain_mm=0.0, river_level_m=2.9,
                                   river_level_warning="normal", condition="clear", source="stub"))

        for code, name, phone, role, agency, zone, secret in DEV_OFFICERS:
            if not db.scalars(select(Officer).where(Officer.employee_code == code)).first():
                db.add(Officer(employee_code=code, name=name, phone=phone, role=role,
                               agency=agency, zone=zone, totp_secret=secret))
                counts["officers"] += 1

        if not db.scalars(select(Alert).limit(1)).first():
            db.add(Alert(
                kind="info", category="service",
                title_i18n={"hi": "पीने का पानी उपलब्ध", "en": "Drinking water available",
                            "bn": "পানীয় জল পাওয়া যাচ্ছে"},
                body_i18n={"hi": "सभी घाटों पर जल स्टेशन खुले हैं।",
                           "en": "Water stations are open at every ghat.",
                           "bn": "সব ঘাটে জল স্টেশন খোলা।"},
                zones=[], channels=["push"], status="published",
            ))
            counts["alerts"] += 1

    return counts


if __name__ == "__main__":  # pragma: no cover
    print("seeded:", seed())
