from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.core import get_settings
from app.db import engine, redis_client, Base, AsyncSessionLocal
from app.api.v1.router import api_router
from app.models import TalentPool

settings = get_settings()

# Public pool constants
PUBLIC_POOL_NAME = "公有人才库"
PUBLIC_POOL_DESCRIPTION = "所有猎头共享的人才库，所有人可见"


async def ensure_public_pool_exists():
    """Ensure the system has exactly one public pool"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TalentPool).where(TalentPool.is_public == True)
        )
        public_pool = result.scalar_one_or_none()

        if not public_pool:
            public_pool = TalentPool(
                name=PUBLIC_POOL_NAME,
                description=PUBLIC_POOL_DESCRIPTION,
                is_public=True,
                owner_id=None  # System owned
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


app = FastAPI(
    title="Talent Library API",
    description="Agent-Friendly Talent Library System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
