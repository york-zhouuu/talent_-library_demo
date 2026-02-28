import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.db import get_db
from app.models import Candidate
from app.schemas import TalentDetailInput, TalentDetailOutput
from app.core import NotFoundError

router = APIRouter()


@router.post("/talent_detail", response_model=TalentDetailOutput)
async def talent_detail(input: TalentDetailInput, db: AsyncSession = Depends(get_db)):
    """
    Skill API for Agent to get talent details.
    Returns comprehensive candidate information.
    """
    stmt = select(Candidate).options(selectinload(Candidate.tags)).where(Candidate.id == input.candidate_id)
    result = await db.execute(stmt)
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise NotFoundError("Candidate", input.candidate_id)

    skills = []
    if candidate.skills:
        try:
            skills = json.loads(candidate.skills)
        except:
            skills = [s.strip() for s in candidate.skills.split(",")]

    return TalentDetailOutput(
        id=candidate.id,
        name=candidate.name,
        phone=candidate.phone,
        email=candidate.email,
        city=candidate.city,
        current_company=candidate.current_company,
        current_title=candidate.current_title,
        years_of_experience=candidate.years_of_experience,
        expected_salary=candidate.expected_salary,
        skills=skills,
        summary=candidate.summary,
        tags=[t.name for t in candidate.tags]
    )
