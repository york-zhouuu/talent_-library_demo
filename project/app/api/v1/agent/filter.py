from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Candidate
from app.schemas import AgentFilterRequest, CandidateResponse
from app.services import SearchService

router = APIRouter()


@router.post("/filter")
async def agent_filter(request: AgentFilterRequest, db: AsyncSession = Depends(get_db)):
    """
    Agent API for structured filtering.
    Supports operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $contains
    """
    service = SearchService(db)
    candidates = await service.filter_search(request.conditions, request.limit, request.offset)

    return {
        "candidates": [
            {
                "id": c.id,
                "name": c.name,
                "city": c.city,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "years_of_experience": c.years_of_experience,
                "expected_salary": c.expected_salary,
                "skills": c.skills
            }
            for c in candidates
        ],
        "count": len(candidates)
    }
