"""
Data models for the knowledge graph.
Shared between KnowledgeGraphLoader, ResumeGraphBuilder, and GraphRAGTool.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KGNode:
    id: str
    label: str
    type: str                        # Domain | Tech | Concept | Component | Pitfall
    domain: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class KGEdge:
    source: str
    target: str
    relation: str                    # BELONGS_TO | HAS_COMPONENT | LEADS_TO | HAS_PITFALL | ...
    question_hint: str = ""          # Pre-written interviewer follow-up hint


@dataclass
class AnchoredEntity:
    """A resume entity that has been matched to a pre-built knowledge graph node."""
    resume_text: str                 # Raw text from resume, e.g. "Transformer-based model"
    kg_node_id: str                  # Matched node id, e.g. "transformer"
    kg_node_label: str
    confidence: float                # 0.0–1.0 match confidence


@dataclass
class TraversalResult:
    """Output of a graph traversal starting from an anchored entity."""
    entry_node_id: str
    entry_node_label: str
    depth_chain: list[dict]          # Ordered list of nodes along the LEADS_TO path
    pitfalls: list[KGNode]           # All HAS_PITFALL targets reachable from entry
    question_hints: list[str]        # Collected question_hint strings along LEADS_TO edges
