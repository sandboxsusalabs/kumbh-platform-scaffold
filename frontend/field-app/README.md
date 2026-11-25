# Field operations app — build order

Not built in this scaffold. Target: a lightweight Android app (or PWA if devices are
shared) for officers, supervisors, response teams, sanitation staff and volunteers,
designed to keep working in crowded areas with poor signal.

## Offline model

Local store (Room / SQLite) is the source of truth for the UI. Every action gets a
`client_ref` at creation, is written locally, and is pushed through `POST /v1/field/sync`
when the network returns. The server answers per item with `applied`, `duplicate` or
`rejected`, and the app reconciles. Never send an action twice with a new `client_ref`.

## Screens and their endpoints

| Screen | Behaviour | Endpoints |
|---|---|---|
| Task inbox | Assigned jobs with `assigned → accepted → en-route → on-site → done`, nearest first | `GET /v1/field/tasks?lat=&lon=`, `POST /v1/field/tasks/{id}/claim`, `POST /v1/field/tasks/{id}/transition` |
| Incident report | Photo, voice note, location, severity — under 30 seconds, works offline | `POST /v1/incidents` (or via `/v1/field/sync`) |
| QR scan | Read a visitor ID or lost-person wristband, show the minimum needed | `GET /v1/visitors/{ref}/scan-view` |
| Facility status | Mark a toilet, water point or parking lot open / closed / full / crowded | `PATCH /v1/map/facilities/{id}/status` or `/v1/field/sync` |
| Team location and check-in | Shares position only while on duty | `POST /v1/sos`-style position ping — add `POST /v1/field/location` |
| Walkie-talk and broadcast | Push-to-talk groups; receive-only critical alerts | `GET /v1/alerts`, `GET /v1/stream/alerts` |
| Checklists and attendance | Shift roster, inspection checklists, geotagged sanitation sign-offs | `GET /v1/field/tasks` (checklist in `payload`), `POST /v1/field/tasks/{id}/transition` with `photo_ref` |
| Lost and found desk mode | Register a found person or item, match against open cases | `GET /v1/lost-persons?status=open`, `POST /v1/lost-persons/{id}/sighting`, `POST /v1/lost-persons/{id}/reunite` |

## Notes

- The app must show the last synced state with a clear "not yet sent" badge; never block
  the officer on a spinner.
- SOS never goes through the sync queue — it calls `POST /v1/sos` directly, and falls
  back to the SMS path if the request fails.
- Photo and voice uploads are background jobs with retry; the incident row is created
  first with the local file reference, and `photo_ref` is filled when the upload lands.
