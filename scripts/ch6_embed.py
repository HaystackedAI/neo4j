"""Ch6: create embeddings for patent summaries, store in Neo4j.

    uv run scripts/ch6_embed.py

Fetches the 219 summaries written by ch6_summarize.py, generates embeddings
via Bedrock Titan Embed, and stores them as Document.embedding property.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from graphbook.bedrock import get_client
from graphbook.config import get_settings
from graphbook.db import get_driver, read, write_batched

FETCH_SUMMARIES = """
MATCH (c:Topic)<-[:IS_IN]-(d:Document)
WHERE c.name = 'Machine Learning' AND d.Summary IS NOT NULL
RETURN elementId(d) AS element_id, d.Summary AS summary
"""

STORE_EMBEDDINGS = """
UNWIND $rows AS row
MATCH (d:Document) WHERE elementId(d) = row.element_id
SET d.embedding = row.embedding
"""

MAX_WORKERS = 8


def embed_summary(doc: dict) -> dict | None:
    """Return {element_id, embedding} or None if the call failed."""
    settings = get_settings().bedrock
    body = json.dumps({
        "inputText": doc["summary"],
        "dimensions": settings.embedding_dimensions,
        "normalize": True,
    })

    try:
        response = get_client().invoke_model(
            modelId=settings.embedding_model,
            body=body,
        )
        result = json.loads(response["body"].read())
        embedding = result["embedding"]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        print(f"  {code} on {doc['element_id']}", file=sys.stderr)
        return None

    return {"element_id": doc["element_id"], "embedding": embedding}


def main() -> int:
    with get_driver() as driver:
        docs = read(driver, FETCH_SUMMARIES)
        print(f"{len(docs)} documents with summaries")
        if not docs:
            print("no summaries — run ch6_summarize.py first", file=sys.stderr)
            return 1

        print(f"embedding {len(docs)} summaries with {MAX_WORKERS} workers")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = [r for r in pool.map(embed_summary, docs) if r is not None]

        failed = len(docs) - len(results)
        if failed:
            print(f"{failed} calls failed", file=sys.stderr)
        if not results:
            return 1

        counters = write_batched(driver, STORE_EMBEDDINGS, results)
        print(f"properties_set = {counters['properties_set']}")

        if counters["properties_set"] != len(results):
            print(
                f"expected {len(results)} — some elementIds did not match",
                file=sys.stderr,
            )
            return 1

    embedding_dim = len(results[0]["embedding"])
    print(f"\nsample embedding dimension: {embedding_dim}")
    print(f"first 5 values: {results[0]['embedding'][:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
