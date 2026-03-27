"""
ResumeGraphBuilder:
  1. LLM extracts tech entities from resume text
  2. Each entity is anchored to a pre-built KG node
     (exact alias → full-text search → fuzzy fallback)
  3. For each project, creates a :ResumeProject node in Neo4j
     linked via -[:MENTIONS]-> to the matched KG Tech nodes

The ResumeProject nodes let us later query:
  MATCH (rp:ResumeProject {session_id: $sid})-[:MENTIONS]->(t)-[:LEADS_TO*]->(c)
  to find all interview-worthy deep-dive paths for a specific candidate.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from langchain_openai import ChatOpenAI
from loguru import logger

from app.config import get_settings
from app.rag.graph_rag.knowledge_base import get_knowledge_graph
from app.rag.graph_rag.schema import AnchoredEntity
from app.rag.parser.resume_parser import ResumeData

settings = get_settings()

_llm = ChatOpenAI(
    model=settings.llm_model_name,
    api_key=settings.dashscope_api_key,
    base_url=settings.llm_base_url,
    temperature=0,
)

_ENTITY_EXTRACTION_PROMPT = """\
你是技术简历分析专家。从以下简历文本中提取所有技术名词（框架、模型、算法、工具、概念）。
每行输出一个词，不加解释和编号。

简历文本：
{resume_text}

技术词汇："""


async def _extract_entities_from_text(text: str) -> list[str]:
    response = await _llm.ainvoke(
        _ENTITY_EXTRACTION_PROMPT.format(resume_text=text[:4000])
    )
    return [line.strip() for line in response.content.strip().splitlines() if line.strip()]


def _anchor_one(entity: str, fuzzy_threshold: float = 0.72) -> AnchoredEntity | None:
    """
    Try to anchor a single entity string to a KG node.
    Priority: exact alias → fulltext index → fuzzy ratio.
    """
    kg = get_knowledge_graph()

    # 1. Exact alias match
    node_id = kg.lookup_by_alias(entity)
    if node_id:
        node = kg.get_node(node_id)
        if node:
            return AnchoredEntity(
                resume_text=entity, kg_node_id=node_id,
                kg_node_label=node.label, confidence=1.0,
            )

    # 2. Full-text / fuzzy search
    candidates = kg.fulltext_search(entity, top_k=1)
    if candidates:
        top = candidates[0]
        score = top.get("score", top.get("confidence", 0))
        # Neo4j returns BM25 score (unbounded); normalize heuristically
        # NetworkX returns ratio score (0-1)
        confidence = min(score, 1.0) if score <= 1.0 else min(score / 5.0, 1.0)
        if confidence >= fuzzy_threshold:
            node = kg.get_node(top["node_id"])
            if node:
                return AnchoredEntity(
                    resume_text=entity, kg_node_id=top["node_id"],
                    kg_node_label=node.label, confidence=round(confidence, 2),
                )

    # 3. Simple ratio fallback (always available)
    entity_lower = entity.lower()
    best_score, best_id = 0.0, None
    for alias, nid in getattr(kg, "_alias_index", {}).items():
        s = SequenceMatcher(None, entity_lower, alias).ratio()
        if s > best_score:
            best_score, best_id = s, nid
    if best_id and best_score >= fuzzy_threshold:
        node = kg.get_node(best_id)
        if node:
            return AnchoredEntity(
                resume_text=entity, kg_node_id=best_id,
                kg_node_label=node.label, confidence=round(best_score, 2),
            )

    return None


def anchor_entities(entities: list[str]) -> list[AnchoredEntity]:
    anchored, seen = [], set()
    for entity in entities:
        result = _anchor_one(entity)
        if result and result.kg_node_id not in seen:
            anchored.append(result)
            seen.add(result.kg_node_id)
    logger.info(f"Anchored {len(anchored)}/{len(entities)} entities to KG nodes")
    return anchored


async def build_session_graph(
    resume: ResumeData,
    session_id: str,
) -> list[AnchoredEntity]:
    """
    Full pipeline:
      ResumeData → entity extraction → KG anchoring → Neo4j ResumeProject nodes

    Returns the list of AnchoredEntity objects stored in InterviewState.
    """
    kg = get_knowledge_graph()
    all_anchored: list[AnchoredEntity] = []

    for project in resume.projects:
        # Combine description + tech_stack for richer entity extraction
        project_text = (
            f"项目：{project.name}\n"
            f"技术栈：{', '.join(project.tech_stack)}\n"
            f"描述：{project.description}"
        )
        entities = await _extract_entities_from_text(project_text)
        anchored = anchor_entities(entities)
        all_anchored.extend(anchored)

        # Write ResumeProject → Tech links into Neo4j
        kg.create_resume_project(
            session_id=session_id,
            project_name=project.name,
            description=project.description,
            anchored_node_ids=[a.kg_node_id for a in anchored],
            confidences=[a.confidence for a in anchored],
        )

    # Also extract from skills section
    skill_entities = await _extract_entities_from_text(", ".join(resume.skills))
    all_anchored.extend(anchor_entities(skill_entities))

    # Deduplicate across projects
    seen: set[str] = set()
    unique = []
    for a in all_anchored:
        if a.kg_node_id not in seen:
            unique.append(a)
            seen.add(a.kg_node_id)

    logger.info(
        f"Session {session_id}: {len(unique)} unique KG nodes anchored "
        f"from {len(resume.projects)} projects"
    )
    return unique
