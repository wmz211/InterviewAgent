"""
InterviewAgent MCP Server
=========================
Exposes interview knowledge tools via Model Context Protocol (stdio transport).

Usage
-----
Register with Claude Desktop by adding to claude_desktop_config.json:

  {
    "mcpServers": {
      "interview-agent": {
        "command": "D:/Homework/InterviewAgent/.venv/Scripts/python",
        "args":    ["D:/Homework/InterviewAgent/mcp_server.py"],
        "env": {
          "DASHSCOPE_API_KEY": "<your-key>",
          "NEO4J_URI":         "bolt://localhost:7687",
          "NEO4J_USERNAME":    "neo4j",
          "NEO4J_PASSWORD":    "<your-password>",
          "GRAPH_BACKEND":     "neo4j"
        }
      }
    }
  }

Or run directly for testing:
  python mcp_server.py
"""
import sys
import os

# Ensure project root is on sys.path so `app.*` imports work
sys.path.insert(0, os.path.dirname(__file__))

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

# MCP uses stdio — redirect ALL logging to stderr so stdout stays clean
import sys
import logging
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

# Redirect loguru to stderr as well
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

import json
from mcp.server.fastmcp import FastMCP
from app.mcp.tools import (
    search_interview_questions as _search_questions,
    search_algorithm_problems as _search_algorithms,
    lookup_tech_concept as _lookup_tech,
    get_question_hints as _get_hints,
    get_interview_phases as _get_phases,
)

mcp = FastMCP(
    "InterviewAgent",
    instructions=(
        "InterviewAgent 知识库工具集。"
        "包含面试题库检索、算法题库检索、技术知识图谱查询和面试阶段信息。"
        "适合用于制定面试方案、出题、追问角度分析等场景。"
    ),
)


# ── Tool 1: 面试题库检索 ───────────────────────────────────────────────────────

@mcp.tool()
def search_interview_questions(
    query: str,
    topic: str = "",
    difficulty: str = "",
    n_results: int = 5,
) -> str:
    """
    从面试题库中向量检索相关题目。

    Args:
        query:      搜索关键词，如"手写注意力机制"、"TCP粘包"、"LRU缓存"
        topic:      限定主题，如"深度学习"、"操作系统"、"数据库"（可选）
        difficulty: 限定难度，如"easy"、"medium"、"hard"（可选）
        n_results:  返回题目数量，默认 5

    Returns:
        JSON 字符串，每条含 question / answer / topic / difficulty / relevance
    """
    try:
        results = _search_questions(query, topic, difficulty, n_results)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Tool 2: 算法题库检索 ───────────────────────────────────────────────────────

@mcp.tool()
def search_algorithm_problems(
    query: str,
    difficulty: str = "",
    n_results: int = 3,
) -> str:
    """
    从算法题库中检索编程题。

    Args:
        query:      搜索描述，如"二叉树层序遍历"、"动态规划背包"
        difficulty: 难度过滤，"easy" / "medium" / "hard"（可选）
        n_results:  返回数量，默认 3

    Returns:
        JSON 字符串，每条含题目描述、解题思路、代码示例
    """
    try:
        results = _search_algorithms(query, difficulty, n_results)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Tool 3: 技术概念查询 ───────────────────────────────────────────────────────

@mcp.tool()
def lookup_tech_concept(tech_name: str) -> str:
    """
    在知识图谱中查找技术/概念节点，返回定义、子组件和常见误区。

    Args:
        tech_name: 技术名称，如"Transformer"、"Redis"、"B+树"、"MVCC"

    Returns:
        JSON 字符串，含 label / type / description / components / pitfalls
    """
    try:
        result = _lookup_tech(tech_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Tool 4: 面试追问路径 ───────────────────────────────────────────────────────

@mcp.tool()
def get_question_hints(tech_name: str, depth: int = 3) -> str:
    """
    沿知识图谱 LEADS_TO 链路生成分层追问路径（L1浅层→L2原理→L3深度）及常见坑。

    Args:
        tech_name: 起点技术，如"注意力机制"、"索引优化"
        depth:     追问深度，1-3，默认 3

    Returns:
        JSON 字符串，含 question_chain（各层追问提示）和 pitfalls（常见误区）
    """
    try:
        result = _get_hints(tech_name, depth)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Tool 5: 面试阶段信息 ───────────────────────────────────────────────────────

@mcp.tool()
def get_interview_phases() -> str:
    """
    返回面试的各个阶段定义、考察重点和典型题型分布。

    Returns:
        JSON 字符串，包含 greeting / resume_dive / cs_fundamentals /
        coding_test / wrap_up 各阶段信息
    """
    try:
        phases = _get_phases()
        return json.dumps(phases, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
