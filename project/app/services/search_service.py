import json
import uuid
from typing import AsyncGenerator
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Candidate
from app.schemas import (
    SearchQuery, SearchResponse, SearchResultItem, MatchReason, FilterCondition,
    SearchStage, StreamingStatusEvent, StreamingPartialResult, StreamingFinalResult
)
from app.services.ai_service import AIService
from app.services.memory_service import MemoryService
from app.services.es_service import get_es_service, ElasticsearchService


class SearchService:
    def __init__(self, db: AsyncSession, use_es: bool = True):
        self.db = db
        self.ai = AIService()
        self.memory = MemoryService()
        self.use_es = use_es
        self._es: ElasticsearchService | None = None

    @property
    def es(self) -> ElasticsearchService:
        if self._es is None:
            self._es = get_es_service()
        return self._es

    async def _is_es_available(self) -> bool:
        """Check if Elasticsearch is available."""
        if not self.use_es:
            return False
        try:
            client = await self.es.connect()
            return await client.ping()
        except Exception:
            return False

    async def intelligent_search(self, query: str, limit: int = 20) -> dict:
        """
        Agent 式智能搜索：LLM 自主推理、泛化、多轮搜索
        Uses Elasticsearch if available, falls back to SQL.
        """
        session_id = str(uuid.uuid4())
        es_available = await self._is_es_available()

        # 定义搜索执行器供 AI 调用
        async def search_executor(search_terms: list, city: str = None,
                                  min_experience: float = None, max_experience: float = None,
                                  max_salary: float = None, limit: int = 50) -> list:
            if es_available:
                # Use Elasticsearch
                return await self.es.search_by_terms(
                    search_terms=search_terms,
                    city=city,
                    min_experience=min_experience,
                    max_experience=max_experience,
                    max_salary=max_salary,
                    limit=limit
                )
            else:
                # Fallback to SQL
                return await self._sql_search_executor(
                    search_terms, city, min_experience, max_experience, max_salary, limit
                )

        # 调用 AI 进行智能搜索
        search_result = await self.ai.intelligent_search(query, search_executor)

        # 对结果进行智能排序
        if search_result["candidates"]:
            ranked_candidates = await self.ai.rank_candidates(query, search_result["candidates"])
        else:
            ranked_candidates = []

        # 构建响应 (确保去重)
        results = []
        seen_ids = set()
        for c in ranked_candidates[:limit]:
            if c["id"] in seen_ids:
                continue
            seen_ids.add(c["id"])
            results.append(SearchResultItem(
                id=c["id"],
                name=c["name"],
                current_title=c.get("current_title"),
                current_company=c.get("current_company"),
                city=c.get("city"),
                years_of_experience=c.get("years_of_experience"),
                expected_salary=c.get("expected_salary"),
                skills=c.get("skills"),
                match_reasons=[MatchReason(field="ai", reason=c.get("match_reason", "AI智能匹配"))],
                fit_summary=c.get("fit_summary")
            ))

        return {
            "session_id": session_id,
            "candidates": results,
            "total": len(results),
            "search_summary": search_result.get("summary", ""),
            "search_history": search_result.get("search_history", []),
            "search_backend": "elasticsearch" if es_available else "sql"
        }

    async def _sql_search_executor(self, search_terms: list, city: str = None,
                                   min_experience: float = None, max_experience: float = None,
                                   max_salary: float = None, limit: int = 50) -> list:
        """SQL-based search executor (fallback)."""
        stmt = select(Candidate)
        filters = []

        # 硬性条件
        if city:
            filters.append(Candidate.city == city)
        if min_experience is not None:
            filters.append(Candidate.years_of_experience >= min_experience)
        if max_experience is not None:
            filters.append(Candidate.years_of_experience <= max_experience)
        if max_salary is not None:
            filters.append(Candidate.expected_salary <= max_salary)

        # 文本搜索条件 (OR)
        text_filters = []
        for term in search_terms:
            text_filters.append(Candidate.skills.ilike(f"%{term}%"))
            text_filters.append(Candidate.current_title.ilike(f"%{term}%"))
            text_filters.append(Candidate.summary.ilike(f"%{term}%"))
            text_filters.append(Candidate.current_company.ilike(f"%{term}%"))

        if filters:
            stmt = stmt.where(and_(*filters))
        if text_filters:
            stmt = stmt.where(or_(*text_filters))

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        candidates = result.scalars().all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "current_title": c.current_title,
                "current_company": c.current_company,
                "city": c.city,
                "years_of_experience": c.years_of_experience,
                "expected_salary": c.expected_salary,
                "skills": c.skills,
                "summary": c.summary
            }
            for c in candidates
        ]

    async def intelligent_search_stream(self, query: str, limit: int = 20) -> AsyncGenerator[dict, None]:
        """
        流式智能搜索：通过 SSE 分阶段返回搜索状态和结果
        Uses Elasticsearch if available, falls back to SQL.
        """
        session_id = str(uuid.uuid4())
        all_candidates = {}
        search_history = []
        es_available = await self._is_es_available()

        # Stage 1: Parsing intent
        yield StreamingStatusEvent(
            stage=SearchStage.PARSING,
            message="正在分析搜索意图..."
        ).model_dump()

        # Stage 2: Expanding keywords
        yield StreamingStatusEvent(
            stage=SearchStage.EXPANDING,
            message="正在扩展相关关键词..."
        ).model_dump()

        # Define search executor
        async def search_executor(search_terms: list, city: str = None,
                                  min_experience: float = None, max_experience: float = None,
                                  max_salary: float = None, limit: int = 50) -> list:
            if es_available:
                return await self.es.search_by_terms(
                    search_terms=search_terms,
                    city=city,
                    min_experience=min_experience,
                    max_experience=max_experience,
                    max_salary=max_salary,
                    limit=limit
                )
            else:
                return await self._sql_search_executor(
                    search_terms, city, min_experience, max_experience, max_salary, limit
                )

        # Stage 3: Searching
        yield StreamingStatusEvent(
            stage=SearchStage.SEARCHING,
            message=f"正在执行多轮搜索 ({'Elasticsearch' if es_available else 'SQL'})..."
        ).model_dump()

        # Execute intelligent search
        search_result = await self.ai.intelligent_search(query, search_executor)
        all_candidates = {c["id"]: c for c in search_result.get("candidates", [])}
        search_history = search_result.get("search_history", [])

        # Yield partial (unranked) results
        if all_candidates:
            unranked_results = [
                SearchResultItem(
                    id=c["id"],
                    name=c["name"],
                    current_title=c.get("current_title"),
                    current_company=c.get("current_company"),
                    city=c.get("city"),
                    years_of_experience=c.get("years_of_experience"),
                    expected_salary=c.get("expected_salary"),
                    skills=c.get("skills"),
                    match_reasons=[],
                    fit_summary=None
                )
                for c in list(all_candidates.values())[:limit]
            ]
            yield StreamingPartialResult(
                candidates=unranked_results,
                is_ranked=False,
                more_coming=True
            ).model_dump()

        # Stage 4: Ranking
        yield StreamingStatusEvent(
            stage=SearchStage.RANKING,
            message=f"正在对 {len(all_candidates)} 位候选人进行智能排序..."
        ).model_dump()

        if search_result["candidates"]:
            ranked_candidates = await self.ai.rank_candidates(query, search_result["candidates"])
        else:
            ranked_candidates = []

        # Stage 5: Generating explanations
        yield StreamingStatusEvent(
            stage=SearchStage.EXPLAINING,
            message="正在生成匹配解释..."
        ).model_dump()

        # Build final results (确保去重)
        final_results = []
        seen_ids = set()
        for c in ranked_candidates[:limit]:
            if c["id"] in seen_ids:
                continue
            seen_ids.add(c["id"])
            final_results.append(SearchResultItem(
                id=c["id"],
                name=c["name"],
                current_title=c.get("current_title"),
                current_company=c.get("current_company"),
                city=c.get("city"),
                years_of_experience=c.get("years_of_experience"),
                expected_salary=c.get("expected_salary"),
                skills=c.get("skills"),
                match_reasons=[MatchReason(field="ai", reason=c.get("match_reason", "AI智能匹配"))],
                fit_summary=c.get("fit_summary")
            ))

        # Final result
        yield StreamingFinalResult(
            candidates=final_results,
            search_process=search_history,
            reasoning=search_result.get("summary", ""),
            total=len(final_results)
        ).model_dump()

    async def quick_search(self, query: SearchQuery) -> SearchResponse:
        """Quick search using ES if available."""
        session_id = str(uuid.uuid4())
        es_available = await self._is_es_available()

        # Parse natural language query
        conditions = await self.ai.parse_search_query(query.query)

        # Store session context
        await self.memory.save_session(session_id, {
            "original_query": query.query,
            "conditions": conditions,
            "pool_id": query.pool_id
        })

        if es_available:
            # Use Elasticsearch
            candidates = await self._execute_es_search(query.query, conditions, query.limit)
        else:
            # Fallback to SQL
            candidates = await self._execute_search(conditions, query.limit)

        # Build response with match reasons (no score)
        results = []
        for c in candidates:
            if es_available:
                # ES returns dicts
                reasons = self._get_es_match_reasons(c, conditions)
                results.append(SearchResultItem(
                    id=c["id"],
                    name=c["name"],
                    current_title=c.get("current_title"),
                    current_company=c.get("current_company"),
                    city=c.get("city"),
                    years_of_experience=c.get("years_of_experience"),
                    expected_salary=c.get("expected_salary"),
                    skills=c.get("skills"),
                    match_reasons=reasons,
                    fit_summary=None
                ))
            else:
                # SQL returns Candidate objects
                reasons = await self._get_match_reasons(c, conditions)
                results.append(SearchResultItem(
                    id=c.id,
                    name=c.name,
                    current_title=c.current_title,
                    current_company=c.current_company,
                    city=c.city,
                    years_of_experience=c.years_of_experience,
                    expected_salary=c.expected_salary,
                    skills=c.skills,
                    match_reasons=reasons,
                    fit_summary=None
                ))

        return SearchResponse(
            session_id=session_id,
            candidates=results,
            total=len(results),
            parsed_conditions=conditions
        )

    async def _execute_es_search(self, query_text: str, conditions: dict, limit: int) -> list[dict]:
        """Execute search using Elasticsearch."""
        # Build search terms from conditions
        search_terms = []
        if conditions.get("skills"):
            search_terms.extend(conditions["skills"])
        if conditions.get("keywords"):
            search_terms.extend(conditions["keywords"])
        if not search_terms:
            search_terms = [query_text]

        # Build filters
        filters = {}
        if conditions.get("city"):
            filters["city"] = conditions["city"]
        if conditions.get("min_experience"):
            filters["min_experience"] = conditions["min_experience"]
        if conditions.get("max_experience"):
            filters["max_experience"] = conditions["max_experience"]
        if conditions.get("max_salary"):
            filters["max_salary"] = conditions["max_salary"]
        if conditions.get("min_salary"):
            filters["min_salary"] = conditions["min_salary"]

        result = await self.es.search(
            query=" ".join(search_terms),
            filters=filters,
            limit=limit,
            highlight=True
        )

        return result["hits"]

    def _get_es_match_reasons(self, candidate: dict, conditions: dict) -> list[MatchReason]:
        """Get match reasons from ES results."""
        reasons = []

        if conditions.get("city") and candidate.get("city") == conditions["city"]:
            reasons.append(MatchReason(field="city", reason=f"位于{candidate['city']}"))

        if conditions.get("skills") and candidate.get("skills"):
            skills_str = candidate["skills"]
            if isinstance(skills_str, str):
                matched = [s for s in conditions["skills"] if s.lower() in skills_str.lower()]
                if matched:
                    reasons.append(MatchReason(field="skills", reason=f"具备技能: {', '.join(matched)}"))

        if candidate.get("years_of_experience"):
            reasons.append(MatchReason(field="experience", reason=f"{candidate['years_of_experience']}年工作经验"))

        if candidate.get("expected_salary"):
            reasons.append(MatchReason(field="salary", reason=f"期望薪资{candidate['expected_salary']}万/年"))

        # Add ES highlights if available
        if "_highlights" in candidate:
            for field, highlights in candidate["_highlights"].items():
                if highlights:
                    reasons.append(MatchReason(field=field, reason=f"匹配: {highlights[0]}"))

        return reasons

    async def deep_search(self, session_id: str, query: str, limit: int = 10) -> SearchResponse:
        # Get previous context
        context = await self.memory.get_session(session_id)
        if not context:
            context = {"conditions": {}}

        # Parse new conditions
        new_conditions = await self.ai.parse_search_query(query)

        # Merge conditions
        merged = self._merge_conditions(context.get("conditions", {}), new_conditions)

        # Update session
        await self.memory.save_session(session_id, {
            **context,
            "conditions": merged,
            "last_query": query
        })

        # Execute search
        es_available = await self._is_es_available()

        if es_available:
            candidates = await self._execute_es_search(query, merged, limit)
        else:
            candidates = await self._execute_search(merged, limit)

        results = []
        for c in candidates:
            if es_available:
                reasons = self._get_es_match_reasons(c, merged)
                results.append(SearchResultItem(
                    id=c["id"],
                    name=c["name"],
                    current_title=c.get("current_title"),
                    current_company=c.get("current_company"),
                    city=c.get("city"),
                    years_of_experience=c.get("years_of_experience"),
                    expected_salary=c.get("expected_salary"),
                    skills=c.get("skills"),
                    match_reasons=reasons,
                    fit_summary=None
                ))
            else:
                reasons = await self._get_match_reasons(c, merged)
                results.append(SearchResultItem(
                    id=c.id,
                    name=c.name,
                    current_title=c.current_title,
                    current_company=c.current_company,
                    city=c.city,
                    years_of_experience=c.years_of_experience,
                    expected_salary=c.expected_salary,
                    skills=c.skills,
                    match_reasons=reasons,
                    fit_summary=None
                ))

        return SearchResponse(
            session_id=session_id,
            candidates=results,
            total=len(results),
            parsed_conditions=merged
        )

    async def filter_search(self, conditions: list[FilterCondition], limit: int, offset: int) -> list[Candidate]:
        stmt = select(Candidate)

        for cond in conditions:
            stmt = self._apply_condition(stmt, cond)

        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _execute_search(self, conditions: dict, limit: int) -> list[Candidate]:
        """SQL-based search (fallback)."""
        stmt = select(Candidate)
        filters = []

        # City filter (exact match)
        if conditions.get("city"):
            filters.append(Candidate.city == conditions["city"])

        # Experience filter
        if conditions.get("min_experience"):
            filters.append(Candidate.years_of_experience >= conditions["min_experience"])

        if conditions.get("max_experience"):
            filters.append(Candidate.years_of_experience <= conditions["max_experience"])

        # Salary filter
        if conditions.get("max_salary"):
            filters.append(Candidate.expected_salary <= conditions["max_salary"])

        if conditions.get("min_salary"):
            filters.append(Candidate.expected_salary >= conditions["min_salary"])

        # Skills and keywords - search across multiple fields
        text_search_filters = []

        if conditions.get("skills"):
            for s in conditions["skills"]:
                text_search_filters.append(Candidate.skills.ilike(f"%{s}%"))
                text_search_filters.append(Candidate.current_title.ilike(f"%{s}%"))
                text_search_filters.append(Candidate.summary.ilike(f"%{s}%"))

        if conditions.get("keywords"):
            for kw in conditions["keywords"]:
                text_search_filters.append(Candidate.summary.ilike(f"%{kw}%"))
                text_search_filters.append(Candidate.current_title.ilike(f"%{kw}%"))
                text_search_filters.append(Candidate.skills.ilike(f"%{kw}%"))
                text_search_filters.append(Candidate.current_company.ilike(f"%{kw}%"))

        # Apply hard filters (city, experience, salary)
        if filters:
            stmt = stmt.where(and_(*filters))

        # Apply text search as OR conditions (if any match, include the candidate)
        if text_search_filters:
            stmt = stmt.where(or_(*text_search_filters))

        # If no conditions at all, return all candidates (up to limit)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _apply_condition(self, stmt, cond: FilterCondition):
        column = getattr(Candidate, cond.field, None)
        if not column:
            return stmt

        op = cond.operator
        val = cond.value

        if op == "$eq":
            return stmt.where(column == val)
        elif op == "$ne":
            return stmt.where(column != val)
        elif op == "$gt":
            return stmt.where(column > val)
        elif op == "$gte":
            return stmt.where(column >= val)
        elif op == "$lt":
            return stmt.where(column < val)
        elif op == "$lte":
            return stmt.where(column <= val)
        elif op == "$in":
            return stmt.where(column.in_(val))
        elif op == "$contains":
            return stmt.where(column.ilike(f"%{val}%"))
        return stmt

    async def _get_match_reasons(self, candidate: Candidate, conditions: dict) -> list[MatchReason]:
        reasons = []

        if conditions.get("city") and candidate.city == conditions["city"]:
            reasons.append(MatchReason(field="city", reason=f"位于{candidate.city}"))

        if conditions.get("skills") and candidate.skills:
            matched = [s for s in conditions["skills"] if s.lower() in candidate.skills.lower()]
            if matched:
                reasons.append(MatchReason(field="skills", reason=f"具备技能: {', '.join(matched)}"))

        if candidate.years_of_experience:
            reasons.append(MatchReason(field="experience", reason=f"{candidate.years_of_experience}年工作经验"))

        if candidate.expected_salary:
            reasons.append(MatchReason(field="salary", reason=f"期望薪资{candidate.expected_salary}万/年"))

        return reasons

    def _merge_conditions(self, old: dict, new: dict) -> dict:
        merged = old.copy()
        for k, v in new.items():
            if v is not None:
                if k == "skills" and merged.get("skills"):
                    merged[k] = list(set(merged[k] + v))
                elif k == "keywords" and merged.get("keywords"):
                    merged[k] = list(set(merged[k] + v))
                else:
                    merged[k] = v
        return merged
