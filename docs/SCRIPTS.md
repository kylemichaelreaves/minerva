# Operator scripts

Every script in [`scripts/`](../scripts/). None of them is part of the
`minerva` CLI.

The tables below are **generated** by
[`generate_scripts_index.py`](../scripts/generate_scripts_index.py) from each
script's own documentation, and `make check` fails when they are stale (#505).
To change an entry, edit the script, then run `make generate-scripts-index`
and commit both.

**The convention.** A Python script carries a module docstring; a shell
script carries a comment block straight after its shebang. The first
paragraph is the summary shown here. Somewhere in that text, one line reads
exactly `Role: workflow` or `Role: oneoff`:

- **`workflow`** — something runs it or tells you to: the Makefile, CI, a
  Claude Code hook (`.claude/settings.json`), CONTRIBUTING / INGESTION /
  MEMORY, another script, or a recurring operator procedure.
- **`oneoff`** — written for a migration or remediation that has landed. It
  stays for the record, and for a re-source that needs the same repair.
  Nothing runs it.

A new script without a docstring or a `Role:` line fails `make check`.

The most-used one is `scripts/snapshot-db.sh <reason>`, which you run before
anything that mutates `data/index.sqlite`. See
[MEMORY.md](MEMORY.md#snapshot-before-destructive-ops). Usage, rotation and
`KEEP` markers are documented in the script's own header.

<!-- BEGIN GENERATED: scripts/generate_scripts_index.py — edit the scripts' docstrings, not this table -->
44 scripts: 32 workflow, 12 one-off.

### Workflow

Run by the Makefile, CI, a hook, another script, or a documented procedure.

| Script | Summary |
|--------|---------|
| [`audit_invariants.py`](../scripts/audit_invariants.py) | Check whole-corpus invariants against the live index (#320). |
| [`build_biblical_alignment.py`](../scripts/build_biblical_alignment.py) | Build verse-to-verse alignment cross-references between the four biblical corpora (Hebrew MT ↔ Septuagint ↔ Vulgate ↔ New Testament). |
| [`check_api_types.py`](../scripts/check_api_types.py) | Verify API contract fixture keys exist on TS wire types (api/types/*.ts), and that the TS ``BlockType`` union matches ``block_types.BLOCK_TYPES``. |
| [`check_author_imports.py`](../scripts/check_author_imports.py) | Fail if code imports deprecated root minerva.&lt;author>_works shims. |
| [`check_author_ingest.py`](../scripts/check_author_ingest.py) | Verify a corpus author is fully wired for ingest (registry, manifest, rules). |
| [`check_coverage_exclusions.py`](../scripts/check_coverage_exclusions.py) | Check that `pyproject.toml`'s coverage `omit` and `sonar-project.properties`'s `sonar.coverage.exclusions` agree on `src/minerva/` (#345). |
| [`check_diff_coverage.py`](../scripts/check_diff_coverage.py) | Fail when the lines this diff changed are under-covered (#255). |
| [`check_format_baseline.py`](../scripts/check_format_baseline.py) | Gate Prettier and ruff formatting against pinned baselines (#483, #136). |
| [`check_pr_citations.py`](../scripts/check_pr_citations.py) | Verify every `PR #N` this repo cites in prose is actually a PR (#335). |
| [`check_pr_link.py`](../scripts/check_pr_link.py) | Verify a PR's closing links registered — and that none registered by accident (#321). |
| [`check_test_location.py`](../scripts/check_test_location.py) | Fail when a frontend test sits under `web/src` instead of `web/tests` (#547). |
| [`chunk_count_validation.py`](../scripts/chunk_count_validation.py) | Validate ingested chunk totals against manifest-declared ranges. |
| [`chunk_granularity.py`](../scripts/chunk_granularity.py) | Gate chunk granularity: catch a parser that emitted a whole work as one chunk. |
| [`ci_scope.py`](../scripts/ci_scope.py) | Decide which `check.yml` suites a PR needs, from the paths it changes (#723). |
| [`clean-hobbes-latin.py`](../scripts/clean-hobbes-latin.py) | Ligature repair for the Molesworth Latin Hobbes OCR. |
| [`clean-sacy-fra.py`](../scripts/clean-sacy-fra.py) | Repair the capital-I misread in the French Sacy OSIS source (#557). |
| [`corpus-quality-audit.py`](../scripts/corpus-quality-audit.py) | Scan ``data/index.sqlite`` for chunks that match heuristics for known corpus-quality bugs and emit a per-author report. |
| [`dashboard_aggregates.py`](../scripts/dashboard_aggregates.py) | Dump dashboard-design aggregates as JSON. |
| [`derive_common_title_tokens.py`](../scripts/derive_common_title_tokens.py) | Derive the common-word work-title tokens that `detect_work` distrusts. |
| [`generate_author_artifacts.py`](../scripts/generate_author_artifacts.py) | Generate corpus_registry, author_ordering, atlasData and dominantPhil from manifest.yaml. |
| [`generate_scripts_index.py`](../scripts/generate_scripts_index.py) | Generate the script index in `docs/SCRIPTS.md` from the scripts themselves (#505). |
| [`hook_commit_hazard.py`](../scripts/hook_commit_hazard.py) | PostToolUse hook (#322, check 1): warn when a just-made commit puts a closing keyword next to an issue number. |
| [`hook_mark_check_passed.py`](../scripts/hook_mark_check_passed.py) | PostToolUse hook (#322, check 3, part 2): mark `make check` as passed. |
| [`hook_mark_dirty.py`](../scripts/hook_mark_dirty.py) | PostToolUse hook (#322, check 3, part 1): mark watched source dirty. |
| [`hook_pr_link_autocheck.py`](../scripts/hook_pr_link_autocheck.py) | PostToolUse hook (#322, check 2): run the PR-link gate right after `gh pr create`, instead of relying on someone remembering to type the make target. |
| [`hook_require_fresh_check.py`](../scripts/hook_require_fresh_check.py) | PreToolUse hook (#322, check 3, part 3): catch a push made after an edit `make check` never saw. |
| [`install-git-hooks.sh`](../scripts/install-git-hooks.sh) | Install the project's git hooks into .git/hooks/. |
| [`repair_stale_xrefs.py`](../scripts/repair_stale_xrefs.py) | Delete the `cross_references` rows `xref_source_span` flags as genuinely stale (#407), so a subsequent `refs build` pass can rediscover them wherever the cited text still exists in the chunk. |
| [`seed_terms.py`](../scripts/seed_terms.py) | Thin wrapper around `minerva terms import` for the original hand-curated Aristotle seed set. |
| [`snapshot-db.sh`](../scripts/snapshot-db.sh) | Snapshot the corpus DB + ingest JSONL before any destructive operation. |
| [`staleness.py`](../scripts/staleness.py) | Shared marker-file comparison for the make-check-staleness gate (#322). |
| [`work_slug_snapshot.py`](../scripts/work_slug_snapshot.py) | Committed stand-in for the gitignored index's work-slug table (#602). |

### One-off

Written for a migration or remediation that has landed. Nothing runs these.

| Script | Summary |
|--------|---------|
| [`clean-boulainvilliers-texts.py`](../scripts/clean-boulainvilliers-texts.py) | Cleanup for the Boulainvilliers source texts. |
| [`clean-cicero-chrome.py`](../scripts/clean-cicero-chrome.py) | Strip Wikisource + Project Gutenberg chrome from Cicero files. |
| [`clean-descartes-principes.py`](../scripts/clean-descartes-principes.py) | Partial cleanup for Descartes' *Principes* parts II-IV. |
| [`clean-gobineau-texts.py`](../scripts/clean-gobineau-texts.py) | One-shot cleanup for the Gobineau source texts. |
| [`clean-hegel-lectures-glossary.py`](../scripts/clean-hegel-lectures-glossary.py) | Remove the OCR'd German→English glossary word-lists from Hegel's *Lectures on the History of Philosophy*. |
| [`clean-marx-gutenberg-chrome.py`](../scripts/clean-marx-gutenberg-chrome.py) | Strip the gutenberg.spiegel.de site chrome from Marx source files. |
| [`clean-renan-texts.py`](../scripts/clean-renan-texts.py) | One-shot cleanup for Renan's source texts. |
| [`clean-rousseau-long-s.py`](../scripts/clean-rousseau-long-s.py) | Normalize literal long-s codepoints in Rousseau's *Premier Discours*. |
| [`extract-essai-pdf.py`](../scripts/extract-essai-pdf.py) | Extract Boulainvilliers's *Essai sur la noblesse de France* from the Gallica PDF (the one with a text layer — replaces the broken EPUB extraction). |
| [`extract-hegel-phil-of-right-footnotes.py`](../scripts/extract-hegel-phil-of-right-footnotes.py) | Extract Hegel's *Elements of the Philosophy of Right* editor's endnotes from the EPUB and emit them as a stand-alone HTML file that the standard corpus-label pipeline can chunk. |
| [`extract-lettres-gallica.py`](../scripts/extract-lettres-gallica.py) | Extract Boulainvilliers's *Lettres sur les anciens parlemens de France* from the Gallica "Text View" HTML exports (3 volumes). |
| [`survey_unmatched_scripture_cites.py`](../scripts/survey_unmatched_scripture_cites.py) | Survey Aquinas + Augustine chunks for scripture-cite forms the existing Latin :class:`ScriptureCiteRule` does NOT match. |
<!-- END GENERATED -->
