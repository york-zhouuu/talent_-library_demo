import json
import time
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas import SearchQuery, DeepSearchQuery, SearchResponse, SearchResultItem, MatchReason
from app.services import SearchService
from app.services.router_service import SearchRouter, SearchPath, SearchRequest, get_search_router
from app.services.es_service import get_es_service

router = APIRouter(prefix="/search", tags=["search"])


class IntelligentSearchQuery(BaseModel):
    query: str
    limit: int = 20


class UnifiedSearchRequest(BaseModel):
    """Unified search query - single entry point for all searches"""
    query: str
    filters: dict | None = None  # {city, min_experience, max_experience, min_salary, max_salary}
    limit: int = 20
    force_path: str | None = None  # "direct" or "full" to override router


@router.post("/")
async def unified_search(request: UnifiedSearchRequest, db: AsyncSession = Depends(get_db)):
    """
    统一搜索接口 - 智能路由

    根据查询内容自动选择最优路径：
    - 简单关键词 (如 "Python", "北京 产品经理") → DIRECT (ES快搜, <100ms)
    - 自然语言 (如 "找能带团队的技术专家") → FULL (AI智能搜索, 3-5s)

    返回统一格式，包含：
    - candidates: 候选人列表（带高亮）
    - aggregations: 聚合统计（城市、经验、薪资分布）
    - search_path: 实际使用的搜索路径
    - latency_ms: 搜索耗时
    """
    start_time = time.time()

    # Determine search path
    search_router = get_search_router()
    router_request = SearchRequest(
        query=request.query,
        filters=request.filters,
        limit=request.limit,
        force_path=request.force_path
    )
    path = search_router.determine_path(router_request)

    # Execute search based on path
    if path == SearchPath.DIRECT:
        result = await _direct_search(request)
    else:  # FULL path - AI search
        result = await _ai_search(request, db)

    latency_ms = int((time.time() - start_time) * 1000)

    return {
        **result,
        "search_path": path.value,
        "path_description": _get_path_description(path),
        "latency_ms": latency_ms
    }


async def _direct_search(request: UnifiedSearchRequest) -> dict:
    """
    Direct ES search - fast keyword matching with aggregations.
    """
    es = get_es_service()

    try:
        # Check if ES is available
        client = await es.connect()
        if not await client.ping():
            raise Exception("ES not available")

        # Execute search with aggregations
        result = await es.search_with_aggregations(
            query=request.query,
            filters=request.filters,
            limit=request.limit
        )

        # Format candidates
        candidates = []
        for hit in result["hits"]:
            # Build match reasons from highlights
            match_reasons = []
            if "_highlights" in hit:
                for field, highlights in hit["_highlights"].items():
                    if highlights:
                        # Clean up highlight markup for display
                        reason = highlights[0].replace("<mark>", "").replace("</mark>", "")
                        match_reasons.append(MatchReason(
                            field=field,
                            reason=f"{_field_label(field)}: {reason[:50]}..."
                        ))

            candidates.append(SearchResultItem(
                id=hit["id"],
                name=hit.get("name", ""),
                current_title=hit.get("current_title"),
                current_company=hit.get("current_company"),
                city=hit.get("city"),
                years_of_experience=hit.get("years_of_experience"),
                expected_salary=hit.get("expected_salary"),
                skills=hit.get("skills"),
                match_reasons=match_reasons if match_reasons else [
                    MatchReason(field="relevance", reason="关键词匹配")
                ],
                fit_summary=None,
                highlights=hit.get("_highlights")
            ))

        return {
            "candidates": candidates,
            "total": result["total"],
            "aggregations": result.get("aggregations", {}),
            "search_backend": "elasticsearch"
        }

    except Exception as e:
        # Fallback to SQL if ES fails
        print(f"ES search failed, falling back to SQL: {e}")
        return await _sql_fallback_search(request)


async def _sql_fallback_search(request: UnifiedSearchRequest) -> dict:
    """SQL fallback when ES is not available."""
    from sqlalchemy import select, or_
    from app.db import AsyncSessionLocal
    from app.models import Candidate

    async with AsyncSessionLocal() as db:
        stmt = select(Candidate)

        # Simple text search
        query = request.query
        if query:
            words = query.split()
            text_filters = []
            for word in words:
                text_filters.append(Candidate.skills.ilike(f"%{word}%"))
                text_filters.append(Candidate.current_title.ilike(f"%{word}%"))
                text_filters.append(Candidate.current_company.ilike(f"%{word}%"))
                text_filters.append(Candidate.city.ilike(f"%{word}%"))
            if text_filters:
                stmt = stmt.where(or_(*text_filters))

        stmt = stmt.limit(request.limit)
        result = await db.execute(stmt)
        candidates_db = result.scalars().all()

        candidates = [
            SearchResultItem(
                id=c.id,
                name=c.name,
                current_title=c.current_title,
                current_company=c.current_company,
                city=c.city,
                years_of_experience=c.years_of_experience,
                expected_salary=c.expected_salary,
                skills=c.skills,
                match_reasons=[MatchReason(field="search", reason="关键词匹配")],
                fit_summary=None
            )
            for c in candidates_db
        ]

        return {
            "candidates": candidates,
            "total": len(candidates),
            "aggregations": {},
            "search_backend": "sql_fallback"
        }


