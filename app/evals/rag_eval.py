"""RAG retrieval evaluation with sparse, dense, hybrid, and graph variants."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence


TOKEN_RE = re.compile(r"[A-Za-z0-9_+\-]+|[\u4e00-\u9fff]+")
EXPANSION_RELATIONS = {"HAS_COMPONENT", "LEADS_TO", "RELATED_TO", "REQUIRES"}


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    node_type: str
    text: str
    order: int


@dataclass(frozen=True)
class SearchResult:
    node_id: str
    score: float
    matched_terms: tuple[str, ...]
    expanded_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphIndex:
    nodes: Mapping[str, GraphNode]
    token_counts: Mapping[str, Counter[str]]
    adjacency: Mapping[str, tuple[str, ...]]


class Retriever(Protocol):
    name: str

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        ...


class EmbeddingModel(Protocol):
    name: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_RE.findall(text.lower()):
        tokens.append(raw_token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw_token):
            tokens.extend(raw_token)
            tokens.extend(raw_token[index : index + 2] for index in range(max(len(raw_token) - 1, 0)))
        else:
            if "_" in raw_token:
                tokens.extend(part for part in raw_token.split("_") if part)
            if "-" in raw_token:
                tokens.extend(part for part in raw_token.split("-") if part)
    return tokens


def build_graph_index(graph: Mapping[str, Any]) -> GraphIndex:
    nodes: dict[str, GraphNode] = {}
    token_counts: dict[str, Counter[str]] = {}

    for order, raw_node in enumerate(graph.get("nodes", [])):
        node_id = str(raw_node["id"])
        aliases = " ".join(str(alias) for alias in raw_node.get("aliases", []))
        text = " ".join(
            str(value)
            for value in (
                raw_node.get("id", ""),
                raw_node.get("label", ""),
                aliases,
                raw_node.get("description", ""),
            )
            if value
        )
        nodes[node_id] = GraphNode(
            node_id=node_id,
            label=str(raw_node.get("label", node_id)),
            node_type=str(raw_node.get("type", "")),
            text=text,
            order=order,
        )
        token_counts[node_id] = Counter(tokenize(text))

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges", []):
        relation = str(edge.get("relation", ""))
        if relation not in EXPANSION_RELATIONS:
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source in nodes and target in nodes:
            adjacency[source].add(target)
            adjacency[target].add(source)

    frozen_adjacency = {
        node_id: tuple(sorted(neighbors, key=lambda neighbor: nodes[neighbor].order))
        for node_id, neighbors in adjacency.items()
    }
    return GraphIndex(nodes=nodes, token_counts=token_counts, adjacency=frozen_adjacency)


class SparseBM25Retriever:
    name = "sparse_bm25"

    def __init__(self, index: GraphIndex, k1: float = 1.5, b: float = 0.75) -> None:
        self.index = index
        self.k1 = k1
        self.b = b
        self.document_frequency = Counter(term for counts in index.token_counts.values() for term in counts)
        self.document_lengths = {node_id: sum(counts.values()) for node_id, counts in index.token_counts.items()}
        total_length = sum(self.document_lengths.values())
        self.average_document_length = total_length / max(len(self.document_lengths), 1)

    def score(self, query: str) -> dict[str, tuple[float, tuple[str, ...]]]:
        query_terms = Counter(tokenize(query))
        scores: dict[str, tuple[float, tuple[str, ...]]] = {}
        if not query_terms:
            return scores

        total_docs = max(len(self.index.nodes), 1)
        for node_id, counts in self.index.token_counts.items():
            matched_terms = tuple(term for term in query_terms if counts.get(term, 0) > 0)
            if not matched_terms:
                continue

            doc_length = self.document_lengths.get(node_id, 0)
            length_norm = 1 - self.b + self.b * doc_length / max(self.average_document_length, 1)
            score = 0.0
            for term in matched_terms:
                term_frequency = counts[term]
                idf = math.log((total_docs - self.document_frequency[term] + 0.5) / (self.document_frequency[term] + 0.5) + 1)
                score += idf * (term_frequency * (self.k1 + 1)) / (term_frequency + self.k1 * length_norm)

            node = self.index.nodes[node_id]
            normalized_query = query.strip().lower()
            if node.node_id.lower() in normalized_query:
                score += 4.0
            if node.label.lower() in normalized_query:
                score += 2.0
            scores[node_id] = (score, matched_terms)

        return scores

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        scores = self.score(query)
        ranked_ids = sorted(scores, key=lambda node_id: (-scores[node_id][0], self.index.nodes[node_id].order))
        return [
            SearchResult(node_id=node_id, score=round(scores[node_id][0], 6), matched_terms=scores[node_id][1])
            for node_id in ranked_ids[:top_k]
        ]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class HashingEmbeddingModel:
    """Deterministic dense fallback for CI and machines without ML models."""

    name = "hashing_embedding"

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[-1] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class DenseRetriever:
    name = "dense"

    def __init__(self, index: GraphIndex, embedding_model: EmbeddingModel | None = None) -> None:
        self.index = index
        self.embedding_model = embedding_model or HashingEmbeddingModel()
        self.name = f"dense:{self.embedding_model.name}"
        self.node_ids = sorted(index.nodes, key=lambda node_id: index.nodes[node_id].order)
        self.document_embeddings = self.embedding_model.embed_documents(
            [index.nodes[node_id].text for node_id in self.node_ids]
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_embedding = self.embedding_model.embed_query(query)
        scored = [
            (node_id, cosine_similarity(query_embedding, embedding))
            for node_id, embedding in zip(self.node_ids, self.document_embeddings)
        ]
        ranked = sorted(scored, key=lambda item: (-item[1], self.index.nodes[item[0]].order))
        return [
            SearchResult(node_id=node_id, score=round(score, 6), matched_terms=())
            for node_id, score in ranked[:top_k]
        ]


class HybridRetriever:
    name = "hybrid_rrf"

    def __init__(self, retrievers: Mapping[str, Retriever], rrf_k: int = 60) -> None:
        self.retrievers = dict(retrievers)
        self.rrf_k = rrf_k

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        fused_scores: dict[str, float] = defaultdict(float)
        matched_terms: dict[str, set[str]] = defaultdict(set)
        sources: dict[str, set[str]] = defaultdict(set)

        for source_name, retriever in self.retrievers.items():
            for rank, result in enumerate(retriever.retrieve(query, top_k=top_k * 4), start=1):
                fused_scores[result.node_id] += 1 / (self.rrf_k + rank)
                matched_terms[result.node_id].update(result.matched_terms)
                sources[result.node_id].add(source_name)

        ranked_ids = sorted(fused_scores, key=lambda node_id: (-fused_scores[node_id], node_id))
        return [
            SearchResult(
                node_id=node_id,
                score=round(fused_scores[node_id], 6),
                matched_terms=tuple(sorted(matched_terms[node_id])),
                expanded_from=tuple(sorted(sources[node_id])),
            )
            for node_id in ranked_ids[:top_k]
        ]


class GraphExpansionRetriever:
    name = "graph_expanded"

    def __init__(
        self,
        index: GraphIndex,
        base_retriever: Retriever,
        first_hop_weight: float = 0.35,
        second_hop_weight: float = 0.15,
    ) -> None:
        self.index = index
        self.base_retriever = base_retriever
        self.name = f"{base_retriever.name}_graph"
        self.first_hop_weight = first_hop_weight
        self.second_hop_weight = second_hop_weight

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        base_results = self.base_retriever.retrieve(query, top_k=top_k * 3)
        scores = {result.node_id: result.score for result in base_results}
        matched_terms = {result.node_id: set(result.matched_terms) for result in base_results}
        expanded_from: dict[str, set[str]] = defaultdict(set)

        for rank, result in enumerate(base_results, start=1):
            seed_weight = result.score / max(rank, 1)
            for neighbor_id in self.index.adjacency.get(result.node_id, ()):
                scores[neighbor_id] = scores.get(neighbor_id, 0.0) + seed_weight * self.first_hop_weight
                expanded_from[neighbor_id].add(result.node_id)
                for second_hop_id in self.index.adjacency.get(neighbor_id, ()):
                    if second_hop_id == result.node_id:
                        continue
                    scores[second_hop_id] = scores.get(second_hop_id, 0.0) + seed_weight * self.second_hop_weight
                    expanded_from[second_hop_id].add(result.node_id)

        ranked_ids = sorted(scores, key=lambda node_id: (-scores[node_id], self.index.nodes[node_id].order))
        return [
            SearchResult(
                node_id=node_id,
                score=round(scores[node_id], 6),
                matched_terms=tuple(sorted(matched_terms.get(node_id, ()))),
                expanded_from=tuple(sorted(expanded_from.get(node_id, ()))),
            )
            for node_id in ranked_ids[:top_k]
        ]


class ChromaGraphNodeRetriever:
    """Dense retriever over the real Chroma graph-node collection."""

    name = "dense_chroma_bge"

    def __init__(
        self,
        collection_name: str,
        persist_dir: str,
        valid_node_ids: Iterable[str],
        embedding_model_name: str,
    ) -> None:
        import chromadb
        from chromadb.utils import embedding_functions

        self.valid_node_ids = set(valid_node_ids)
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model_name,
            local_files_only=True,
            normalize_embeddings=True,
        )
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(
            collection_name,
            embedding_function=embedding_function,
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k * 4,
            include=["metadatas", "distances"],
        )
        output: list[SearchResult] = []
        seen: set[str] = set()
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for metadata, distance in zip(metadatas, distances):
            node_id = str((metadata or {}).get("node_id", ""))
            if not node_id or node_id in seen or node_id not in self.valid_node_ids:
                continue
            seen.add(node_id)
            output.append(
                SearchResult(
                    node_id=node_id,
                    score=round(1 - float(distance), 6),
                    matched_terms=(),
                    expanded_from=("chroma",),
                )
            )
            if len(output) >= top_k:
                break
        return output


class Neo4jGraphExpansionRetriever:
    """Graph expansion over real Neo4j relationships."""

    name = "neo4j_graph_expanded"

    def __init__(
        self,
        base_retriever: Retriever,
        uri: str,
        username: str,
        password: str,
        database: str,
        relations: Iterable[str] = EXPANSION_RELATIONS,
        first_hop_weight: float = 0.35,
        second_hop_weight: float = 0.15,
    ) -> None:
        from neo4j import GraphDatabase

        self.base_retriever = base_retriever
        self.database = database
        self.relations = tuple(relations)
        self.first_hop_weight = first_hop_weight
        self.second_hop_weight = second_hop_weight
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.driver.verify_connectivity()

    def _neighbors(self, node_ids: Sequence[str]) -> dict[str, list[str]]:
        if not node_ids:
            return {}
        with self.driver.session(database=self.database) as session:
            rows = session.run(
                """
                MATCH (n)-[r]-(m)
                WHERE n.id IN $node_ids AND type(r) IN $relations
                RETURN n.id AS source, collect(DISTINCT m.id) AS neighbors
                """,
                node_ids=list(node_ids),
                relations=list(self.relations),
            ).data()
        return {str(row["source"]): [str(value) for value in row["neighbors"] if value] for row in rows}

    def retrieve(self, query: str, top_k: int = 5) -> list[SearchResult]:
        base_results = self.base_retriever.retrieve(query, top_k=top_k * 3)
        scores = {result.node_id: result.score for result in base_results}
        matched_terms = {result.node_id: set(result.matched_terms) for result in base_results}
        expanded_from: dict[str, set[str]] = defaultdict(set)

        first_hop = self._neighbors([result.node_id for result in base_results])
        second_hop = self._neighbors(
            sorted({neighbor for neighbors in first_hop.values() for neighbor in neighbors})
        )
        for rank, result in enumerate(base_results, start=1):
            seed_weight = result.score / max(rank, 1)
            for neighbor_id in first_hop.get(result.node_id, []):
                scores[neighbor_id] = scores.get(neighbor_id, 0.0) + seed_weight * self.first_hop_weight
                expanded_from[neighbor_id].add(result.node_id)
                for second_hop_id in second_hop.get(neighbor_id, []):
                    if second_hop_id == result.node_id:
                        continue
                    scores[second_hop_id] = scores.get(second_hop_id, 0.0) + seed_weight * self.second_hop_weight
                    expanded_from[second_hop_id].add(result.node_id)

        ranked_ids = sorted(scores, key=lambda node_id: (-scores[node_id], node_id))
        return [
            SearchResult(
                node_id=node_id,
                score=round(scores[node_id], 6),
                matched_terms=tuple(sorted(matched_terms.get(node_id, ()))),
                expanded_from=tuple(sorted(expanded_from.get(node_id, ()))),
            )
            for node_id in ranked_ids[:top_k]
        ]


def recall_at_k(ranked_ids: Sequence[str], expected_ids: Iterable[str], k: int) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0
    retrieved = set(ranked_ids[:k])
    return len(expected & retrieved) / len(expected)


def mean_reciprocal_rank_at_k(
    ranked_ids: Sequence[str],
    expected_ids: Iterable[str],
    k: int,
) -> float:
    expected = set(expected_ids)
    for rank, node_id in enumerate(ranked_ids[:k], start=1):
        if node_id in expected:
            return 1 / rank
    return 0.0


def evaluate_retriever_cases(
    cases: Sequence[Mapping[str, Any]],
    retriever: Retriever,
    top_k: int = 5,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    recall_scores: list[float] = []
    mrr_scores: list[float] = []

    for case in cases:
        expected_ids = [str(node_id) for node_id in case.get("expected_node_ids", [])]
        results = retriever.retrieve(str(case["query"]), top_k=top_k)
        ranked_ids = [result.node_id for result in results]
        recall = recall_at_k(ranked_ids, expected_ids, top_k)
        mrr = mean_reciprocal_rank_at_k(ranked_ids, expected_ids, top_k)
        recall_scores.append(recall)
        mrr_scores.append(mrr)
        rows.append(
            {
                "case_id": case.get("id", ""),
                "language": case.get("language", "unknown"),
                "query": case["query"],
                "expected_node_ids": expected_ids,
                "retrieved_node_ids": ranked_ids,
                f"recall_at_{top_k}": round(recall, 4),
                f"mrr_at_{top_k}": round(mrr, 4),
                "results": [
                    {
                        "node_id": result.node_id,
                        "score": result.score,
                        "matched_terms": list(result.matched_terms),
                        "expanded_from": list(result.expanded_from),
                    }
                    for result in results
                ],
            }
        )

    case_count = len(cases)
    return {
        "case_count": case_count,
        f"recall_at_{top_k}": round(sum(recall_scores) / case_count, 4) if case_count else 0.0,
        f"mrr_at_{top_k}": round(sum(mrr_scores) / case_count, 4) if case_count else 0.0,
        "cases": rows,
    }


def evaluate_ablation(
    cases: Sequence[Mapping[str, Any]],
    retrievers: Mapping[str, Retriever],
    top_k: int = 5,
) -> dict[str, Any]:
    return {
        "case_count": len(cases),
        "top_k": top_k,
        "strategies": {
            name: evaluate_retriever_cases(cases, retriever, top_k=top_k)
            for name, retriever in retrievers.items()
        },
    }


def lexical_scores(query: str, index: GraphIndex) -> dict[str, tuple[float, tuple[str, ...]]]:
    return SparseBM25Retriever(index).score(query)


def retrieve(
    query: str,
    index: GraphIndex,
    top_k: int = 5,
    expand_graph: bool = True,
) -> list[SearchResult]:
    retriever: Retriever = SparseBM25Retriever(index)
    if expand_graph:
        retriever = GraphExpansionRetriever(index, retriever)
    return retriever.retrieve(query, top_k=top_k)


def evaluate_cases(
    cases: Sequence[Mapping[str, Any]],
    index: GraphIndex,
    top_k: int = 5,
) -> dict[str, Any]:
    return evaluate_retriever_cases(cases, GraphExpansionRetriever(index, SparseBM25Retriever(index)), top_k=top_k)


def build_default_retrievers(index: GraphIndex) -> dict[str, Retriever]:
    sparse = SparseBM25Retriever(index)
    dense = DenseRetriever(index)
    hybrid = HybridRetriever({"sparse": sparse, "dense": dense})
    return {
        "sparse_bm25": sparse,
        "dense_hashing": dense,
        "hybrid_rrf": hybrid,
        "hybrid_rrf_graph": GraphExpansionRetriever(index, hybrid),
    }


def build_sentence_transformer_retrievers(index: GraphIndex, model_name: str) -> dict[str, Retriever]:
    from sentence_transformers import SentenceTransformer

    class SentenceTransformerEmbeddingModel:
        name = f"sentence_transformer:{model_name}"

        def __init__(self) -> None:
            self.model = SentenceTransformer(model_name)

        def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
            return self.model.encode(list(texts), normalize_embeddings=True).tolist()

        def embed_query(self, text: str) -> list[float]:
            return self.model.encode([text], normalize_embeddings=True)[0].tolist()

    sparse = SparseBM25Retriever(index)
    dense = DenseRetriever(index, SentenceTransformerEmbeddingModel())
    hybrid = HybridRetriever({"sparse": sparse, "dense": dense})
    return {
        "sparse_bm25": sparse,
        "dense_sentence_transformer": dense,
        "hybrid_rrf": hybrid,
        "hybrid_rrf_graph": GraphExpansionRetriever(index, hybrid),
    }


def build_chroma_neo4j_retrievers(
    index: GraphIndex,
    chroma_collection_name: str,
    chroma_persist_dir: str,
    chroma_embedding_model_name: str,
    neo4j_uri: str = "",
    neo4j_username: str = "",
    neo4j_password: str = "",
    neo4j_database: str = "",
) -> tuple[dict[str, Retriever], dict[str, str]]:
    sparse = SparseBM25Retriever(index)
    retrievers: dict[str, Retriever] = {"sparse_bm25": sparse}
    status: dict[str, str] = {}

    try:
        dense = ChromaGraphNodeRetriever(
            collection_name=chroma_collection_name,
            persist_dir=chroma_persist_dir,
            valid_node_ids=index.nodes.keys(),
            embedding_model_name=chroma_embedding_model_name,
        )
        retrievers["dense_chroma_bge"] = dense
        hybrid = HybridRetriever({"sparse": sparse, "dense": dense})
        retrievers["hybrid_rrf"] = hybrid
        status["chroma"] = "ok"
    except Exception as exc:
        hybrid = HybridRetriever({"sparse": sparse})
        retrievers["hybrid_rrf"] = hybrid
        status["chroma"] = f"unavailable: {exc}"

    try:
        if not all([neo4j_uri, neo4j_username, neo4j_password, neo4j_database]):
            raise ValueError("Neo4j settings are incomplete")
        retrievers["hybrid_rrf_neo4j_graph"] = Neo4jGraphExpansionRetriever(
            base_retriever=hybrid,
            uri=neo4j_uri,
            username=neo4j_username,
            password=neo4j_password,
            database=neo4j_database,
        )
        status["neo4j"] = "ok"
    except Exception as exc:
        retrievers["hybrid_rrf_json_graph"] = GraphExpansionRetriever(index, hybrid)
        status["neo4j"] = f"unavailable: {exc}"

    return retrievers, status
