import json
from anthropic import AsyncAnthropic
from app.core import get_settings, AIServiceError

settings = get_settings()

# 定义搜索工具供 LLM 调用
SEARCH_TOOLS = [
    {
        "name": "search_candidates",
        "description": "搜索人才库中的候选人。可以根据多个条件进行搜索，所有条件是 OR 关系（满足任一条件即可返回）。建议多次调用此工具，每次使用不同的搜索策略，以获得更全面的结果。",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索词列表，会在职位、技能、简介、公司中匹配。建议包含：原始词、同义词、相关概念、英文对应词等"
                },
                "city": {
                    "type": "string",
                    "description": "城市筛选（精确匹配），如：北京、上海、深圳"
                },
                "min_experience": {
                    "type": "number",
                    "description": "最低工作年限"
                },
                "max_experience": {
                    "type": "number",
                    "description": "最高工作年限"
                },
                "max_salary": {
                    "type": "number",
                    "description": "最高期望薪资（万/年）"
                }
            },
            "required": ["search_terms"]
        }
    },
    {
        "name": "get_all_candidates",
        "description": "获取人才库中的所有候选人列表，用于了解库中有哪些人才。当搜索结果为空或需要浏览全部人才时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回数量限制，默认20",
                    "default": 20
                }
            }
        }
    }
]


class AIService:
    def __init__(self):
        self.client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url if settings.anthropic_base_url else None
        )
        self.model = "claude-sonnet-4-5-20250929"

    def _extract_text(self, response) -> str:
        """Extract text from response, handling thinking blocks"""
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text
        return ""

    async def intelligent_search(self, query: str, search_executor) -> dict:
        """
        Agent 式智能搜索：让 LLM 自主推理、泛化查询、多轮搜索

        Args:
            query: 用户的自然语言查询
            search_executor: 执行搜索的回调函数

        Returns:
            包含候选人列表和搜索过程说明的字典
        """
        system_prompt = """你是一个专业的人才搜索助手。你的任务是根据用户的搜索需求，智能地搜索人才库并返回最匹配的候选人。

你需要：
1. **理解用户意图**：分析用户真正想找什么样的人
2. **推理泛化**：思考相关的职位名称、技能、关键词
   - 例如：用户搜"产品经理"，你应该也搜索：PM、Product Manager、产品设计、产品运营等
   - 例如：用户搜"会Python"，你应该也搜索：Python开发、后端开发、数据分析、爬虫等
3. **多轮搜索**：使用不同的搜索策略多次搜索，确保不遗漏
4. **结果评估**：根据匹配度对结果进行排序

搜索策略建议：
- 第一轮：使用原始关键词搜索
- 第二轮：使用同义词和相关概念搜索
- 第三轮：使用更宽泛的上位概念搜索
- 如果结果为空，尝试获取全部候选人并人工筛选

请开始搜索，搜索完成后，返回一段总结说明你的搜索过程和结果。"""

        messages = [
            {"role": "user", "content": f"请帮我搜索：{query}"}
        ]

        all_candidates = {}  # 用 id 去重
        search_history = []  # 记录搜索过程
        max_turns = 5  # 最多搜索轮数

        for turn in range(max_turns):
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                tools=SEARCH_TOOLS,
                messages=messages
            )

            # 检查是否有工具调用
            tool_calls = [block for block in response.content if block.type == "tool_use"]

            if not tool_calls:
                # 没有工具调用，LLM 已完成搜索，提取总结
                summary = self._extract_text(response)
                break

            # 处理所有工具调用
            tool_results = []
            for tool_call in tool_calls:
                tool_name = tool_call.name
                tool_input = tool_call.input

                if tool_name == "search_candidates":
                    # 执行搜索
                    results = await search_executor(
                        search_terms=tool_input.get("search_terms", []),
                        city=tool_input.get("city"),
                        min_experience=tool_input.get("min_experience"),
                        max_experience=tool_input.get("max_experience"),
                        max_salary=tool_input.get("max_salary")
                    )

                    # 记录搜索历史
                    search_history.append({
                        "terms": tool_input.get("search_terms", []),
                        "found": len(results)
                    })

                    # 合并结果（去重）
                    for c in results:
                        all_candidates[c["id"]] = c

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps({
                            "found": len(results),
                            "candidates": [{"id": c["id"], "name": c["name"], "title": c.get("current_title"), "company": c.get("current_company")} for c in results[:10]]
                        }, ensure_ascii=False)
                    })

                elif tool_name == "get_all_candidates":
                    # 获取所有候选人
                    results = await search_executor(
                        search_terms=[],
                        limit=tool_input.get("limit", 20)
                    )

                    for c in results:
                        all_candidates[c["id"]] = c

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": json.dumps({
                            "total": len(results),
                            "candidates": [{"id": c["id"], "name": c["name"], "title": c.get("current_title"), "skills": c.get("skills")} for c in results]
                        }, ensure_ascii=False)
                    })

            # 将工具调用结果添加到消息中
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            summary = "搜索完成"

        return {
            "candidates": list(all_candidates.values()),
            "search_history": search_history,
            "summary": summary,
            "total_found": len(all_candidates)
        }

    async def rank_candidates(self, query: str, candidates: list) -> list:
        """让 LLM 对搜索结果进行智能排序，返回排序后的列表和匹配解释（无分数）"""
        if not candidates:
            return []

        # 简化候选人信息用于排序
        candidates_info = []
        for c in candidates[:20]:  # 最多处理20个
            candidates_info.append({
                "id": c.get("id"),
                "name": c.get("name"),
                "title": c.get("current_title"),
                "company": c.get("current_company"),
                "city": c.get("city"),
                "experience": c.get("years_of_experience"),
                "skills": c.get("skills"),
                "summary": c.get("summary", "")[:200]
            })

        prompt = f"""根据用户搜索需求，对以下候选人进行排序。

用户搜索：{query}

候选人列表：
{json.dumps(candidates_info, ensure_ascii=False, indent=2)}

请返回JSON数组，按匹配度从高到低排序，每个元素包含：
- id: 候选人ID
- fit_summary: 一句话总结为什么这个候选人匹配（例如："5年产品经验，有大模型项目落地经历"）
- match_reason: 匹配理由（简短说明）

只返回JSON数组，格式如：
[{{"id": 1, "fit_summary": "5年产品经验，有大模型项目落地经历", "match_reason": "职位和技能高度匹配"}}]"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            content = self._extract_text(response)
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                rankings = json.loads(content[start:end])

                # 根据排序结果重新排列候选人，保持 LLM 返回的顺序
                id_to_ranking = {r["id"]: (i, r) for i, r in enumerate(rankings)}
                sorted_candidates = []
                for c in candidates:
                    idx, ranking = id_to_ranking.get(c.get("id"), (999, {}))
                    c["_sort_order"] = idx
                    c["fit_summary"] = ranking.get("fit_summary", "")
                    c["match_reason"] = ranking.get("match_reason", "")
                    sorted_candidates.append(c)

                sorted_candidates.sort(key=lambda x: x.get("_sort_order", 999))
                # 清理临时排序字段
                for c in sorted_candidates:
                    c.pop("_sort_order", None)
                return sorted_candidates
        except Exception as e:
            print(f"Ranking failed: {e}")

        return candidates

    async def generate_fit_summary(self, candidate: dict, query: str) -> str:
        """为单个候选人生成一句话匹配总结"""
        prompt = f"""根据搜索需求，用一句话（15-30字）总结这个候选人为什么匹配。

