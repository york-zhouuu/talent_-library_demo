from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.core import get_settings
from app.db import engine, redis_client, Base, AsyncSessionLocal
from app.api.v1.router import api_router
from app.models import TalentPool
from app.services import close_es_service

settings = get_settings()

# Public pool constants
PUBLIC_POOL_NAME = "公有人才库"
PUBLIC_POOL_DESCRIPTION = "所有猎头共享的人才库，所有人可见"


async def ensure_public_pool_exists():
    """Ensure the system has exactly one org-wide shared pool"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TalentPool).where(
                TalentPool.share_scope == "org",
                TalentPool.name == PUBLIC_POOL_NAME
            )
        )
        public_pool = result.scalar_one_or_none()

        if not public_pool:
            public_pool = TalentPool(
                name=PUBLIC_POOL_NAME,
                description=PUBLIC_POOL_DESCRIPTION,
                share_scope="org",
                is_public=True,
                owner_id="system"
            )
            db.add(public_pool)
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - create tables for SQLite
    if "sqlite" in settings.database_url:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Ensure public pool exists
    await ensure_public_pool_exists()

    yield
    # Shutdown
    await engine.dispose()
    await redis_client.close()
    await close_es_service()


app = FastAPI(
    title="Talent Library API",
    description="Agent-Friendly Talent Library System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend - allow all origins for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
