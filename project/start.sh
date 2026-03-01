#!/bin/bash
# Talent Library 启动脚本
# 启动后端 API 和 MCP Server

cd /Users/york_z/Desktop/talent_library_test1/project

echo "🚀 启动 Talent Library..."

# 检查依赖
if ! pip show mcp &>/dev/null; then
    echo "📦 安装 MCP 依赖..."
    pip install mcp httpx
fi

# 启动后端 API (后台运行)
echo "🔧 启动后端 API (端口 8000)..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# 等待 API 启动
sleep 3

# 检查 API 是否启动成功
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 后端 API 启动成功"
else
    echo "⚠️  后端 API 可能未完全启动，继续..."
fi

echo ""
echo "=========================================="
echo "🎉 Talent Library 已启动!"
echo "=========================================="
echo ""
echo "后端 API:  http://localhost:8000"
echo "API 文档:  http://localhost:8000/docs"
echo ""
echo "OpenClaw 集成:"
echo "  - MCP Server 已配置到 openclaw.json"
echo "  - Skill 已安装到 ~/.openclaw/workspace/skills/talent-library/"
echo ""
echo "测试 MCP Server:"
echo "  python -m mcp_server.server"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 等待中断
wait $API_PID
