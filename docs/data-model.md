# Data model

One database, 22 tables, four groups. Every fact has exactly one owning table, which is
what keeps the visitor app, the dashboard and the field app from disagreeing.

## identity

| Table | Key fields | Rules |
|---|---|---|
| `visitors` | `phone` (unique), `name`, `age`, `gender`, `home_state`, `language`, `emergency_contacts` (JSON, ≤2), `id_card_token` (unique), `group_id`, `last_lat/lon`, `verification_method`, `is_active` | Created at first OTP login with phone only; `name` present means "registration complete". No Aadhaar number is stored, only the fact and method of verification. Deletion clears the profile and sets `is_active = false` |
| `otp_requests` | `phone`, `code_hash`, `attempts`, `expires_at`, `consumed_at` | OTP is stored as an HMAC, never in clear. Five attempts, then the challenge is dead |
| `groups` | `leader_visitor_id`, `location_sharing` | Sharing is off by default; an open SOS overrides it |
| `group_members` | `group_id`, `visitor_id` (nullable), `name`, `age`, `is_minor`, `wristband_code`, `role`, `invite_state`, `guardian_member_id`, `missing_since` | `visitor_id` is empty for children and elders without phones — they exist as name, age and a printed wristband code |
| `officers` | `employee_code` (unique), `role`, `agency`, `zone`, `totp_secret` | Agency + zone scope every query an official makes |

## geo

| Table | Key fields | Rules |
|---|---|---|
| `map_layers` | `key` (PK), `owner_agency`, `geometry_type`, `is_visible`, `sort_order` | 14 layers, each with a named owner — the design's "every layer has a data owner" |
| `facilities` | `layer_key`, `category`, `name`, `lat`, `lon`, `zone_code`, `status`, `capacity`, `occupied`, `is_accessible`, `owner_agency`, `updated_by` | `status` is the single field of record for open/closed/full/crowded. PostGIS adds `geom geography(Point,4326)` kept in step by a trigger, with a GiST index |
| `zone_density` | `zone_code` (PK), `is_ghat`, `level`, `capacity`, `estimated_persons`, `occupancy_ratio`, `inflow_per_min`, `outflow_per_min`, `one_way_flow`, `is_closed`, `source`, `centroid_lat/lon` | `level` derives from ratio: ≥0.85 red, ≥0.60 amber, else green. Centroids let routing detour until polygons land |
| `snan_slots` | `date`, `ghat_code`, `start_time`, `end_time`, `is_shahi` | Shahi snan days are highlighted in the app |
| `weather_snapshots` | `temperature_c`, `rain_mm`, `river_level_m`, `river_level_warning` | Latest reading served to weak-network clients |

## ops

| Table | Key fields | Rules |
|---|---|---|
| `sos_events` | `reference` (unique), `visitor_id`, `group_id`, `category`, `lat/lon`, `is_silent`, `channel`, `priority`, `status`, `assigned_team`, `assigned_task_id`, `acknowledged_at`, `client_ref` (unique) | Priority 1 for medical, fire, lost child. `client_ref` makes offline replay idempotent |
| `incidents` | `reference`, `reporter_id`, `kind`, `lat/lon`, `photo_ref`, `voice_ref`, `severity`, `client_ref` | Field reports; replay-safe |
| `lost_person_cases` | `case_no` (unique), `reported_by_visitor_id`, `group_member_id`, `subject_name`, `subject_age`, `photo_ref`, `last_seen_*`, `centre_id`, `status`, `is_child` | `open → sighting → reunited`; one registry for all three apps |
| `lost_person_sightings` | `case_id`, `reported_by`, `lat/lon`, `note` | Family-visible progress |
| `tasks` | `code` (unique), `kind`, `assignee_id`, `agency`, `priority`, `state`, `lat/lon`, `payload` (JSON), `checklist` (JSON) | Created by the API for every SOS and lost-person case |
| `task_events` | `task_id`, `state`, `actor_id`, `lat/lon`, `photo_ref` | Geotagged proof of each transition |
| `feedback` | `ticket_no` (unique), `visitor_id`, `category`, `agency`, `status`, `client_ref` | Routed to the responsible agency by category |

### Task state machine

```
assigned → accepted → en_route → on_site → done
    └──────────┴───────────┴──────────┴──→ cancelled
```

Any other move returns 409. `done` and `cancelled` are terminal.

## comms

| Table | Key fields | Rules |
|---|---|---|
| `alerts` | `kind`, `category`, `title_i18n` (JSON), `body_i18n` (JSON), `zones`, `languages`, `audience`, `channels`, `requires_ack`, `status`, `expires_at` | Text per language at write time; zone-scoped alerts are invisible outside their zones; critical alerts require an ack |
| `alert_deliveries` | `alert_id`, `channel`, `target_count`, `sent_count`, `failed_count`, `error` | A silent channel failure is visible to the control room |
| `alert_receipts` | `alert_id`, `principal_id`, `read_at` | Pinned alerts cannot be dismissed before a receipt exists |
| `audit_logs` | `actor_id`, `actor_role`, `agency`, `action`, `object_type`, `object_id`, `ip`, `meta` (JSON) | Append-only: no update or delete endpoint. Written on every personal-data read and sensitive action |

## Indexing and retention

- Indexed: visitor phone and ID token; facility layer, category, zone, lat, lon; zone
  level; SOS status and created-at; incident status; task assignee, state, zone; audit
  action and created-at.
- PostGIS GiST index on `facilities.geom` for radius and nearest queries.
- Retention: location columns are cleared on the published post-event schedule; SOS,
  lost-person and incident records are retained per the administration's rule, with
  personal fields detached from the profile on erasure.
