import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.schemas import SearchQuery, DeepSearchQuery, SearchResponse
from app.services import SearchService
from app.services.router_service import SearchRouter, SearchPath, SearchRequest, get_search_router

router = APIRouter(prefix="/search", tags=["search"])


class IntelligentSearchQuery(BaseModel):
    query: str
    limit: int = 20


class UnifiedSearchQuery(BaseModel):
    """Unified search query that the router analyzes"""
    query: str | None = None
    keywords: list[str] | None = None
    filters: dict | None = None
    similar_to_candidate_id: int | None = None
    session_id: str | None = None
    status_filter: str | None = None
    limit: int = 20


@router.post("/natural/stream")
async def streaming_search(query: IntelligentSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    流式智能搜索（SSE）：实时返回搜索状态和结果

    通过 Server-Sent Events 分阶段返回：
    - status: 当前搜索阶段状态
    - partial_result: 未排序的初步结果
    - final_result: 最终排序后的结果

    Path: FULL (L1→L2→L3→L4)
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

    - LLM 会自动理解用户意图
    - 推理相关的职位、技能、关键词
    - 执行多轮搜索以获得更全面的结果
    - 智能排序和评分

    Path: FULL (L1→L2→L3→L4)
    """
    service = SearchService(db)
    return await service.intelligent_search(query.query, query.limit)


@router.post("/quick", response_model=SearchResponse)
async def quick_search(query: SearchQuery, db: AsyncSession = Depends(get_db)):
    """
    快速搜索：解析自然语言后直接查询

    Path: DIRECT (L1→L4)
    """
    service = SearchService(db)
    return await service.quick_search(query)


@router.post("/deep", response_model=SearchResponse)
async def deep_search(query: DeepSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    深度搜索：多轮对话，持续细化搜索条件

    Path: FULL (L1→L2→L3→L4) with session context
    """
    service = SearchService(db)
    return await service.deep_search(query.session_id, query.query, query.limit)


@router.post("/unified")
async def unified_search(query: UnifiedSearchQuery, db: AsyncSession = Depends(get_db)):
    """
    统一搜索接口：根据请求特征自动选择最优搜索路径

    路由规则:
    - similar_to_candidate_id → SEMANTIC path (L1→L2→L4)
    - status_filter → SERVICE path (L1→L3→L4)
    - 自然语言 query → FULL path (L1→L2→L3→L4)
    - 关键词/过滤器 → DIRECT path (L1→L4)
    """
    search_router = get_search_router()
    request = SearchRequest(
        query=query.query,
        keywords=query.keywords,
        filters=query.filters,
        similar_to_candidate_id=query.similar_to_candidate_id,
        session_id=query.session_id,
        status_filter=query.status_filter,
        limit=query.limit
    )

    path = search_router.determine_path(request)
    service = SearchService(db)

    # Execute search based on determined path
    if path == SearchPath.FULL:
        result = await service.intelligent_search(query.query or "", query.limit)
    elif path == SearchPath.SEMANTIC:
        # TODO: Implement semantic similarity search
        # For now, fallback to intelligent search
        result = await service.intelligent_search(
            f"找和候选人 {query.similar_to_candidate_id} 类似的人",
            query.limit
        )
    elif path == SearchPath.SERVICE:
        # TODO: Implement status-based search using CKB Layer 3
        # For now, fallback to quick search with status hint
        from app.schemas import SearchQuery as SQ
        result = await service.quick_search(SQ(
            query=f"状态: {query.status_filter}",
            limit=query.limit
        ))
    else:  # DIRECT
        from app.schemas import SearchQuery as SQ
        result = await service.quick_search(SQ(
            query=query.query or " ".join(query.keywords or []),
            limit=query.limit
        ))

    # Add path info to response
    if isinstance(result, dict):
        result["search_path"] = path.value
        result["path_info"] = search_router.get_path_description(path)

    return result


@router.get("/path/analyze")
async def analyze_search_path(query: str = Query(..., description="The search query to analyze")):
    """
    分析搜索查询并返回推荐的搜索路径

    用于调试和理解路由决策
    """
    search_router = get_search_router()
    request = SearchRequest(query=query)
    path = search_router.determine_path(request)

    return {
        "query": query,
        "recommended_path": path.value,
        "is_natural_language": search_router._is_natural_language(query),
        "path_info": search_router.get_path_description(path)
    }


@router.get("/paths")
async def list_search_paths():
    """
    列出所有可用的搜索路径及其说明
    """
    search_router = get_search_router()
    return {
        path.value: search_router.get_path_description(path)
        for path in SearchPath
    }
