# API reference (v1)

Base URL `/v1`. Auth is `Authorization: Bearer <jwt>` unless marked public.
Interactive docs while running: `/docs` (OpenAPI at `/openapi.json`).

Roles: `visitor`, `volunteer`, `officer`, `supervisor`, `control_room`, `agency_admin`,
`admin`. `CONTROL` below means `control_room | agency_admin | admin`; `FIELD` means
`officer | supervisor | control_room | agency_admin | admin | volunteer`.

## Auth

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/auth/otp/request` | public | `{phone}` → `{request_id, expires_in, dev_otp?}`. 5 requests per number per 10 min |
| POST | `/auth/otp/verify` | public | `{request_id, phone, otp}` → token; creates the visitor row on first login |
| POST | `/auth/officer/login` | public | `{employee_code, phone, otp, totp}`; TOTP required when MFA is on |
| GET | `/auth/me` | any | Echoes role, agency, zone |
| POST | `/auth/refresh` | any | Fresh token from a valid one |

## Visitors and identity

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/visitors` | visitor | Profile: name, age, gender, home state, language, ≤2 emergency contacts, accessibility, optional verification |
| GET | `/visitors/me` | visitor | Own profile |
| PATCH | `/visitors/me` | visitor | `language`, `large_text` |
| GET | `/visitors/me/id-card` | visitor | `qr_payload` (`KUMBH:VID:<ref>`), signed `offline_token`, validity |
| POST | `/visitors/me/location` | visitor | `lat`, `lon` — event-period only |
| GET | `/visitors/{ref}/scan-view` | SCAN roles | Accepts visitor id **or** QR reference; minimum fields only; audited |
| DELETE | `/visitors/me` | visitor | Erasure request: deactivates and clears the profile |

## Groups

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/groups` | visitor | Leader is the caller; limit 20 members |
| GET | `/groups/{id}` | leader or official | Group with members |
| POST | `/groups/{id}/members` | leader | By phone (invite → `pending`) or by name+age (wristband code) |
| POST | `/groups/{id}/members/{mid}/accept` | invited visitor | Accept a link request |
| DELETE | `/groups/{id}/members/{mid}` | leader | Revoke; leader cannot be removed |
| POST | `/groups/{id}/location-sharing` | leader | `{enabled}` |
| POST | `/groups/{id}/locations` | member | 403 unless sharing is on or an SOS is open |
| POST | `/groups/{id}/members/{mid}/missing` | leader | Opens a lost-person case and a field task in one tap |

## Map, facilities, crowd, schedule, weather

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/map/layers` | public | Visible layers with owning agency |
| GET | `/map/facilities` | public | Filter `category`, `layer_key`, `zone_code`, `status` |
| GET | `/map/nearby` | public | `lat`, `lon`, `radius_m`, `category` → sorted by distance with walk minutes |
| GET | `/map/facilities/{id}` | public | One facility |
| PATCH | `/map/facilities/{id}/status` | FIELD | `open | closed | full | crowded`; agency ownership enforced |
| GET | `/map/route` | public | `from_*`, `to_*`, `mode=walk|vehicle`; avoids red zones and closures |
| GET | `/crowd/zones` | public | Levels, occupancy, inflow/outflow, one-way flags |
| GET | `/crowd/ghats` | public | Ghats only |
| POST | `/crowd/ingest` | CONTROL | CCTV / gate / network reading; recomputes level |
| GET | `/schedule/snan` | public | `?date=`; `is_shahi` flagged |
| GET | `/weather` | public | Temperature, rain, river level and warning |

## Alerts

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/alerts` | public | `language`, `zone`; localised text, `pinned` for critical |
| POST | `/alerts` | CONTROL | Broadcast; critical alerts gain a second channel automatically |
| POST | `/alerts/{id}/read` | any | Acknowledgement for pinned alerts |
| GET | `/alerts/{id}/deliveries` | CONTROL | Per-channel sent/failed counters |
| DELETE | `/alerts/{id}` | CONTROL | Withdraw |

## SOS and incidents

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/sos` | any authenticated | `category`, `lat`, `lon`, `silent`, `channel`, `client_ref` (idempotent) |
| GET | `/sos` | CONTROL | Priority-ordered queue |
| GET | `/sos/{id}` | owner or official | Status |
| POST | `/sos/{id}/assign` | CONTROL | `{team, task_id?}`; records acknowledgement |
| POST | `/sos/{id}/close` | FIELD | Close with an optional note |
| POST | `/incidents` | FIELD | Photo, voice, location, severity; `client_ref` idempotent |
| GET | `/incidents` | FIELD | Filter `status`, `kind` |
| PATCH | `/incidents/{id}` | FIELD | Update status |

## Lost and found

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/lost-persons` | any authenticated | Photo, description, last-seen point; creates a search task |
| GET | `/lost-persons` | FIELD | Registry; filter `status`, `is_child` |
| GET | `/lost-persons/{id}` | reporter or official | Case with sightings — the family sees progress |
| POST | `/lost-persons/{id}/sighting` | FIELD | Log a sighting; status → `sighting` |
| POST | `/lost-persons/{id}/reunite` | FIELD | Status → `reunited`; clears the missing flag and closes the task |

## Field app

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/field/tasks` | FIELD | My inbox; `include_unassigned`, `state`; sort by `lat`/`lon` when given |
| POST | `/field/tasks/{id}/claim` | FIELD | Claim an unassigned task |
| POST | `/field/tasks/{id}/transition` | FIELD | `accepted → en_route → on_site → done`; 409 on an illegal move; geotagged proof stored |
| POST | `/field/sync` | FIELD | Batch replay; per-item `applied | duplicate | rejected` |

## Feedback

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/feedback` | any authenticated | Category, description, location, photo; returns `ticket_no` |
| GET | `/feedback/mine` | any authenticated | My tickets |
| GET | `/feedback` | CONTROL | Agency queue |
| POST | `/feedback/{id}/resolve` | CONTROL | Close with timestamp |

## Administration

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/admin/analytics/summary` | CONTROL | Footfall, active SOS, open cases, red/amber zones, median SOS ack |
| GET | `/admin/audit-logs` | agency_admin, admin | Filter `action`, `actor_id` |
| GET | `/admin/officers` | agency_admin, admin | Accounts with agency, zone, MFA state |
| POST | `/admin/officers/{id}/deactivate` | agency_admin, admin | Immediate disable |

## Live

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/stream/alerts` | `?token=` | SSE: alerts as broadcast, 20 s heartbeat |
| WS | `/ws/ops?token=` | official token | SOS, incidents, zone density, task states; client may send `{"type":"ping"}` |
| GET | `/stream/stats` | public | Connected client counts (debug) |

## Root-level probes

`GET /healthz`, `GET /readyz` (database check), `GET /version` (build stamp, language
list, which integrations are configured).

## Error shape

FastAPI's default: `{"detail": "..."}` with 401 (token), 403 (role or ownership),
404, 409 (illegal state transition or duplicate claim), 429 (OTP rate limit), 500
(logged server-side; the body never carries a stack trace).