搜索需求：{query}

候选人信息：
- 姓名：{candidate.get('name')}
- 职位：{candidate.get('current_title')}
- 公司：{candidate.get('current_company')}
- 城市：{candidate.get('city')}
- 经验：{candidate.get('years_of_experience')}年
- 技能：{candidate.get('skills', '')[:200]}

只返回一句话总结，不要其他内容。例如："5年产品经验，主导过多款AI产品" """

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            return self._extract_text(response).strip()
        except Exception as e:
            print(f"Generate fit summary failed: {e}")
            return ""

    async def parse_resume(self, text: str) -> dict:
        prompt = """从以下简历文本中提取结构化信息，返回JSON格式：
{
    "name": "姓名",
    "phone": "手机号",
    "email": "邮箱",
    "city": "所在城市",
    "current_company": "当前公司",
    "current_title": "当前职位",
    "years_of_experience": 工作年限(数字),
    "expected_salary": 期望薪资(万/年，数字),
    "skills": ["技能1", "技能2"],
    "summary": "个人简介/亮点总结"
}

只返回JSON，不要其他内容。如果某字段无法提取，设为null。

简历内容：
""" + text[:8000]

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            content = self._extract_text(response)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return {}
        except json.JSONDecodeError:
            return {}
        except Exception as e:
            raise AIServiceError(f"Resume parsing failed: {str(e)}")

    async def parse_search_query(self, query: str) -> dict:
        prompt = """将以下自然语言搜索条件解析为结构化JSON：
{
    "skills": ["技能要求"],
    "city": "城市",
    "min_experience": 最低工作年限,
    "max_experience": 最高工作年限,
    "min_salary": 最低薪资(万/年),
    "max_salary": 最高薪资(万/年),
    "keywords": ["其他关键词"]
}
只返回JSON，不要其他内容。如果某字段无法从查询中提取，设为null。

搜索条件：""" + query

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            content = self._extract_text(response)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return {}
        except json.JSONDecodeError:
            return {}
        except Exception as e:
            raise AIServiceError(f"Query parsing failed: {str(e)}")

    async def generate_match_reasons(self, candidate: dict, conditions: dict) -> list[dict]:
        prompt = f"""分析候选人与搜索条件的匹配情况，返回匹配理由列表：
候选人信息：{json.dumps(candidate, ensure_ascii=False)}
搜索条件：{json.dumps(conditions, ensure_ascii=False)}

返回JSON数组格式：
[{{"field": "字段名", "reason": "匹配理由"}}]
只返回JSON数组。"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            content = self._extract_text(response)
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return []
        except:
            return [{"field": "general", "reason": "符合搜索条件"}]
