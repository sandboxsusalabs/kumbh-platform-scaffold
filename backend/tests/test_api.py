"""End-to-end smoke test over the paths the three apps actually use.

One test per critical journey, in the order a real day runs: register, get an ID,
find a toilet, raise an SOS, work it from the field, close the case.
"""
from __future__ import annotations

from tests.conftest import auth, officer_token, visitor_token

OFFICER = ("CR-001", "9000000001")   # control room
ADMIN = ("AD-001", "9000000004")     # mela administrator


def test_health_and_version(client):
    assert client.get("/healthz").json()["status"] == "ok"
    version = client.get("/version").json()
    assert "hi" in version["languages"] and "en" in version["languages"]
    assert version["integrations"]["kafka"] is False  # tests run without a broker


def test_registration_issues_an_offline_id(client):
    token = visitor_token(client, "9876500001")
    created = client.post("/v1/visitors", headers=auth(token), json={
        "name": "Asha Devi",
        "age": 68,
        "gender": "female",
        "home_state": "Bihar",
        "language": "hi",
        "emergency_contacts": [{"name": "Ravi", "phone": "9876500002", "relation": "son"}],
    })
    assert created.status_code == 201, created.text
    assert created.json()["language"] == "hi"

    card = client.get("/v1/visitors/me/id-card", headers=auth(token)).json()
    assert card["qr_payload"].startswith("KUMBH:VID:")
    assert card["offline_token"].startswith("KMID1.")
    # The QR must not carry personal data.
    assert "Asha" not in card["qr_payload"] and "9876500002" not in card["qr_payload"]


def test_officer_scan_sees_minimum_and_is_audited(client):
    visitor = visitor_token(client, "9876500010")
    client.post("/v1/visitors", headers=auth(visitor), json={
        "name": "Mohan Lal", "age": 41, "language": "en",
        "emergency_contacts": [{"name": "Sita", "phone": "9876500011", "relation": "wife"}],
    })
    card = client.get("/v1/visitors/me/id-card", headers=auth(visitor)).json()
    reference = card["qr_payload"].split(":")[-1]

    officer = officer_token(client, *OFFICER)
    scanned = client.get(f"/v1/visitors/{reference}/scan-view", headers=auth(officer))
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["name"] == "Mohan Lal"
    assert body["audited"] is True

    admin = officer_token(client, *ADMIN)
    logs = client.get("/v1/admin/audit-logs?action=idcard.scan", headers=auth(admin)).json()
    assert any(entry["object_id"] for entry in logs), "scan must appear in the audit log"


def test_visitor_token_cannot_read_the_audit_log(client):
    visitor = visitor_token(client, "9876500020")
    assert client.get("/v1/admin/audit-logs", headers=auth(visitor)).status_code == 403


def test_nearby_search_returns_nearest_first(client):
    facilities = client.get("/v1/map/nearby", params={
        "lat": 29.9562, "lon": 78.1707, "radius_m": 2000, "category": "toilet",
    }).json()
    assert facilities, "seeded toilets must be reachable from Har Ki Pauri"
    distances = [row["distance_m"] for row in facilities]
    assert distances == sorted(distances)
    assert facilities[0]["facility"]["category"] == "toilet"
    assert facilities[0]["walk_minutes"] >= 1


def test_crowd_levels_and_red_zone_route_avoidance(client):
    zones = client.get("/v1/crowd/zones").json()
    assert any(zone["level"] == "red" for zone in zones)
    ghats = client.get("/v1/crowd/ghats").json()
    assert all(ghat["is_ghat"] for ghat in ghats)

    route = client.get("/v1/map/route", params={
        "from_lat": 29.9538, "from_lon": 78.1690, "to_lat": 29.9641, "to_lon": 78.1748,
    }).json()
    assert route["engine"] == "stub"
    assert route["avoided_zones"] >= 1
    assert route["distance_m"] > 0


def test_sos_creates_a_dispatch_task_and_can_be_closed(client):
    visitor = visitor_token(client, "9876500030")
    client.post("/v1/visitors", headers=auth(visitor), json={"name": "Test Pilgrim", "language": "hi"})

    sos = client.post("/v1/sos", headers=auth(visitor), json={
        "category": "medical", "lat": 29.9562, "lon": 78.1707,
        "silent": True, "client_ref": "e2e-sos-1",
    })
    assert sos.status_code == 201, sos.text
    body = sos.json()
    assert body["reference"].startswith("SOS-")
    assert body["priority"] == 1
    assert body["assigned_task_id"], "an SOS must never exist without a task"

    # Offline replay with the same client_ref must not create a second call.
    replay = client.post("/v1/sos", headers=auth(visitor), json={
        "category": "medical", "lat": 29.9562, "lon": 78.1707, "client_ref": "e2e-sos-1",
    })
    assert replay.json()["id"] == body["id"]

    control = officer_token(client, *OFFICER)
    assigned = client.post(f"/v1/sos/{body['id']}/assign", headers=auth(control),
                           json={"team": "medical-04"})
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "assigned"
    assert assigned.json()["acknowledged_at"]

    closed = client.post(f"/v1/sos/{body['id']}/close?note=patient+stabilised",
                         headers=auth(control))
    assert closed.json()["status"] == "closed"


