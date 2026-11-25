# Command dashboard — build order

Not built in this scaffold. The API side is complete; this is the screen plan and the
exact endpoints each screen reads, so the work is mechanical.

## Shell

Role-based web console. Every login is tied to a role, an agency and a zone; the shared
live map and alert board are visible to all, agency workspaces only to their own staff.
Sensitive actions (viewing personal data, mass broadcast) need a higher role and are
audited server-side.

Layout: left rail of modules → module workspace → right drawer for the common operating
picture (map + alert board + live socket).

## Modules and their endpoints

| Module | Screens | Endpoints |
|---|---|---|
| Common operating picture | Live map, incident board, staff and vehicle positions | `WS /v1/ws/ops`, `GET /v1/crowd/zones`, `GET /v1/incidents`, `GET /v1/sos` |
| Crowd management | Zone capacity table, inflow/outflow charts, threshold alerts, one-way and closure orders | `GET /v1/crowd/zones`, `POST /v1/crowd/ingest` (manual override), `PATCH /v1/map/facilities/{id}/status` |
| Incident and SOS desk | Incoming queue, nearest-team assignment, closure tracking | `GET /v1/sos`, `POST /v1/sos/{id}/assign`, `POST /v1/sos/{id}/close`, `GET /v1/field/tasks` |
| Lost and found | Case registry, photo matching, reunion | `GET /v1/lost-persons`, `POST /v1/lost-persons/{id}/reunite`, `POST /v1/lost-persons/{id}/sighting` |
| Health | Bed and ambulance status, first-aid posts, outbreak signals | `GET /v1/map/facilities?category=medical`, `PATCH /v1/map/facilities/{id}/status` |
| Sanitation | Toilet cleaning status, waste tasks, complaint ageing | `GET /v1/map/facilities?category=toilet`, `GET /v1/feedback?agency=municipal` |
| Water and utilities | Water points, power and lighting faults | `GET /v1/map/facilities?category=water`, `GET /v1/incidents?kind=fault` |
| Transport and parking | Parking occupancy, shuttle tracking, diversions | `GET /v1/map/facilities?category=parking`, `GET /v1/map/facilities?category=bus_stop` |
| Fire and disaster | Fire alerts, river-level warnings, evacuation plans | `GET /v1/weather`, `GET /v1/incidents?kind=fire`, `GET /v1/alerts` |
| Broadcast | Compose per language and zone, choose channels, watch delivery | `POST /v1/alerts`, `GET /v1/alerts/{id}/deliveries` |
| Analytics | Daily footfall, response times, complaint trends, PDF/Excel export | `GET /v1/admin/analytics/summary` |
| Administration | Users, roles, facilities, schedule, content, audit log | `GET /v1/admin/officers`, `GET /v1/admin/audit-logs`, `POST /v1/admin/officers/{id}/deactivate` |

## Notes for whoever builds it

- Use the WebSocket for anything that must move in seconds (SOS, zone level, task state);
  poll the analytics endpoints on a minute.
- Map tiles come from the GIS service; never draw a synthetic map in the console.
- Every table that shows a person must link to the audit entry for that view — the
  privacy notice promises it.
- Export to PDF and Excel is a server-side job; add `GET /v1/admin/exports/{kind}` rather
  than building it in the browser.
