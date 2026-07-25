# Chapter 4 — Cypher Query Language

Status: **done** (2026-07-25). Ch5 (Bloom / Power BI viz) skipped — jumping to Ch6.

## Getting the dataset onto Aura Free

The book's recipe dataset is **2.23M recipes / 135,638 ingredients / 10.46M
relationships** — far past AuraDB Free's 200k nodes / 400k rels.

**Trimmed the CSVs on disk** (never filter server-side during ingest — ingestion stays
pure raw). Filter used: `title CONTAINS 'cornbread' OR 'spice'` — semantically the two
keywords Ch4 actually queries, so ingredient co-occurrence structure survives. An
arbitrary `LIMIT` would have shredded it.

| File | Before | After |
|---|---|---|
| `Recipe_Node.csv` | 2,231,142 | **26,602** |
| `Ingredient_Node.csv` | 135,638 | **7,075** |
| `Recipe_to_Ingredient_Relationship.csv` | 10,457,463 | **126,602** |

Result: **33,677 nodes / 126,602 rels** — 17% / 32% of budget. Referential integrity
kept both directions (no orphan rel rows, no unreferenced ingredients). Also dropped
the one blank-named ingredient + its rels — same junk-hub bug class as Ch3's SAR `''`.

Loaded via `LOAD CSV` over the **Git LFS media URL**
(`media.githubusercontent.com/media/<owner>/<repo>/refs/heads/main/...`) — `raw.` won't
serve LFS files.

### Import gotchas

**Backtick the neo4j-admin-format headers.** `Recipe_ID:ID(Recipe-ID)`,
`:START_ID(Recipe-ID)`, `Ingredient_Name:string` contain colons/parens, so Cypher needs
`` `...` `` to read them as one identifier. Inconsistent in the source: `Ingredient_ID`
is plain, no backticks needed.

**`MATCH`, not `MERGE`, for relationship endpoints.** `MERGE` would *invent* an empty
node when a reference is broken, masking the error. `MATCH` skips the row instead —
loud via a count mismatch.

**A `MATCH` that finds nothing inside `CALL {}` is NOT an error.** Ran the relationship
load before the ingredient load: 126k rows, zero created, reported as *"no changes, no
records"* — no warning, no failure. Verify counts after **every** load step, not at the
end.

**`CALL (row) { ... } IN TRANSACTIONS OF n ROWS`** — scoped-variable form (5.23+). The
book's `CALL { WITH row ... }` still parses on 5.27 but `WITH row` inside is deprecated.
Cannot run inside an explicit transaction, so it's Browser/Desktop or an auto-commit
driver call only — **not** `session.execute_write()`.

## Chapter 4 blockers on Aura Free (tier limits, not client limits)

| Book code | Why it fails |
|---|---|
| `:use recipe` | Aura exposes exactly **one** user database, always named `neo4j` — on *every* tier. Architectural, not a Free limit. `CREATE DATABASE` never works. |
| `apoc.node.degree()` | APOC not on Aura Free |
| `gds.graph.project` / `gds.nodeSimilarity` | GDS needs **AuraDS**, a separate paid product |
| `neo4j-admin database import` | Offline tool: needs a stopped DBMS + filesystem access. Desktop-connected-to-Aura can't do it either. |

Instance vs database: **instance** = a whole managed deployment (own URI, creds, RAM).
**database** = a logical DB inside one instance (Enterprise multi-DB — what the book
assumes, because it runs local Desktop). Aura = 1 instance : 1 database. Free allows
more than one instance per account, so per-chapter isolation = separate instances
(swap the `.env` block), not `:use`.

## Cypher learned

**`WITH` is the pipe and marks the aggregation boundary.** `WHERE` before a `WITH`
filters rows pre-aggregation; `WHERE` after it filters post-aggregation. That's SQL's
`WHERE` vs `HAVING` — Cypher needs no second keyword. Non-aggregated keys in a `WITH`
*are* the grouping keys; there is no `GROUP BY`.

**List predicates** — Cypher's answer to `EXISTS`/`ALL` subqueries, over collected lists:
```cypher
WITH recipe, collect(i.Ingredient_Name) AS ingredients
WHERE all(ingredient IN ['almonds','walnuts'] WHERE ingredient IN ingredients)
```
Siblings: `any()`, `none()`, `single()`. Solves "has **both** X and Y", which the
pattern itself can't express (each match is a single relationship, so the pattern's
`IN [...]` is an OR). Cheaper equivalent when the first `WHERE` already restricts:
```cypher
WITH recipe, count(DISTINCT i) AS matched WHERE matched = 2
```
`all()` scales badly on long lists; `DISTINCT` matters if an ingredient links twice.

