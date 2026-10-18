"""Central router assembling all API v1 domain sub-routers."""

from fastapi import APIRouter

from backend.app.api.v1.endpoints import agent, auth, documents, health, memory

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["Health"])
api_v1_router.include_router(auth.router)
api_v1_router.include_router(memory.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(agent.router)
