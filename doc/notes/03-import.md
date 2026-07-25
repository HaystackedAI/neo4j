# Chapter 3 — Importing Data into Neo4j

Status: **done** (2026-07-25). Chapter 2 skipped (Python primer + local install; already covered by Section 0).

Dataset: `Fake_Data_FBI_Neo4j.csv` — 19 rows of synthetic-identity fraud data. Carried
forward into Ch10.

**Done entirely in the Neo4j Browser (Aura console), no Python.** Per tool priority:
console > Cypher > CLI > Python.

## The model

```
(:Person {full_name})
   ├─[:HAS_SSN]──────→ (:SSN {ssn})
   ├─[:HAS_PHONE]────→ (:Phone {number})
   ├─[:HAS_EMAIL]────→ (:Email {address})
   ├─[:HAS_IP]───────→ (:IP {address})
   ├─[:HAS_ADDRESS]──→ (:Address {address})
   ├─[:HAS_SAR]──────→ (:SAR {report_number})       # optional
   └─[:HAS_CASE]─────→ (:FBICase {case_number})     # optional
```

Final counts: Person 19, Email 19, Phone 17, Address 17, SSN 10, IP 10, FBICase 2, SAR 1.

### Node or property? — the central modeling rule

> A value becomes a **node** when you want to traverse *to* it and find who else
> shares it. It stays a **property** when it only describes its owner.

Same instinct as normalizing in SQL, but the payoff isn't storage — it's that the join
becomes a first-class traversable thing. Email ended up 19 nodes for 19 people: shared
by no one, so as a node it earns nothing and could have stayed a property. SSN at 10
nodes for 19 people is where the value is.

## Mistake I made, and the fix

First attempt constrained `Person.ssn` UNIQUE and `MERGE`d on it. 19 rows collapsed to
**10 Person nodes** and each row's `SET` overwrote the previous one — John Doe's node
ended up holding Ava Jones' name.