**`LIMIT` after aggregation is deceptive.** `collect(...) ... LIMIT 3` still aggregates
over all 8,688 matches first — Cypher can't short-circuit it. To make it cheap, limit
*before* expanding:
```cypher
MATCH (r:Recipe) WHERE r.Recipe_Title CONTAINS 'cornbread'
WITH r LIMIT 3
MATCH (r)-[:USES]->(i:Ingredient)
RETURN r.Recipe_Title, collect(i.Ingredient_Name)
```
Matters a lot for MCP tools that must answer fast.

**`CONTAINS` can't use a range index** — full scan of all 26,602 titles. Fine here; the
real fix is a full-text index.

**`elementId()`, not `id()`.** `id()` is deprecated — Neo4j reuses internal IDs after
deletion. `elementId()` returns a string; still fine for dedup since you only need *a*
consistent ordering.

**Deduping symmetric pairs.** `(r1)-[:USES]->(i)<-[:USES]-(r2)` matches every pair
twice (A,B) and (B,A). Kill one with `elementId(r1) < elementId(r2)`, or a natural
unique property when one exists (Ch3 used `p1.full_name < p2.full_name`).

## Degree — and two more book bugs

Book cell 18 uses APOC. Pure-Cypher replacement:
```cypher
MATCH (r:Recipe)-[:USES]->()
WITH r, count(*) AS degree
SET r.degree = degree;
```

Better than the book's version for two reasons:

1. `apoc.node.degree(recipe)` counts **all** rels, **both** directions, **any** type. So
   re-running book cell 18 *after* cell 21 creates `SIMILAR_TO` gives different degree
   values. Latent bug. Ours counts only outgoing `:USES`.
2. The book scopes cell 18 to `CONTAINS 'cornbread'`, so `degree` is `null` everywhere
   else. Cell 19 then filters `r1.degree > 10` — and **`null > 10` is `null`, not
   false and not an error**, so every non-cornbread recipe is silently excluded. That's
   why the book's counts look small. We set it on all 26,602.

Degree = relationship count. Cheapest centrality measure; identifies **supernodes**.
Precomputing it as a property is standard (traversal-time counting is expensive), at
the cost of staleness — wrong the instant anyone adds a relationship.

Distribution here: median 8, max 33, **3,983 recipes with degree > 10** (Ch4's
similarity threshold).

## Supernodes gate the projection

`(r1:Recipe)-[:USES]->(i)<-[:USES]-(r2:Recipe)` is a self-join through ingredient hubs.
**An ingredient of degree *n* generates *n²* recipe pairs** — `salt`, `sugar`, `butter`
appear in thousands of recipes, so this can explode into millions of paths and hang a
1GB Free instance. Check hub degree *before* running any projection:
```cypher
MATCH (i:Ingredient)<-[:USES]-()
WITH i, count(*) AS recipes
RETURN i.Ingredient_Name, recipes ORDER BY recipes DESC LIMIT 15;
```
Same lesson as Ch3's SAR/FBICase hubs, now as a performance problem rather than a
correctness one.

## Entity resolution is correctness in a graph

`USES` was **derived by NLP extraction** from scraped recipe text (RecipeNLG-style
corpus — see the `Link`/`Source` properties), not human curation. So it carries scrape
noise: `Cinnamon` vs `cinnamon` as separate nodes, `"spiced nuts"` vs `"spiced nuts "`
as separate recipes.

Every such duplicate **splits a co-occurrence signal** — recipes using `Cinnamon` never
look similar to recipes using `cinnamon`, because they attach to different nodes. In a
relational schema a duplicate lookup row is untidy; in a graph it silently halves every
traversal through that node. Ch3's fraud detection worked *only* because the SSN strings
matched exactly — `123-45-6789` vs `123456789` would have hidden the ring entirely.

Relevant to the MCP endgame: whatever graph you query was built by some pipeline, and
its entity-resolution quality is a hard ceiling on what your tools can retrieve.

## Concept: SQL → graph is a re-encoding, not a re-modelling

