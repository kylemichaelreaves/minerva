#!/usr/bin/env bash
# Snapshot the corpus DB + ingest JSONL before any destructive operation.
#
# Usage:
#   scripts/snapshot-db.sh <short-reason>
#
# Writes to data/snapshots/<timestamp>-<reason>/ a copy of
# data/index.sqlite, the satellite databases, and (if present)
# data/chunks.jsonl. The reason tag is required and goes into the
# directory name so a later `ls data/snapshots/` reads as a log of what
# was about to happen.
#
# Set MINERVA_DATA_DIR to point at a different data/ — used by the tests,
# which must never snapshot the live 8.4G corpus.
#
# The DB is copied via `sqlite3 .backup`, NOT a filesystem cp: the DB
# runs in WAL mode, and a plain copy grabs the main file without the
# -wal sibling — silently dropping every not-yet-checkpointed commit
# (the newest LLM-verified xrefs are exactly what lands there) and
# risking a torn copy if a checkpoint runs mid-cp. .backup takes the
# proper locks and folds the WAL in. It's O(filesize) rather than the
# old clonefile O(metadata) — ~a minute for the ~8G DB — which is the
# price of a snapshot that actually contains the data.
#
# The satellite databases go through the same .backup for the same
# reason. metrics.sqlite joined WAL in #630 and inherited the hazard
# without inheriting the warning — measured, a plain cp of it produced a
# readable database missing 5,000 committed rows (#639). conversations,
# translations and concept_cache are still journal_mode=delete and would
# survive a cp today, but they are copied the same way rather than
# differently: the safe call costs nothing on a <1M file, and a per-file
# rule would have to be re-checked every time one of them changes mode,
# which is the mistake this is fixing.
#
# Rotation policy: keeps the most recent $MINERVA_SNAPSHOT_KEEP
# snapshots (default 5). Older ones are pruned automatically so the
# snapshot directory doesn't grow without bound — at ~8.8G per snapshot
# of the current DB, 5 is ~44G; the old default of 20 quietly grew to
# 128G.
#
# Rotation names every directory it removes, with its reason tag, BEFORE
# removing it. It used to print `(pruned 3 older snapshots)` afterwards,
# which is true and tells you nothing about which three — that is what it
# said while destroying three ~8.8G rollback points, one of them the
# baseline an issue comment cited (#653).
#
# To keep one permanently, `touch` a KEEP file inside it:
#
#     touch data/snapshots/20260911T201736Z-before-0035/KEEP
#
# A protected snapshot is never pruned AND does not count against
# $MINERVA_SNAPSHOT_KEEP — otherwise protecting one would silently
# shorten how far back the unprotected history reaches, which is a second
# surprise deletion caused by preventing the first. The corollary is that
# protection is the one way this directory can grow without bound, which
# is the point: you asked for it by name.
#
# MINERVA_SNAPSHOT_DRY_RUN=1 reports what rotation would prune and writes
# nothing at all — no snapshot, no deletions.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <short-reason>" >&2
    echo "  example: $0 pre-llm-verify" >&2
    exit 1
fi

reason="$1"
# Strip any path-unfriendly characters from the reason; keep it as a
# slug so the directory name is shell-safe.
reason_slug=$(printf '%s' "$reason" | tr -c '[:alnum:]._-' '-' | sed 's/--*/-/g; s/^-//; s/-$//')
if [[ -z "$reason_slug" ]]; then
    echo "error: reason '$reason' contains no usable characters" >&2
    exit 1
fi

# Repo-root anchor: the script lives in scripts/, so the repo root is
# its parent. Resolving via dirname keeps the script callable from any
# cwd.
repo_root=$(cd "$(dirname "$0")/.." && pwd)
data_dir="${MINERVA_DATA_DIR:-$repo_root/data}"
snapshot_root="$data_dir/snapshots"

if [[ ! -f "$data_dir/index.sqlite" ]]; then
    echo "error: $data_dir/index.sqlite does not exist; nothing to snapshot" >&2
    exit 1
fi

# Reason tag of a snapshot directory, for the prune report. A name alone
# is a timestamp; the reason is what tells you whether losing it matters.
describe_snapshot() {
    local name="$1" reason=""
    if [[ -f "$snapshot_root/$name/manifest.txt" ]]; then
        reason=$(sed -n 's/^reason: //p' "$snapshot_root/$name/manifest.txt" | head -1)
    fi
    if [[ -n "$reason" ]]; then
        printf '%s  (reason: %s)' "$name" "$reason"
    else
        printf '%s' "$name"
    fi
}

# Split existing snapshots into protected (KEEP marker) and prunable,
# oldest first. Lexical order is chronological — the names are ISO 8601
# in UTC.
protected_snapshots=()
prunable_snapshots=()
if [[ -d "$snapshot_root" ]]; then
    while IFS= read -r snap_name; do
        [[ -n "$snap_name" ]] || continue
        if [[ -e "$snapshot_root/$snap_name/KEEP" ]]; then
            protected_snapshots+=("$snap_name")
        else
            prunable_snapshots+=("$snap_name")
        fi
    done < <(cd "$snapshot_root" 2>/dev/null && ls -1d -- *-* 2>/dev/null | sort)
fi

