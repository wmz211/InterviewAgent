# InterviewAgent — AI 模拟面试教练

基于 LangGraph + GraphRAG 的全栈 AI 面试模拟系统。上传简历与 JD，由 AI 面试官主导多轮技术面试，最终生成能力评估报告。

## 功能特性

- **多阶段面试流程**：开场破冰 → 简历深挖 → JD 技术考察 → 编程题 → 总结评估
- **GraphRAG 混合检索**：GLiNER 实体抽取 + BM25 + 向量检索（bge-m3）+ RRF 融合，精准匹配技术知识图谱节点
- **知识图谱**：覆盖 LLM、Agent、RAG、推理优化等 AI 工程领域的技术知识图谱
- **Function Calling**：4 个 Agent Tool 按面试阶段分配，驱动图谱检索与题库召回
- **多模态支持**：DashScope TTS 语音合成 + FunASR 实时语音识别
- **LangSmith 监控**：全链路 trace/span 级可观测性
- **历史记录**：面试结束后持久化存储，支持查看历史报告与对话记录

## 技术栈

| 层级 | 技术 |
|------|------|
| LLM | Qwen-Max（DashScope API） |
| Agent 框架 | LangGraph |
| 图数据库 | Neo4j |
| 向量数据库 | ChromaDB |
| 向量模型 | BAAI/bge-m3 |
| NER 模型 | knowledgator/gliner-x-base |
| 后端 | FastAPI |
| 监控 | LangSmith |

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入以下必填项：

```
DASHSCOPE_API_KEY=your_key
NEO4J_PASSWORD=your_password
LANGCHAIN_API_KEY=your_langsmith_key  # 可选
```

### 3. 启动 Neo4j

```bash
docker-compose up -d
```

### 4. 初始化数据库

```bash
python scripts/init_neo4j.py      # 初始化知识图谱
python scripts/init_vector_db.py  # 初始化题库向量索引
```

### 5. 启动服务

```bash
python app/main.py
```

访问 http://localhost:8000

## 项目结构

```
app/
├── agents/nodes/     # 面试各阶段节点（LangGraph）
├── agents/tools/     # Agent Tool 定义（Function Calling）
├── api/              # FastAPI 路由与端点
├── audio/            # TTS / ASR 处理
├── core/             # 状态机与会话管理
├── evaluation/       # 评分与报告生成
└── rag/              # GraphRAG + 向量检索

data/
├── tech_knowledge_graph.json   # 知识图谱初始数据
└── question_bank/              # 面试题库

scripts/              # 初始化与维护脚本
static/               # 前端页面
```

## 系统架构

```
用户上传简历 + JD
       ↓
  简历解析 + 实体锚定（anchored_entities）
       ↓
  LangGraph 状态机路由
  ┌────────────────────────────────┐
  │  greeting → resume_dive        │
  │      → jd_tech (GraphRAG)      │
  │      → coding_test (VectorDB)  │
  │      → wrap_up → 评估报告      │
  └────────────────────────────────┘
```

jd_tech 阶段 GraphRAG 流水线：
```
JD 文本 → GLiNER 实体抽取
       → BM25 召回 + 向量召回
       → RRF 融合 → Top5 节点
       → LEADS_TO 图边展开成追问链
       → LLM Function Calling 生成问题
```