async def _ai_search(request: UnifiedSearchRequest, db: AsyncSession) -> dict:
    """
    AI-powered intelligent search - understands intent and executes multi-round search.
    """
    service = SearchService(db)
    result = await service.intelligent_search(request.query, request.limit)

    # Try to get aggregations from ES if available
    aggregations = {}
    try:
        es = get_es_service()
        client = await es.connect()
        if await client.ping():
            # Get aggregations based on AI search results
            agg_result = await es.search_with_aggregations(
                query=request.query,
                filters=request.filters,
                limit=1  # We just want aggregations
            )
            aggregations = agg_result.get("aggregations", {})
    except Exception:
        pass

    return {
        "candidates": result.get("candidates", []),
        "total": result.get("total", 0),
        "aggregations": aggregations,
        "search_summary": result.get("search_summary", ""),
        "search_history": result.get("search_history", []),
        "search_backend": result.get("search_backend", "ai")
    }


def _field_label(field: str) -> str:
    """Convert field name to Chinese label."""
    labels = {
        "skills": "技能",
        "summary": "简介",
        "current_title": "职位",
        "current_company": "公司",
        "name": "姓名"
    }
    return labels.get(field, field)


def _get_path_description(path: SearchPath) -> str:
    """Get a short description of the search path."""
    descriptions = {
        SearchPath.DIRECT: "快速搜索 (ES关键词匹配)",
        SearchPath.FULL: "AI智能搜索 (意图理解+多轮搜索)",
        SearchPath.SEMANTIC: "语义相似搜索",
        SearchPath.SERVICE: "状态筛选搜索"
    }
    return descriptions.get(path, "")


# ==================== Legacy Endpoints (kept for compatibility) ====================

@router.post("/natural/stream")
async def streaming_search(query: IntelligentSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    流式智能搜索（SSE）：实时返回搜索状态和结果
    """
    async def event_generator():
        service = SearchService(db)
        async for event in service.intelligent_search_stream(query.query, query.limit):
            event_type = event.get("type", "status")
            yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/intelligent")
async def intelligent_search(query: IntelligentSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    Agent 式智能搜索：LLM 自主推理、泛化查询、多轮搜索
    """
    service = SearchService(db)
    return await service.intelligent_search(query.query, query.limit)


@router.post("/quick", response_model=SearchResponse)
async def quick_search(query: SearchQuery, db: AsyncSession = Depends(get_db)):
    """
    快速搜索：解析自然语言后直接查询
    """
    service = SearchService(db)
    return await service.quick_search(query)


@router.post("/deep", response_model=SearchResponse)
async def deep_search(query: DeepSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    深度搜索：多轮对话，持续细化搜索条件
    """
    service = SearchService(db)
    return await service.deep_search(query.session_id, query.query, query.limit)


@router.get("/path/analyze")
async def analyze_search_path(query: str = Query(..., description="The search query to analyze")):
    """
    分析搜索查询并返回推荐的搜索路径（调试用）
    """
    search_router = get_search_router()
    request = SearchRequest(query=query)
    path = search_router.determine_path(request)

    return {
        "query": query,
        "recommended_path": path.value,
        "path_description": _get_path_description(path),
        "is_natural_language": path == SearchPath.FULL
    }


@router.get("/paths")
async def list_search_paths():
    """
    列出所有可用的搜索路径及其说明
    """
    return {
        "direct": {
            "name": "快速搜索",
            "description": "ES关键词匹配，适合简单查询如 'Python 北京'",
            "latency": "<100ms"
        },
        "full": {
            "name": "AI智能搜索",
            "description": "LLM意图理解+多轮搜索，适合复杂需求如 '找能带团队的技术专家'",
            "latency": "3-5s"
        },
        "semantic": {
            "name": "语义相似搜索",
            "description": "基于候选人画像的相似度匹配",
            "latency": "1-2s"
        },
        "service": {
            "name": "状态筛选",
            "description": "基于候选人状态（面试中、已联系等）筛选",
            "latency": "<500ms"
        }
    }
