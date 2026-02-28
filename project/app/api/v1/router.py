from fastapi import APIRouter
from app.api.v1 import candidates, talent_pools, tags, search
from app.api.v1.skill import talent_search, talent_detail
from app.api.v1.agent import filter as agent_filter, batch as agent_batch

api_router = APIRouter()

# CRUD APIs
api_router.include_router(candidates.router)
api_router.include_router(talent_pools.router)
api_router.include_router(tags.router)
api_router.include_router(search.router)

# Skill APIs (for Agent)
api_router.include_router(talent_search.router, prefix="/skill", tags=["skill"])
api_router.include_router(talent_detail.router, prefix="/skill", tags=["skill"])

# Agent APIs
api_router.include_router(agent_filter.router, prefix="/agent", tags=["agent"])
api_router.include_router(agent_batch.router, prefix="/agent", tags=["agent"])


@api_router.get("/")
async def root():
    return {"message": "Talent Library API v1"}
