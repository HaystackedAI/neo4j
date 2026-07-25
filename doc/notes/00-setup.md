# Section 0 — Setup

Status: **done** (2026-07-25)

## What we built

```
B:\neo4j\
├── .env                       # real credentials (gitignored)
├── .env.example               # committed template
├── pyproject.toml             # project name "neo4jj", hatchling build, src layout
├── scripts\
│   └── check_connection.py    # smoke test
└── src\graphbook\
    ├── __init__.py
    ├── config.py              # pydantic-settings
    └── db.py                  # driver lifecycle + read helper
```

## Environment

- **Package manager:** `uv`. Deps: `neo4j>=6.2.0`, `pydantic-settings>=2.14.2`.
  Run everything as `uv run scripts/<file>.py` — never activate the venv by hand.
- **Database:** Neo4j **AuraDB Free** (console.neo4j.com). ~200k nodes / 400k rels,
  auto-pauses after 3 idle days. Credentials are shown **once** at creation.
- Server reported by `dbms.components()`: **Neo4j Kernel 5.27-aura (enterprise)**,
  **Cypher 5**.

### Gotchas hit

| Problem | Cause | Fix |
|---|---|---|
| `uv add neo4j` refused | `pyproject.toml` had `name = "neo4j"` — a package can't depend on itself | renamed project to `neo4jj` |
| `database=6b5c38f0` in output | pasted the Aura **instance ID** into `NEO4J_DATABASE` | on Aura Free the database is always literally `neo4j` |

- Directory `B:\neo4j` is harmless — Python puts the *script's* dir on `sys.path`,
  not its parent. But never create a `neo4j.py` file or `neo4j/` package inside the
  project; that *would* shadow the driver. Hence the package is named `graphbook`.

## Design decisions

**`src/` layout + `[build-system]`.** Adding hatchling makes this an installable
package, so `uv sync` installs it editable and `from graphbook.config import ...`
resolves from anywhere. Without it uv treats the project as a bare application and
the import only works from the repo root.

**Nested `BaseSettings` with `env_prefix`.** `Neo4jSettings` prefixes every field
with `NEO4J_`, so the field is just `uri` but reads `NEO4J_URI`. Later chapters bolt
on a sibling `BedrockSettings` without field-name collisions.

**`get_settings()` + `lru_cache` instead of a module-level `settings = Settings()`.**
A module-level instance validates at *import* time, so merely importing the package
explodes when `.env` is absent — breaks tests and CI. The cached function defers
validation to first use and is still a true singleton
(`get_settings.cache_clear()` resets it in tests).

**`SecretStr` for the password.** Renders as `**********` in reprs and tracebacks;
unwrap with `.get_secret_value()` at the call site only.

**`extra="ignore"`.** Aura's downloaded credentials file also defines
`AURA_INSTANCEID` / `AURA_INSTANCENAME`; without this they'd raise a validation error.

## Driver facts (book is stale here)

The driver is a **connection pool**, not a connection — build one per process, share
it, close it on shutdown. `get_driver()` is a context manager that also calls
`verify_connectivity()` so bad credentials fail immediately with a clear error
instead of timing out inside the first query.

**`execute_query()` vs the book.** The 2024 book teaches:

```python
with driver.session() as session:
    result = session.run(...)
```

Still valid, but since driver 5.8 `driver.execute_query()` is the recommended default
for one-off queries: it opens the session, wraps the call in a **managed transaction
that retries on transient errors** (leader switch, network blip — real on Aura), and
eagerly consumes the result. Returns an `EagerResult` named tuple:
`(records, summary, keys)`. Sessions are now the low-level escape hatch (needed for
explicit multi-query transactions and result streaming).

**Trailing underscores** (`database_`, `routing_`, `parameters_`) exist because every
kwarg *without* one is treated as a Cypher parameter. Prefer passing params through
the explicit `parameters_` dict — loose kwargs work but a param named `database` would
silently collide with a driver option.

**`routing_=RoutingControl.READ`** lets Aura route the query to a read replica.
Habit worth forming even when it doesn't yet matter.

## Cypher

Always parameterize: `RETURN $greeting AS msg` with `greeting="..."`. Never
string-format values into Cypher — same injection risk as SQL, and parameters let the
server cache the query plan.

## Verified output

```
connecting to neo4j+s://6b5c38f0.databases.neo4j.io (database=neo4j)
hello from aura
Neo4j Kernel 5.27-aura (enterprise)
Cypher 5 ()
```

## Version notes for later chapters

Aura Free runs 5.27, *behind* the calendar-versioned 2025.x releases. So deprecations
that landed upstream are **not yet live** on this instance — the book's 5.x syntax
mostly works as printed:

- Vector index: `db.index.vector.queryNodes` still current here (upstream 2026.04
  replaces it with a `SEARCH` clause).
- In-DB embeddings: `genai.vector.encode` still current here (upstream → `ai.text.embed`).
- But **do** use `CREATE VECTOR INDEX ... OPTIONS {...}`, not the old
  `db.index.vector.createNodeIndex` procedure — that one is already dead in 5.27.

Aura is Enterprise-edition kernel even on Free, so constraint types the book calls
Enterprise-only (node key, property existence) are available.

## Next

Chapter 2 — Cypher basics and graph data modeling.
