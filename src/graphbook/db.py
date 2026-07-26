"""Neo4j driver lifecycle.

The driver is a connection *pool*, not a connection: build one per process,
share it, close it on shutdown.
"""

from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl, SummaryCounters

from graphbook.config import get_settings


@contextmanager
def get_driver() -> Iterator[Driver]:
    """Yield a connected driver, closing its pool on exit.

    Connectivity is verified up front so bad credentials fail here with a
    clear error instead of timing out inside the first query.
    """
    settings = get_settings().neo4j
    with GraphDatabase.driver(settings.uri, auth=settings.auth) as driver:
        driver.verify_connectivity()
        yield driver


def read(
    driver: Driver,
    query: str,
    /,
    **parameters: Any,
) -> list[dict[str, Any]]:
    """Run a read query in a managed transaction; return records as dicts.

    Retries automatically on transient errors (leader switch, network blip),
    which matters on Aura.
    """
    result = driver.execute_query(
        query,
        parameters_=parameters,
        database_=get_settings().neo4j.database,
        routing_=RoutingControl.READ,
    )
    return [record.data() for record in result.records]


def write(
    driver: Driver,
    query: str,
    /,
    **parameters: Any,
) -> SummaryCounters:
    """Run a write query in a managed transaction; return what it changed.

    Returns the counters (properties_set, nodes_created, ...) rather than rows,
    because that is what you want to assert on after a write.
    """
    result = driver.execute_query(
        query,
        parameters_=parameters,
        database_=get_settings().neo4j.database,
        routing_=RoutingControl.WRITE,
    )
    return result.summary.counters


def write_batched(
    driver: Driver,
    query: str,
    rows: Sequence[dict[str, Any]],
    /,
    batch_size: int = 1_000,
    **parameters: Any,
) -> Counter[str]:
    """Apply `query` once per batch, with the batch bound to `$rows`.

    `query` must start with `UNWIND $rows AS row` and use `row.<key>`. One
    round-trip and one transaction per batch, instead of one per record --
    the per-record `session.run` loop the book uses costs a full network
    round-trip and its own transaction commit for every single update.

    Batching rather than one giant `$rows` keeps each transaction's memory
    bounded; a failed batch rolls back alone, so partial progress survives.
    Counters are summed across batches.
    """
    totals: Counter[str] = Counter()
    for start in range(0, len(rows), batch_size):
        counters = write(
            driver,
            query,
            rows=rows[start : start + batch_size],
            **parameters,
        )
        totals.update(
            {
                name: value
                for name, value in vars(counters).items()
                if isinstance(value, int)
            }
        )
    return totals
