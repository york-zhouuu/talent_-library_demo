#!/usr/bin/env python3
"""
Talent Library MCP Server

Exposes talent library capabilities as MCP tools for AI agents.
Run with: python -m mcp_server.server
"""

import json
import asyncio
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import httpx

# Talent Library API base URL
API_BASE = "http://localhost:8000/api/v1"

# Initialize MCP server
server = Server("talent-library")


def make_text_content(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


async def api_request(method: str, endpoint: str, data: dict | None = None) -> dict:
    """Make API request to talent library backend."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = f"{API_BASE}{endpoint}"
        if method == "GET":
            response = await client.get(url, params=data)
        elif method == "POST":
            response = await client.post(url, json=data)
        elif method == "DELETE":
            response = await client.delete(url)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()
        return response.json() if response.text else {}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available talent library tools."""
    return [
        Tool(
            name="talent_search",
            description="""搜索人才库中的候选人。支持自然语言查询，如"找3个会Python的后端工程师"、"北京的产品经理"等。

返回匹配的候选人列表，包含姓名、职位、公司、技能、匹配原因等信息。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言搜索查询，如'5年以上Python经验的后端'、'上海的产品经理'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制，默认10",
                        "default": 10
                    },
                    "pool_id": {
                        "type": "integer",
                        "description": "可选，指定在某个人才库中搜索"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="talent_get_candidate",
            description="获取单个候选人的详细信息，包括完整简历、工作经历、技能、联系方式等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "候选人ID"
                    }
                },
                "required": ["candidate_id"]
            }
        ),
        Tool(
            name="talent_list_pools",
            description="列出所有人才库（公有库和私有库），包含每个库的候选人数量。",
            inputSchema={
                "type": "object",
                "properties": {
                    "is_public": {
                        "type": "boolean",
                        "description": "可选，筛选公有库(true)或私有库(false)"
                    }
                }
            }
        ),
        Tool(
            name="talent_get_pool_candidates",
            description="获取指定人才库中的候选人列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "integer",
                        "description": "人才库ID"
                    },
                    "page": {
                        "type": "integer",
                        "description": "页码，默认1",
                        "default": 1
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "每页数量，默认20",
                        "default": 20
                    }
                },
                "required": ["pool_id"]
            }
        ),
        Tool(
            name="talent_add_to_pool",
            description="将候选人添加到指定人才库中。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "integer",
                        "description": "人才库ID"
                    },
                    "candidate_id": {
                        "type": "integer",
                        "description": "候选人ID"
                    }
                },
                "required": ["pool_id", "candidate_id"]
            }
        ),
        Tool(
            name="talent_remove_from_pool",
            description="将候选人从指定人才库中移除。",
            inputSchema={
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "integer",
                        "description": "人才库ID"
                    },
                    "candidate_id": {
                        "type": "integer",
                        "description": "候选人ID"
                    }
                },
                "required": ["pool_id", "candidate_id"]
            }
        ),
        Tool(
            name="talent_create_pool",
            description="创建一个新的私有人才库。",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "人才库名称"
                    },
                    "description": {
                        "type": "string",
                        "description": "人才库描述"
                    },
                    "owner_id": {
                        "type": "string",
                        "description": "所有者ID，如HR的用户名或邮箱"
                    }
                },
                "required": ["name", "owner_id"]
            }
        ),
        Tool(
            name="talent_update_status",
            description="""更新候选人的状态。可用状态：
- new: 新建档
- contacted: 已联系
- interviewing: 面试中
- offered: 已发offer
- hired: 已入职
- rejected: 已拒绝
- withdrawn: 已放弃""",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "候选人ID"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["new", "contacted", "interviewing", "offered", "hired", "rejected", "withdrawn"],
                        "description": "新状态"
                    },
                    "note": {
                        "type": "string",
                        "description": "状态变更备注"
                    }
                },
                "required": ["candidate_id", "status"]
            }
        ),
        Tool(
            name="talent_add_note",
            description="为候选人添加备注，如面试反馈、沟通记录等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "候选人ID"
                    },
                    "note": {
                        "type": "string",
                        "description": "备注内容"
                    }
                },
                "required": ["candidate_id", "note"]
            }
        ),
        Tool(
            name="talent_get_stats",
            description="获取人才库的统计数据，包括总候选人数、各人才库分布等。",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a talent library tool."""
    try:
        if name == "talent_search":
            query = arguments["query"]
            limit = arguments.get("limit", 10)
            pool_id = arguments.get("pool_id")

            data = {"query": query, "limit": limit}
            if pool_id:
                data["pool_id"] = pool_id

            result = await api_request("POST", "/search/quick", data)

            # Format results for readability
            candidates = result.get("candidates", [])
            if not candidates:
                return make_text_content("未找到匹配的候选人。")

            output = f"找到 {len(candidates)} 位匹配的候选人：\n\n"
            for i, c in enumerate(candidates, 1):
                output += f"**{i}. {c['name']}** (ID: {c['id']})\n"
                if c.get('current_title'):
                    output += f"   职位: {c['current_title']}"
                    if c.get('current_company'):
                        output += f" @ {c['current_company']}"
                    output += "\n"
                if c.get('city'):
                    output += f"   城市: {c['city']}\n"
                if c.get('years_of_experience'):
                    output += f"   经验: {c['years_of_experience']}年\n"
                if c.get('skills'):
                    output += f"   技能: {c['skills'][:100]}{'...' if len(c.get('skills', '')) > 100 else ''}\n"
                if c.get('fit_summary'):
                    output += f"   匹配: {c['fit_summary']}\n"
                output += "\n"

            return make_text_content(output)

        elif name == "talent_get_candidate":
            candidate_id = arguments["candidate_id"]
            result = await api_request("GET", f"/candidates/{candidate_id}")

            c = result
            output = f"# {c['name']} (ID: {c['id']})\n\n"
            output += "## 基本信息\n"
            if c.get('phone'):
                output += f"- 电话: {c['phone']}\n"
            if c.get('email'):
                output += f"- 邮箱: {c['email']}\n"
            if c.get('city'):
                output += f"- 城市: {c['city']}\n"

            output += "\n## 职业信息\n"
            if c.get('current_title'):
                output += f"- 职位: {c['current_title']}\n"
            if c.get('current_company'):
                output += f"- 公司: {c['current_company']}\n"
            if c.get('years_of_experience'):
                output += f"- 经验: {c['years_of_experience']}年\n"
            if c.get('expected_salary'):
                output += f"- 期望薪资: {c['expected_salary']}万/年\n"

            if c.get('skills'):
                output += f"\n## 技能\n{c['skills']}\n"

            if c.get('summary'):
                output += f"\n## 简介\n{c['summary']}\n"

            if c.get('tags'):
                tags = [t['name'] for t in c['tags']]
                output += f"\n## 标签\n{', '.join(tags)}\n"

            return make_text_content(output)

        elif name == "talent_list_pools":
            params = {}
            if "is_public" in arguments:
                params["is_public"] = arguments["is_public"]

            result = await api_request("GET", "/talent-pools", params)
            pools = result.get("items", [])

            if not pools:
                return make_text_content("暂无人才库。")

            output = "人才库列表：\n\n"
            for p in pools:
                icon = "🌐" if p['is_public'] else "🔒"
                output += f"{icon} **{p['name']}** (ID: {p['id']})\n"
                output += f"   候选人数: {p['candidate_count']}\n"
                if p.get('description'):
                    output += f"   描述: {p['description']}\n"
                output += "\n"

            return make_text_content(output)

        elif name == "talent_get_pool_candidates":
            pool_id = arguments["pool_id"]
            page = arguments.get("page", 1)
            page_size = arguments.get("page_size", 20)

            result = await api_request("GET", f"/talent-pools/{pool_id}/candidates", {
                "page": page,
                "page_size": page_size
            })

            candidates = result.get("items", [])
            total = result.get("total", 0)

            output = f"人才库候选人（共 {total} 人，第 {page} 页）：\n\n"
            for c in candidates:
                output += f"- **{c['name']}** (ID: {c['id']})"
                if c.get('current_title'):
                    output += f" - {c['current_title']}"
                output += "\n"

            return make_text_content(output)

        elif name == "talent_add_to_pool":
            pool_id = arguments["pool_id"]
            candidate_id = arguments["candidate_id"]
            await api_request("POST", f"/talent-pools/{pool_id}/candidates/{candidate_id}")
            return make_text_content(f"已将候选人 {candidate_id} 添加到人才库 {pool_id}。")

        elif name == "talent_remove_from_pool":
            pool_id = arguments["pool_id"]
            candidate_id = arguments["candidate_id"]
            await api_request("DELETE", f"/talent-pools/{pool_id}/candidates/{candidate_id}")
            return make_text_content(f"已将候选人 {candidate_id} 从人才库 {pool_id} 移除。")

        elif name == "talent_create_pool":
            data = {
                "name": arguments["name"],
                "owner_id": arguments["owner_id"],
                "is_public": False
            }
            if "description" in arguments:
                data["description"] = arguments["description"]

            result = await api_request("POST", "/talent-pools", data)
            return make_text_content(f"已创建人才库「{result['name']}」(ID: {result['id']})。")

        elif name == "talent_update_status":
            candidate_id = arguments["candidate_id"]
            data = {"status": arguments["status"]}
            if "note" in arguments:
                data["note"] = arguments["note"]

            await api_request("POST", f"/candidates/{candidate_id}/knowledge/status", data)
            return make_text_content(f"已更新候选人 {candidate_id} 状态为「{arguments['status']}」。")

        elif name == "talent_add_note":
            candidate_id = arguments["candidate_id"]
            note = arguments["note"]
            await api_request("POST", f"/candidates/{candidate_id}/knowledge/note", {"note": note})
            return make_text_content(f"已为候选人 {candidate_id} 添加备注。")

        elif name == "talent_get_stats":
            # Get candidates count
            candidates_result = await api_request("GET", "/candidates", {"page": 1, "page_size": 1})
            total_candidates = candidates_result.get("total", 0)

            # Get pools
            pools_result = await api_request("GET", "/talent-pools")
            pools = pools_result.get("items", [])

            public_pools = [p for p in pools if p['is_public']]
            private_pools = [p for p in pools if not p['is_public']]

            output = "# 人才库统计\n\n"
            output += f"- 总候选人数: {total_candidates}\n"
            output += f"- 人才库数量: {len(pools)} (公有: {len(public_pools)}, 私有: {len(private_pools)})\n"

            if pools:
                output += "\n## 各库分布\n"
                for p in pools:
                    icon = "🌐" if p['is_public'] else "🔒"
                    output += f"- {icon} {p['name']}: {p['candidate_count']} 人\n"

            return make_text_content(output)

        else:
            return make_text_content(f"未知工具: {name}")

    except httpx.HTTPStatusError as e:
        return make_text_content(f"API 错误: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        return make_text_content(f"执行错误: {str(e)}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
