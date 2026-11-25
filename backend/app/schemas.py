"""Request and response contracts for the public API.

Grouped by area to keep the scaffold navigable; split into a package once the API
surface grows past this.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import SUPPORTED_LANGUAGES


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=10, max_length=15, examples=["9876543210"])

    @field_validator("phone")
    @classmethod
    def _digits(cls, value: str) -> str:
        cleaned = value.strip().replace(" ", "").replace("-", "")
        if not cleaned.lstrip("+").isdigit():
            raise ValueError("phone must contain digits only")
        return cleaned


class OtpRequestOut(BaseModel):
    request_id: str
    expires_in: int
    channel: str = "sms"
    dev_otp: Optional[str] = None  # only when OTP_DEBUG_RETURN=1


class OtpVerifyIn(BaseModel):
    request_id: str
    phone: str
    otp: str = Field(min_length=4, max_length=8)


class OfficerLoginIn(BaseModel):
    employee_code: str
    phone: str
    otp: str
    totp: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    is_registered: bool = False


# ---------------------------------------------------------------- visitor
class VisitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    gender: Optional[Literal["female", "male", "other"]] = None
    home_state: Optional[str] = None
    language: str = "hi"
    emergency_contacts: List[Dict[str, str]] = Field(default_factory=list, max_length=2)
    accessibility_needs: List[str] = Field(default_factory=list)
    large_text: bool = False
    # Verification is opt-in; the identifier itself is never stored.
    verification: Optional[Literal["aadhaar", "digilocker"]] = None

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")
        return value


class VisitorOut(ORM):
    id: str
    name: Optional[str]
    age: Optional[int]
    gender: Optional[str]
    home_state: Optional[str]
    language: str
    emergency_contacts: List[Dict[str, str]] = []
    accessibility_needs: List[str] = []
    large_text: bool
    group_id: Optional[str]
    created_at: datetime


class IdCardOut(BaseModel):
    visitor_id: str
    qr_payload: str
    offline_token: str
    issued_at: str
    valid_until: str
    qr_hint: str


class ScanViewOut(BaseModel):
    """The minimum a field officer sees after scanning a visitor QR."""

    visitor_ref: str
    name: Optional[str]
    age: Optional[int]
    group_id: Optional[str]
    group_name: Optional[str]
    emergency_contacts: List[Dict[str, str]]
    language: str
    scanned_by: str
    audited: bool = True


# ---------------------------------------------------------------- groups
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    leader_visitor_id: str


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    phone: Optional[str] = None
    is_minor: bool = False
    guardian_member_id: Optional[str] = None


class MemberOut(ORM):
    id: str
    name: str
    age: Optional[int]
    visitor_id: Optional[str]
    is_minor: bool
    role: str
    invite_state: str
    wristband_code: Optional[str]
    missing_since: Optional[datetime]


class GroupOut(ORM):
    id: str
    name: str
    leader_visitor_id: str
    location_sharing: bool
    members: List[MemberOut] = []


class LocationSharingIn(BaseModel):
    enabled: bool


class GroupLocationsIn(BaseModel):
    """Members push their last known point while sharing is on, or during an SOS."""

    locations: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------- map / facilities
class FacilityOut(ORM):
    id: str
    layer_key: str
    category: str
    name: str
    lat: float
    lon: float
    zone_code: Optional[str]
    status: str
    capacity: Optional[int]
    occupied: Optional[int]
    is_accessible: bool
    opening_hours: Optional[str]
    owner_agency: str
    updated_at: datetime


class NearbyOut(BaseModel):
    facility: FacilityOut
    distance_m: float
    walk_minutes: int


class LayerOut(ORM):
    key: str
    name: str
    owner_agency: str
    geometry_type: str
    is_visible: bool
    sort_order: int
    updated_at: datetime


class FacilityStatusIn(BaseModel):
    status: Literal["open", "closed", "full", "crowded"]
    occupied: Optional[int] = None
    note: Optional[str] = None


class RouteOut(BaseModel):
    mode: str
    engine: str
    note: str
    distance_m: float
    duration_s: int
    waypoints: List[Dict[str, float]]
    avoided_zones: int


# ---------------------------------------------------------------- crowd / schedule
class ZoneOut(ORM):
    zone_code: str
    name: str
    is_ghat: bool
    level: str
    capacity: int
    estimated_persons: int
    occupancy_ratio: float
    inflow_per_min: int
    outflow_per_min: int
    one_way_flow: Optional[str]
    is_closed: bool
    updated_at: datetime


class CrowdIngestIn(BaseModel):
    zone_code: str
    estimated_persons: int = Field(ge=0)
    inflow_per_min: int = 0
    outflow_per_min: int = 0
    source: Literal["cctv", "gate", "network", "manual"] = "cctv"
    one_way_flow: Optional[Literal["inward", "outward"]] = None
    is_closed: Optional[bool] = None


class SnanSlotOut(ORM):
    id: str
    date: date
    ghat_code: str
    ghat_name: str
    start_time: time
    end_time: time
    is_shahi: bool
    note: Optional[str]


class WeatherOut(ORM):
    temperature_c: float
    rain_mm: float
    river_level_m: Optional[float]
    river_level_warning: Optional[str]
    condition: str
    recorded_at: datetime


# ---------------------------------------------------------------- alerts
class AlertCreate(BaseModel):
    kind: Literal["info", "critical"] = "info"
    category: str = "general"
    title_i18n: Dict[str, str]
    body_i18n: Dict[str, str]
    zones: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    audience: Literal["all", "visitors", "field", "agency"] = "all"
    channels: List[Literal["push", "sms", "pa", "in_app"]] = Field(default_factory=lambda: ["push"])
    requires_ack: bool = False
    expires_at: Optional[datetime] = None

    @field_validator("title_i18n", "body_i18n")
    @classmethod
    def _has_language(cls, value: Dict[str, str]) -> Dict[str, str]:
        if not value:
            raise ValueError("at least one language is required")
        for code in value:
            if code not in SUPPORTED_LANGUAGES:
                raise ValueError(f"unsupported language {code}")
        return value


class AlertOut(ORM):
    id: str
    kind: str
    category: str
    title_i18n: Dict[str, str]
    body_i18n: Dict[str, str]
    zones: List[str]
    audience: str
    channels: List[str] = []
    requires_ack: bool
    status: str
    created_at: datetime
    expires_at: Optional[datetime]


class AlertDeliveryOut(ORM):
    channel: str
    target_count: int
    sent_count: int
    failed_count: int


class BroadcastOut(BaseModel):
    alert: AlertOut
    deliveries: List[AlertDeliveryOut]
    degraded_channels: List[str] = []


# ---------------------------------------------------------------- SOS / incidents
class SosCreate(BaseModel):
    category: Literal["medical", "police", "fire", "lost_child", "other"] = "medical"
    lat: Optional[float] = None
    lon: Optional[float] = None
    accuracy_m: Optional[float] = None
    silent: bool = False
    channel: Literal["data", "sms", "voice", "ussd"] = "data"
    note: Optional[str] = None
    client_ref: Optional[str] = None


class SosOut(ORM):
    id: str
    reference: str
    category: str
    status: str
    priority: int
    channel: str
    lat: Optional[float]
    lon: Optional[float]
    assigned_team: Optional[str]
    assigned_task_id: Optional[str]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    closed_at: Optional[datetime]


class SosAssignIn(BaseModel):
    team: str
    task_id: Optional[str] = None


class IncidentCreate(BaseModel):
    kind: Literal["crowd_crush", "medical", "fire", "fault", "other"]
    description: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    zone_code: Optional[str] = None
    photo_ref: Optional[str] = None
    voice_ref: Optional[str] = None
    severity: Literal["low", "medium", "high"] = "medium"
    client_ref: Optional[str] = None
    created_at_client: Optional[datetime] = None


class IncidentOut(ORM):
    id: str
    reference: str
    kind: str
    description: Optional[str]
    zone_code: Optional[str]
    severity: str
    status: str
    photo_ref: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------- lost persons
class LostPersonCreate(BaseModel):
    subject_name: str = Field(min_length=1, max_length=120)
    subject_age: Optional[int] = Field(default=None, ge=0, le=120)
    subject_gender: Optional[Literal["male", "female", "other"]] = None
    description: Optional[str] = Field(default=None, max_length=1200)
    photo_ref: Optional[str] = None
    last_seen_lat: Optional[float] = None
    last_seen_lon: Optional[float] = None
    last_seen_place: Optional[str] = Field(default=None, max_length=160)
    last_seen_at: Optional[datetime] = None
    languages_spoken: Optional[str] = Field(default=None, max_length=240)
    medical_needs: Optional[str] = Field(default=None, max_length=500)
    reporter_name: Optional[str] = Field(default=None, max_length=120)
    reporter_phone: Optional[str] = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    reporter_relation: Optional[str] = Field(default=None, max_length=40)
    alternate_phone: Optional[str] = Field(default=None, pattern=r"^[6-9][0-9]{9}$")
    reporter_location: Optional[str] = Field(default=None, max_length=160)
    group_member_id: Optional[str] = None
    is_child: bool = False


class LostPersonOut(ORM):
    id: str
    case_no: str
    subject_name: str
    subject_age: Optional[int]
    description: Optional[str]
    last_seen_place: Optional[str]
    status: str
    is_child: bool
    photo_ref: Optional[str]
    created_at: datetime
    reunited_at: Optional[datetime]


class SightingIn(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    note: Optional[str] = None


# ---------------------------------------------------------------- field app
class TaskOut(ORM):
    id: str
    code: str
    kind: str
    title: str
    description: Optional[str]
    zone_code: Optional[str]
    priority: int
    state: str
    lat: Optional[float]
    lon: Optional[float]
    due_at: Optional[datetime]
    checklist: List[Any] = []
    payload: Dict[str, Any] = {}


class TaskTransitionIn(BaseModel):
    state: Literal["accepted", "en_route", "on_site", "done", "cancelled"]
    lat: Optional[float] = None
    lon: Optional[float] = None
    photo_ref: Optional[str] = None
    note: Optional[str] = None


class SyncItem(BaseModel):
    """One queued offline action from the field app."""

    kind: Literal["incident", "facility_status", "task_transition", "sos"]
    client_ref: str
    payload: Dict[str, Any]


class SyncIn(BaseModel):
    items: List[SyncItem] = Field(default_factory=list, max_length=200)


class SyncItemResult(BaseModel):
    client_ref: str
    status: Literal["applied", "duplicate", "rejected"]
    server_id: Optional[str] = None
    reason: Optional[str] = None


class SyncOut(BaseModel):
    results: List[SyncItemResult]
    server_time: datetime


# ---------------------------------------------------------------- feedback
class FeedbackCreate(BaseModel):
    category: Literal["sanitation", "water", "safety", "transport", "staff", "other"]
    description: str = Field(min_length=4, max_length=2000)
    lat: Optional[float] = None
    lon: Optional[float] = None
    photo_ref: Optional[str] = None
    client_ref: Optional[str] = None


class FeedbackOut(ORM):
    id: str
    ticket_no: str
    category: str
    description: str
    status: str
    agency: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]


# ---------------------------------------------------------------- admin
class AnalyticsSummary(BaseModel):
    generated_at: datetime
    registered_visitors: int
    active_sos: int
    open_incidents: int
    open_lost_cases: int
    open_tasks: int
    open_complaints: int
    zones_red: int
    zones_amber: int
    median_sos_ack_seconds: Optional[float]
    alerts_last_24h: int
