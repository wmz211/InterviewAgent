from __future__ import annotations

import unittest

from app.evals.rag_eval import (
    DenseRetriever,
    GraphExpansionRetriever,
    HybridRetriever,
    SparseBM25Retriever,
    build_graph_index,
    evaluate_ablation,
    evaluate_cases,
    mean_reciprocal_rank_at_k,
    recall_at_k,
    retrieve,
)


MINI_GRAPH = {
    "nodes": [
        {
            "id": "rag",
            "label": "RAG",
            "type": "Tech",
            "aliases": ["retrieval augmented generation"],
            "description": "External knowledge retrieval for LLM generation.",
        },
        {
            "id": "vector_retrieval",
            "label": "Vector Retrieval",
            "type": "Component",
            "aliases": ["semantic search"],
            "description": "Embedding based dense retrieval.",
        },
        {
            "id": "hybrid_search",
            "label": "Hybrid Search",
            "type": "Concept",
            "aliases": ["BM25 vector fusion"],
            "description": "Combines sparse keyword search and vector retrieval.",
        },
        {
            "id": "tool_calling",
            "label": "Tool Calling",
            "type": "Concept",
            "aliases": ["function calling"],
            "description": "Agent chooses external tools with schemas.",
        },
    ],
    "edges": [
        {"source": "rag", "target": "vector_retrieval", "relation": "HAS_COMPONENT"},
        {"source": "vector_retrieval", "target": "hybrid_search", "relation": "LEADS_TO"},
    ],
}


class RagEvalTests(unittest.TestCase):
    def test_tokenizer_supports_chinese_and_english_queries(self) -> None:
        index = build_graph_index(MINI_GRAPH)
        sparse = SparseBM25Retriever(index)

        results = sparse.retrieve("请考察 RAG 检索增强生成 和 hybrid search", top_k=3)

        self.assertIn("rag", [result.node_id for result in results])
        self.assertIn("hybrid_search", [result.node_id for result in results])

    def test_metrics_score_expected_ids(self) -> None:
        ranked_ids = ["rag", "vector_retrieval", "hybrid_search"]
        expected_ids = ["hybrid_search", "reranking"]

        self.assertEqual(recall_at_k(ranked_ids, expected_ids, k=3), 0.5)
        self.assertAlmostEqual(
            mean_reciprocal_rank_at_k(ranked_ids, expected_ids, k=3),
            1 / 3,
        )

    def test_retrieve_ranks_matching_node_first(self) -> None:
        index = build_graph_index(MINI_GRAPH)

        results = retrieve("RAG retrieval augmented generation", index, top_k=3)

        self.assertEqual(results[0].node_id, "rag")

    def test_graph_expansion_recovers_connected_follow_up_topic(self) -> None:
        index = build_graph_index(MINI_GRAPH)

        lexical = retrieve("RAG retrieval augmented generation", index, top_k=3, expand_graph=False)
        expanded = retrieve("RAG retrieval augmented generation", index, top_k=3, expand_graph=True)

        self.assertNotIn("hybrid_search", [result.node_id for result in lexical[:2]])
        self.assertIn("hybrid_search", [result.node_id for result in expanded])

    def test_evaluate_cases_returns_summary_and_per_case_rows(self) -> None:
        index = build_graph_index(MINI_GRAPH)
        cases = [
            {
                "id": "rag_case",
                "query": "RAG retrieval augmented generation",
                "expected_node_ids": ["rag", "vector_retrieval"],
            }
        ]

        report = evaluate_cases(cases, index, top_k=3)

        self.assertEqual(report["case_count"], 1)
        self.assertGreaterEqual(report["recall_at_3"], 0.5)
        self.assertEqual(report["cases"][0]["case_id"], "rag_case")
        self.assertIn("rag", report["cases"][0]["retrieved_node_ids"])

    def test_hybrid_retriever_fuses_sparse_and_dense_results(self) -> None:
        index = build_graph_index(MINI_GRAPH)
        sparse = SparseBM25Retriever(index)

        class FakeEmbeddingModel:
            name = "fake"

            def embed_documents(self, texts):
                return [[1.0, 0.0] if "Tool Calling" in text else [0.0, 1.0] for text in texts]

            def embed_query(self, text):
                return [1.0, 0.0]

        dense = DenseRetriever(index, FakeEmbeddingModel())
        hybrid = HybridRetriever({"sparse": sparse, "dense": dense})

        results = hybrid.retrieve("RAG retrieval augmented generation tool schema", top_k=4)
        result_ids = [result.node_id for result in results]

        self.assertIn("rag", result_ids)
        self.assertIn("tool_calling", result_ids)

    def test_evaluate_ablation_compares_multiple_strategies(self) -> None:
        index = build_graph_index(MINI_GRAPH)
        sparse = SparseBM25Retriever(index)
        graph_sparse = GraphExpansionRetriever(index, sparse)
        cases = [
            {
                "id": "rag_case",
                "query": "RAG retrieval augmented generation",
                "expected_node_ids": ["rag", "vector_retrieval", "hybrid_search"],
            }
        ]

        report = evaluate_ablation(
            cases,
            {
                "sparse": sparse,
                "sparse_graph": graph_sparse,
            },
            top_k=3,
        )

        self.assertEqual(report["case_count"], 1)
        self.assertIn("sparse", report["strategies"])
        self.assertIn("sparse_graph", report["strategies"])
        self.assertGreaterEqual(
            report["strategies"]["sparse_graph"]["recall_at_3"],
            report["strategies"]["sparse"]["recall_at_3"],
        )


if __name__ == "__main__":
    unittest.main()
