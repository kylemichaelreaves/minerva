"""Declarative registry of corpus ingest sources."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

from .. import tei
from ..paths import REPO_ROOT

PathKind = Literal["dir", "file"]
ParseFn = Callable[[Path], Iterator[tei.Chunk]]


@dataclasses.dataclass(frozen=True)
class IngestSource:
    id: str
    default_path: Path
    parse: ParseFn
    path_kind: PathKind = "dir"
    param_name: str | None = None
    cli_flag: str | None = None
    help: str = ""

    @property
    def kwarg_name(self) -> str:
        return self.param_name or f"{self.id}_dir" if self.path_kind == "dir" else f"{self.id}_text"

    @property
    def argparse_flag(self) -> str:
        if self.cli_flag:
            return self.cli_flag
        name = self.kwarg_name.replace("_", "-")
        return f"--{name}"

    def path_present(self, path: Path | None) -> bool:
        if path is None:
            return False
        return path.is_file() if self.path_kind == "file" else path.is_dir()


# --- Parser factories (lazy imports keep optional deps off the critical path) ---


def _tei_dir(corpus: str, author: str) -> ParseFn:
    def parse(path: Path) -> Iterator[tei.Chunk]:
        yield from tei.parse_dir(path, corpus=corpus, author=author)

    return parse


def _module_parse_dir(module: str, attr: str = "parse_dir") -> ParseFn:
    def parse(path: Path) -> Iterator[tei.Chunk]:
        import importlib

        mod = importlib.import_module(f"minerva.{module}")
        yield from getattr(mod, attr)(path)

    return parse


def _corpus_label(label: str, works_module: str) -> ParseFn:
    def parse(path: Path) -> Iterator[tei.Chunk]:
        import importlib

        from .. import corpus as corpus_parse

        works = importlib.import_module(f"minerva.authors.{works_module}")
        yield from corpus_parse.parse_dir(path, works.find_work, label=label)

    return parse


def _presocratic_parse(path: Path) -> Iterator[tei.Chunk]:
    from minerva.sources import presocratic

    yield from presocratic.parse_file(path)


def _drama_dir(corpus: str, author: str) -> ParseFn:
    """Factory for the Greek-tragedy parser. Mirrors ``_tei_dir`` but
    routes through ``tei_drama.parse_dir``, which handles the verse-
    drama TEI P5 markup (``<l n=>`` lines + ``<sp><speaker>`` blocks)
    and looks up canonical play titles from ``tragedians.TRAGEDIANS``."""

    def parse(path: Path) -> Iterator[tei.Chunk]:
        from minerva.sources import tei_drama

        yield from tei_drama.parse_dir(path, corpus=corpus, author=author)

    return parse


# --- Default paths (mirror legacy ingest.py) ---

_P = REPO_ROOT

INGEST_SOURCES: tuple[IngestSource, ...] = (
    IngestSource(
        "plato",
        _P / "perseus" / "raw_xml",
        _tei_dir("plato", "Plato"),
        help="Directory of Plato Perseus XML files.",
    ),
    IngestSource(
        "aristotle",
        _P / "perseus" / "raw_xml_aristotle",
        _tei_dir("aristotle", "Aristotle"),
        help="Directory of Aristotle Perseus XML files.",
    ),
    IngestSource(
        "homer",
        _P / "perseus" / "raw_xml_homer",
        _tei_dir("homer", "Homer"),
        help="Directory of Homer Perseus XML files (Iliad + Odyssey).",
    ),
    IngestSource(
        "aeschylus",
        _P / "perseus" / "raw_xml_aeschylus",
        _drama_dir("aeschylus", "Aeschylus"),
        help="Directory of Aeschylus verse-drama TEI P5 files (canonical-greekLit).",
    ),
    IngestSource(
        "sophocles",
        _P / "perseus" / "raw_xml_sophocles",
        _drama_dir("sophocles", "Sophocles"),
        help="Directory of Sophocles verse-drama TEI P5 files (canonical-greekLit).",
    ),
    IngestSource(
        "euripides",
        _P / "perseus" / "raw_xml_euripides",
        _drama_dir("euripides", "Euripides"),
        help="Directory of Euripides verse-drama TEI P5 files (canonical-greekLit).",
    ),
    IngestSource(
        "lxx",
        _P / "perseus" / "raw_xml_lxx",
        _module_parse_dir("sources.tei_lxx"),
        help="Directory of Septuagint TEI P5 XML from First1KGreek tlg0527.",
    ),
    IngestSource(
        "nt",
        _P / "data" / "nt" / "raw_grc",
        _module_parse_dir("sources.sblgnt"),
        help="Directory of SBLGNT per-book XML files (Matt.xml...Rev.xml).",
    ),
    IngestSource(
        "vulgate",
        _P / "data" / "vulgate" / "raw_lat",
        _module_parse_dir("sources.vulgate"),
        help="Directory of Clementine Vulgate per-book .lat files.",
    ),
    IngestSource(
        "luther_1912",
        _P / "data" / "luther_1912" / "raw_deu",
        _module_parse_dir("sources.luther_1912"),
        help="Directory holding the Luther 1912 Zefania XML (single luther_1912.xml file).",
    ),
    IngestSource(
        "luther_1545",
        _P / "data" / "luther_1545" / "raw_deu",
        _module_parse_dir("sources.luther_1545"),
        help="Directory holding the Luther 1545 Zefania XML (Letzte-Hand, Frühneuhochdeutsch).",
    ),
    IngestSource(
        "kjv",
        _P / "data" / "kjv" / "raw_eng",
        _module_parse_dir("sources.kjv"),
        help="Directory holding the King James (1611) Zefania XML.",
    ),
    IngestSource(
        "sacy",
        _P / "data" / "sacy" / "raw_fra",
        _module_parse_dir("sources.sacy"),
        help="Directory holding the Lemaistre de Sacy (1696) per-book files (HTML or text).",
    ),
    IngestSource(
        "hebrew_mt",
        _P / "data" / "hebrew_mt" / "raw",
        _module_parse_dir("sources.hebrew_mt"),
        help="Directory of OSHB Westminster Leningrad Codex OSIS XML files (Gen.xml ... 2Chr.xml).",
    ),
    IngestSource(
        "quran",
        _P / "data" / "quran" / "raw",
        _module_parse_dir("sources.quran"),
        help="Directory holding the Tanzil Uthmani Quran XML (quran-uthmani.xml).",
    ),
    IngestSource(
        "aristotle_first1k",
        _P / "perseus" / "raw_xml_aristotle_first1k",
        _module_parse_dir("sources.tei_p5"),
        help="Directory of supplemental First1KGreek Aristotle TEI P5 XML.",
    ),
    IngestSource(
        "aristotle_ica",
        _P / "perseus" / "raw_text_aristotle_ica",
        _module_parse_dir("sources.ica_parse"),
        help="Directory of ICA English Aristotle plain-text translations.",
    ),
    IngestSource(
        "hegel",
        _P / "data" / "hegel",
        _corpus_label("hegel", "hegel_works"),
        help="Directory of Hegel PDFs / EPUBs / HTML files (see authors/hegel_works.py).",
    ),
    IngestSource(
        "kant",
        _P / "data" / "kant",
        _corpus_label("kant", "kant_works"),
        help="Directory of Kant German originals from zeno.org (see authors/kant_works.py).",
    ),
    IngestSource(
        "kant_en",
        _P / "data" / "kant_en",
        _corpus_label("kant-en", "kant_works"),
        help="Directory of Cambridge English Kant PDFs (see authors/kant_works.py).",
    ),
    IngestSource(
        "descartes_la",
        _P / "data" / "descartes" / "raw_la",
        _corpus_label("descartes-la", "descartes_works"),
        help="Directory of Descartes Latin originals (see authors/descartes_works.py).",
    ),
    IngestSource(
        "descartes_fr",
        _P / "data" / "descartes" / "raw_fr",
        _corpus_label("descartes-fr", "descartes_works"),
        help="Directory of Descartes French translations (see authors/descartes_works.py).",
    ),
    IngestSource(
        "spinoza_la",
        _P / "data" / "spinoza" / "raw_la",
        _corpus_label("spinoza-la", "spinoza_works"),
        help="Directory of Spinoza Latin originals (see authors/spinoza_works.py).",
    ),
    IngestSource(
        "augustine_la",
        _P / "data" / "augustine" / "raw_la",
        _corpus_label("augustine-la", "augustine_works"),
        help="Directory of Augustine Latin originals (see authors/augustine_works.py).",
    ),
    IngestSource(
        "aquinas_la",
        _P / "data" / "aquinas" / "raw_la",
        _corpus_label("aquinas-la", "aquinas_works"),
        help="Directory of Aquinas Latin originals (see authors/aquinas_works.py).",
    ),
    IngestSource(
        "hobbes",
        _P / "data" / "hobbes" / "raw_eng",
        _corpus_label("hobbes", "hobbes_works"),
        help="Directory of Hobbes Gutenberg texts (see authors/hobbes_works.py).",
    ),
    IngestSource(
        "hobbes_la",
        _P / "data" / "hobbes" / "raw_lat",
        _module_parse_dir("sources.hobbes_la"),
        help="Directory of Hobbes Latin IA-OCR texts (see hobbes_la.py).",
    ),
    IngestSource(
        "pascal",
        _P / "data" / "pascal" / "raw_fra",
        _corpus_label("pascal", "pascal_works"),
        help="Directory of Pascal Gutenberg texts (see authors/pascal_works.py).",
    ),
    IngestSource(
        "hume",
        _P / "data" / "hume" / "raw_eng",
        _corpus_label("hume", "hume_works"),
        help="Directory of Hume Gutenberg texts (see authors/hume_works.py).",
    ),
    IngestSource(
        "locke",
        _P / "data" / "locke" / "raw_eng",
        _corpus_label("locke", "locke_works"),
        help="Directory of Locke Gutenberg texts (see authors/locke_works.py).",
    ),
    IngestSource(
        "rousseau",
        _P / "data" / "rousseau" / "raw_fra",
        _corpus_label("rousseau", "rousseau_works"),
        help="Directory of Rousseau Gutenberg texts (see authors/rousseau_works.py).",
    ),
    IngestSource(
        "marx",
        _P / "data" / "marx" / "raw_deu",
        _corpus_label("marx", "marx_works"),
        help="Directory of clean Marx HTML-derived texts (see authors/marx_works.py).",
    ),
    IngestSource(
        "marx_ocr",
        _P / "data" / "marx" / "raw_deu_ocr",
        _module_parse_dir("sources.marx_de"),
        help="Directory of Marx Kapital IA-OCR texts (see marx_de.py).",
    ),
    IngestSource(
        "nietzsche",
        _P / "data" / "nietzsche" / "raw_deu",
        _corpus_label("nietzsche", "nietzsche_works"),
        help="Directory of Nietzsche zeno.org HTML files (see authors/nietzsche_works.py).",
    ),
    IngestSource(
        "cicero_la",
        _P / "data" / "cicero" / "raw_la",
        _corpus_label("cicero-la", "cicero_works"),
        help="Directory of Cicero Latin works (la.wikisource transcriptions).",
    ),
    IngestSource(
        "cicero_en",
        _P / "data" / "cicero" / "raw_eng",
        _corpus_label("cicero-en", "cicero_works"),
        help="Directory of Cicero English translations.",
    ),
    IngestSource(
        "lucretius",
        _P / "data" / "lucretius" / "raw",
        _tei_dir("lucretius", "Lucretius"),
        help="Directory of Lucretius (Latin + English, Perseus dltext + PG Leonard).",
    ),
    IngestSource(
        "epictetus",
        _P / "data" / "epictetus" / "raw",
        _tei_dir("epictetus", "Epictetus"),
        help="Directory of Epictetus (Greek + English, Perseus dltext).",
    ),
    IngestSource(
        "marcus_aurelius",
        _P / "data" / "marcus_aurelius" / "raw",
        _corpus_label("marcus-aurelius", "marcus_aurelius_works"),
        help="Directory of Marcus Aurelius (Greek el.wikisource + PG Long Meditations).",
    ),
    IngestSource(
        "presocratic",
        _P / "data" / "presocratic" / "diefragmentederv12diel_hocr_searchtext.txt",
        _presocratic_parse,
        path_kind="file",
        param_name="presocratic_text",
        cli_flag="--presocratic-text",
        help=(
            "Path to the OCR'd Diels Vorsokratiker text "
            "(see authors/presocratic_works.py for the Phase-1 philosopher list)."
        ),
    ),
    # ─── Pre-philosophical Greek (6th c. BCE) ───────────────────
    # Theognis: aristocratic elegist, subject of Nietzsche's 1867
    # philological dissertation. Source TBD in Phase B — likely
    # Perseus Bergk edition + Edmonds Loeb 1931 English.
    IngestSource(
        "theognis",
        _P / "data" / "theognis",
        _corpus_label("theognis", "theognis_works"),
        help="Directory of Theognidea (Greek + English; Phase B sources Perseus + Loeb).",
    ),
    # Aesop: pre-philosophical fabulist; source of Hegel's "Hic
    # Rhodus, hic salta" / "Hier ist die Rose" reference. Ingest
    # covers Babrius (grc) and Phaedrus (lat) verse traditions.
    # Phaedrus is sourced from PerseusDL canonical-latinLit phi0975 —
    # TEI P5 with EpiDoc namespacing and ``<l>`` verse-line bodies
    # (not the older Perseus TEI.2). Walks via ``tei_p5.parse_dir``
    # in its flat-layout mode, which handles both Latin and English
    # facing-page XML via the ``_lat`` / ``_eng`` filename suffix.
    # Phaedrus Latin verse + Perseus English. The dedicated tei_p5
    # parser claims the .xml files; .txt files (the Babrius half,
    # below) are silently skipped here and handled by the
    # _corpus_label-routed entry that follows.
    IngestSource(
        "aesop",
        _P / "data" / "aesop",
        _module_parse_dir("sources.tei_p5"),
        help="Directory of Aesop's Fables — Phaedrus Latin + English (Perseus TEI P5).",
    ),
    # Babrius Greek verse + Davies English — archive.org OCR
    # extracted by perseus/download_babrius.py into plain .txt.
    # Mirrors the Origen pattern (two parsers, same data dir,
    # each handling its own file types).
    IngestSource(
        "aesop_babrius",
        _P / "data" / "aesop",
        _corpus_label("aesop", "aesop_works"),
        help="Directory of Aesop's Fables — Babrius (archive.org OCR plain text).",
    ),
    # ─── Patristic ─────────────────────────────────────────────
    # Origen *Contra Celsum*: First1KGreek TLG 2042 (Koetschau GCS
    # 1899) + Crombie ANF 1872 English. Hosts all extant Celsus
    # fragments — Celsus himself is an out-of-corpus reference
    # target only (no corpus slug).
    #
    # Wired as TWO IngestSource entries pointing at the same data
    # directory: the Greek is First1KGreek TEI P5 and walks via
    # ``tei_p5.parse_dir`` (flat single-work layout — see that
    # module); the English is NewAdvent HTML and walks via the
    # corpus-label pipeline. Both parsers see only the files they
    # know how to handle (the TEI P5 path globs ``*_grc.xml``, the
    # corpus-label path skips ``.xml`` files — see pipeline.parse_file).
    IngestSource(
        "origen_grc",
        _P / "data" / "origen",
        _module_parse_dir("sources.tei_p5"),
        help="Directory of Origen *Contra Celsum* Greek (First1KGreek TLG 2042, TEI P5).",
    ),
    IngestSource(
        "origen_eng",
        _P / "data" / "origen",
        _corpus_label("origen", "origen_works"),
        help="Directory of Origen *Contra Celsum* English (NewAdvent / Crombie ANF 1872 HTML).",
    ),
    # ─── Early Modern (French) — additional ───────────────────
    # Henri de Boulainvilliers (1658-1722). Proximate historical
    # source for Nietzsche's Frankish-conquest / blond-beast material
    # (GM I.5/I.11). Single IngestSource for both French originals
    # and the rare 1739 English Dryden translation — the lang column
    # comes from each CorpusWork's declaration, so the pipeline
    # parses every file in the dir correctly without needing two
    # IngestSources. See ``add-boulainvilliers-plan`` memory.
    IngestSource(
        "boulainvilliers",
        _P / "data" / "boulainvilliers",
        _corpus_label("boulainvilliers", "boulainvilliers_works"),
        help="Directory of Boulainvilliers (French originals + 1739 Dryden English).",
    ),
    # ─── 19th-c French mediation chain to Nietzsche ──────────────
    # Arthur de Gobineau — *Essai sur l'inégalité des races
    # humaines* (1853-55, 4 vols). The racial-determinism
    # reformulation of Boulainvilliers's Frankish thesis.
    IngestSource(
        "gobineau",
        _P / "data" / "gobineau",
        _corpus_label("gobineau", "gobineau_works"),
        help="Directory of Gobineau (Essai sur l'inégalité — 4 French volumes).",
    ),
    # Ernest Renan — *Vie de Jésus* (1863), *L'Antéchrist* (1877),
    # *Histoire du peuple d'Israël* (1887-93, 5 vols). Nietzsche's
    # direct target in *Der Antichrist*; the priestly-class material
    # in the Histoire is GM I.7-8's source.
    IngestSource(
        "renan",
        _P / "data" / "renan",
        _corpus_label("renan", "renan_works"),
        help="Directory of Renan (Vie de Jésus, L'Antéchrist, Peuple d'Israël 5 vols).",
    ),
)


def default_paths_by_param() -> dict[str, Path]:
    return {s.kwarg_name: s.default_path for s in INGEST_SOURCES}


def build_iter_corpus_kwargs(**overrides: Path | None) -> dict[str, Path | None]:
    """Map legacy keyword names to paths, applying overrides."""
    defaults = default_paths_by_param()
    out: dict[str, Path | None] = {}
    for source in INGEST_SOURCES:
        key = source.kwarg_name
        if key in overrides:
            out[key] = overrides[key]
        else:
            out[key] = defaults[key]
    return out


def iter_registered_chunks(
    paths: dict[str, Path | None],
    *,
    only: frozenset[str] | None = None,
    per_source_timing: bool = False,
) -> Iterator[tei.Chunk]:
    """Walk every configured corpus source whose path exists on disk.

    ``only``: when set, only sources whose ``IngestSource.id`` matches
    are walked. Used by ``minerva ingest --only <id>[,<id>...]``
    (Phase 1b of the 2026-05-29 remediation plan) to iterate one or
    two corpora during parser-development cycles instead of all ~40.

    ``per_source_timing``: when true, prints a ``timing: ingest:<id>
    Xs (Ny chunks)`` line to stderr after each source completes. The
    flag is off by default so library callers (non-CLI) don't get
    surprise stderr noise; ``cmd_ingest`` flips it on under
    ``--timing`` or implicitly whenever a single source took noticeable
    wall time.
    """

    import sys as _sys
    import time as _time

    for source in INGEST_SOURCES:
        if only is not None and source.id not in only:
            continue
        path = paths.get(source.kwarg_name)
        if not source.path_present(path):
            continue
        if not per_source_timing:
            yield from source.parse(path)  # type: ignore[arg-type]
            continue
        start = _time.perf_counter()
        n = 0
        for chunk in source.parse(path):  # type: ignore[arg-type]
            n += 1
            yield chunk
        elapsed = _time.perf_counter() - start
        # Round to centiseconds; lots of trivial sources finish in
        # <100 ms and a full-precision float just clutters the output.
        print(
            f"timing: ingest:{source.id}  {elapsed:.2f}s ({n} chunks)",
            file=_sys.stderr,
        )
