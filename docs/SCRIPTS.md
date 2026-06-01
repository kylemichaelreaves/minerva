# Operator scripts

One-off scripts in [`scripts/`](../scripts/). Not part of the `minerva` CLI.

| Script | When to run |
|--------|-------------|
| [`snapshot-db.sh`](../scripts/snapshot-db.sh) | Before any destructive change to `data/index.sqlite` — see [MEMORY.md](MEMORY.md#snapshot-before-destructive-ops) |
| [`seed_terms.py`](../scripts/seed_terms.py) | Bulk seed term-glossary rows from YAML specs under `data/glossary/` |
| [`build_biblical_alignment.py`](../scripts/build_biblical_alignment.py) | Build cross-edition biblical alignment data after MT/LXX/Vulgate ingest |
| [`dashboard_aggregates.py`](../scripts/dashboard_aggregates.py) | Regenerate [`dashboard_aggregates.json`](dashboard_aggregates.json) after xref work |

## snapshot-db.sh

```sh
scripts/snapshot-db.sh pre-<short-reason>
```

Writes `data/snapshots/<timestamp>-<reason>/` with copies of `index.sqlite` and
`chunks.jsonl` (when present). Keeps the 20 most recent snapshots automatically.

## dashboard_aggregates.py

```sh
uv run python scripts/dashboard_aggregates.py > docs/dashboard_aggregates.json
```

Requires a populated `data/index.sqlite`. Produces xref statistics for dashboard
design (per-author degree tables, source/target matrix, curator status breakdown).