The relationships **already exist in SQL**; they're just not addressable.

| Relational | Neo4j |
|---|---|
| table | node label |
| row | node |
| column | property |
| **FK column (1:N)** | **relationship, child → parent** |
| **junction table (N:N)** | **relationship** |
| junction table's extra columns | relationship properties |
| lookup/enum table | property or label (often vanishes) |

No new information is required — a relational schema already contains a complete graph.
`USES` is not an extra thing Neo4j demands; it's the `recipe_ingredient` junction table
any relational recipe app already has, renamed. The ORM just hides it behind
`recipe.ingredients`.

### What SQL lacks

A relationship in SQL is **predicated on its host** — `customer_id` can't be uttered
without naming its table. In a graph it's an independent, addressable entity:

```cypher
MATCH ()-[u:USES]->() RETURN count(u);              -- names no label at all
MATCH ()-[r]->() RETURN type(r), count(*);          -- inventory of every edge type
```

Neither has a SQL equivalent — there's no column to point at. Hence:

```cypher
MATCH (p1)-[]->(shared)<-[]-(p2)        -- any type (Ch3 spanned 6 identifier types)
MATCH (a)-[:KNOWS*1..5]->(b)            -- variable depth
MATCH p = shortestPath((a)-[*]-(b))
```

**Variable-length traversal is the genuinely new capability.** In SQL that's a recursive
CTE, where each hop is another index lookup against a growing intermediate set. Neo4j
stores relationships as pointers on both endpoints, so a hop is a pointer dereference
whose cost is independent of total store size — *index-free adjacency*.

Honest framing for the "why not just Postgres?" conversation: **if your queries are
always 1–2 joins deep, a graph buys readability, not power.** The payoff arrives when
depth is variable or unknown — fraud rings, supply chains, org hierarchies,
recommendation paths.

### Where each model hits its ceiling

- **SQL can't quantify over relationships** — no "any edge", no "1 to 5 edges".
- **Neo4j can't attach a relationship to a relationship.** To say something *about* a
  link (who recorded it, when it was disputed, what evidence backs it) you must promote
  it to a node — **reification**. A junction table with rich columns and its own
  lifecycle (`booking` joining passenger + flight, with price/seat/timestamp) usually
  deserves to be a node, not a relationship.

A relationship is first-class but **not free-standing**: it can't exist without both
endpoints, which is why `DELETE` on a connected node throws and needs `DETACH DELETE`.

### The judgment calls a mechanical FK translation won't make

1. **Naming and direction** — an FK gives no verb. `PLACED_BY` vs `BELONGS_TO` vs
   `FOR_CUSTOMER`. 200 FKs = 200 naming decisions, and bad ones make Cypher unreadable
   forever.
2. **Which columns become nodes** — no FK to guide you. `person.ssn` is just a column;
   a mechanical translation keeps it a property, and Ch3's fraud query becomes
   impossible. *A value becomes a node when you want to traverse to it and ask who else
   shares it.*
3. **Which tables shouldn't survive**, and which junction tables should become nodes.

## Graph introspection (matters for the MCP endgame)

```cypher
CALL db.schema.visualization();       -- the whole meta-model, no data touched
CALL db.schema.nodeTypeProperties();  -- labels + property names/types
CALL db.schema.relTypeProperties();
```
This is how an agent discovers an unknown graph's shape before generating Cypher — the
official `mcp-neo4j-cypher` server exposes it as its `get_neo4j_schema` tool. It's the
piece that makes text-to-Cypher work at all.

## Not done

- **`gds.nodeSimilarity` / `SIMILAR_TO` write-back** (cells 20–22) — needs AuraDS.
  Pure-Cypher Jaccard is possible but the supernode blowup must be capped first.
- Ran out of scope before the hub-degree check and `EXPLAIN`/`PROFILE` section.
- Book's `Individual`/`FRIEND_OF` toy graph (cells 1–6) — trivial, skipped.

## Next

Chapter 6 — Enriching data with an LLM. **Substitution: AWS Bedrock cheapest models
instead of the book's OpenAI API** (`amazon.nova-micro-v1:0` for text,
`amazon.titan-embed-text-v2:0` @ 1024 dims for embeddings). Also restores
`patents-aura.dump` via the Aura console's Backup & restore — which **replaces the
entire database**, so the recipe + FBI graphs go away at that point.
