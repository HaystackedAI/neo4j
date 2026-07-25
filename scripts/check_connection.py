"""Smoke test: prove we can reach Aura and run Cypher.

    uv run scripts/check_connection.py
"""

import sys

from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

from graphbook.config import get_settings
from graphbook.db import get_driver, read


def main() -> int:
    settings = get_settings().neo4j
    print(f"connecting to {settings.uri} (database={settings.database})")

    try:
        with get_driver() as driver:
            rows = read(driver, "RETURN $greeting AS msg", greeting="hello from aura")
            print(rows[0]["msg"])

            components = read(
                driver,
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN name, versions[0] AS version, edition",
            )
            for row in components:
                print(f"{row['name']} {row['version']} ({row['edition']})")
    except AuthError:
        print("auth failed — check NEO4J_USERNAME / NEO4J_PASSWORD", file=sys.stderr)
        return 1
    except ServiceUnavailable:
        print(
            "cannot reach the instance — check NEO4J_URI, and that the Aura "
            "instance is Running (free instances pause after 3 idle days)",
            file=sys.stderr,
        )
        return 1
    except Neo4jError as exc:
        print(f"query failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
