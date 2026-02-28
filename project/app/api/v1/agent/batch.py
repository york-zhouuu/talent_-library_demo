from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models import Candidate
from app.schemas import BatchGetRequest, BatchUpdateRequest

router = APIRouter()


@router.post("/batch/get")
async def batch_get(request: BatchGetRequest, db: AsyncSession = Depends(get_db)):
    """
    Agent API for batch getting candidates.
    """
    stmt = select(Candidate).options(selectinload(Candidate.tags)).where(Candidate.id.in_(request.ids))
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    return {
        "candidates": [
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "city": c.city,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "years_of_experience": c.years_of_experience,
                "expected_salary": c.expected_salary,
                "skills": c.skills,
                "summary": c.summary,
                "tags": [t.name for t in c.tags]
            }
            for c in candidates
        ]
    }


@router.post("/batch/update")
async def batch_update(request: BatchUpdateRequest, db: AsyncSession = Depends(get_db)):
    """
    Agent API for batch updating candidates.
    """
    stmt = select(Candidate).where(Candidate.id.in_(request.ids))
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    updated = []
    for c in candidates:
        for key, value in request.update.items():
            if hasattr(c, key):
                setattr(c, key, value)
        updated.append(c.id)

    await db.commit()

    return {"updated_ids": updated, "count": len(updated)}
