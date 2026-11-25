"""API v1 router assembly.

Three front ends, one contract:
    /v1/auth, /v1/visitors, /v1/groups           visitor app
    /v1/map, /v1/crowd, /v1/alerts, /v1/sos       visitor app + dashboard
    /v1/field/*, /v1/incidents                    field app
    /v1/admin/*                                   dashboard
"""
from fastapi import APIRouter

from app.api.v1 import admin, alerts, auth, crowd, feedback, field, lost, map as map_router, ops, realtime, visitors

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(visitors.router)
api_router.include_router(map_router.router)
api_router.include_router(crowd.router)
api_router.include_router(alerts.router)
api_router.include_router(ops.router)
api_router.include_router(lost.router)
api_router.include_router(field.router)
api_router.include_router(feedback.router)
api_router.include_router(admin.router)
api_router.include_router(realtime.router)