keep="${MINERVA_SNAPSHOT_KEEP:-5}"
if ! [[ "$keep" =~ ^[0-9]+$ ]] || (( keep < 1 )); then
    echo "warning: MINERVA_SNAPSHOT_KEEP='$keep' is not a positive integer; using 5" >&2
    keep=5
fi

if [[ -n "${MINERVA_SNAPSHOT_DRY_RUN:-}" ]]; then
    # Counts the snapshot this run WOULD have taken, since that is the one
    # whose arrival does the evicting.
    would_have=$(( ${#prunable_snapshots[@]} + 1 ))
    echo "dry run: nothing written." >&2
    echo "  ${#prunable_snapshots[@]} prunable + ${#protected_snapshots[@]} protected snapshot(s); keep=$keep" >&2
    if (( would_have > keep )); then
        overflow_count=$(( would_have - keep ))
        echo "  would prune $overflow_count:" >&2
        for old in "${prunable_snapshots[@]:0:$overflow_count}"; do
            echo "    $(describe_snapshot "$old")" >&2
        done
    else
        echo "  would prune 0" >&2
    fi
    if (( ${#protected_snapshots[@]} > 0 )); then
        echo "  protected, never pruned:" >&2
        for kept in "${protected_snapshots[@]}"; do
            echo "    $(describe_snapshot "$kept")" >&2
        done
    fi
    exit 0
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot_dir="$snapshot_root/${timestamp}-${reason_slug}"
mkdir -p "$snapshot_dir"

# WAL-safe copy via the backup API (see header). Fallback for hosts
# without the sqlite3 CLI: copy main + -wal + -shm together — only
# consistent if nothing is writing, hence the loud warning.
# Satellites are optional — a fresh checkout has none of them — so the
# list is filtered by existence rather than required.
satellites=(metrics conversations translations concept_cache)

if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$data_dir/index.sqlite" ".backup '$snapshot_dir/index.sqlite'"
    for name in "${satellites[@]}"; do
        if [[ -f "$data_dir/$name.sqlite" ]]; then
            sqlite3 "$data_dir/$name.sqlite" ".backup '$snapshot_dir/$name.sqlite'"
        fi
    done
else
    echo "warning: sqlite3 CLI not found — falling back to file copy of" >&2
    echo "         each database + its WAL siblings. Only consistent if no" >&2
    echo "         process is writing to them right now." >&2
    for stem in index "${satellites[@]}"; do
        for f in "$stem.sqlite" "$stem.sqlite-wal" "$stem.sqlite-shm"; do
            if [[ -f "$data_dir/$f" ]]; then
                cp -p "$data_dir/$f" "$snapshot_dir/$f"
            fi
        done
    done
fi

# chunks.jsonl is the upstream ingest artifact — if it's gone, the
# snapshot is fine without it, but having both lets us reconstruct
# both halves of an ingest+index cycle.
if [[ -f "$data_dir/chunks.jsonl" ]]; then
    if cp -cp "$data_dir/chunks.jsonl" "$snapshot_dir/chunks.jsonl" 2>/dev/null; then
        :
    else
        cp -p "$data_dir/chunks.jsonl" "$snapshot_dir/chunks.jsonl"
    fi
fi

# Drop a tiny manifest. Records the reason + what host produced the
# snapshot + which migration head was applied (cheap; one sqlite call).
{
    echo "reason: $reason"
    echo "reason_slug: $reason_slug"
    echo "timestamp_utc: $timestamp"
    echo "host: $(hostname)"
    echo "cwd: $repo_root"
    if command -v sqlite3 >/dev/null 2>&1; then
        head=$(sqlite3 "$snapshot_dir/index.sqlite" \
            "SELECT MAX(version) FROM schema_migrations" 2>/dev/null || true)
        echo "migration_head: ${head:-unknown}"
        xref=$(sqlite3 "$snapshot_dir/index.sqlite" \
            "SELECT COUNT(*) FROM cross_references" 2>/dev/null || true)
        echo "cross_references_count: ${xref:-unknown}"
        chunks=$(sqlite3 "$snapshot_dir/index.sqlite" \
            "SELECT COUNT(*) FROM chunks" 2>/dev/null || true)
        echo "chunks_count: ${chunks:-unknown}"
    fi
} > "$snapshot_dir/manifest.txt"

# Rotation: keep the N most-recent PRUNABLE snapshots, drop the rest.
# The partition, the keep count and the ordering were all established
# above (the dry-run path needs them before anything is written).
# while-read (not mapfile) so the script also runs under macOS's
# /bin/bash 3.2 if the env-resolved bash is ever the system one.
#
# The snapshot just taken is itself prunable and is not in the array —
# it is counted here, because its arrival is what does the evicting.
prunable_total=$(( ${#prunable_snapshots[@]} + 1 ))
if (( prunable_total > keep )); then
    overflow_count=$(( prunable_total - keep ))
    # Name them BEFORE deleting: this output is the only record that a
    # ~8.8G rollback point existed.
    echo "pruning $overflow_count older snapshot$( (( overflow_count == 1 )) || echo s ):" >&2
    for old in "${prunable_snapshots[@]:0:$overflow_count}"; do
        echo "  $(describe_snapshot "$old")" >&2
        rm -rf -- "$snapshot_root/$old"
    done
fi

echo "$snapshot_dir"
