"""Curator commands for the cross-reference layer.

Phase 1 commands:

* ``add`` — record a single manual reference by chunk_id + target ids.
* ``list`` — filter the cross-references table by source / target / status.
* ``load-spec`` — load YAML curator specs from ``data/glossary/refs/``.
* ``targets`` — list / search the ``reference_targets`` table.

Phase 2-4 commands:

* ``build`` — run auto-detection: ``--strategy rules`` (Phase 2),
  ``--strategy embed-verify`` (Phase 3 cosine verification + allusion
  sweep), or ``--strategy llm-verify`` (Phase 4 LLM verification).
* ``review`` — terminal curator walker over `curator_status='auto'`
  rows; approve / reject / skip per row.

Patterned on ``cli/terms/__init__.py`` — single ``register_subparsers``
function called by the top-level CLI.
"""

from __future__ import annotations

import argparse

from ... import llm as llm_mod
from ...refs.constants import CURATED_BY_VALUES
from ...refs.llm_verify import LLM_VERIFY_DEFAULT_EFFORT
from .add import cmd_refs_add
from .build import cmd_refs_build
from .list_cmd import cmd_refs_list
from .load_spec_cmd import cmd_refs_load_spec
from .review import cmd_refs_review
from .targets import cmd_refs_targets


def register_subparsers(parent_subparsers: argparse._SubParsersAction) -> None:
    """Attach the ``refs`` subcommand group to the top-level CLI."""

    # Local import keeps the parent-cli import path light and avoids
    # cycles (`cli/refs/` is imported by `cli/__init__.py`).
    from .._shared import add_common_db_arg as _add_common_db_arg

    p_refs = parent_subparsers.add_parser(
        "refs", help="Curator commands for the cross-reference layer."
    )
    subs = p_refs.add_subparsers(dest="refs_cmd", required=True)

    # ── add ──
    pa = subs.add_parser("add", help="Record one manual cross-reference.")
    _add_common_db_arg(pa)
    pa.add_argument(
        "--source-chunk",
        required=True,
        help="Source chunk_id (the chunk where the reference appears).",
    )
    target_grp = pa.add_mutually_exclusive_group(required=True)
    target_grp.add_argument(
        "--target-id",
        type=int,
        help="Existing reference_targets.id. Use `minerva refs targets` to find one.",
    )
    target_grp.add_argument(
        "--target",
        help=(
            "Target as 'Author / Work' — e.g. 'Aristotle / De anima'. "
            "Creates the reference_targets row on first use; auto-links "
            "to a works row when (author, title) matches."
        ),
    )
    pa.add_argument(
        "--target-chunk",
        help="Optional in-corpus chunk_id for the specific target passage.",
    )
    pa.add_argument(
        "--target-locator",
        help="Optional canonical citation string, e.g. 'III.7' or 'Republic 514a'.",
    )
    pa.add_argument(
        "--type",
        dest="ref_type",
        required=True,
        choices=(
            "cites",
            "quotes",
            "paraphrases",
            "alludes",
            "comments_on",
            "translates",
            "disputes",
            "corrects",
        ),
        help="Reference kind.",
    )
    pa.add_argument(
        "--quoted-phrase",
        help="Literal quoted text, when the reference is a quotation.",
    )
    pa.add_argument(
        "--source-form",
        help="The surface form that signals the reference ('Philosophus', 'ut Plato dicit', …). Required for shadow-address stability if you want this row to survive a re-ingest.",
    )
    pa.add_argument(
        "--source-span",
        help="Character span in the source chunk's text as `start:end`.",
    )
    pa.add_argument("--note", help="Curator note (markdown).")
    pa.add_argument(
        "--confidence",
        type=float,
        default=1.0,
        help="Manual entries default to 1.0; lower if uncertain.",
    )
    pa.set_defaults(func=cmd_refs_add)

    # ── list ──
    pl = subs.add_parser("list", help="List cross-references.")
    _add_common_db_arg(pl)
    pl.add_argument(
        "--source-author",
        help="Filter by source-side author (e.g. 'Aquinas').",
    )
    pl.add_argument(
        "--target-author",
        help="Filter by target-side canonical author (e.g. 'Aristotle').",
    )
    pl.add_argument(
        "--target-work",
        help="Filter by target-side canonical work (e.g. 'De anima').",
    )
    pl.add_argument(
        "--status",
        choices=("auto", "approved", "rejected", "manual"),
        help="Filter by curator_status.",
    )
    pl.add_argument(
        "--curated-by",
        choices=(*CURATED_BY_VALUES, "none"),
        help="Filter by who decided the row; 'none' = no verdict author recorded.",
    )
    pl.add_argument("--limit", type=int, default=50)
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_refs_list)

    # ── load-spec ──
    pls = subs.add_parser(
        "load-spec",
        help="Load one or more YAML cross-reference specs (data/glossary/refs/*.yaml).",
    )
    _add_common_db_arg(pls)
    pls.add_argument(
        "paths",
        nargs="+",
        help="YAML spec file paths (or directories — all *.yaml under each is loaded).",
    )
    pls.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + validate without writing to the DB.",
    )
    pls.set_defaults(func=cmd_refs_load_spec)

    # ── targets ──
    pt = subs.add_parser("targets", help="List reference_targets rows.")
    _add_common_db_arg(pt)
    pt.add_argument("--author", help="Filter by canonical_author.")
    pt.add_argument(
        "--in-corpus",
        action="store_true",
        help="Show only targets with an in_corpus_work_id (linkable to a chunk).",
    )
    pt.add_argument(
        "--out-of-corpus",
        action="store_true",
        help="Show only targets WITHOUT an in_corpus_work_id (Cicero, Plotinus, …).",
    )
    pt.add_argument("--limit", type=int, default=100)
    pt.add_argument("--json", action="store_true")
    pt.set_defaults(func=cmd_refs_targets)

    # ── build (Phases 2-4: auto-detection strategies) ──
    pb = subs.add_parser(
        "build",
        help="Run cross-reference auto-detection (rules, embed-verify, or llm-verify).",
    )
    _add_common_db_arg(pb)
    pb.add_argument(
        "--strategy",
        choices=("rules", "embed-verify", "llm-verify"),
        default="rules",
        help=(
            "Detection stage to run: 'rules' (default) inserts rule-based "
            "candidates; 'embed-verify' cosine-checks quoted rows + sweeps "
            "for allusions; 'llm-verify' LLM-verifies auto rows."
        ),
    )
    pb.add_argument(
        "--source-author",
        help="Restrict the build to one source author (e.g. 'Aquinas'). Faster targeted re-runs.",
    )
    pb.add_argument(
        "--source-work",
        help=(
            "Restrict --strategy llm-verify to one source work title (e.g. "
            "'Nachgelassene Fragmente (KGW)'). Pairs with --source-author for "
            "cheap, targeted verification of a single newly-added work."
        ),
    )
    pb.add_argument(
        "--limit",
        type=int,
        help=(
            "[--strategy rules only] Cap the chunks fetched for scanning, "
            "before the scan-state cache skips current ones — so on an "
            "already-scanned author it can scan 0. Refused under the verify "
            "strategies, which never read it; bound a paid llm-verify run "
            "with --max-rows or --max-llm-calls."
        ),
    )
    pb.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-500-chunks progress to stderr.",
    )
    pb.add_argument(
        "--refresh-only",
        action="store_true",
        help=(
            "[--strategy rules only] Rescan the scope and refresh the rows "
            "today's rules match — rule-tier confidence/source_method "
            "(#518) and stale spans (#715) — inserting nothing and leaving "
            "the scan-state cache alone. The live backfill for a re-tuned "
            "rule; snapshot the DB first."
        ),
    )
    pb.add_argument(
        "--rescan-all",
        action="store_true",
        help=(
            "Force a full rules pass, ignoring the refs_scan_state "
            "skip cache. Editing a rules module no longer needs this: "
            "the cache stores a fingerprint of the compiled rule set "
            "and re-scans that author on its own — configuration (#287) "
            "and, since #304, the logic of the rule's methods too. "
            "Kept as the escape hatch for a fingerprint that is itself "
            "wrong, not for any edit a curator makes."
        ),
    )
    pb.add_argument(
        "--resume",
        action="store_true",
        help=(
            "[--strategy llm-verify only] Resume from "
            "meta.refs.llm_verify.last_row_id checkpoint instead of "
            "starting from the top. Useful for picking up after the "
            "--max-llm-calls budget was exhausted."
        ),
    )
    pb.add_argument(
        "--rejudge-blind",
        action="store_true",
        help=(
            "[--strategy llm-verify only] Instead of unjudged rows, re-judge "
            "the rows llm-verify rejected before #713 without the citation in "
            "the excerpt it was shown. Always resumes from its own checkpoint, "
            "so a finished re-judge is a no-op. Snapshot the DB first (#714)."
        ),
    )
    # ── embed-verify flags (Phase 3 strategy) ──
    pb.add_argument(
        "--target-author",
        help="Restrict the embed-verify pass to one target canonical author.",
    )
    pb.add_argument(
        "--promote-threshold",
        type=float,
        default=0.80,
        help="Cosine score at which a quoted-phrase auto-row is promoted to rule+embed (default: 0.80).",
    )
    pb.add_argument(
        "--reject-threshold",
        type=float,
        default=0.50,
        help="Cosine score below which a quoted-phrase auto-row is auto-rejected (default: 0.50).",
    )
    pb.add_argument(
        "--allusion-threshold",
        type=float,
        default=0.85,
        help="Cosine score at which an embed-only cross-author neighbor becomes an alludes candidate (default: 0.85).",
    )
    pb.add_argument(
        "--allusion-top-k",
        type=int,
        default=3,
        help="Per-source-chunk maximum target neighbors to emit (default: 3).",
    )
    pb.add_argument(
        "--min-chunk-chars",
        type=int,
        default=80,
        help=(
            "Skip chunks shorter than this many characters in the allusion "
            "sweep. Filters out boilerplate (section banners like '§ 46', "
            "'Anmerkung', 'Articulus 1') that produce cosine~1.0 noise "
            "without semantic content (default: 80)."
        ),
    )
    pb.add_argument(
        "--pair",
        action="append",
        help=(
            "Allusion pair as 'Source/Target' (or 'Source Target'); repeatable. "
            "Defaults to a curated channel set; override to scope a focused run."
        ),
    )
    pb.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip PASS A (quoted-phrase verifier). Useful for an allusion-only sweep.",
    )
    pb.add_argument(
        "--skip-allusions",
        action="store_true",
        help="Skip PASS B (allusion sweep). Useful when only the quote verifier matters.",
    )
    # ── llm-verify flags (Phase 4 strategy) ──
    pb.add_argument(
        "--llm-backend",
        default="anthropic",
        choices=("none", "openai", "anthropic", "ollama"),
        help="LLM backend for --strategy llm-verify (default: anthropic).",
    )
    pb.add_argument(
        "--llm-model",
        help="Model name (default: claude-sonnet-5-5 for anthropic; gpt-4o-mini for openai; llama3.1 for ollama).",
    )
    pb.add_argument(
        "--llm-effort",
        choices=llm_mod.EFFORT_LEVELS,
        default=None,
        help=(
            "Anthropic output_config.effort for llm-verify "
            f"(default: {LLM_VERIFY_DEFAULT_EFFORT}, chosen by the #744 sweep). "
            "Ignored by the other backends."
        ),
    )
    pb.add_argument(
        "--llm-base-url",
        help=(
            "Override the backend's base URL (advanced; for local proxies / "
            "vendor mirrors). Non-default hosts require "
            "--unsafe-llm-base-url-host since the credential goes to "
            "whatever host is named here."
        ),
    )
    pb.add_argument(
        "--unsafe-llm-base-url-host",
        action="store_true",
        help=(
            "Explicit opt-in to send the LLM credential to a non-default "
            "host via --llm-base-url. Required for anything outside the "
            "vendor's API host or localhost."
        ),
    )
    pb.add_argument(
        "--max-llm-calls",
        type=int,
        default=100,
        help=(
            "Cost guard — caps total API calls for --strategy llm-verify "
            "(default: 100). The verifier stops when the budget is "
            "exhausted; re-running picks up where it left off."
        ),
    )
    pb.add_argument(
        "--max-rows",
        type=int,
        help=(
            "[--strategy llm-verify only] Cap the rows examined. Binds "
            "alongside --max-llm-calls × --batch-size, whichever is tighter; "
            "--resume continues from the last capped row."
        ),
    )
    pb.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Rows per LLM call for --strategy llm-verify (default: 10).",
    )
    pb.add_argument(
        "--min-confidence",
        type=float,
        help="Restrict --strategy llm-verify to rows with confidence >= this value.",
    )
    pb.add_argument(
        "--include-short-chunks",
        action="store_true",
        help=(
            "Don't skip rows whose SOURCE chunk is under 80 chars (the "
            "boilerplate-tied embed_only false-positives). Default is to "
            "skip — these almost always come back rejected and waste tokens. "
            "Target length is never a filter: short cited passages are normal "
            "for scripture (#265)."
        ),
    )
    pb.add_argument(
        "--include-strong",
        action="store_true",
        help=(
            "Don't skip rule_strong rows (Aquinas Philosophus etc.). Default "
            "is to skip — they're 0.92+ confidence from definitional "
            "conventions and don't gain much from LLM verification."
        ),
    )
    pb.add_argument(
        "--sleep-between-calls",
        type=float,
        default=0.0,
        help="Seconds to sleep between LLM calls (rate-limit friendly).",
    )
    pb.set_defaults(func=cmd_refs_build)

    # ── review (Phase 2 curator walker) ──
    prv = subs.add_parser(
        "review",
        help="Walk auto-detected refs, approve/reject one row at a time.",
    )
    _add_common_db_arg(prv)
    prv.add_argument(
        "--source-author",
        help="Restrict the walker to one source author (e.g. 'Aquinas').",
    )
    prv.add_argument(
        "--target-author",
        help="Restrict to one target author (e.g. 'Aristotle' for the Aquinas-Philosophus stream).",
    )
    prv.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum rows to show per session (default: 50).",
    )
    prv.set_defaults(func=cmd_refs_review)
