#!/usr/bin/env bash
# Snapshot the corpus DB + ingest JSONL before any destructive operation.
#
# Usage:
#   scripts/snapshot-db.sh <short-reason>
#
# Writes to data/snapshots/<timestamp>-<reason>/ a copy of
# data/index.sqlite and (if present) data/chunks.jsonl. The reason
# tag is required and goes into the directory name so a later
# `ls data/snapshots/` reads as a log of what was about to happen.
#
# A timestamped directory is faster (and atomic-enough) than copying
# files individually — cp -c on macOS uses APFS clonefile when source
# and dest are on the same volume, so the cost is O(metadata) rather
# than O(filesize). The fallback path uses regular cp for Linux /
# non-APFS hosts.
#
# Rotation policy: keeps the most recent $MINERVA_SNAPSHOT_KEEP
# snapshots (default 5). Older ones are pruned automatically so the
# snapshot directory doesn't grow without bound — at ~7G per snapshot
# of the current DB, 5 is ~35G; the old default of 20 quietly grew to
# 128G. If you need a permanent baseline, copy the snapshot directory
# out of data/snapshots/ to data/snapshots-archive/ (or anywhere
# outside the auto-rotation).

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
data_dir="$repo_root/data"
snapshot_root="$data_dir/snapshots"

if [[ ! -f "$data_dir/index.sqlite" ]]; then
    echo "error: $data_dir/index.sqlite does not exist; nothing to snapshot" >&2
    exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
snapshot_dir="$snapshot_root/${timestamp}-${reason_slug}"
mkdir -p "$snapshot_dir"

# cp -c uses APFS clonefile on macOS — O(1) copy, no actual block
# duplication until one side is written. Falls back gracefully on
# Linux which doesn't know -c. The -p preserves mtime so we can later
# see when the source file was last written, not just when the snapshot
# was taken.
if cp -cp "$data_dir/index.sqlite" "$snapshot_dir/index.sqlite" 2>/dev/null; then
    :
else
    cp -p "$data_dir/index.sqlite" "$snapshot_dir/index.sqlite"
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

# Rotation: keep the N most-recent snapshots, drop the rest. Sorting
# by directory name works because the timestamp prefix is ISO 8601 in
# UTC, so lexical order == chronological order. Override the keep
# count per-invocation with MINERVA_SNAPSHOT_KEEP (e.g. bump it before
# a risky multi-step migration where you want more rollback points).
keep="${MINERVA_SNAPSHOT_KEEP:-5}"
if ! [[ "$keep" =~ ^[0-9]+$ ]] || (( keep < 1 )); then
    echo "warning: MINERVA_SNAPSHOT_KEEP='$keep' is not a positive integer; using 5" >&2
    keep=5
fi
mapfile -t all_snapshots < <(
    cd "$snapshot_root" && ls -1d -- *-* 2>/dev/null | sort
)
if (( ${#all_snapshots[@]} > keep )); then
    overflow_count=$(( ${#all_snapshots[@]} - keep ))
    for old in "${all_snapshots[@]:0:$overflow_count}"; do
        rm -rf -- "$snapshot_root/$old"
    done
    echo "(pruned $overflow_count older snapshot$( (( overflow_count == 1 )) || echo s ))" >&2
fi

echo "$snapshot_dir"
