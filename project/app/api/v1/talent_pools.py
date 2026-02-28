from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models import TalentPool, Candidate, candidate_pools
from app.schemas import TalentPoolCreate, TalentPoolResponse
from app.core import NotFoundError, ValidationError

router = APIRouter(prefix="/talent-pools", tags=["talent-pools"])


@router.post("", response_model=TalentPoolResponse)
async def create_pool(data: TalentPoolCreate, db: AsyncSession = Depends(get_db)):
    # Public pool is system-created, users can only create private pools
    if data.is_public:
        raise ValidationError("公有库由系统创建，不可手动创建")

    # Private pool must have an owner
    if not data.owner_id:
        raise ValidationError("私有库必须指定所有者")

    pool = TalentPool(**data.model_dump())
    db.add(pool)
    await db.commit()
    await db.refresh(pool)
    return TalentPoolResponse(**pool.__dict__, candidate_count=0)


@router.get("")
async def list_pools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_public: bool | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    stmt = select(TalentPool)
    if is_public is not None:
        stmt = stmt.where(TalentPool.is_public == is_public)
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    pools = list(result.scalars().all())

    # Get candidate counts
    response = []
    for pool in pools:
        count_stmt = select(func.count()).select_from(candidate_pools).where(
            candidate_pools.c.pool_id == pool.id
        )
        count = await db.scalar(count_stmt) or 0
        response.append(TalentPoolResponse(**pool.__dict__, candidate_count=count))

    return {"items": response, "page": page, "page_size": page_size}


@router.get("/{pool_id}", response_model=TalentPoolResponse)
async def get_pool(pool_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    count_stmt = select(func.count()).select_from(candidate_pools).where(
        candidate_pools.c.pool_id == pool_id
    )
    count = await db.scalar(count_stmt) or 0

    return TalentPoolResponse(**pool.__dict__, candidate_count=count)


@router.delete("/{pool_id}")
async def delete_pool(pool_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    # Cannot delete the public pool
    if pool.is_public:
        raise ValidationError("公有库不可删除")

    await db.delete(pool)
    await db.commit()
    return {"message": "Pool deleted"}


@router.post("/{pool_id}/candidates/{candidate_id}")
async def add_candidate_to_pool(pool_id: int, candidate_id: int, db: AsyncSession = Depends(get_db)):
    pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    cand_stmt = select(Candidate).where(Candidate.id == candidate_id)
    cand_result = await db.execute(cand_stmt)
    candidate = cand_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    if candidate not in pool.candidates:
        pool.candidates.append(candidate)
        await db.commit()

    return {"message": "Candidate added to pool"}


@router.delete("/{pool_id}/candidates/{candidate_id}")
async def remove_candidate_from_pool(pool_id: int, candidate_id: int, db: AsyncSession = Depends(get_db)):
    pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    cand_stmt = select(Candidate).where(Candidate.id == candidate_id)
    cand_result = await db.execute(cand_stmt)
    candidate = cand_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    if candidate in pool.candidates:
        pool.candidates.remove(candidate)
        await db.commit()

    return {"message": "Candidate removed from pool"}


@router.get("/{pool_id}/candidates")
async def list_pool_candidates(
    pool_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    pool_stmt = select(TalentPool).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    offset = (page - 1) * page_size
    stmt = (
        select(Candidate)
        .join(candidate_pools)
        .where(candidate_pools.c.pool_id == pool_id)
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    count_stmt = select(func.count()).select_from(candidate_pools).where(
        candidate_pools.c.pool_id == pool_id
    )
    total = await db.scalar(count_stmt) or 0

    return {"items": candidates, "total": total, "page": page, "page_size": page_size}
