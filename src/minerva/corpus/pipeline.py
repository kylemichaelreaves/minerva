"""Format dispatch + ingest driver.

`parse_file` figures out how to extract text from one file (PDF /
EPUB / HTML), picks the splitter the work's `locator` field names,
and yields chunks. `parse_dir` walks a directory, looks each file up
in a corpus-specific `find_work` table, and routes through
`parse_file`.

Multi-work files (the Cambridge Gregor "Practical Philosophy"
omnibus, where one PDF holds twelve Kant works at known page ranges)
are supported via an optional `find_works` (plural) callable on the
works module.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from ..corpus_extract import (
    IngestDepsMissing,
    extract_epub,
    extract_html,
    extract_ocr_pages,
    extract_pdf,
)
from ..corpus_works import CorpusWork
from ..tei import Chunk
from .editorial_runs import apply_editorial_runs
from .split_aquinas import split_aquinas
from .split_augustine import split_augustine
from .split_descartes import split_descartes, split_descartes_articles
from .split_descartes_objections import split_descartes_objections
from .split_ekgwb import split_ekgwb
from .split_hegel_pr_de import split_hegel_pr_de
from .split_hegel_pr_epub import split_hegel_pr_epub
from .split_kant import split_by_kant_ab
from .split_kapital_mew import split_kapital_mew
from .split_paragraphic import (
    split_by_chapter,
    split_by_fable,
    split_by_paragraph,
    split_by_section,
)
from .split_platon_werke import split_platon_werke
from .split_spinoza import split_spinoza
from .split_spinoza_ethica import split_spinoza_ethica
from .split_stephanus_de import split_stephanus_de
from .split_zeno import split_zeno_pages

# Per-run parse-failure log. ``parse_dir`` is a generator consumed
# lazily through closures in ``ingest/registry.py``, so it can't
# return a status without breaking its iterator contract — instead
# every caught per-file failure is recorded here. ``cmd_ingest``
# calls :func:`reset_parse_failures` before a run and
# :func:`parse_failures` after the output is written, so a partial
# parse still produces JSONL for what succeeded but the run exits
# non-zero. The parallel ingest workers do the same inside their
# subprocess and ship the list back in the worker result dict.
_PARSE_FAILURES: list[str] = []


def reset_parse_failures() -> None:
    """Clear the per-run failure log (call before starting a parse run)."""

    _PARSE_FAILURES.clear()


def parse_failures() -> list[str]:
    """Return the failures recorded since the last reset."""

    return list(_PARSE_FAILURES)


def record_parse_failure(msg: str) -> None:
    """Append one parse failure and print it to stderr."""

    _PARSE_FAILURES.append(msg)
    print(msg, file=sys.stderr)


def _yield_structured(
    chunks: Iterator[Chunk],
    path: Path,
    work: CorpusWork,
) -> Iterator[Chunk]:
    """Materialize a structure-aware splitter and warn on zero output."""

    materialized = list(chunks)
    if not materialized:
        print(
            f"parse: {path.name!r} produced 0 chunks under {work.locator!r} "
            f"(structured parser; no fallback available)"
        )
    yield from materialized


_SPLITTERS = {
    "section": split_by_section,
    "paragraph": split_by_paragraph,
    "chapter": split_by_chapter,
    "fable": split_by_fable,
    "kant_ab": split_by_kant_ab,
    "descartes": split_descartes,
    "descartes_articles": split_descartes_articles,
    "spinoza": split_spinoza,
    "augustine": split_augustine,
    "aquinas": split_aquinas,
}


def parse_file(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    suffix = path.suffix.lower()
    if path.name.lower().endswith(".ocr.json"):
        # A re-OCR artefact standing in for a scan whose embedded text
        # layer is unusable (#540). Checked before the suffix dispatch
        # because `.ocr.json`'s suffix is `.json`, which means nothing
        # else here. Everything downstream — page furniture, splitters,
        # locators — is unchanged: this swaps where the page text comes
        # from, not what is done with it.
        text = extract_ocr_pages(path)
    elif suffix == ".pdf":
        if work.locator == "platon_werke":
            # "Platon: die Werke" — one PDF holding every dialogue + the
            # Letters. The multi-work splitter reads the pages directly
            # (heading detection + Stephanus-marker reconstruction), so it
            # bypasses the flat extract_pdf + single-work _SPLITTERS path.
            yield from _yield_structured(split_platon_werke(path, work), path, work)
            return
        # ``work.pages`` (when set) carves a sub-range of the PDF for
        # this CorpusWork. Used by the Cambridge "Practical Philosophy"
        # Gregor omnibus, where one file contains a dozen Kant works
        # at well-known page ranges from the bookmark TOC.
        text = extract_pdf(path, pages=work.pages)
    elif suffix == ".epub":
        if work.locator == "pr_structured":
            # Hegel PR: structure-aware parser reads the EPUB markup
            # directly (typed main/remark/addition chunks per §), not the
            # flattened text. See split_hegel_pr_epub.
            yield from _yield_structured(split_hegel_pr_epub(path, work), path, work)
            return
        text = extract_epub(path)
    elif suffix in {".html", ".htm"}:
        # zeno.org dumps from `perseus/download_hegel_de.py` carry
        # ZENO_PAGE markers — we use those for clean chapter boundaries
        # rather than guessing headings from extracted plain text.
        raw = path.read_text(encoding="utf-8", errors="replace")
        if work.locator == "pr_de_structured":
            # Hegel PR (German): §-aware parser over the zeno.org markup,
            # splicing the Gans-OCR Zusätze. See split_hegel_pr_de.
            yield from _yield_structured(split_hegel_pr_de(path, work), path, work)
            return
        if work.locator == "spinoza_ethica":
            # Spinoza's Ethica (Latin): structure-aware parser over the
            # thelatinlibrary.com per-Part markup — splits each proposition
            # into its geometric apparatus and types Scholia as 'remark'.
            yield from _yield_structured(split_spinoza_ethica(path, work), path, work)
            return
        if work.locator == "descartes_objections":
            # Objections & Réponses (fr.wikisource Parsoid HTML):
            # voice-aware parser typing objector paragraphs
            # block_type='objection' with the objector in `speaker`.
            yield from _yield_structured(split_descartes_objections(path, work), path, work)
            return
        if work.locator == "kapital_mew":
            # Das Kapital I–III (mlwerke.de MEW pages via Wayback):
            # paragraph chunks with MEW page numbers + Marx's own
            # footnotes typed 'remark'. See split_kapital_mew.
            yield from _yield_structured(split_kapital_mew(path, work), path, work)
            return
        if "ZENO_PAGE:" in raw:
            yield from _yield_structured(split_zeno_pages(raw, work, path), path, work)
            return
        if work.locator == "ekgwb":
            # eKGWB Nachlass pages: the splitter needs the raw HTML
            # structure (div1/head/txt_block), not extracted plain text.
            yield from _yield_structured(split_ekgwb(raw, work, path), path, work)
            return
        text = extract_html(path)
    elif suffix == ".hocr":
        # MDZ per-page hOCR (Schleiermacher Der Staat) — the splitter
        # needs the raw hOCR (word bounding boxes carry the marginal
        # Stephanus numbers), not extracted plain text.
        raw = path.read_text(encoding="utf-8", errors="replace")
        yield from _yield_structured(split_stephanus_de(raw, work, path), path, work)
        return
    elif suffix == ".txt":
        # Descartes-style plain-text drops from Gutenberg, pre-split
        # by `perseus/download_descartes.py` into one work per file.
        # No extraction step needed — the splitter walks the raw text.
        text = path.read_text(encoding="utf-8")
    elif suffix == ".xml":
        # XML files (TEI.2, TEI P5, EpiDoc) are handled by dedicated
        # parsers (``tei.parse_dir`` / ``tei_p5.parse_dir`` / etc.)
        # wired into ``ingest/registry.py``. When the corpus-label
        # pipeline is also pointed at the same directory (e.g. Origen,
        # where ``contra_celsum_grc.xml`` and ``contra_celsum_eng.html``
        # share a folder and the Greek goes through ``tei_p5``), the
        # `.xml` file is claimed by its `find_work` entry but extracted
        # by the other pipeline. Skip silently here so the two parsers
        # can coexist without a `ValueError` blowing up the reingest.
        return
    else:
        raise ValueError(f"unsupported file extension {suffix!r} for {path.name}")
    splitter = _SPLITTERS[work.locator]
    chunks = list(splitter(text, work, path))
    # Fallback: if the configured locator produced nothing (a translation
    # without paragraph numbering, say, or with a heading style that doesn't
    # match `_HEADING_RE`), retry with `chapter` so we still index *some*
    # content rather than silently dropping the whole work.
    if not chunks and work.locator != "chapter":
        print(
            f"parse: {path.name!r} produced 0 chunks under '{work.locator}'; "
            f"retrying with 'chapter' fallback"
        )
        chunks = list(split_by_chapter(text, work, path))
    yield from apply_editorial_runs(chunks, work)


def parse_dir(
    directory: Path,
    find_work: Callable[[str], CorpusWork | None],
    *,
    label: str,
    find_works: Callable[[str], list[CorpusWork]] | None = None,
) -> Iterable[Chunk]:
    """Walk a directory; dispatch each known file to its splitter.

    ``find_work`` must be the author module's ``find_work`` callable
    (e.g. ``hegel_works.find_work``, ``kant_works.find_work``).

    Multi-work files: when ``find_work`` returns a CorpusWork whose ``pages``
    field is set, the file may be claimed by multiple Works at
    different page ranges. Pass the module's ``find_works`` (plural)
    callable explicitly — it returns the full list of Works claiming a
    file, and each one runs through ``parse_file`` with its own
    ``pages`` slice. This is how the Cambridge "Practical Philosophy"
    Gregor PDF unpacks into 12 separate CorpusWork rows.

    ``find_works`` must be passed explicitly: ``find_work`` callables
    built by ``make_find_work`` are closures whose ``__module__`` is
    ``minerva.corpus_works``, so reflective sibling lookup can never
    find the author module's plural variant.
    """

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        works_for_path: list[CorpusWork] = []
        if find_works is not None:
            works_for_path = list(find_works(path.name))
        else:
            single = find_work(path.name)
            if single is not None:
                works_for_path = [single]
        if not works_for_path:
            print(f"{label}: skipping unknown file {path.name!r}")
            continue
        for work in works_for_path:
            try:
                yield from parse_file(path, work)
            except IngestDepsMissing:
                raise
            except Exception as exc:  # one bad file shouldn't kill the whole ingest
                record_parse_failure(
                    f"{label}: failed to parse {path.name!r} as {work.code!r}: {exc}"
                )
