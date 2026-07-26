"""Ch6: summarize Machine Learning patents with Bedrock, write results back.

    uv run scripts/ch6_summarize.py

The book stops at a dataframe column. We persist the summary onto the
Document node instead, so the enrichment is part of the graph and available
to later chapters.
"""

import sys
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import ClientError

from graphbook.bedrock import generate_text
from graphbook.db import get_driver, read, write_batched

ML_PATENTS = """
MATCH (c:Topic)<-[:IS_IN]-(a:Document)-[:ASSIGNED_TO]->(b:Assignee)
WHERE c.name = 'Machine Learning'
RETURN elementId(a) AS element_id
     , a.title AS title
     , b.name AS owner
     , a.abstract AS abstract
LIMIT 300
"""

# UNWIND turns the list bound to $rows into one row per element: a single
# statement and a single transaction for the whole batch.
STORE_SUMMARIES = """
UNWIND $rows AS row
MATCH (d:Document) WHERE elementId(d) = row.element_id
SET d.Summary = row.summary
"""

PROMPT = (
    "Summarize the following patent abstract in laymen's terms in fewer than "
    "100 words: {abstract}"
)

MAX_WORKERS = 8


def summarize(patent: dict) -> dict | None:
    """Return the patent with a `summary` key, or None if the call failed.

    One bad abstract should not abort 300 summaries, so failures are dropped
    and counted rather than raised.
    """
    try:
        summary = generate_text(PROMPT.format(abstract=patent["abstract"]))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        print(f"  {code} on {patent['title'][:60]!r}", file=sys.stderr)
        return None
    return {"element_id": patent["element_id"], "summary": summary}


def main() -> int:
    with get_driver() as driver:
        patents = read(driver, ML_PATENTS)
        print(f"{len(patents)} Machine Learning patents")
        if not patents:
            print(
                "no rows — check the exact Topic.name spelling in the EDA output",
                file=sys.stderr,
            )
            return 1

        missing = [p for p in patents if not p["abstract"]]
        if missing:
            print(f"{len(missing)} have no abstract, skipping those")
        todo = [p for p in patents if p["abstract"]]

        # Bedrock calls are IO-bound, so threads overlap the round-trips.
        # Serial .apply() over 300 abstracts would take minutes.
        print(f"summarizing {len(todo)} abstracts with {MAX_WORKERS} workers")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = [r for r in pool.map(summarize, todo) if r is not None]

        failed = len(todo) - len(results)
        if failed:
            print(f"{failed} calls failed", file=sys.stderr)
        if not results:
            return 1

        counters = write_batched(driver, STORE_SUMMARIES, results)
        print(f"properties_set = {counters['properties_set']}")

        # A MATCH that finds nothing is not an error in Cypher: it silently
        # sets nothing. Comparing counts is the only way to catch that.
        if counters["properties_set"] != len(results):
            print(
                f"expected {len(results)} — some elementIds did not match",
                file=sys.stderr,
            )
            return 1

    print("\nsample:")
    print(f"  {results[0]['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
