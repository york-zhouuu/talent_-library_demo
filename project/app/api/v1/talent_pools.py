from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models import TalentPool, Candidate, candidate_pools, pool_shares
from app.schemas import (
    TalentPoolCreate, TalentPoolUpdate, TalentPoolResponse,
    ShareScope, PoolShareCreate, PoolShareResponse
)
from app.core import NotFoundError, ValidationError

router = APIRouter(prefix="/talent-pools", tags=["talent-pools"])


def get_current_user(x_user_id: str = Header(default="default_user")) -> str:
    """从请求头获取当前用户ID"""
    return x_user_id


async def get_pool_shares(db: AsyncSession, pool_id: int) -> list[PoolShareResponse]:
    """获取人才库的共享列表"""
    stmt = select(pool_shares).where(pool_shares.c.pool_id == pool_id)
    result = await db.execute(stmt)
    shares = result.fetchall()
    return [PoolShareResponse(user_id=s.user_id, permission=s.permission) for s in shares]


async def can_access_pool(db: AsyncSession, pool: TalentPool, user_id: str) -> bool:
    """检查用户是否有权访问人才库"""
    # 所有者始终有权限
    if pool.owner_id == user_id:
        return True

    # 根据共享范围判断
    if pool.share_scope == "org":
        return True  # 全组织可见

    if pool.share_scope == "team" and pool.team_id:
        # TODO: 检查用户是否在团队中 (需要团队服务)
        return True  # 暂时允许

    if pool.share_scope == "custom":
        # 检查是否在共享列表中
        stmt = select(pool_shares).where(
            and_(pool_shares.c.pool_id == pool.id, pool_shares.c.user_id == user_id)
        )
        result = await db.execute(stmt)
        return result.fetchone() is not None

    return False


async def can_edit_pool(db: AsyncSession, pool: TalentPool, user_id: str) -> bool:
    """检查用户是否有编辑权限"""
    if pool.owner_id == user_id:
        return True

    if pool.share_scope == "custom":
        stmt = select(pool_shares).where(
            and_(
                pool_shares.c.pool_id == pool.id,
                pool_shares.c.user_id == user_id,
                pool_shares.c.permission.in_(["edit", "admin"])
            )
        )
        result = await db.execute(stmt)
        return result.fetchone() is not None

    return False


