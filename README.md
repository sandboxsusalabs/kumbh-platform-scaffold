# Haridwar Kumbh Mela platform — scaffold

One shared backend serving three front ends: a multilingual visitor app, a web command
dashboard for the administration and agencies, and a field app for officers and workers.
This repository is the working skeleton of that system — the backend runs, the API
contract is complete, and the visitor app shell is built and wired to it.

Built to the solution design dated 17 Nov 2026 (architecture, registration and digital
ID, groups, GIS map, SOS, lost person, dashboard modules, field app, security, scale).

```
kumbh-platform/
├── backend/                 FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── api/v1/          13 routers, one per module
│   │   ├── models/          identity, geo, ops, comms
│   │   ├── services/        otp, ids, geo, events (Kafka), realtime, audit
│   │   ├── workers/         Kafka consumers (SOS, alerts, crowd, incidents)
│   │   └── seeds/           demo layers, facilities, zones, schedule
│   ├── alembic/             initial migration incl. PostGIS geometry + GiST index
│   └── tests/               14 end-to-end tests over the real API
├── frontend/
│   ├── visitor-app/         working shell: home, map, alerts, ID, help, SOS
│   ├── dashboard/           stub — build order and API map
│   └── field-app/           stub — build order and API map
└── docs/                    architecture, API reference, data model
```

## Run it

```bash
# 1. API only, no infrastructure needed (SQLite + no Kafka; publishes are recorded)
cd backend
pip install -r ../requirements.txt
python -m app.seeds.seed
uvicorn app.main:app --reload --port 8000
#   docs       http://localhost:8000/docs
#   visitor app http://localhost:8000/app/

# 2. Full stack (PostGIS + Redis + Kafka + API + worker)
cp .env.example .env
docker compose up --build
cd backend && alembic upgrade head && python -m app.seeds.seed
```

Tests: `cd backend && python -m pytest -q` (14 pass, no external services needed).

### Try the visitor journey against the running API

```bash
# OTP is returned in the response while OTP_DEBUG_RETURN=1 (dev only)
curl -s -X POST localhost:8000/v1/auth/otp/request -H 'content-type: application/json' \
  -d '{"phone":"9876543210"}'
curl -s -X POST localhost:8000/v1/auth/otp/verify -H 'content-type: application/json' \
  -d '{"request_id":"<id>","phone":"9876543210","otp":"<dev_otp>"}'
```

Officer logins need a TOTP code. The seeded dev accounts share the secret
`JBSWY3DPEHPK3PXP`; generate the current code with:

```bash
python -c "import base64,hmac,hashlib,struct,time; \
k=base64.b32decode('JBSWY3DPEHPK3PXP'); c=int(time.time()//30); \
d=hmac.new(k,struct.pack('>Q',c),hashlib.sha1).digest(); i=d[-1]&15; \
v=struct.unpack('>I',d[i:i+4])[0]&0x7fffffff; print(f'{v%1000000:06d}')"
```

Accounts: `CR-001` / 9000000001 (control room), `MH-014` / 9000000002 (health
supervisor), `MC-021` / 9000000003 (sanitation), `AD-001` / 9000000004 (admin).

## What is real and what is stubbed

**Real, tested end to end**

- OTP registration → digital ID → QR payload and signed offline card
- Groups, members, phone-less wristband codes, one-tap "missing" → lost-person case
- Facility and layer registry with owner agency, field status updates
- Nearest-facility search, green/amber/red crowd levels, crowd ingest
- SOS: durable write → dispatch task → priority event → WebSocket push → assign → close
- Field task state machine (assigned → accepted → en-route → on-site → done), 409 on
  illegal transitions
- Offline sync with idempotency by `client_ref` (incidents, facility status, transitions)
- Lost-person registry, sightings, reunion, task auto-close
- Alerts with per-language text, zone scoping, and a forced second channel for critical
- Audit log on every personal-data read and sensitive action
- Analytics summary, role gates, JWT auth, Alembic migration up and down

**Stubbed, with the seam marked in code**

- SMS, push and public-address gateways (`services/otp.py`, `workers/runner.py`)
- Routing engine — returns a straight-line plan flagged `engine: "stub"` until OSRM or
  Valhalla is configured; zone avoidance uses zone centroids until polygons land
- CCTV / gate-counter / network-density ingest: the endpoint and level logic exist, the
  agency feed adapters do not
- QR *image* rendering (payload and offline token are produced; add the `qrcode` library
  or render client-side)
- DigiLocker / Aadhaar verification: the opt-in flag is stored, the provider call is not
- Redis is configured but the broker and rate limiter are in-process; the cross-replica
  fan-out hook is marked in `services/realtime.py`

## Design decisions worth knowing

- **Lat/lon doubles are the source of truth**; PostGIS adds a `geography` column, a sync
  trigger and a GiST index in the migration. Dev and tests run on SQLite, so nothing
  needs PostGIS to start.
- **The database write comes first, the queue second.** An SOS row and its dispatch task
  are committed before the Kafka publish, so a broker outage loses no call.
- **The QR carries a reference, not a person.** `KUMBH:VID:<token>`; resolving it needs
  officer login and is audited.
- **One contract for three apps.** No app-to-app calls; every fact has one owner table.
- **Critical alerts cannot ride one channel** — the API appends SMS if only push is sent.

## Next steps

1. Replace the three gateway stubs (SMS, push, PA) with the state's providers.
2. Load the real layer data from each owning agency; verify on the ground (phase 1 exit
   check in the design).
3. Build the dashboard shell against `/v1/crowd/*`, `/v1/sos`, `/v1/incidents`,
   `/v1/admin/*` and the `/v1/ws/ops` socket — see `frontend/dashboard/README.md`.
4. Build the field app against `/v1/field/*` — see `frontend/field-app/README.md`.
5. Load-test to 2x the agreed capacity targets, then a CERT-In audit before go-live.
