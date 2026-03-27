"""
KnowledgeGraph — Neo4j primary backend, NetworkX fallback.

Public API (same regardless of backend):
  get_node(node_id)              → KGNode | None
  lookup_by_alias(text)          → str | None   (node_id)
  get_leads_to_chain(id, depth)  → list[dict]
  get_pitfalls(id, recursive)    → list[KGNode]
  get_components(id)             → list[KGNode]

Factory:
  get_knowledge_graph()          → singleton instance
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.config import get_settings
from app.rag.graph_rag.schema import KGNode

# ══════════════════════════════════════════════════════════════════════
# 模块级单例：GLiNER 和 SentenceTransformer 只初始化一次
# ══════════════════════════════════════════════════════════════════════

_gliner_model = None   # GLiNER | "unavailable"
_embed_model  = None   # SentenceTransformer | "unavailable"

def _get_gliner():
    global _gliner_model
    if _gliner_model is None:
        try:
            from gliner import GLiNER
            _gliner_model = GLiNER.from_pretrained("knowledgator/gliner-x-base")
            logger.info("GLiNER loaded: knowledgator/gliner-x-base")
        except Exception as e:
            logger.warning(f"GLiNER unavailable ({e}); will use regex fallback")
            _gliner_model = "unavailable"
    return None if _gliner_model == "unavailable" else _gliner_model

def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("BAAI/bge-m3")
            logger.info("SentenceTransformer loaded: BAAI/bge-m3")
        except Exception as e:
            logger.warning(f"SentenceTransformer unavailable ({e}); vector search disabled")
            _embed_model = "unavailable"
    return None if _embed_model == "unavailable" else _embed_model


def rrf_merge(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion — 只看排名，不依赖分数量纲。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank + 1)
    return scores

settings = get_settings()
GRAPH_JSON_PATH = Path(__file__).parents[3] / "data" / "tech_knowledge_graph.json"


# ══════════════════════════════════════════════════════════════════════
# Neo4j Backend
# ══════════════════════════════════════════════════════════════════════

class Neo4jKnowledgeGraph:
    """
    Queries the pre-built knowledge graph stored in Neo4j.
    Connection is lazy — first query triggers connect.
    """

    def __init__(self):
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        self._db = settings.neo4j_database
        logger.info(f"Neo4jKnowledgeGraph connected to {settings.neo4j_uri}")
        self.build_bm25_index()
        self.build_vector_index()

    def _session(self):
        return self._driver.session(database=self._db)

    def _row_to_node(self, props: dict) -> KGNode:
        return KGNode(
            id=props["id"],
            label=props.get("label", ""),
            type=props.get("type", ""),          # stored as node label in Neo4j
            domain=props.get("domain", ""),
            aliases=list(props.get("aliases", [])),
            description=props.get("description", ""),
        )

    def get_node(self, node_id: str) -> KGNode | None:
        with self._session() as s:
            result = s.run(
                "MATCH (n {id: $id}) RETURN n, labels(n)[0] AS lbl",
                id=node_id,
            ).single()
        if not result:
            return None
        props = dict(result["n"])
        props["type"] = result["lbl"]
        return self._row_to_node(props)

    def lookup_by_alias(self, text: str) -> str | None:
        """
        Exact alias lookup (case-insensitive):
          1. Check label match
          2. Check aliases list membership
        Returns node_id or None.
        """
        text_lower = text.strip().lower()
        with self._session() as s:
            result = s.run(
                """
                MATCH (n)
                WHERE toLower(n.label) = $text
                   OR toLower($text) IN [a IN n.aliases | toLower(a)]
                RETURN n.id AS node_id LIMIT 1
                """,
                text=text_lower,
            ).single()
        return result["node_id"] if result else None

    @staticmethod
    def _escape_lucene(text: str) -> str:
        """Escape Lucene special characters so fulltext queries never crash."""
        # Strip characters that confuse Lucene: + - & | ! ( ) { } [ ] ^ " ~ * ? : \ /
        # and common Chinese/Japanese punctuation that can appear in JD text.
        return re.sub(r'[+\-&|!(){}[\]^"~*?:\\/，。；：！？、【】《》「」『』""''\s]+', ' ', text).strip()

    def fulltext_search(self, text: str, top_k: int = 3) -> list[dict]:
        """
        Full-text index search for fuzzy alias matching.
        Returns list of {node_id, label, type, score}.
        """
        safe = self._escape_lucene(text)
        if not safe:
            return []
        with self._session() as s:
            results = s.run(
                """
                CALL db.index.fulltext.queryNodes('alias_fulltext', $search_text)
                YIELD node, score
                RETURN node.id AS node_id, node.label AS label,
                       labels(node)[0] AS type, score
                ORDER BY score DESC LIMIT $k
                """,
                search_text=safe,
                k=top_k,
            ).data()
        return results

    def get_leads_to_chain(self, start_id: str, max_depth: int = 3) -> list[dict]:
        """
        Follow LEADS_TO edges from start_id, ordered by depth.
        Returns: [{node_id, label, type, description, question_hint}, ...]
        """
        # Cypher does not allow parameterized relationship depth — embed as literal.
        # max_depth is always an int from our own code, not user input.
        query = f"""
                MATCH path = (start {{id: $start_id}})-[:LEADS_TO*1..{max_depth}]->(node)
                RETURN
                    node.id          AS node_id,
                    node.label       AS label,
                    labels(node)[0]  AS type,
                    node.description AS description,
                    [r IN relationships(path) | r.question_hint][-1] AS question_hint,
                    length(path)     AS depth
                ORDER BY depth
                """
        with self._session() as s:
            rows = s.run(query, start_id=start_id).data()

        # De-duplicate by depth — keep first occurrence at each level
        seen_depths: set[int] = set()
        chain = []
        for row in rows:
            d = row["depth"]
            if d not in seen_depths:
                chain.append({
                    "node_id":      row["node_id"],
                    "label":        row["label"],
                    "type":         row["type"],
                    "description":  row["description"],
                    "question_hint": row["question_hint"] or "",
                })
                seen_depths.add(d)
        return chain

    def get_pitfalls(self, node_id: str, recursive: bool = True) -> list[KGNode]:
        """
        Collect Pitfall nodes reachable from node_id.
        recursive=True also follows HAS_COMPONENT one hop first.
        """
        with self._session() as s:
            if recursive:
                rows = s.run(
                    """
                    MATCH (start {id: $id})
                    OPTIONAL MATCH (start)-[:HAS_PITFALL]->(p1:Pitfall)
                    OPTIONAL MATCH (start)-[:HAS_COMPONENT]->(c)-[:HAS_PITFALL]->(p2:Pitfall)
                    WITH collect(DISTINCT p1) + collect(DISTINCT p2) AS all_p
                    UNWIND all_p AS p
                    WITH p WHERE p IS NOT NULL
                    RETURN DISTINCT p, labels(p)[0] AS lbl
                    """,
                    id=node_id,
                ).data()
            else:
                rows = s.run(
                    """
                    MATCH (start {id: $id})-[:HAS_PITFALL]->(p:Pitfall)
                    RETURN p, labels(p)[0] AS lbl
                    """,
                    id=node_id,
                ).data()

        pitfalls = []
        for row in rows:
            props = dict(row["p"])
            props["type"] = row["lbl"]
            pitfalls.append(self._row_to_node(props))
        return pitfalls

    def get_components(self, node_id: str) -> list[KGNode]:
        with self._session() as s:
            rows = s.run(
                """
                MATCH ({id: $id})-[:HAS_COMPONENT]->(c)
                RETURN c, labels(c)[0] AS lbl
                """,
                id=node_id,
            ).data()
        result = []
        for row in rows:
            props = dict(row["c"])
            props["type"] = row["lbl"]
            result.append(self._row_to_node(props))
        return result

    def create_resume_project(
        self,
        session_id: str,
        project_name: str,
        description: str,
        anchored_node_ids: list[str],
        confidences: list[float],
    ) -> None:
        """
        Create a ResumeProject node and link it to anchored KG nodes via MENTIONS.
        Called by builder.py after anchoring.
        """
        project_id = f"proj_{session_id}_{project_name[:20].replace(' ', '_')}"
        with self._session() as s:
            s.run(
                """
                MERGE (rp:ResumeProject {id: $id})
                SET rp.session_id   = $session_id,
                    rp.name         = $name,
                    rp.description  = $description
                """,
                id=project_id,
                session_id=session_id,
                name=project_name,
                description=description,
            )
            for node_id, confidence in zip(anchored_node_ids, confidences):
                s.run(
                    """
                    MATCH (rp:ResumeProject {id: $proj_id})
                    MATCH (tech {id: $tech_id})
                    MERGE (rp)-[m:MENTIONS]->(tech)
                    SET m.confidence = $confidence
                    """,
                    proj_id=project_id,
                    tech_id=node_id,
                    confidence=confidence,
                )
        logger.info(
            f"ResumeProject '{project_name}' linked to {len(anchored_node_ids)} KG nodes"
        )

    # ── Hybrid retrieval index ─────────────────────────────────────

    def _load_all_node_texts(self) -> list[tuple[str, str]]:
        """Return [(node_id, label + aliases text), ...] for all KG nodes."""
        with self._session() as s:
            rows = s.run(
                "MATCH (n) WHERE NOT n:ResumeProject "
                "RETURN n.id AS id, n.label AS label, n.aliases AS aliases"
            ).data()
        return [
            (r["id"], (r["label"] or "") + " " + " ".join(r["aliases"] or []))
            for r in rows if r["id"]
        ]

    def build_bm25_index(self) -> None:
        try:
            import jieba
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25/jieba not installed; BM25 index skipped")
            return
        node_texts = self._load_all_node_texts()
        self._bm25_node_ids: list[str] = [t[0] for t in node_texts]
        corpus = [list(jieba.cut(t[1])) for t in node_texts]
        self._bm25 = BM25Okapi(corpus)
        logger.info(f"BM25 index built: {len(self._bm25_node_ids)} nodes")

    def bm25_search(self, terms: list[str]) -> dict[str, float]:
        if not hasattr(self, "_bm25") or not terms:
            return {}
        import jieba
        query_tokens = [tok for term in terms for tok in jieba.cut(term)]
        scores = self._bm25.get_scores(query_tokens)
        return {self._bm25_node_ids[i]: float(scores[i])
                for i in range(len(self._bm25_node_ids))}

    def build_vector_index(self) -> None:
        embed = _get_embed_model()
        if embed is None:
            return
        import numpy as np
        node_texts = self._load_all_node_texts()
        self._vector_node_ids: list[str] = [t[0] for t in node_texts]
        texts = [t[1] for t in node_texts]
        self._node_matrix = embed.encode(texts, batch_size=32, show_progress_bar=False)
        logger.info(f"Vector index built: {len(self._vector_node_ids)} nodes, dim={self._node_matrix.shape[1]}")

    def vector_search(self, terms: list[str]) -> dict[str, float]:
        embed = _get_embed_model()
        if embed is None or not hasattr(self, "_node_matrix") or not terms:
            return {}
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        scores: dict[str, float] = {}
        for term in terms:
            vec = embed.encode(term).reshape(1, -1)
            sims = cosine_similarity(vec, self._node_matrix)[0]
            for i, nid in enumerate(self._vector_node_ids):
                scores[nid] = max(scores.get(nid, 0.0), float(sims[i]))
        return scores

    def delete_session_nodes(self, session_id: str) -> int:
        """Delete all ResumeProject nodes (and their MENTIONS edges) for a session."""
        with self._session() as s:
            result = s.run(
                """
                MATCH (rp:ResumeProject {session_id: $sid})
                DETACH DELETE rp
                RETURN count(rp) AS deleted
                """,
                sid=session_id,
            )
            deleted = (result.single() or {}).get("deleted", 0)
        logger.info(f"Deleted {deleted} ResumeProject node(s) for session {session_id}")
        return deleted

    def close(self):
        self._driver.close()


# ══════════════════════════════════════════════════════════════════════
# NetworkX Fallback Backend
# ══════════════════════════════════════════════════════════════════════

class NetworkXKnowledgeGraph:
    """In-memory fallback. Loaded from JSON at startup."""

    def __init__(self):
        import networkx as nx
        from difflib import SequenceMatcher

        self._nx = nx
        self._SequenceMatcher = SequenceMatcher
        self.graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, KGNode] = {}
        self._alias_index: dict[str, str] = {}
        self._load()

    def _load(self):
        import networkx as nx
        logger.info(f"Loading NetworkX graph from {GRAPH_JSON_PATH}")
        with open(GRAPH_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for raw in data["nodes"]:
            node = KGNode(
                id=raw["id"], label=raw["label"], type=raw["type"],
                domain=raw.get("domain"), aliases=raw.get("aliases", []),
                description=raw.get("description", ""),
            )
            self._nodes[node.id] = node
            self.graph.add_node(node.id, **{
                "label": node.label, "type": node.type,
                "domain": node.domain, "description": node.description,
            })
            self._alias_index[node.label.lower()] = node.id
            for alias in node.aliases:
                self._alias_index[alias.lower()] = node.id
        for raw in data["edges"]:
            self.graph.add_edge(
                raw["source"], raw["target"],
                relation=raw["relation"],
                question_hint=raw.get("question_hint", ""),
            )
        logger.info(f"NetworkX graph loaded: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        self.build_bm25_index()
        self.build_vector_index()

    def get_node(self, node_id: str) -> KGNode | None:
        return self._nodes.get(node_id)

    def lookup_by_alias(self, text: str) -> str | None:
        return self._alias_index.get(text.strip().lower())

    def fulltext_search(self, text: str, top_k: int = 3) -> list[dict]:
        text_lower = text.lower()
        scored = []
        for alias, node_id in self._alias_index.items():
            score = self._SequenceMatcher(None, text_lower, alias).ratio()
            if score >= 0.6:
                scored.append((score, node_id))
        best: dict[str, float] = {}
        for score, nid in scored:
            if nid not in best or score > best[nid]:
                best[nid] = score
        return [
            {"node_id": nid, "label": self._nodes[nid].label,
             "type": self._nodes[nid].type, "score": s}
            for nid, s in sorted(best.items(), key=lambda x: -x[1])[:top_k]
            if nid in self._nodes
        ]

    def get_leads_to_chain(self, start_id: str, max_depth: int = 3) -> list[dict]:
        chain, current, visited = [], start_id, {start_id}
        for _ in range(max_depth):
            edges = [
                (t, d) for _, t, d in self.graph.out_edges(current, data=True)
                if d.get("relation") == "LEADS_TO" and t not in visited
            ]
            if not edges:
                break
            target, data = edges[0]
            node = self._nodes.get(target)
            if not node:
                break
            chain.append({
                "node_id": target, "label": node.label, "type": node.type,
                "description": node.description, "question_hint": data.get("question_hint", ""),
            })
            visited.add(target)
            current = target
        return chain

    def get_pitfalls(self, node_id: str, recursive: bool = True) -> list[KGNode]:
        targets = {node_id}
        if recursive:
            targets |= {
                t for _, t, d in self.graph.out_edges(node_id, data=True)
                if d.get("relation") == "HAS_COMPONENT"
            }
        pitfalls = []
        for src in targets:
            for _, t, d in self.graph.out_edges(src, data=True):
                if d.get("relation") == "HAS_PITFALL" and t in self._nodes:
                    pitfalls.append(self._nodes[t])
        return pitfalls

    def get_components(self, node_id: str) -> list[KGNode]:
        return [
            self._nodes[t]
            for _, t, d in self.graph.out_edges(node_id, data=True)
            if d.get("relation") == "HAS_COMPONENT" and t in self._nodes
        ]

    # ── Hybrid retrieval index ─────────────────────────────────────

    def _get_all_node_texts(self) -> list[tuple[str, str]]:
        return [
            (nid, node.label + " " + " ".join(node.aliases))
            for nid, node in self._nodes.items()
        ]

    def build_bm25_index(self) -> None:
        try:
            import jieba
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25/jieba not installed; BM25 index skipped")
            return
        node_texts = self._get_all_node_texts()
        self._bm25_node_ids: list[str] = [t[0] for t in node_texts]
        corpus = [list(jieba.cut(t[1])) for t in node_texts]
        self._bm25 = BM25Okapi(corpus)
        logger.info(f"BM25 index built (NetworkX): {len(self._bm25_node_ids)} nodes")

    def bm25_search(self, terms: list[str]) -> dict[str, float]:
        if not hasattr(self, "_bm25") or not terms:
            return {}
        import jieba
        query_tokens = [tok for term in terms for tok in jieba.cut(term)]
        scores = self._bm25.get_scores(query_tokens)
        return {self._bm25_node_ids[i]: float(scores[i])
                for i in range(len(self._bm25_node_ids))}

    def build_vector_index(self) -> None:
        embed = _get_embed_model()
        if embed is None:
            return
        import numpy as np
        node_texts = self._get_all_node_texts()
        self._vector_node_ids: list[str] = [t[0] for t in node_texts]
        texts = [t[1] for t in node_texts]
        self._node_matrix = embed.encode(texts, batch_size=32, show_progress_bar=False)
        logger.info(f"Vector index built (NetworkX): {len(self._vector_node_ids)} nodes")

    def vector_search(self, terms: list[str]) -> dict[str, float]:
        embed = _get_embed_model()
        if embed is None or not hasattr(self, "_node_matrix") or not terms:
            return {}
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        scores: dict[str, float] = {}
        for term in terms:
            vec = embed.encode(term).reshape(1, -1)
            sims = cosine_similarity(vec, self._node_matrix)[0]
            for i, nid in enumerate(self._vector_node_ids):
                scores[nid] = max(scores.get(nid, 0.0), float(sims[i]))
        return scores

    def create_resume_project(self, *args, **kwargs):
        logger.warning("NetworkX backend: ResumeProject not persisted (in-memory only)")

    def delete_session_nodes(self, session_id: str) -> int:
        return 0  # NetworkX backend: nothing to delete


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def get_knowledge_graph() -> Neo4jKnowledgeGraph | NetworkXKnowledgeGraph:
    """
    Return singleton based on GRAPH_BACKEND env var.
    Neo4j is the primary backend; NetworkX is the fallback.
    """
    if settings.graph_backend == "neo4j":
        try:
            kg = Neo4jKnowledgeGraph()
            kg._driver.verify_connectivity()
            return kg
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}), falling back to NetworkX")
    return NetworkXKnowledgeGraph()
