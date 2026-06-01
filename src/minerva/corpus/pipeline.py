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

from collections.abc import Iterable, Iterator
from pathlib import Path

from ..corpus_extract import IngestDepsMissing, extract_epub, extract_html, extract_pdf
from ..corpus_works import CorpusWork
from ..tei import Chunk
from .split_aquinas import split_aquinas
from .split_augustine import split_augustine
from .split_descartes import split_descartes, split_descartes_articles
from .split_kant import split_by_kant_ab
from .split_paragraphic import split_by_chapter, split_by_paragraph, split_by_section
from .split_spinoza import split_spinoza
from .split_zeno import split_zeno_pages

_SPLITTERS = {
    "section": split_by_section,
    "paragraph": split_by_paragraph,
    "chapter": split_by_chapter,
    "kant_ab": split_by_kant_ab,
    "descartes": split_descartes,
    "descartes_articles": split_descartes_articles,
    "spinoza": split_spinoza,
    "augustine": split_augustine,
    "aquinas": split_aquinas,
}


def parse_file(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        # ``work.pages`` (when set) carves a sub-range of the PDF for
        # this CorpusWork. Used by the Cambridge "Practical Philosophy"
        # Gregor omnibus, where one file contains a dozen Kant works
        # at well-known page ranges from the bookmark TOC.
        text = extract_pdf(path, pages=work.pages)
    elif suffix == ".epub":
        text = extract_epub(path)
    elif suffix in {".html", ".htm"}:
        # zeno.org dumps from `perseus/download_hegel_de.py` carry
        # ZENO_PAGE markers — we use those for clean chapter boundaries
        # rather than guessing headings from extracted plain text.
        raw = path.read_text(encoding="utf-8", errors="replace")
        if "ZENO_PAGE:" in raw:
            yield from split_zeno_pages(raw, work, path)
            return
        text = extract_html(path)
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
    yield from chunks


def parse_dir(
    directory: Path,
    find_work: object,
    *,
    label: str,
) -> Iterable[Chunk]:
    """Walk a directory; dispatch each known file to its splitter.

    ``find_work`` must be the author module's ``find_work`` callable
    (e.g. ``hegel_works.find_work``, ``kant_works.find_work``).

    Multi-work files: when ``find_work`` returns a CorpusWork whose ``pages``
    field is set, the file may be claimed by multiple Works at
    different page ranges. We support this by calling ``find_works``
    (plural) on the module if available — that callable returns the
    full list of Works claiming the file. Each one runs through
    ``parse_file`` with its own ``pages`` slice. This is how the
    Cambridge "Practical Philosophy" Gregor PDF unpacks into 12
    separate CorpusWork rows.
    """

    # Discover the plural variant on whichever works module supplied
    # `find_work`. If unavailable, fall back to single-CorpusWork-per-file
    # behaviour identical to the pre-multi-work version.
    find_works = getattr(find_work, "__self__", None) and getattr(
        find_work.__self__, "find_works", None
    )
    if find_works is None:
        # `find_work` is a module-level function; look up its sibling
        # in the same module if present.
        mod = getattr(find_work, "__module__", None)
        if mod is not None:
            import sys as _sys

            mod_obj = _sys.modules.get(mod)
            if mod_obj is not None and hasattr(mod_obj, "find_works"):
                find_works = mod_obj.find_works

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
                print(f"{label}: failed to parse {path.name!r} as {work.code!r}: {exc}")
