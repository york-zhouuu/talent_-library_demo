# Talent Library MCP Server

为 OpenClaw 等 AI Agent 提供人才库能力的 MCP (Model Context Protocol) 服务器。

## 安装

```bash
cd /path/to/talent_library_test1/project
pip install mcp httpx
```

## 运行

```bash
# 确保 Talent Library 后端在运行
uvicorn app.main:app --reload --port 8000

# 启动 MCP Server
python -m mcp_server.server
```

## 可用工具

| 工具名 | 描述 |
|--------|------|
| `talent_search` | 自然语言搜索候选人 |
| `talent_get_candidate` | 获取候选人详情 |
| `talent_list_pools` | 列出人才库 |
| `talent_get_pool_candidates` | 获取库中候选人 |
| `talent_add_to_pool` | 添加候选人到库 |
| `talent_remove_from_pool` | 从库中移除候选人 |
| `talent_create_pool` | 创建私有库 |
| `talent_update_status` | 更新候选人状态 |
| `talent_add_note` | 添加备注 |
| `talent_get_stats` | 获取统计数据 |

## 与 OpenClaw 集成

1. 将 MCP Server 配置添加到 `~/.openclaw/openclaw.json`
2. 创建 Skill 文件 `~/.openclaw/workspace/skills/talent-library/SKILL.md`

详见 OpenClaw Skill 目录中的配置说明。
