"""
Search Router Service

Determines which search path to use based on the request characteristics:
- FULL: L1→L2→L3→L4 (Natural language search with all layers)
- SEMANTIC: L1→L2→L4 (Similar candidate search)
- SERVICE: L1→L3→L4 (Status/interaction based search)
- DIRECT: L1→L4 (Simple keyword/filter search)
"""

from enum import Enum
from pydantic import BaseModel


class SearchPath(str, Enum):
    FULL = "full"        # L1→L2→L3→L4: Full path for complex NL queries
    SEMANTIC = "semantic"  # L1→L2→L4: Semantic similarity search
    SERVICE = "service"    # L1→L3→L4: Service/status based queries
    DIRECT = "direct"      # L1→L4: Direct filter/keyword search


class SearchRequest(BaseModel):
    """Unified search request that the router analyzes"""
    query: str | None = None
    keywords: list[str] | None = None
    filters: dict | None = None
    similar_to_candidate_id: int | None = None
    session_id: str | None = None
    job_context_id: str | None = None
    status_filter: str | None = None  # e.g., "interviewing", "new"
    limit: int = 20


class SearchRouter:
    """
    Determines the optimal search path based on request characteristics.

    Path Selection Logic:
    1. If similar_to_candidate_id is provided → SEMANTIC path
    2. If status_filter is provided → SERVICE path
    3. If query is natural language (detected) → FULL path
    4. Otherwise → DIRECT path

    Additionally, session_id presence affects Layer 4 usage.
    """

    # Keywords that indicate natural language query
    NL_INDICATORS = [
        "找", "搜", "有", "会", "能", "做过", "具备", "擅长",
        "经验", "背景", "之前", "曾经", "想要", "需要",
        "相关", "类似", "差不多", "左右", "以上", "以下",
        "who", "with", "having", "experienced", "skilled"
    ]

    # Keywords that indicate structured/filter query
    STRUCTURED_INDICATORS = [
        "city:", "salary:", "experience:", "skill:",
        "status:", "company:", "title:",
        "=", ">", "<", ">=", "<="
    ]

    def determine_path(self, request: SearchRequest) -> SearchPath:
        """
        Analyze the search request and determine the optimal path.

        Args:
            request: The search request to analyze

        Returns:
            The recommended SearchPath
        """
        # Check for semantic similarity search
        if request.similar_to_candidate_id is not None:
            return SearchPath.SEMANTIC

        # Check for service/status-based search
        if request.status_filter:
            return SearchPath.SERVICE

        # Check if query is natural language
        if request.query:
            if self._is_natural_language(request.query):
                return SearchPath.FULL

        # Check if using structured filters
        if request.filters or request.keywords:
            return SearchPath.DIRECT

        # Default to FULL for any query text
        if request.query:
            return SearchPath.FULL

        return SearchPath.DIRECT

    def _is_natural_language(self, query: str) -> bool:
        """
        Detect if a query is natural language vs structured search.

        Returns True if the query appears to be natural language.
        """
        query_lower = query.lower()

        # Check for structured indicators (likely not NL)
        for indicator in self.STRUCTURED_INDICATORS:
            if indicator in query_lower:
                return False

        # Check for NL indicators
        for indicator in self.NL_INDICATORS:
            if indicator in query_lower:
                return True

        # If query is longer than 10 chars with spaces, likely NL
        if len(query) > 10 and " " in query:
            return True

        # Short single-word queries are likely keywords
        if " " not in query and len(query) < 15:
            return False

        # Default to NL for medium-length queries
        return len(query) > 5

    def get_path_description(self, path: SearchPath) -> dict:
        """Get a description of what each path does"""
        descriptions = {
            SearchPath.FULL: {
                "name": "Full Path",
                "layers": ["L1 (Raw Data)", "L2 (AI Profile)", "L3 (Human Knowledge)", "L4 (Session)"],
                "description": "Complete analysis using all CKB layers. Best for complex natural language queries.",
                "typical_latency": "10-15s",
                "use_cases": ["AI智能搜索", "自然语言查询", "复杂需求匹配"]
            },
            SearchPath.SEMANTIC: {
                "name": "Semantic Path",
                "layers": ["L1 (Raw Data)", "L2 (AI Profile)", "L4 (Session)"],
                "description": "Semantic similarity search using AI profiles. Skips human knowledge layer.",
                "typical_latency": "3-5s",
                "use_cases": ["相似候选人推荐", "人才发现", "技能匹配"]
            },
            SearchPath.SERVICE: {
                "name": "Service Path",
                "layers": ["L1 (Raw Data)", "L3 (Human Knowledge)", "L4 (Session)"],
                "description": "Status and interaction based search. Focuses on human feedback.",
                "typical_latency": "1-2s",
                "use_cases": ["状态筛选", "已联系候选人", "面试中候选人"]
            },
            SearchPath.DIRECT: {
                "name": "Direct Path",
                "layers": ["L1 (Raw Data)", "L4 (Session)"],
                "description": "Direct database query. Fastest path for simple filters.",
                "typical_latency": "<500ms",
                "use_cases": ["关键词搜索", "字段过滤", "ID查询"]
            }
        }
        return descriptions.get(path, {})


# Singleton instance for convenience
_router_instance = None


def get_search_router() -> SearchRouter:
    """Get the global SearchRouter instance"""
    global _router_instance
    if _router_instance is None:
        _router_instance = SearchRouter()
    return _router_instance