@router.post("", response_model=TalentPoolResponse)
async def create_pool(
    data: TalentPoolCreate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """创建人才库"""
    # 使用当前用户作为所有者
    pool = TalentPool(
        name=data.name,
        description=data.description,
        owner_id=data.owner_id or current_user,
        share_scope=data.share_scope.value,
        team_id=data.team_id
    )
    db.add(pool)
    await db.commit()
    await db.refresh(pool)

    return TalentPoolResponse(
        id=pool.id,
        name=pool.name,
        description=pool.description,
        owner_id=pool.owner_id,
        share_scope=ShareScope(pool.share_scope),
        team_id=pool.team_id,
        created_at=pool.created_at,
        updated_at=pool.updated_at,
        candidate_count=0,
        shared_with=[]
    )


@router.get("")
async def list_pools(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """列出用户可访问的人才库"""
    offset = (page - 1) * page_size

    # 查询用户可访问的库：自己的 + 组织共享的 + 自定义共享给自己的
    stmt = select(TalentPool).where(
        or_(
            TalentPool.owner_id == current_user,
            TalentPool.share_scope == "org",
            and_(
                TalentPool.share_scope == "custom",
                TalentPool.id.in_(
                    select(pool_shares.c.pool_id).where(pool_shares.c.user_id == current_user)
                )
            )
        )
    ).offset(offset).limit(page_size)

    result = await db.execute(stmt)
    pools = list(result.scalars().all())

    # 获取候选人数量和共享信息
    response = []
    for pool in pools:
        count_stmt = select(func.count()).select_from(candidate_pools).where(
            candidate_pools.c.pool_id == pool.id
        )
        count = await db.scalar(count_stmt) or 0

        shares = await get_pool_shares(db, pool.id) if pool.share_scope == "custom" else []

        response.append(TalentPoolResponse(
            id=pool.id,
            name=pool.name,
            description=pool.description,
            owner_id=pool.owner_id,
            share_scope=ShareScope(pool.share_scope),
            team_id=pool.team_id,
            created_at=pool.created_at,
            updated_at=pool.updated_at,
            candidate_count=count,
            shared_with=shares
        ))

    return {"items": response, "page": page, "page_size": page_size}


@router.get("/{pool_id}", response_model=TalentPoolResponse)
async def get_pool(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """获取人才库详情"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if not await can_access_pool(db, pool, current_user):
        raise ValidationError("无权访问此人才库")

    count_stmt = select(func.count()).select_from(candidate_pools).where(
        candidate_pools.c.pool_id == pool_id
    )
    count = await db.scalar(count_stmt) or 0

    shares = await get_pool_shares(db, pool.id) if pool.share_scope == "custom" else []

    return TalentPoolResponse(
        id=pool.id,
        name=pool.name,
        description=pool.description,
        owner_id=pool.owner_id,
        share_scope=ShareScope(pool.share_scope),
        team_id=pool.team_id,
        created_at=pool.created_at,
        updated_at=pool.updated_at,
        candidate_count=count,
        shared_with=shares
    )


@router.put("/{pool_id}", response_model=TalentPoolResponse)
async def update_pool(
    pool_id: int,
    data: TalentPoolUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """更新人才库"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    # 只有所有者可以修改设置
    if pool.owner_id != current_user:
        raise ValidationError("只有所有者可以修改人才库设置")

    if data.name is not None:
        pool.name = data.name
    if data.description is not None:
        pool.description = data.description
    if data.share_scope is not None:
        pool.share_scope = data.share_scope.value
    if data.team_id is not None:
        pool.team_id = data.team_id

    await db.commit()
    await db.refresh(pool)

    count_stmt = select(func.count()).select_from(candidate_pools).where(
        candidate_pools.c.pool_id == pool_id
    )
    count = await db.scalar(count_stmt) or 0
    shares = await get_pool_shares(db, pool.id) if pool.share_scope == "custom" else []

    return TalentPoolResponse(
        id=pool.id,
        name=pool.name,
        description=pool.description,
        owner_id=pool.owner_id,
        share_scope=ShareScope(pool.share_scope),
        team_id=pool.team_id,
        created_at=pool.created_at,
        updated_at=pool.updated_at,
        candidate_count=count,
        shared_with=shares
    )


@router.delete("/{pool_id}")
async def delete_pool(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """删除人才库"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if pool.owner_id != current_user:
        raise ValidationError("只有所有者可以删除人才库")

    await db.delete(pool)
    await db.commit()
    return {"message": "人才库已删除"}


# ==================== 共享管理 ====================

@router.post("/{pool_id}/shares")
async def add_share(
    pool_id: int,
    share: PoolShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """添加共享"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if pool.owner_id != current_user:
        raise ValidationError("只有所有者可以管理共享")

    # 自动切换到 custom 模式
    if pool.share_scope != "custom":
        pool.share_scope = "custom"

    # 检查是否已共享
    check_stmt = select(pool_shares).where(
        and_(pool_shares.c.pool_id == pool_id, pool_shares.c.user_id == share.user_id)
    )
    existing = await db.execute(check_stmt)
    if existing.fetchone():
        # 更新权限
        update_stmt = pool_shares.update().where(
            and_(pool_shares.c.pool_id == pool_id, pool_shares.c.user_id == share.user_id)
        ).values(permission=share.permission.value)
        await db.execute(update_stmt)
    else:
        # 添加新共享
        insert_stmt = pool_shares.insert().values(
            pool_id=pool_id,
            user_id=share.user_id,
            permission=share.permission.value
        )
        await db.execute(insert_stmt)

    await db.commit()
    return {"message": f"已共享给 {share.user_id}"}


@router.delete("/{pool_id}/shares/{user_id}")
async def remove_share(
    pool_id: int,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """移除共享"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if pool.owner_id != current_user:
        raise ValidationError("只有所有者可以管理共享")

    delete_stmt = pool_shares.delete().where(
        and_(pool_shares.c.pool_id == pool_id, pool_shares.c.user_id == user_id)
    )
    await db.execute(delete_stmt)
    await db.commit()
    return {"message": f"已取消对 {user_id} 的共享"}


@router.get("/{pool_id}/shares")
async def list_shares(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """获取共享列表"""
    stmt = select(TalentPool).where(TalentPool.id == pool_id)
    result = await db.execute(stmt)
    pool = result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if not await can_access_pool(db, pool, current_user):
        raise ValidationError("无权访问此人才库")

    shares = await get_pool_shares(db, pool_id)
    return {"shares": shares}


# ==================== 候选人管理 ====================

@router.post("/{pool_id}/candidates/{candidate_id}")
async def add_candidate_to_pool(
    pool_id: int,
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """添加候选人到人才库"""
    pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if not await can_edit_pool(db, pool, current_user):
        raise ValidationError("无权编辑此人才库")

    cand_stmt = select(Candidate).where(Candidate.id == candidate_id)
    cand_result = await db.execute(cand_stmt)
    candidate = cand_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    if candidate not in pool.candidates:
        pool.candidates.append(candidate)
        await db.commit()

    return {"message": "候选人已添加到人才库"}


@router.delete("/{pool_id}/candidates/{candidate_id}")
async def remove_candidate_from_pool(
    pool_id: int,
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """从人才库移除候选人"""
    pool_stmt = select(TalentPool).options(selectinload(TalentPool.candidates)).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if not await can_edit_pool(db, pool, current_user):
        raise ValidationError("无权编辑此人才库")

    cand_stmt = select(Candidate).where(Candidate.id == candidate_id)
    cand_result = await db.execute(cand_stmt)
    candidate = cand_result.scalar_one_or_none()
    if not candidate:
        raise NotFoundError("Candidate", candidate_id)

    if candidate in pool.candidates:
        pool.candidates.remove(candidate)
        await db.commit()

    return {"message": "候选人已从人才库移除"}


@router.get("/{pool_id}/candidates")
async def list_pool_candidates(
    pool_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """获取人才库中的候选人"""
    pool_stmt = select(TalentPool).where(TalentPool.id == pool_id)
    pool_result = await db.execute(pool_stmt)
    pool = pool_result.scalar_one_or_none()
    if not pool:
        raise NotFoundError("TalentPool", pool_id)

    if not await can_access_pool(db, pool, current_user):
        raise ValidationError("无权访问此人才库")

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
