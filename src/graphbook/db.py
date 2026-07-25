"""Neo4j driver lifecycle.

The driver is a connection *pool*, not a connection: build one per process,
share it, close it on shutdown.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from neo4j import Driver, GraphDatabase, RoutingControl

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
