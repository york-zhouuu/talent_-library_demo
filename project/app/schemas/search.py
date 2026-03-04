from enum import Enum
from typing import Literal
from pydantic import BaseModel


class SearchQuery(BaseModel):
    query: str
    limit: int = 10
    pool_id: int | None = None


class DeepSearchQuery(BaseModel):
    session_id: str
    query: str
    limit: int = 10


class MatchReason(BaseModel):
    field: str
    reason: str


class SearchResultItem(BaseModel):
    id: int
    name: str
    current_title: str | None
    current_company: str | None
    city: str | None
    years_of_experience: float | None
    expected_salary: float | None
    skills: str | None
    match_reasons: list[MatchReason]
    fit_summary: str | None = None  # 一句话总结匹配原因
    highlights: dict | None = None  # ES 高亮匹配片段 {"skills": ["<mark>Python</mark>..."]}


class AggregationBucket(BaseModel):
    value: str
    count: int


class SearchAggregations(BaseModel):
    cities: list[AggregationBucket] | None = None
    experience: list[AggregationBucket] | None = None
    salary: list[AggregationBucket] | None = None


class SearchResponse(BaseModel):
    session_id: str
    candidates: list[SearchResultItem]
    total: int
    parsed_conditions: dict | None = None


class FilterCondition(BaseModel):
    field: str
    operator: str  # $eq, $ne, $gt, $gte, $lt, $lte, $in, $contains
    value: str | int | float | list


class AgentFilterRequest(BaseModel):
    conditions: list[FilterCondition]
    limit: int = 10
    offset: int = 0


class BatchGetRequest(BaseModel):
    ids: list[int]


class BatchUpdateRequest(BaseModel):
    ids: list[int]
    update: dict


# ==================== Phase 1: SSE Streaming ====================

class SearchStage(str, Enum):
    PARSING = "parsing"
    EXPANDING = "expanding"
    SEARCHING = "searching"
    RANKING = "ranking"
    EXPLAINING = "explaining"


class StreamingStatusEvent(BaseModel):
    type: Literal["status"] = "status"
    stage: SearchStage
    message: str
    progress: int | None = None


class StreamingPartialResult(BaseModel):
    type: Literal["partial_result"] = "partial_result"
    candidates: list[SearchResultItem]
    is_ranked: bool
    more_coming: bool


class StreamingFinalResult(BaseModel):
    type: Literal["final_result"] = "final_result"
    candidates: list[SearchResultItem]
    search_process: list[dict]
    reasoning: str
    total: int
