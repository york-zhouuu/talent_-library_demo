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


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AIService()
        self.memory = MemoryService()

    async def intelligent_search(self, query: str, limit: int = 20) -> dict:
        """
        Agent 式智能搜索：LLM 自主推理、泛化、多轮搜索
        """
        session_id = str(uuid.uuid4())

        # 定义搜索执行器供 AI 调用
        async def search_executor(search_terms: list, city: str = None,
                                  min_experience: float = None, max_experience: float = None,
                                  max_salary: float = None, limit: int = 50) -> list:
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

        # 调用 AI 进行智能搜索
        search_result = await self.ai.intelligent_search(query, search_executor)

        # 对结果进行智能排序
        if search_result["candidates"]:
            ranked_candidates = await self.ai.rank_candidates(query, search_result["candidates"])
        else:
            ranked_candidates = []

        # 构建响应
        results = []
        for c in ranked_candidates[:limit]:
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
            "search_history": search_result.get("search_history", [])
        }

    async def intelligent_search_stream(self, query: str, limit: int = 20) -> AsyncGenerator[dict, None]:
        """
        流式智能搜索：通过 SSE 分阶段返回搜索状态和结果
        """
        session_id = str(uuid.uuid4())
        all_candidates = {}
        search_history = []

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
            stmt = select(Candidate)
            filters = []

            if city:
                filters.append(Candidate.city == city)
            if min_experience is not None:
                filters.append(Candidate.years_of_experience >= min_experience)
            if max_experience is not None:
                filters.append(Candidate.years_of_experience <= max_experience)
            if max_salary is not None:
                filters.append(Candidate.expected_salary <= max_salary)

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

        # Stage 3: Searching
        yield StreamingStatusEvent(
            stage=SearchStage.SEARCHING,
            message="正在执行多轮搜索..."
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

        # Build final results
        final_results = []
        for c in ranked_candidates[:limit]:
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
        session_id = str(uuid.uuid4())

        # Parse natural language query
        conditions = await self.ai.parse_search_query(query.query)

        # Store session context
        await self.memory.save_session(session_id, {
            "original_query": query.query,
            "conditions": conditions,
            "pool_id": query.pool_id
        })

        # Build and execute query
        candidates = await self._execute_search(conditions, query.limit)

        # Build response with match reasons (no score)
        results = []
        for c in candidates:
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
                fit_summary=None  # Quick search doesn't generate fit summary
            ))

        return SearchResponse(
            session_id=session_id,
            candidates=results,
            total=len(results),
            parsed_conditions=conditions
        )

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
        candidates = await self._execute_search(merged, limit)

        results = []
        for c in candidates:
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