def test_field_task_lifecycle(client):
    control = officer_token(client, *OFFICER)
    visitor = visitor_token(client, "9876500040")
    sos = client.post("/v1/sos", headers=auth(visitor), json={
        "category": "police", "lat": 29.9558, "lon": 78.1706,
    }).json()

    tasks = client.get("/v1/field/tasks", params={"include_unassigned": True},
                       headers=auth(control)).json()
    task = next(item for item in tasks if item["payload"].get("sos_id") == sos["id"])

    claimed = client.post(f"/v1/field/tasks/{task['id']}/claim", headers=auth(control))
    assert claimed.status_code == 200

    for state in ("en_route", "on_site", "done"):
        response = client.post(f"/v1/field/tasks/{task['id']}/transition",
                               headers=auth(control), json={"state": state, "lat": 29.956})
        assert response.status_code == 200, response.text
        assert response.json()["state"] == state

    # A finished task cannot go backwards.
    backwards = client.post(f"/v1/field/tasks/{task['id']}/transition",
                            headers=auth(control), json={"state": "en_route"})
    assert backwards.status_code == 409


def test_offline_sync_is_idempotent(client):
    officer = officer_token(client, "MH-014", "9000000002")
    payload = {
        "items": [{
            "kind": "incident",
            "client_ref": "offline-incident-77",
            "payload": {"kind": "fault", "description": "water point leaking",
                        "lat": 29.9549, "lon": 78.1699, "zone_code": "Z2"},
        }]
    }
    first = client.post("/v1/field/sync", headers=auth(officer), json=payload).json()
    second = client.post("/v1/field/sync", headers=auth(officer), json=payload).json()
    assert first["results"][0]["status"] == "applied"
    assert second["results"][0]["status"] == "duplicate"
    assert first["results"][0]["server_id"] == second["results"][0]["server_id"]


def test_facility_status_update_reaches_the_map(client):
    officer = officer_token(client, "MC-021", "9000000003")
    toilets = client.get("/v1/map/facilities", params={"category": "toilet"}).json()
    target = next(item for item in toilets if item["owner_agency"] == "municipal")

    updated = client.patch(f"/v1/map/facilities/{target['id']}/status",
                           headers=auth(officer), json={"status": "closed", "note": "cleaning"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "closed"

    # Another agency's officer cannot change it.
    health = officer_token(client, "MH-014", "9000000002")
    forbidden = client.patch(f"/v1/map/facilities/{target['id']}/status",
                             headers=auth(health), json={"status": "open"})
    assert forbidden.status_code == 403


def test_lost_person_case_reaches_reunion(client):
    visitor = visitor_token(client, "9876500050")
    client.post("/v1/visitors", headers=auth(visitor), json={"name": "Guardian", "language": "hi"})
    case = client.post("/v1/lost-persons", headers=auth(visitor), json={
        "subject_name": "Chotu", "subject_age": 7, "is_child": True,
        "last_seen_place": "Har Ki Pauri", "last_seen_lat": 29.9562, "last_seen_lon": 78.1707,
    })
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]
    assert case.json()["case_no"].startswith("LP-")

    officer = officer_token(client, *OFFICER)
    sighting = client.post(f"/v1/lost-persons/{case_id}/sighting", headers=auth(officer),
                           json={"lat": 29.9585, "lon": 78.1668, "note": "at help desk"})
    assert sighting.json()["status"] == "sighting"

    reunited = client.post(f"/v1/lost-persons/{case_id}/reunite", headers=auth(officer))
    assert reunited.json()["status"] == "reunited"
    assert reunited.json()["reunited_at"]


def test_critical_alert_gets_a_second_channel(client):
    control = officer_token(client, *OFFICER)
    broadcast = client.post("/v1/alerts", headers=auth(control), json={
        "kind": "critical",
        "title_i18n": {"hi": "घाट बंद", "en": "Ghat closed"},
        "body_i18n": {"hi": "हर की पौड़ी बंद है", "en": "Har Ki Pauri is closed"},
        "zones": ["Z1"],
        "channels": ["push"],
    })
    assert broadcast.status_code == 201, broadcast.text
    body = broadcast.json()
    assert set(body["alert"]["channels"]) >= {"push", "sms"}

    # A zone-scoped alert is only shown inside that zone.
    inside = client.get("/v1/alerts", params={"language": "hi", "zone": "Z1"}).json()
    outside = client.get("/v1/alerts", params={"language": "hi", "zone": "Z5"}).json()
    assert any(item["id"] == body["alert"]["id"] for item in inside)
    assert not any(item["id"] == body["alert"]["id"] for item in outside)


def test_analytics_summary_counts_live_work(client):
    admin = officer_token(client, *ADMIN)
    summary = client.get("/v1/admin/analytics/summary", headers=auth(admin)).json()
    assert summary["registered_visitors"] >= 1
    assert summary["zones_red"] >= 1
    assert summary["open_lost_cases"] >= 0


def test_visitor_app_shell_is_served(client):
    page = client.get("/app/")
    assert page.status_code == 200
    assert "Kumbh" in page.text
    assert client.get("/app/app.js").status_code == 200
