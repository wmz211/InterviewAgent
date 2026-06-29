# RAG Evaluation

This project includes an offline RAG retrieval evaluation path. It can run in dependency-free CI mode, and it can also run with a real multilingual SentenceTransformer dense retriever when the model dependencies are available.

## What It Measures

- `Recall@K`: whether expected knowledge graph nodes appear in the top K retrieved nodes.
- `MRR@K`: how early the first relevant node appears.
- Sparse retrieval: BM25 over node id, label, aliases, and description, with English tokenization plus Chinese unigram/bigram terms.
- Dense retrieval: embedding-based retrieval through a pluggable embedding model.
- Hybrid retrieval: Reciprocal Rank Fusion over sparse and dense results.
- Graph-aware retrieval behavior: hybrid results are expanded through interview-relevant graph edges such as `HAS_COMPONENT`, `LEADS_TO`, `RELATED_TO`, and `REQUIRES`.

## Files

- `evals/rag_cases.json`: curated evaluation cases.
- `app/evals/rag_eval.py`: reusable evaluator, metrics, tokenizer, lexical baseline, and graph expansion.
- `scripts/run_rag_eval.py`: CLI entry point.
- `output/rag_eval_report.json`: generated report.

## Run

CI-friendly mode:

```bash
python scripts/run_rag_eval.py
```

Real multilingual embedding mode:

```bash
python scripts/run_rag_eval.py --dense-backend sentence-transformer --embedding-model paraphrase-multilingual-MiniLM-L12-v2
```

Latest local dependency-free baseline:

- Cases: 14
- `sparse_bm25`: `Recall@5=0.8190`, `MRR@5=1.0000`
- `dense_hashing`: `Recall@5=0.5679`, `MRR@5=0.8893`
- `hybrid_rrf`: `Recall@5=0.7238`, `MRR@5=1.0000`
- `hybrid_rrf_graph`: `Recall@5=0.8964`, `MRR@5=0.8571`

The hashing dense backend is intentionally a deterministic CI fallback, not a semantic model. A production-quality score should be reported from the SentenceTransformer backend or a Chroma-backed retriever using the same cases.

## Resume Angle

Built a bilingual RAG evaluation dataset and ablation pipeline for a GraphRAG interview agent, comparing BM25 sparse retrieval, embedding dense retrieval, RRF hybrid fusion, and graph-expanded retrieval with Recall@K/MRR@K over expected knowledge graph nodes.
