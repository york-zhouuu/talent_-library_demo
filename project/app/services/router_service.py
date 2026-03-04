"""
Search Router Service

Determines which search path to use based on the request characteristics:
- FULL: L1→L2→L3→L4 (Natural language search with all layers, AI-powered)
- SEMANTIC: L1→L2→L4 (Similar candidate search)
- SERVICE: L1→L3→L4 (Status/interaction based search)
- DIRECT: L1→L4 (Simple keyword/filter search, ES-powered)
"""

import re
from enum import Enum
from pydantic import BaseModel


class SearchPath(str, Enum):
    FULL = "full"        # L1→L2→L3→L4: Full path for complex NL queries (AI)
    SEMANTIC = "semantic"  # L1→L2→L4: Semantic similarity search
    SERVICE = "service"    # L1→L3→L4: Service/status based queries
    DIRECT = "direct"      # L1→L4: Direct filter/keyword search (ES fast)


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
    # 新增：允许用户强制指定路径
    force_path: str | None = None  # "direct" or "full"


class SearchRouter:
    """
    Determines the optimal search path based on request characteristics.

    Path Selection Logic:
    1. If force_path is provided → Use that path
    2. If similar_to_candidate_id is provided → SEMANTIC path
    3. If status_filter is provided → SERVICE path
    4. If query is natural language (detected) → FULL path (AI)
    5. Otherwise → DIRECT path (ES fast search)

    DIRECT vs FULL:
    - DIRECT: Simple keywords like "Python", "北京 Java", "产品经理"
      → Uses ES multi_match, <100ms response
    - FULL: Complex NL like "找能带团队的大模型专家", "有创业经历的CTO"
      → Uses AI to understand intent, multiple search rounds, 3-5s response
    """

    # Keywords that indicate natural language query → needs AI
    NL_INDICATORS = [
        # 意图动词
        "找", "搜", "推荐", "帮我", "想要", "需要", "求",
        # 能力描述
        "会", "能", "做过", "具备", "擅长", "精通", "熟悉",
        # 背景描述
        "经验", "背景", "之前", "曾经", "出身", "毕业",
        # 模糊条件
        "相关", "类似", "差不多", "左右", "大概",
        # 复杂修饰
        "比较", "最好", "优先", "不要", "除了",
        # 场景描述
        "能带团队", "有管理", "能独立", "有创业",
        # 英文
        "who", "with", "having", "experienced", "skilled", "looking for"
    ]

    # Keywords that indicate structured/filter query → ES direct
    STRUCTURED_INDICATORS = [
        "city:", "salary:", "experience:", "skill:",
        "status:", "company:", "title:",
        "=", ">", "<", ">=", "<="
    ]

    # Common skill/role keywords that should use fast search
    KEYWORD_PATTERNS = [
        # 编程语言
        r"^(python|java|go|golang|rust|c\+\+|javascript|typescript|php|ruby|scala|kotlin)$",
        # 技术栈
        r"^(react|vue|angular|node|spring|django|flask|kubernetes|docker|aws|gcp|azure)$",
        # 职位
        r"^(工程师|开发|架构师|产品经理|设计师|运营|测试|前端|后端|全栈|算法|数据)$",
        # 城市
        r"^(北京|上海|深圳|杭州|广州|成都|南京|武汉|西安|苏州)$",
    ]

    def determine_path(self, request: SearchRequest) -> SearchPath:
        """
        Analyze the search request and determine the optimal path.

        Args:
            request: The search request to analyze

        Returns:
            The recommended SearchPath
        """
        # Allow user to force a specific path
        if request.force_path:
            if request.force_path == "direct":
                return SearchPath.DIRECT
            elif request.force_path == "full":
                return SearchPath.FULL

        # Check for semantic similarity search
        if request.similar_to_candidate_id is not None:
            return SearchPath.SEMANTIC

        # Check for service/status-based search
        if request.status_filter:
            return SearchPath.SERVICE

        # Check if using structured filters directly
        if request.filters or request.keywords:
            return SearchPath.DIRECT

        # Analyze query text
        if request.query:
            return self._analyze_query(request.query)

        return SearchPath.DIRECT

    def _analyze_query(self, query: str) -> SearchPath:
        """
        Analyze query text to determine if it needs AI or can use fast ES search.

        Returns DIRECT for:
        - Single keywords: "Python", "产品经理"
        - Simple combinations: "Python 北京", "Java 5年"
        - Known skill/role patterns

        Returns FULL for:
        - Natural language with intent: "找一个...", "有...经验的"
        - Complex descriptions: "能带团队的技术专家"
        - Queries needing semantic understanding
        """
        query_lower = query.lower().strip()
        query_stripped = query.strip()

        # Check for structured indicators (definitely DIRECT)
        for indicator in self.STRUCTURED_INDICATORS:
            if indicator in query_lower:
                return SearchPath.DIRECT

        # Check for NL indicators (definitely FULL/AI)
        for indicator in self.NL_INDICATORS:
            if indicator in query_stripped:
                return SearchPath.FULL

        # Check if query is just common keywords
        words = query_stripped.split()

        # Single word - check if it's a known keyword
        if len(words) == 1:
            for pattern in self.KEYWORD_PATTERNS:
                if re.match(pattern, query_lower, re.IGNORECASE):
                    return SearchPath.DIRECT
            # Single Chinese word (2-6 chars) - likely a keyword
            if len(query_stripped) <= 6 and self._is_chinese(query_stripped):
                return SearchPath.DIRECT
            # Single short English word - likely a keyword
            if len(query_stripped) <= 15 and query_stripped.isascii():
                return SearchPath.DIRECT

        # Two words - likely "skill + location" or "skill + skill"
        if len(words) == 2:
            # Check if both are simple keywords
            simple_count = 0
            for word in words:
                word_lower = word.lower()
                for pattern in self.KEYWORD_PATTERNS:
                    if re.match(pattern, word_lower, re.IGNORECASE):
                        simple_count += 1
                        break
                else:
                    # Check if it's a short Chinese word
                    if len(word) <= 4 and self._is_chinese(word):
                        simple_count += 1
            if simple_count == 2:
                return SearchPath.DIRECT

        # Three or fewer short words without NL indicators - still try DIRECT
        if len(words) <= 3 and all(len(w) <= 8 for w in words):
            # No NL indicators found, short query - use fast search
            return SearchPath.DIRECT

        # Longer or complex query - use AI
        return SearchPath.FULL

    def _is_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters."""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    def _is_natural_language(self, query: str) -> bool:
        """
        Legacy method - now uses _analyze_query internally.
        """
        return self._analyze_query(query) == SearchPath.FULL

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
