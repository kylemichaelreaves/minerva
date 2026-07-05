-- 0023_edition_local_title.sql
-- ════════════════════════════════════════════════════════════════════
-- Subordinate per-edition/translation display title.
--
-- Canonical `works.title` is the work's own name (for Greek authors, the
-- Latinized-Greek form — "Politeia", "Euthyphron"). Each edition and
-- translation of that work may present its own local title — the English
-- translation of "Politeia" is titled "Republic"; a German translation
-- keeps its German title — surfaced by the reader's edition switcher.
--
-- Additive nullable columns (no CHECK/UNIQUE), so a plain ADD COLUMN is
-- enough — no PRAGMA table-rebuild. NULL means "use the canonical title".
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE editions ADD COLUMN title_local TEXT;
ALTER TABLE translations ADD COLUMN title_local TEXT;
