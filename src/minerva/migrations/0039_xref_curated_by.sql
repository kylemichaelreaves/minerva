-- 0039_xref_curated_by.sql
-- ════════════════════════════════════════════════════════════════════
-- Who last gave a verdict on a cross-reference, and when (#718).
--
-- A curator's rejection (review walker, PATCH /api/references/:id) wrote
-- only `curator_status`, so it read exactly like llm-verify's own: both
-- `rejected` + `source_method='rule+embed+llm'`. A bulk re-judge could not
-- tell which rows a person had decided, and could overturn them.
--
-- `source_method` stays what it is — how the row was *detected* (the
-- Network verification panel groups by it). The verdict's author lives
-- here instead:
--
--   curated_by  'human' | 'llm' | 'embed', NULL = no verdict recorded
--               (every row that predates this migration, and new rows)
--   curated_at  ISO-8601 UTC of that verdict
--
-- Bulk verifiers skip `curated_by = 'human'`. Nullable with a CHECK and no
-- default, so a plain ADD COLUMN suffices — no table rebuild.
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE cross_references ADD COLUMN curated_by TEXT
    CHECK (curated_by IS NULL OR curated_by IN ('human', 'llm', 'embed'));
ALTER TABLE cross_references ADD COLUMN curated_at TEXT;
