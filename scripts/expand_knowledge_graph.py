"""
LLM-assisted knowledge graph expansion script.

Usage:
    python scripts/expand_knowledge_graph.py --topic "Kubernetes" --domain "domain_dist"
    python scripts/expand_knowledge_graph.py --topic "MySQL事务" --domain "domain_db"

The script:
  1. Asks the LLM to generate new nodes + edges
  2. Shows the generated JSON for review
  3. On confirmation: merges into tech_knowledge_graph.json AND syncs to Neo4j
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parents[1]))

from openai import OpenAI

from app.config import get_settings

settings = get_settings()
GRAPH_PATH = Path("data/tech_knowledge_graph.json")

_EXPAND_PROMPT = """
你是一个技术知识图谱构建专家。请为技术主题「{topic}」生成知识图谱节点和边，
严格遵守以下JSON Schema，输出可直接解析的JSON（不要任何解释或markdown代码块）。

已有的节点类型(type): Domain | Tech | Concept | Component | Pitfall
已有的边类型(relation): BELONGS_TO | HAS_COMPONENT | LEADS_TO | HAS_PITFALL | REQUIRES | RELATED_TO

边中的 LEADS_TO 代表面试追问的递进路径，必须形成线性链（A→B→C），
question_hint 是面试官在追问时说的话（口语化，15-40字）。

请生成：
- 1个主Tech节点（{topic}）
- 3-5个相关的Concept/Component节点
- 2-4个Pitfall节点（常见踩坑点）
- 完整的边（包含 LEADS_TO 追问链）

所属 domain: {domain}

输出格式（纯JSON，不含注释）：
{{
  "nodes": [...],
  "edges": [...]
}}
"""


def expand_topic(topic: str, domain: str) -> dict:
    client = OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
    )
    response = client.chat.completions.create(
        model=settings.llm_model_name,
        messages=[{"role": "user", "content": _EXPAND_PROMPT.format(topic=topic, domain=domain)}],
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown code block if present
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")]

    return json.loads(raw)


def merge_into_graph(new_data: dict, graph_path: Path = GRAPH_PATH) -> None:
    with open(graph_path, encoding="utf-8") as f:
        existing = json.load(f)

    existing_node_ids = {n["id"] for n in existing["nodes"]}
    existing_edges = {(e["source"], e["target"], e["relation"]) for e in existing["edges"]}

    added_nodes, added_edges = 0, 0

    for node in new_data.get("nodes", []):
        if node["id"] not in existing_node_ids:
            existing["nodes"].append(node)
            existing_node_ids.add(node["id"])
            added_nodes += 1

    for edge in new_data.get("edges", []):
        key = (edge["source"], edge["target"], edge["relation"])
        if key not in existing_edges:
            existing["edges"].append(edge)
            existing_edges.add(key)
            added_edges += 1

    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"Merged: +{added_nodes} nodes, +{added_edges} edges → {graph_path}")


VALID_NODE_TYPES = {"Domain", "Tech", "Concept", "Component", "Pitfall"}
VALID_RELATIONS  = {"BELONGS_TO", "HAS_COMPONENT", "LEADS_TO", "HAS_PITFALL", "REQUIRES", "RELATED_TO"}


def sync_to_neo4j(new_data: dict) -> None:
    """Sync new nodes and edges into Neo4j using MERGE (idempotent)."""
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[warn] neo4j package not installed, skipping Neo4j sync.")
        return

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"[warn] Neo4j unavailable ({e}), skipping sync.")
        driver.close()
        return

    added_nodes = added_edges = 0
    with driver.session(database=settings.neo4j_database) as s:
        for node in new_data.get("nodes", []):
            node_type = node.get("type", "Tech")
            if node_type not in VALID_NODE_TYPES:
                continue
            aliases = node.get("aliases", [])
            # node_type validated against VALID_NODE_TYPES — safe to embed in Cypher
            cypher_node = f"MERGE (n:{node_type} {{id: $id}}) SET n.label=$label, n.domain=$domain, n.aliases=$aliases, n.aliases_text=$aliases_text, n.description=$description"  # type: ignore[assignment]
            s.run(cypher_node, id=node["id"], label=node["label"],  # type: ignore[arg-type]
                  domain=node.get("domain", ""), aliases=aliases,
                  aliases_text=" ".join(aliases), description=node.get("description", ""))
            added_nodes += 1

        for edge in new_data.get("edges", []):
            relation = edge.get("relation", "")
            if relation not in VALID_RELATIONS:
                continue
            # relation validated against VALID_RELATIONS — safe to embed in Cypher
            cypher_edge = f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) MERGE (a)-[r:{relation}]->(b) SET r.question_hint=$hint"  # type: ignore[assignment]
            s.run(cypher_edge, src=edge["source"], tgt=edge["target"], hint=edge.get("question_hint", ""))  # type: ignore[arg-type]
            added_edges += 1

    driver.close()
    print(f"Neo4j synced: +{added_nodes} nodes, +{added_edges} edges")


def main():
    parser = argparse.ArgumentParser(description="Expand tech_knowledge_graph.json via LLM")
    parser.add_argument("--topic", required=True, help="Technology topic to expand, e.g. 'Kubernetes'")
    parser.add_argument("--domain", default="domain_dist",
                        help="Target domain node id (default: domain_dist)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print generated JSON without merging")
    args = parser.parse_args()

    print(f"Generating knowledge graph nodes for: {args.topic} ...")
    new_data = expand_topic(args.topic, args.domain)

    print("\n── Generated JSON ──────────────────────────────────────")
    print(json.dumps(new_data, ensure_ascii=False, indent=2))
    print("────────────────────────────────────────────────────────\n")

    if args.dry_run:
        print("[dry-run] Skipping merge.")
        return

    confirm = input("Merge into tech_knowledge_graph.json and sync Neo4j? [y/N] ").strip().lower()
    if confirm == "y":
        merge_into_graph(new_data)
        sync_to_neo4j(new_data)
    else:
        print("Aborted.")


if __name__ == "__main__":
    main()