Root cause: SSN is *deliberately shared* in this dataset (that's the fraud signal), so
it can never be a Person key. Shared values must be their own nodes. Fixed by
`MATCH (n) DETACH DELETE n`, dropping the constraint, and remodeling.

`DETACH DELETE` deletes a node's relationships first. Plain `DELETE` on a connected
node throws — Neo4j refuses to leave dangling relationships, unlike a SQL delete with
no FK.

## Schema first, always

The book creates constraints *after* import (cell 25). Backwards, for two reasons:

1. **Correctness.** `MERGE (:Phone {number:'555'})` = "match, else create". Without a
   uniqueness constraint, two concurrent transactions both find nothing and both
   insert → silent duplicates. The constraint is the only real guard.
2. **Speed.** A constraint auto-creates a backing index (visible as `ownedIndex` in
   `SHOW CONSTRAINTS`, same name as the constraint — never managed by hand). Without
   it every `MERGE` is a full label scan: minutes instead of milliseconds at 200k nodes.

Syntax: `REQUIRE` (5.17+), not the book's deprecated `ASSERT`.

`SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties;` — the `YIELD` keeps
Browser in Table view; without it the nested columns force the JSON view.

## MERGE is the import primitive

There is no `INSERT ... ON CONFLICT`. `MERGE` on a constrained property makes an import
**idempotent** — run it five times, same graph. The book uses `CREATE`, so re-running a
cell silently doubles the data. Most important import habit in Neo4j.

## Bugs found in the book's Chapter 3

| # | Book code | Problem |
|---|---|---|
| 1 | `WHERE p.suspicious_activity_report IS NOT NULL` | `LOAD CSV` yields `''` for empty fields, **not** `null` — `null` only for *missing columns*. So the filter never filters, and it creates a junk `(:SAR {report_number:''})` hub that every unreported person links to. Test `<> ''` instead. |
| 2 | cell 12 writes `p.FBI_case_number`, reads `p.fbi_case_number` | Cypher properties are case-sensitive → matches nothing, creates zero nodes. Normalize to lowercase on import. |
| 3 | `LOAD CSV FROM 'file:///...'` | No filesystem on Aura. Needs an HTTPS URL. |
| 4 | `CREATE` for import | Not idempotent (see above). |
| 5 | `f"""..."""` on queries with no interpolation | Pointless, and invites the injection habit. |

## Cypher learned

**No `IF` statement.** Conditional writes use `FOREACH` over a list that is either
`[1]` (once) or `[]` (never):

```cypher
FOREACH (_ IN CASE WHEN row.FBI_case_number <> '' THEN [1] ELSE [] END |
  MERGE (c:FBICase {case_number: row.FBI_case_number})
  MERGE (p)-[:HAS_CASE]->(c)
)
```

**`WITH` is the pipe** and the spine of the language: `MATCH → WITH → RETURN`. Closest
SQL analogue is a chain of CTEs, except `WITH` also **implicitly GROUP BYs** — the
non-aggregated keys in a `WITH` *are* the grouping keys. Cypher has no `GROUP BY`
keyword. `collect()` ≈ `array_agg`.

**No type inference in `LOAD CSV`** — everything is a string. Explicit
`toInteger()` / `toFloat()` required, unlike a SQL bulk loader.

**Batching.** For big files, wrap in a subquery:
```cypher
LOAD CSV WITH HEADERS FROM '...' AS row
CALL (row) { MERGE (p:Person {ssn: row.ssn}) } IN TRANSACTIONS OF 1000 ROWS;
```
Note `CALL (row) {` — the scoped-variable form (5.23+). The book's
`CALL { WITH row ... }` still parses on 5.27 but `WITH row` inside the braces is
deprecated. Needed above ~100k rows or the transaction heap blows.

**Label predicates in WHERE:** `AND NOT shared:SAR` — filtering on node type. No SQL
equivalent.

**Git LFS gotcha:** the vendored CSV is LFS-tracked, so `raw.githubusercontent.com`
won't serve it. Use `media.githubusercontent.com/media/<owner>/<repo>/refs/heads/main/...`.

## The payoff query

Any shared identifier, in one query:

```cypher
MATCH (p1:Person)-[]->(shared)<-[]-(p2:Person)
WHERE p1.full_name < p2.full_name
  AND NOT shared:SAR AND NOT shared:FBICase
WITH p1, p2, collect(labels(shared)[0]) AS via, count(*) AS strength
WHERE strength >= 2
RETURN p1.full_name, p2.full_name, strength, via ORDER BY strength DESC;
```

| p1 | p2 | strength | via |
|---|---|---|---|
| Grace Jackson | John Doe | 4 | SSN, Phone, IP, Address |
| Jane Smith | Oliver Harris | 4 | SSN, Phone, IP, Address |
| Liam Wilson | Lucas Kim | 2 | SSN, IP |
| Mia Rodriguez | Olivia Anderson | 2 | SSN, IP |

`-[]->` = **any relationship type**, so one query spans all six identifier types at
once. The relational equivalent is a UNION over six join paths, rewritten every time
you add an identifier. Here a new identifier node type needs **no query change** —
`strength` just goes up. That is the actual argument for the property graph.

`p1.full_name < p2.full_name` dedupes the symmetric pair (A→B and B→A both match).

### Supernodes — the modeling judgment that mattered most

Six people share SAR `68789`, so `MERGE` built one high-degree hub and *every pair
through it* counted as a connection — 33 spurious pairs, more noise than signal. But
SAR/FBICase are **case membership** (investigators' output), not identity evidence.
Excluding them left exactly the 4 real suspects above.

High-degree hub nodes distort every traversal through them. Distinguishing
**structural** nodes from **evidential** ones is the core judgment call in graph
modeling — and `strength >= 2` across independent identifiers is a far harder signal
than any single shared value (which could just be a typo).

## Not done

- Aura **Data Importer** (visual drag-CSV → model → map columns). Worth a pass later
  for the visual modeling practice.
- `neo4j-admin database import` (bulk offline loader) — not available on Aura.
- Book's pandas/iris section — skipped, no Neo4j content.

## Next

Chapter 4 — Cypher Query Language (MATCH/WHERE/RETURN depth, COLLECT, CONTAINS,
EXISTS, degree functions, graph projections, `SIMILAR_RECIPE`, EXPLAIN/PROFILE).
