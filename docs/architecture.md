# Architecture

## System context

```
   Visitor app (mobile web / PWA)      Command dashboard (web)      Field app (Android)
   multilingual, offline-first         role-based, live map         offline queue, QR scan
              \                              |                            /
               \                             |                           /
                └────────────  API gateway (FastAPI, /v1)  ─────────────┘
                                       |
        ┌──────────────┬───────────────┼────────────────┬──────────────┐
        |              |               |                |              |
   PostgreSQL      Redis           Kafka            Object store    SSE / WebSocket
   + PostGIS     cache, geo,     sos.priority      photos, voice    live alerts (visitors)
   (one source   rate limits     alert.broadcast   notes            ops picture (dashboard)
    of truth)                    crowd.telemetry
                                 incident.report
        |
   Feeds in: CCTV and video analytics, gate and turnstile counters, GPS on buses and
   ambulances, weather and river-level, agency systems (police / health / fire /
   municipal / transport), SMS and push gateways, map tiles and routing.
```

Three apps, one contract. Nothing calls another app directly: a change made in the
dashboard is a row in the shared database and an event on the bus, so the visitor app
and the field app cannot disagree with it.

## Service layout in this repository

| Piece | Path | Responsibility |
|---|---|---|
| API | `backend/app/api/v1/` | 13 routers; sync endpoints in the threadpool, SSE/WebSocket async |
| Domain services | `backend/app/services/` | OTP, digital ID, geo maths, event bus, live broker, audit |
| Workers | `backend/app/workers/runner.py` | Kafka consumers: SOS escalation, alert fan-out, crowd folding, incident mirroring |
| Schema | `backend/app/models/` | Four groups: identity, geo, ops, comms |
| Migration | `backend/alembic/versions/` | Initial schema + PostGIS geometry, sync trigger, GiST index |

The API and the workers share the same models and services; the worker container runs
the same image with a different command.

## Module map — design section to code

| Design area | Endpoints | Tables |
|---|---|---|
| Registration and digital ID | `POST /v1/auth/otp/request`, `/verify`, `POST /v1/visitors`, `GET /v1/visitors/me/id-card` | `visitors`, `otp_requests` |
| QR scan by field staff | `GET /v1/visitors/{ref}/scan-view` | `audit_logs` |
| Family and group | `/v1/groups`, `/members`, `/location-sharing`, `/locations`, `/members/{id}/missing` | `groups`, `group_members` |
| GIS map and layers | `/v1/map/layers`, `/facilities`, `/nearby`, `/route`, `PATCH /facilities/{id}/status` | `map_layers`, `facilities`, `zone_density` |
| Crowd density | `/v1/crowd/zones`, `/ghats`, `POST /crowd/ingest` | `zone_density` |
| Bathing schedule | `/v1/schedule/snan` | `snan_slots` |
| Weather and river level | `/v1/weather` | `weather_snapshots` |
| Alerts and broadcast | `/v1/alerts`, `POST /v1/alerts`, `/read`, `/deliveries` | `alerts`, `alert_deliveries`, `alert_receipts` |
| SOS | `POST /v1/sos`, `/assign`, `/close` | `sos_events`, `tasks` |
| Incidents | `/v1/incidents` | `incidents` |
| Lost and found | `/v1/lost-persons`, `/sighting`, `/reunite` | `lost_person_cases`, `lost_person_sightings` |
| Field operations | `/v1/field/tasks`, `/transition`, `/claim`, `/sync` | `tasks`, `task_events` |
| Feedback and helpline | `/v1/feedback`, `/mine`, `/{id}/resolve` | `feedback` |
| Analytics and administration | `/v1/admin/analytics/summary`, `/audit-logs`, `/officers` | `audit_logs`, `officers` |
| Live surfaces | `GET /v1/stream/alerts` (SSE), `WS /v1/ws/ops` | in-process broker |

## Request paths that matter

**SOS (must never fail).** Write `sos_events` and its `tasks` row in one transaction →
commit → publish to `sos.priority` → push to the ops socket → return. A broker or socket
failure is logged and the call still stands. Replays carrying the same `client_ref`
return the original call instead of creating a second one.

**Facility status (must never disagree).** Field app patches the facility row, which is
the single field of record; the event `facility.status` invalidates the edge cache, and
the visitor app reads the same row. No per-app copies.

**Alert (must reach everyone).** Alert rows carry text per language so the read path
never calls a translation service. Fan-out to push/SMS/PA happens in the worker, which
writes sent and failed counts back to `alert_deliveries`; a channel that silently fails
is visible to the control room. Critical alerts are pinned, require an acknowledgement
(`alert_receipts`), and always carry at least two channels.

## Offline and weak-network strategy

| Layer | Behaviour |
|---|---|
| Visitor app | Cached shell and last-known data; offline map tiles downloaded at registration; ID works offline via the signed `KMID1.` token; SOS falls back to SMS and a helpline call |
| Field app | Every action queued locally with a `client_ref`, replayed through `POST /v1/field/sync`; duplicates are detected server-side and reported as `duplicate`, not applied twice |
| Read-heavy data | Announcements, schedule and facilities are cacheable at the edge; the app shows the last known copy rather than an empty screen |
| Alerts | Push, SMS and public address in parallel; no single channel is a point of failure |

## Scale and resilience

- Stateless API behind a load balancer, auto-scaled on request rate; sessions are in the
  token, not in memory.
- Postgres primary with a read replica for the dashboard's read-heavy analytics; PostGIS
  GiST index for nearest-facility and radius queries.
- Kafka decouples ingest bursts (a shahi snan morning) from processing; the SOS topic has
  its own consumer group so normal traffic can never starve it.
- Redis for rate limits, session-adjacent caches and team geo-sets (nearest responder).
- Standby control room and a DR site; failover rehearsed before the event, not during it.

## Security and privacy

- OTP for visitors; OTP + TOTP for officials (`OFFICER_MFA_REQUIRED`); JWT carries role,
  agency and zone, so every query can be scoped.
- Role gates per route (`require_roles`), plus agency ownership checks on writes to
  another agency's layer.
- `audit_logs` records actor, role, agency, IP, object and metadata for every personal
  data read (`idcard.scan`, `visitor.register`) and every sensitive action
  (`alert.broadcast`, `sos.assign`, `officer.deactivate`). Append-only by policy: no
  update or delete endpoint exists.
- Minimal data: no Aadhaar number is ever stored — only the fact and method of
  verification. Location is kept for the event period and erased on the published
  schedule; `DELETE /v1/visitors/me` clears the profile on request.
- Data residency in India on a MeitY-empanelled cloud; TLS in transit, encryption at rest
  at the database and bucket level.

## Open decisions that block work

These come from the design document's own open questions and need the administration:

1. Data-layer ownership and API access for CCTV and crowd feeds.
2. Peak daily visitors, the required language list, and whether the helpline is the
   state's 112 system (the Dial 112 integration is unconfirmed).
3. Whether Aadhaar or DigiLocker verification is wanted at all.
4. Capacity targets (concurrent users, SOS per minute, alert delivery time) — needed
   before the load test can be designed.
5. Mela dates, bathing calendar and the authoritative ghat list.
