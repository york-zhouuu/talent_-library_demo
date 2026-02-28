import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models import Candidate
from app.schemas import TalentSearchInput, TalentSearchOutput, TalentSearchResult
from app.services import SearchService

router = APIRouter()


@router.post("/talent_search", response_model=TalentSearchOutput)
async def talent_search(input: TalentSearchInput, db: AsyncSession = Depends(get_db)):
    """
    Skill API for Agent to search talents.
    Returns structured results optimized for Agent consumption.
    """
    service = SearchService(db)
    from app.schemas import SearchQuery
    result = await service.quick_search(SearchQuery(
        query=input.query,
        limit=input.limit,
        pool_id=input.pool_id
    ))

    search_results = []
    for c in result.candidates:
        search_results.append(TalentSearchResult(
            id=c.id,
            name=c.name,
            title=c.current_title,
            company=c.current_company,
            city=c.city,
            experience_years=c.years_of_experience,
            salary_expectation=c.expected_salary,
            match_score=c.match_score,
            match_summary="; ".join([r.reason for r in c.match_reasons])
        ))

    return TalentSearchOutput(
        results=search_results,
        total_found=result.total,
        session_id=result.session_id
    )
