"""Central router assembling all API v1 domain sub-routers."""

from fastapi import APIRouter

from backend.app.api.v1.endpoints import (
    agent,
    auth,
    automation,
    devices,
    documents,
    health,
    memory,
    sync,
    voice,
)

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["Health"])
api_v1_router.include_router(auth.router)
api_v1_router.include_router(memory.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(agent.router)
api_v1_router.include_router(automation.router)
api_v1_router.include_router(devices.router)
api_v1_router.include_router(sync.router)
api_v1_router.include_router(voice.router)
