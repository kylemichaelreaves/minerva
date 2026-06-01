-- 0020_refs_scan_state.sql
-- ════════════════════════════════════════════════════════════════════
-- Skip-already-scanned state for `refs build --strategy rules`.
--
-- Phase 6a of the 2026-05-30 ingestion-bottleneck remediation II plan.
-- Without this table, every `refs build` (rules strategy) re-walks
-- every chunk in the corpus + re-evaluates every rule module —
-- ~344K chunks × dozens of patterns per source-author module — even
-- when nothing has changed. This dominates wall time on touchup
-- runs and discourages running it often enough to keep xrefs fresh.
--
-- Design: a (chunk_id PK, text_hash, scanned_at) row per chunk we've
-- already scanned. The rules runner skips a chunk when its current
-- text_hash matches a stored hash (text unchanged → re-scanning
-- would emit the same candidate set we'd just be deduped against).
-- `--rescan-all` ignores the table and forces a full pass — needed
-- when a rules module itself changes and would now match where it
-- didn't before.
--
-- Update semantics: after a chunk is scanned, the runner upserts its
-- (chunk_id, sha1(text)) here. content-stable re-runs become near-
-- no-ops (one COUNT-style hash compare per chunk).
--
-- This is a soft cache: rows with stale chunk_ids (after a re-ingest
-- that changed text) are harmless — they refer to ids no longer in
-- chunks_full, so they'll never be hit by the join in the runner.
-- A `index --reset` rebuild may want to TRUNCATE this for symmetry
-- with the lemma / xref restore dance, but the table being out-of-
-- date never wedges correctness — just causes a more thorough scan.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS refs_scan_state (
    chunk_id   TEXT PRIMARY KEY,
    text_hash  TEXT NOT NULL,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
