from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Tag
from app.schemas import TagCreate, TagResponse
from app.core import NotFoundError

router = APIRouter(prefix="/tags", tags=["tags"])


@router.post("", response_model=TagResponse)
async def create_tag(data: TagCreate, db: AsyncSession = Depends(get_db)):
    tag = Tag(**data.model_dump())
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.get("")
async def list_tags(
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    stmt = select(Tag)
    if category:
        stmt = stmt.where(Tag.category == category)
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    tags = list(result.scalars().all())

    count_stmt = select(func.count(Tag.id))
    if category:
        count_stmt = count_stmt.where(Tag.category == category)
    total = await db.scalar(count_stmt)

    return {"items": tags, "total": total or 0, "page": page, "page_size": page_size}


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    if not tag:
        raise NotFoundError("Tag", tag_id)
    return tag


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Tag).where(Tag.id == tag_id)
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    if not tag:
        raise NotFoundError("Tag", tag_id)

    await db.delete(tag)
    await db.commit()
    return {"message": "Tag deleted"}
