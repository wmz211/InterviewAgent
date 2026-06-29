"""Generate RAG eval cases from real knowledge-graph nodes and edges."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = PROJECT_ROOT / "data" / "tech_knowledge_graph.json"
CASES_PATH = PROJECT_ROOT / "evals" / "rag_cases.json"

CASE_RELATIONS = {"HAS_COMPONENT", "LEADS_TO", "RELATED_TO", "REQUIRES"}
MAX_CASES = 48


def first_alias(node: dict, fallback: str = "") -> str:
    aliases = node.get("aliases") or []
    return str(aliases[0]) if aliases else fallback


def short_description(node: dict) -> str:
    description = str(node.get("description", "")).strip()
    if len(description) <= 60:
        return description
    return description[:60]


def build_query(source: dict, target: dict, relation: str, index: int) -> tuple[str, str]:
    source_label = str(source.get("label", source["id"]))
    target_label = str(target.get("label", target["id"]))
    source_alias = first_alias(source, source_label)
    target_alias = first_alias(target, target_label)
    source_desc = short_description(source)
    target_desc = short_description(target)

    if index % 3 == 0:
        return (
            "zh",
            f"请围绕{source_label}继续追问{target_label}，关注{source_alias}、{target_alias}以及{target_desc}",
        )
    if index % 3 == 1:
        return (
            "en",
            f"Interview follow-up from {source_label} to {target_label}: {source_alias}, {target_alias}, {source_desc}",
        )
    return (
        "mixed",
        f"{source_label} 面试追问到 {target_label}: explain {source_alias}, {target_alias}, {target_desc}",
    )


def main() -> int:
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = {str(node["id"]): node for node in graph["nodes"]}
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in graph["edges"]:
        if edge["relation"] not in CASE_RELATIONS:
            continue
        source = str(edge["source"])
        target = str(edge["target"])
        if source in nodes and target in nodes:
            outgoing[source].append(target)
            incoming[target].append(source)

    cases = []
    selected_edges = [
        edge
        for edge in graph["edges"]
        if edge["relation"] in CASE_RELATIONS
        and edge["source"] in nodes
        and edge["target"] in nodes
        and nodes[edge["source"]].get("type") != "Domain"
        and nodes[edge["target"]].get("type") != "Domain"
    ]
    for index, edge in enumerate(selected_edges[:MAX_CASES]):
        source_id = str(edge["source"])
        target_id = str(edge["target"])
        language, query = build_query(nodes[source_id], nodes[target_id], edge["relation"], index)
        expected = [source_id, target_id]
        expected.extend(outgoing.get(target_id, [])[:2])
        expected.extend(incoming.get(source_id, [])[:1])

        deduped_expected = []
        for node_id in expected:
            if node_id not in deduped_expected:
                deduped_expected.append(node_id)

        cases.append(
            {
                "id": f"kg_{index + 1:03d}_{edge['relation'].lower()}_{source_id}_to_{target_id}",
                "language": language,
                "source_node_id": source_id,
                "target_node_id": target_id,
                "relation": edge["relation"],
                "query": query,
                "expected_node_ids": deduped_expected[:5],
            }
        )

    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(cases)} eval cases from {GRAPH_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {CASES_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
