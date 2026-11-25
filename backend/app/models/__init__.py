"""Model registry. Importing this module registers every table on `Base.metadata`."""
from app.models.comms import Alert, AlertDelivery, AlertReceipt, AuditLog
from app.models.geo import (
    FACILITY_CATEGORIES,
    LAYER_KEYS,
    Facility,
    MapLayer,
    SnanSlot,
    WeatherSnapshot,
    ZoneDensity,
)
from app.models.identity import Group, GroupMember, Officer, OtpRequest, Visitor
from app.models.ops import (
    SOS_STATES,
    TASK_STATES,
    Feedback,
    Incident,
    LostPersonCase,
    LostPersonSighting,
    SosEvent,
    Task,
    TaskEvent,
)

__all__ = [
    "Alert", "AlertDelivery", "AlertReceipt", "AuditLog",
    "Facility", "MapLayer", "SnanSlot", "WeatherSnapshot", "ZoneDensity",
    "FACILITY_CATEGORIES", "LAYER_KEYS",
    "Group", "GroupMember", "Officer", "OtpRequest", "Visitor",
    "Feedback", "Incident", "LostPersonCase", "LostPersonSighting",
    "SosEvent", "Task", "TaskEvent", "SOS_STATES", "TASK_STATES",
]
