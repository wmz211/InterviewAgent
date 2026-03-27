"""
One-time script: import tech_knowledge_graph.json → Neo4j.

Run from project root AFTER Neo4j container is healthy:
    python scripts/init_neo4j.py

What this does:
  1. Creates uniqueness constraints + indexes for fast lookup
  2. MERGEs all nodes with correct labels (Tech/Concept/Component/Pitfall/Domain)
  3. MERGEs all edges with relation type + question_hint property
  4. Prints import summary

Safe to re-run: MERGE is idempotent.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable
from loguru import logger

from app.config import get_settings

settings = get_settings()
GRAPH_JSON = Path(__file__).parents[1] / "data" / "tech_knowledge_graph.json"

# ── Valid types from our schema ────────────────────────────────────
VALID_NODE_TYPES = {"Domain", "Tech", "Concept", "Component", "Pitfall"}
VALID_RELATIONS  = {"BELONGS_TO", "HAS_COMPONENT", "LEADS_TO", "HAS_PITFALL", "REQUIRES", "RELATED_TO"}


def wait_for_neo4j(driver, max_retries: int = 20) -> None:
    """Poll until Neo4j accepts connections."""
    for i in range(max_retries):
        try:
            driver.verify_connectivity()
            logger.info("Neo4j connection established.")
            return
        except ServiceUnavailable:
            logger.info(f"Waiting for Neo4j... ({i+1}/{max_retries})")
            time.sleep(3)
    raise RuntimeError("Neo4j did not become available in time.")


def create_schema(session) -> None:
    """Uniqueness constraints + indexes. Safe to run multiple times."""
    logger.info("Creating schema constraints and indexes...")

    for label in VALID_NODE_TYPES:
        # Uniqueness constraint on id
        session.run(f"""
            CREATE CONSTRAINT {label.lower()}_id_unique IF NOT EXISTS
            FOR (n:{label}) REQUIRE n.id IS UNIQUE
        """)

    # Composite index for alias lookups across all node types
    session.run("""
        CREATE INDEX node_label_idx IF NOT EXISTS
        FOR (n:Tech) ON (n.label)
    """)

    # Full-text index for fuzzy alias search (used by lookup_tech_node)
    session.run("""
        CREATE FULLTEXT INDEX alias_fulltext IF NOT EXISTS
        FOR (n:Tech|Concept|Component|Pitfall)
        ON EACH [n.label, n.aliases_text]
    """)

    logger.info("Schema ready.")


def import_nodes(session, nodes: list[dict]) -> int:
    count = 0
    for node in nodes:
        node_type = node["type"]
        if node_type not in VALID_NODE_TYPES:
            logger.warning(f"Skipping unknown node type: {node_type}")
            continue

        aliases = node.get("aliases", [])
        # Store aliases as both list and space-joined string for full-text index
        aliases_text = " ".join(aliases)

        # Label cannot be parameterized in Cypher — safe to use f-string
        # since node_type is validated against VALID_NODE_TYPES above.
        session.run(
            f"""
            MERGE (n:{node_type} {{id: $id}})
            SET n.label       = $label,
                n.domain      = $domain,
                n.aliases     = $aliases,
                n.aliases_text = $aliases_text,
                n.description = $description
            """,
            id=node["id"],
            label=node["label"],
            domain=node.get("domain", ""),
            aliases=aliases,
            aliases_text=aliases_text,
            description=node.get("description", ""),
        )
        count += 1
    return count


def import_edges(session, edges: list[dict]) -> int:
    count = 0
    for edge in edges:
        relation = edge["relation"]
        if relation not in VALID_RELATIONS:
            logger.warning(f"Skipping unknown relation: {relation}")
            continue

        # Relation type also cannot be parameterized — validated above.
        session.run(
            f"""
            MATCH (a {{id: $source}})
            MATCH (b {{id: $target}})
            MERGE (a)-[r:{relation}]->(b)
            SET r.question_hint = $question_hint
            """,
            source=edge["source"],
            target=edge["target"],
            question_hint=edge.get("question_hint", ""),
        )
        count += 1
    return count


def verify_import(session) -> dict:
    result = session.run("""
        MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt
        ORDER BY label
    """)
    node_counts = {r["label"]: r["cnt"] for r in result}

    result = session.run("""
        MATCH ()-[r]->() RETURN type(r) as rel, count(r) as cnt
        ORDER BY rel
    """)
    edge_counts = {r["rel"]: r["cnt"] for r in result}

    return {"nodes": node_counts, "edges": edge_counts}


def main():
    logger.info(f"Connecting to Neo4j at {settings.neo4j_uri}")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )

    wait_for_neo4j(driver)

    with open(GRAPH_JSON, encoding="utf-8") as f:
        graph_data = json.load(f)

    nodes = graph_data["nodes"]
    edges = graph_data["edges"]
    logger.info(f"Loaded {len(nodes)} nodes, {len(edges)} edges from JSON")

    with driver.session(database=settings.neo4j_database) as session:
        create_schema(session)

        logger.info("Importing nodes...")
        n_nodes = import_nodes(session, nodes)
        logger.info(f"  Imported {n_nodes} nodes")

        logger.info("Importing edges...")
        n_edges = import_edges(session, edges)
        logger.info(f"  Imported {n_edges} edges")

        logger.info("Verifying...")
        summary = verify_import(session)

    driver.close()

    print("\n── Import Summary ───────────────────────────────")
    print("Nodes:")
    for label, cnt in summary["nodes"].items():
        print(f"  {label:12s}: {cnt}")
    print("Edges:")
    for rel, cnt in summary["edges"].items():
        print(f"  {rel:20s}: {cnt}")
    print("────────────────────────────────────────────────")
    print("\nNeo4j Browser: http://localhost:7474")
    print("Login: neo4j / interviewagent123")
    print("\nTry this Cypher to explore the interview graph:")
    print("  MATCH (t:Tech)-[:LEADS_TO*1..3]->(c) RETURN t,c LIMIT 50")


if __name__ == "__main__":
    main()
