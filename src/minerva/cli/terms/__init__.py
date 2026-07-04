"""Curator commands for the term glossary.

Subcommands live in three sibling modules grouped by what they
operate on:

* ``crud``     — single-term life cycle (list / show / add) plus
                 ``canonical`` for the per-(work, language) flag.
* ``linking``  — schema-level browse and cross-link commands
                 (``works``, ``editions``, ``translations``,
                 ``render``, ``relate``).
* ``locators`` — locator-driven commands that anchor an occurrence
                 inside a chunk (``find``, ``tag``,
                 ``suggest-locator``).

This file's only job is :func:`register_subparsers` — the top-level
``minerva`` CLI calls it to wire ``minerva terms <subcommand>`` into
its argparse tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._io import _add_common_db_arg
from .bulk import cmd_terms_import
from .crud import (
    cmd_terms_add,
    cmd_terms_canonical,
    cmd_terms_list,
    cmd_terms_show,
)
from .lemmatize import cmd_terms_lemmatize
from .linking import (
    cmd_terms_editions,
    cmd_terms_relate,
    cmd_terms_render,
    cmd_terms_translations,
    cmd_terms_works,
)
from .locators import (
    cmd_terms_find,
    cmd_terms_suggest_locator,
    cmd_terms_tag,
)


def _cmd_aggregate_lemmas(args: argparse.Namespace) -> int:
    """Rebuild the lemma_counts materialized aggregate."""

    from ... import store
    from ...concordance import aggregate

    # Open through store.open_db so schema + migrations are applied:
    # the `lemma_counts` table this command rebuilds is created by
    # migration 0019, not the base schema. A raw connect would crash
    # with "no such table" on any index that predates 0019 and was
    # never re-opened via `minerva index`.
    conn = store.open_db(args.db)
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        summary = aggregate.build(conn, verbose=True)
    finally:
        conn.close()
    print(
        f"aggregate-lemmas: {summary['total']:,} rows in "
        f"{summary['elapsed_seconds']:.1f}s"
    )
    return 0


def register_subparsers(parent_subparsers: argparse._SubParsersAction) -> None:
    """Attach the ``terms`` subcommand to the top-level CLI parser.

    Called from :func:`minerva.cli.build_parser`. Splitting the
    declarations out of the entry-point keeps that file focused on
    the historical commands and lets the term-glossary commands
    evolve independently."""

    p_terms = parent_subparsers.add_parser("terms", help="Curator commands for the term glossary.")
    subs = p_terms.add_subparsers(dest="terms_cmd", required=True)

    # ── list ──
    pl = subs.add_parser("list", help="List terms.")
    _add_common_db_arg(pl)
    pl.add_argument("--lang", help="Filter by source language (e.g., grc, deu).")
    pl.add_argument("--like", help="Substring filter on source_form.")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_terms_list)

    # ── show ──
    ps = subs.add_parser("show", help="Show one term plus its renderings and occurrences.")
    _add_common_db_arg(ps)
    ps.add_argument("term_id_or_form", help="Numeric id or exact source_form.")
    ps.add_argument("--lang", help="Source language (only used when looking up by form).")
    ps.set_defaults(func=cmd_terms_show)

    # ── add ──
    pa = subs.add_parser("add", help="Create a new term.")
    _add_common_db_arg(pa)
    pa.add_argument("--form", required=True, help="Source form (e.g., 'λόγος').")
    pa.add_argument("--lang", required=True, help="ISO 639-3 source language.")
    pa.add_argument("--gloss", required=True, help="One-line English summary.")
    pa.add_argument("--description", help="Markdown body, '-' to read stdin.")
    pa.add_argument("--description-file", type=Path, help="Read description from a file.")
    pa.add_argument("--transliteration", help="Optional transliteration ('logos').")
    pa.add_argument("--lemma", help="Dictionary headword if different from --form.")
    pa.set_defaults(func=cmd_terms_add)

    # ── works / editions / translations / find ──
    pw = subs.add_parser("works", help="List works.")
    _add_common_db_arg(pw)
    pw.add_argument("--like", help="Substring filter on author or title.")
    pw.add_argument("--json", action="store_true")
    pw.set_defaults(func=cmd_terms_works)

    pe = subs.add_parser("editions", help="List editions.")
    _add_common_db_arg(pe)
    pe.add_argument("--work-id", type=int, help="Filter by work id.")
    pe.add_argument("--json", action="store_true")
    pe.set_defaults(func=cmd_terms_editions)

    pt = subs.add_parser("translations", help="List translations.")
    _add_common_db_arg(pt)
    pt.add_argument("--work-id", type=int, help="Filter by work id.")
    pt.add_argument("--json", action="store_true")
    pt.set_defaults(func=cmd_terms_translations)

    pf = subs.add_parser(
        "find",
        help="Resolve a (work, lang, section) locator to a chunk_id.",
    )
    _add_common_db_arg(pf)
    pf.add_argument("--work", required=True, help="Exact work title.")
    pf.add_argument("--lang", required=True, help="ISO 639-3 language.")
    pf.add_argument("--section", help="Exact section locator (e.g., '514a', '§44').")
    pf.add_argument("--limit", type=int, default=10)
    pf.add_argument("--json", action="store_true")
    pf.set_defaults(func=cmd_terms_find)

    # ── render ──
    pr = subs.add_parser(
        "render",
        help="Set a translator's default rendering of a term.",
    )
    _add_common_db_arg(pr)
    pr.add_argument("--term", dest="term_id", type=int, required=True)
    pr.add_argument("--translation", dest="translation_id", type=int, required=True)
    pr.add_argument(
        "--as",
        dest="rendering",
        required=True,
        help="The translator's chosen rendering (e.g., 'sublation').",
    )
    pr.add_argument("--note", help="Markdown justification, '-' for stdin.")
    pr.add_argument("--note-file", type=Path)
    pr.set_defaults(func=cmd_terms_render)

    # ── relate ──
    pre = subs.add_parser("relate", help="Record a relation between two terms.")
    _add_common_db_arg(pre)
    pre.add_argument("--a", type=int, required=True, help="First term id.")
    pre.add_argument("--b", type=int, required=True, help="Second term id.")
    pre.add_argument("--kind", help="Relation kind (synonym, contrast, cognate, …).")
    pre.add_argument("--note")
    pre.add_argument("--note-file", type=Path)
    pre.add_argument(
        "--symmetric",
        action="store_true",
        help="Insert the reverse relation too (B → A).",
    )
    pre.set_defaults(func=cmd_terms_relate)

    # ── tag (the heavy one) ──
    ptag = subs.add_parser(
        "tag",
        help="Mark an occurrence of a term in a specific source chunk.",
    )
    _add_common_db_arg(ptag)
    ptag.add_argument("--term", type=int, required=True, help="Term id.")
    ptag.add_argument("--chunk", required=True, help="chunk_id (use `terms find` first).")
    ptag.add_argument(
        "--occurrence",
        type=int,
        default=1,
        help="1-based index of which match in the chunk to tag.",
    )
    ptag.add_argument("--tradition", help="Interpretive tradition tag (free text).")
    ptag.add_argument(
        "--locator",
        help=(
            "Explicit citation locator, overriding the chunk's section. "
            "Use when the work's citation_system doesn't match what the "
            "parser put in chunks.section — most notably Critique of "
            "Pure Reason (citation_system='kant_ab'), where A/B page "
            "markers like 'A123' or 'B147' aren't yet auto-extracted "
            "into section values."
        ),
    )
    ptag.set_defaults(func=cmd_terms_tag)

    # ── canonical ──
    pcn = subs.add_parser(
        "canonical",
        help="Mark / unmark an edition as canonical for its (work, language) pair.",
    )
    _add_common_db_arg(pcn)
    pcn.add_argument("--edition", type=int, required=True)
    pcn.add_argument(
        "--unset",
        action="store_true",
        help="Mark as non-canonical instead of canonical.",
    )
    pcn.set_defaults(func=cmd_terms_canonical)

    # ── import ──
    pim = subs.add_parser(
        "import",
        help=(
            "Bulk-import a YAML glossary spec — declarative, "
            "idempotent. The spec carries terms + renderings + "
            "apply_to targets; the importer uses chunk_lemmas for "
            "languages with a lemmatizer (currently deu) and falls "
            "back to surface-form regex for the rest (currently grc)."
        ),
    )
    _add_common_db_arg(pim)
    pim.add_argument("path", type=Path, help="YAML spec file to import.")
    pim.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + count what would happen; no writes.",
    )
    pim.add_argument(
        "--only-work",
        metavar="TITLE",
        help="Restrict apply_to entries to this work title.",
    )
    pim.add_argument(
        "--report",
        choices=("text", "json"),
        default="text",
    )
    pim.set_defaults(func=cmd_terms_import)

    # ── lemmatize ──
    plm = subs.add_parser(
        "lemmatize",
        help=(
            "Populate the chunk_lemmas cache for one language. Run "
            "once after a fresh ingest; later runs skip chunks "
            "already cached. The glossary importer joins this cache "
            "against terms.lemma to find term occurrences."
        ),
    )
    _add_common_db_arg(plm)
    # choices come from the lemmatizer's supported set so a typo like
    # "de" is rejected at parse time (exit 2) instead of returning 0 as
    # a silent no-op that a pipeline mistakes for success (issue #67).
    from ...lemmatize import SUPPORTED_LANGUAGES

    plm.add_argument(
        "--lang",
        required=True,
        choices=sorted(SUPPORTED_LANGUAGES),
        help="ISO 639-3 source language.",
    )
    plm.add_argument(
        "--edition-id",
        type=int,
        help="Restrict to one edition; default is every chunk in the language.",
    )
    plm.add_argument(
        "--all",
        action="store_true",
        help="Re-process every chunk, not just those missing from the cache.",
    )
    plm.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts + show a sample tokenisation; no writes.",
    )
    plm.add_argument(
        "--skip-aggregate",
        action="store_true",
        help=(
            "Don't rebuild the lemma_counts table at the end of the "
            "lemmatize pass. Use when running multiple languages "
            "back-to-back and you'd rather rebuild aggregates once "
            "via `minerva terms aggregate-lemmas`."
        ),
    )
    plm.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help=(
            "spaCy `nlp.pipe` batch size (deu, fra, eng, grc, lat when "
            "LatinCy is installed). Ignored on Stanza-only paths (heb, "
            "ara, or grc/lat Stanza fallback)."
        ),
    )
    plm.add_argument(
        "--n-process",
        dest="n_process",
        type=int,
        default=4,
        help=(
            "spaCy `nlp.pipe` worker count for parallel tokenization. "
            "Each worker loads its own model copy (~80–250 MB). 4 is a "
            "safe default; -1 uses all cores. Ignored on Stanza backends."
        ),
    )
    plm.set_defaults(func=cmd_terms_lemmatize)

    # ── aggregate-lemmas ──
    pag = subs.add_parser(
        "aggregate-lemmas",
        help=(
            "Rebuild the lemma_counts materialized aggregate from "
            "chunk_lemmas. Auto-runs at the end of `terms lemmatize` "
            "unless --skip-aggregate; this command is for ad-hoc "
            "rebuilds (e.g. after a partial re-lemmatize)."
        ),
    )
    _add_common_db_arg(pag)
    pag.set_defaults(func=_cmd_aggregate_lemmas)

    # ── suggest-locator ──
    psl = subs.add_parser(
        "suggest-locator",
        help=(
            "Suggest A/B (or other) locators for a chunk that lacks one, "
            "by looking up sibling translations at the same relative "
            "document position. Useful for German KrV chunks since the "
            "zeno source doesn't preserve Kant's A/B marginal pagination."
        ),
    )
    _add_common_db_arg(psl)
    psl.add_argument("--chunk", required=True, help="chunk_id to align.")
    psl.add_argument("--json", action="store_true")
    psl.set_defaults(func=cmd_terms_suggest_locator)
