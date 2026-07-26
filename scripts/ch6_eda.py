"""Ch6, p.103: exploratory analysis of the patents graph.

Book expects 39,270 Documents, and "medical devices" as the top topic with
390 documents.

    uv run scripts/ch6_eda.py
"""

from graphbook.db import get_driver, read

DOCUMENT_COUNT = "MATCH (a:Document) RETURN count(a) AS Number_Documents"

TOP_TOPICS = """
MATCH (a:Topic)<-[:IS_IN]-(b:Document)
RETURN a.name AS Topic_Name, count(b) AS topic_count
ORDER BY topic_count DESC
LIMIT 5
"""

TOP_ASSIGNEES = """
MATCH (a:Document)-[:ASSIGNED_TO]->(b:Assignee)
RETURN b.name AS Assignee_Name, count(a) AS document_count
ORDER BY document_count DESC
LIMIT 5
"""

# Not in the book, but the first thing worth knowing about an unfamiliar
# graph: Neo4j has no declared schema, so this samples what is actually
# stored rather than reading a catalog.
LABEL_COUNTS = """
MATCH (n)
UNWIND labels(n) AS label
RETURN label, count(*) AS node_count
ORDER BY node_count DESC
"""

REL_TYPE_COUNTS = """
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(*) AS rel_count
ORDER BY rel_count DESC
"""


def show(title: str, rows: list[dict], /) -> None:
    """Print rows as an aligned table under a heading."""
    print(f"\n{title}")
    if not rows:
        print("  (no rows)")
        return
    widths = {key: max(len(key), *(len(str(r[key])) for r in rows)) for key in rows[0]}
    print("  " + "  ".join(key.ljust(widths[key]) for key in rows[0]))
    print("  " + "  ".join("-" * widths[key] for key in rows[0]))
    for row in rows:
        print("  " + "  ".join(str(row[key]).ljust(widths[key]) for key in row))


def main() -> int:
    with get_driver() as driver:
        show("Nodes per label", read(driver, LABEL_COUNTS))
        show("Relationships per type", read(driver, REL_TYPE_COUNTS))
        show("Document count", read(driver, DOCUMENT_COUNT))
        show("Top 5 topics", read(driver, TOP_TOPICS))
        show("Top 5 assignees", read(driver, TOP_ASSIGNEES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
