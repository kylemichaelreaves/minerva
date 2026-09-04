"""Structure-aware parser for Spinoza's *Ethica* (Latin, thelatinlibrary.com).

Unlike the flat ``ethica.txt`` (one merged chunk per proposition — statement
+ demonstration + scholium + corollary fused), the Latin Library edition
labels the full geometric apparatus inline, so we can split each proposition
into its parts and, crucially, separate the **Scholia** (where Spinoza's
philosophy lives) as their own retrievable, citable units.

The five Part pages (``ethica_ll_<N>.html``) are HTML: each logical unit is a
``<p>`` led by a bold label. Headers (DEFINITIONES / AXIOMATA / POSTULATA /
AFFECTUUM DEFINITIONES / APPENDIX) set a numbering context under which bare
``I .`` / ``II .`` items fall; PROPOSITIO opens a proposition carrying
DEMONSTRATIO / ALITER (alt. demonstration) / SCHOLIUM / COROLLARIUM;
EXPLICATIO attaches to the preceding definition; Part IV's APPENDIX is a run
of CAPUT chapters.

Locators match the corpus convention (``split_spinoza``): ``E I, P7``,
``E I, P7 Dem.``, ``E I, P7 Schol.``, ``E I, Def. 1``, ``E I, App.``. Only
SCHOLIUM / EXPLICATIO get ``block_type='remark'`` (authorial elaboration set
apart from the formal argument); everything else is body. All of it is
Spinoza's own words — nothing is excluded from retrieval.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..sources._roman import roman_to_int
from ..tei import Chunk, _make_chunk_id, _norm_text

_PART_RE = re.compile(r"_(\d)\.html?$", re.I)
_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
_NUM_ITEM_RE = re.compile(r"^([IVXLC]+)\s*\.\s+(.*)", re.S)
_LABEL_RE = re.compile(
    r"^(PROPOSITIO|DEMONSTRATIO|SCHOLIUM|COROLLARIUM|COROLLARIA|ALITER|EXPLICATIO|"
    r"LEMMA|CAPUT|POSTULATUM|DEFINITIO|AXIOMA)\b\.?\s*([IVXLC]+|\d+)?\s*[:.]?\s*(.*)",
    re.S | re.I,
)
# PRÆFATIO / PRAEFATIO opener — anchored so it never catches "PROPOSITIO"
# (which also starts "PR" and whose affect-heavy bodies often contain the
# substring "fatio"). Part IV lost 65 of 73 propositions to that bug.
_PRAEF_RE = re.compile(r"^PR[AÆ]E?FATIO\b", re.I)
# Section-context headers (no chunk of their own — they set the numbering
# mode for the bare "I ." items that follow). Note: only the PLURAL forms
# are headers; the SINGULAR "AXIOMA: <content>" (Part IV) is a labelled item
# handled via _LABEL_RE, so it isn't listed here.
_HEADERS = {
    "DEFINITIONES": "def",
    "AXIOMATA": "axiom",
    "POSTULATA": "postulate",
    "AFFECTUUM DEFINITIONES": "affectdef",
}


def _label_number(tok: str | None) -> int | None:
    r"""A label's number group → int, or None when there isn't one.

    `_LABEL_RE`'s group is Roman **or** arabic (``[IVXLC]+|\d+``), and
    this module used to feed both to a local Roman converter that
    scored unknown characters as 0 (#509). Every digit is outside the
    Roman alphabet, so "PROPOSITIO 14" read as 0 — which mislabelled
    the item as ``E I, P0`` *and* detached its apparatus, because the
    `if cur_prop` tests below treat 0 as "no proposition yet" and fall
    back to the part-level ``E I, Dem.``. The shared converter
    (:func:`minerva.sources._roman.roman_to_int`) is strict and returns
    None for anything non-Roman, so the arabic branch needs its own
    `int()` path rather than a more tolerant numeral parser.

    None means "no usable number"; every caller already handles that by
    continuing its own sequence, which is what a missing token did.
    """

    if tok is None:
        return None
    if tok.isdigit():
        return int(tok) or None
    return roman_to_int(tok)


def _is_banner(t: str) -> bool:
    # Part title / divider lines that aren't content.
    if t.startswith(("SPINOZAE ETHICA", "PARS ", "FINIS")):
        return True
    # All-caps short line with no sentence punctuation (e.g. "DE DEO").
    return len(t) < 40 and t == t.upper() and "." not in t and ":" not in t


def split_spinoza_ethica(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        from ..corpus_extract import IngestDepsMissing

        raise IngestDepsMissing(
            "HTML ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    m = _PART_RE.search(path.name)
    part = int(m.group(1)) if m else 1
    roman = _ROMAN.get(part, str(part))
    book = f"Ethica {roman}"
    html = path.read_text(encoding="latin-1", errors="replace")
    # Parts II–V from thelatinlibrary.com NEVER close their <p> tags, so the
    # lenient ``html.parser`` nests them 200+ deep and ``get_text`` on each
    # returns all descendant text (90 KB "paragraphs"). The ``lxml`` builder
    # follows the HTML5 spec (a <p> auto-closes at the next <p>), yielding flat
    # sibling paragraphs. Fall back to ``html.parser`` only if lxml is absent.
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # Part I omits the DEFINITIONES / AXIOMATA section headers entirely — its
    # eight definitions then seven axioms start straight in as "I ." items —
    # so we seed def-mode and flip to axiom-mode when the numbering resets.
    mode: str | None = "def" if part == 1 else None  # def|axiom|postulate|affectdef|appendix
    cur_prop: int | None = None
    cur_def: int | None = None
    cur_aff: int | None = None  # current AFFECTUUM-DEFINITIONES item (Part III)
    last_num = 0  # last bare "I ." ordinal seen (to detect a def→axiom reset)
    sub_counts: dict[tuple[str, str], int] = {}  # (prop/def key, kind) -> count
    pending: tuple[str, str | None, list[str]] | None = None  # (section, block_type, parts)

    def make(section: str, block_type: str | None, text: str) -> Chunk | None:
        text = _norm_text(text)
        if not text:
            return None
        chunk_id = _make_chunk_id(path.name, work.title, work.lang, book, section, "", text[:120])
        return Chunk(
            chunk_id=chunk_id, corpus=work.corpus, author=work.author, work=work.title,
            lang=work.lang, section=section, book=book, page=None, speaker=None, text=text,
            source_file=path.name, translator=work.translator, edition_year=work.edition_year,
            citation_system=work.citation_system, block_type=block_type,
        )

    def flush() -> Chunk | None:
        nonlocal pending
        if pending is None:
            return None
        section, bt, parts = pending
        pending = None
        return make(section, bt, "\n\n".join(parts))

    def suffix(key: str, kind: str, base: str) -> str:
        sub_counts[(key, kind)] = sub_counts.get((key, kind), 0) + 1
        k = sub_counts[(key, kind)]
        return base if k == 1 else f"{base} {k}"

    for p in soup.find_all("p"):
        raw = p.get_text(" ", strip=True)
        t = re.sub(r"\s+", " ", raw).strip()
        if not t:
            continue

        # thelatinlibrary.com page chrome trails the final unit of each part
        # ("Neo-Latin", "The Latin Library", "The Classics Page") with no label
        # to flush it, so it would otherwise append to the last chunk.
        low = t.lower()
        if "the latin library" in low or "the classics page" in low or low == "neo-latin":
            continue

        upper = t.upper()
        header_mode = next((v for h, v in _HEADERS.items() if upper.startswith(h)), None)
        lab = _LABEL_RE.match(t)
        num = _NUM_ITEM_RE.match(t)
        is_special = bool(
            header_mode or lab or num or upper.startswith("APPENDIX") or _PRAEF_RE.match(t)
        )
        # Banner / part-title lines (short all-caps, no punctuation) are skipped
        # — but ONLY when they aren't a structural header/label/numbered item.
        if not is_special and _is_banner(t):
            continue

        if header_mode is not None:
            ch = flush()
            if ch:
                yield ch
            mode = header_mode
            continue
        if upper.startswith("APPENDIX"):
            ch = flush()
            if ch:
                yield ch
            mode = "appendix"
            body = t[len("APPENDIX"):].lstrip(" .:")
            pending = (f"E {roman}, App.", None, [body]) if body else (f"E {roman}, App.", None, [])
            continue
        if _PRAEF_RE.match(t):  # PRÆFATIO / PRAEFATIO
            ch = flush()
            if ch:
                yield ch
            body = _PRAEF_RE.sub("", t).lstrip(" .:")
            pending = (f"E {roman}, Praef.", None, [body])
            mode = None
            continue

        if lab:
            kind = lab.group(1).upper()
            n_tok = lab.group(2)
            body = lab.group(3)
            ch = flush()
            if ch:
                yield ch
            if kind == "PROPOSITIO":
                n_prop = _label_number(n_tok)
                cur_prop = n_prop if n_prop is not None else (cur_prop or 0) + 1
                pending = (f"E {roman}, P{cur_prop}", None, [body])
            elif kind in ("DEMONSTRATIO", "ALITER"):
                base = f"E {roman}, P{cur_prop} Dem." if cur_prop else f"E {roman}, Dem."
                if kind == "ALITER":
                    base = f"{base} (alt.)"
                pending = (suffix(f"P{cur_prop}", kind, base), None, [body])
            elif kind == "SCHOLIUM":
                base = f"E {roman}, P{cur_prop} Schol." if cur_prop else f"E {roman}, Schol."
                pending = (suffix(f"P{cur_prop}", "S", base), "remark", [body])
            elif kind in ("COROLLARIUM", "COROLLARIA"):
                base = f"E {roman}, P{cur_prop} Cor." if cur_prop else f"E {roman}, Cor."
                pending = (suffix(f"P{cur_prop}", "C", base), None, [body])
            elif kind == "EXPLICATIO":
                if mode == "affectdef" and cur_aff:
                    anchor = f"Aff. Def. {cur_aff}"
                elif mode == "def" and cur_def:
                    anchor = f"Def. {cur_def}"
                else:
                    anchor = "expl."
                base = f"E {roman}, {anchor} Expl."
                pending = (suffix(anchor, "EX", base), "remark", [body])
            elif kind == "LEMMA":
                pending = (f"E {roman}, Lemma {n_tok or '?'}", None, [body])
            elif kind == "CAPUT":
                pending = (f"E {roman}, App. {n_tok or '?'}", None, [body])
            elif kind == "POSTULATUM":
                pending = (f"E {roman}, Post. {n_tok or '?'}", None, [body])
            elif kind == "DEFINITIO":
                n_def = _label_number(n_tok)
                cur_def = n_def if n_def is not None else (cur_def or 0) + 1
                pending = (f"E {roman}, Def. {cur_def}", None, [body])
            elif kind == "AXIOMA":
                # Singular "AXIOMA[ I] : <content>" — Part IV's lone axiom, and
                # Part II's physical-digression axioms about bodies ("AXIOMA I/II"
                # after 2p13). Number sequentially per part; tag the digression
                # set (which appears after propositions begin) so it doesn't
                # collide with the main axioms.
                n_ax = sub_counts.get((roman, "AX"), 0) + 1
                sub_counts[(roman, "AX")] = n_ax
                tag = " (Lem.)" if cur_prop is not None else ""
                pending = (f"E {roman}, Ax. {n_ax}{tag}", None, [body])
            continue

        if num:
            n = _label_number(num.group(1))
            if n is None:  # pragma: no cover — _NUM_ITEM_RE is [IVXLC]+ only
                continue
            body = num.group(2)
            ch = flush()
            if ch:
                yield ch
            # Part I has no AXIOMATA header: when the bare numbering resets
            # (… VII, VIII → I) while still in seeded def-mode, the axioms
            # have begun.
            if mode == "def" and n <= last_num:
                mode = "axiom"
            last_num = n
            if mode == "def":
                cur_def = n
                pending = (f"E {roman}, Def. {n}", None, [body])
            elif mode == "axiom":
                # Part II's physical digression (after 2p13) restarts axiom
                # numbering for its axioms about bodies; tag them so they don't
                # collide with the main axioms, which precede all propositions.
                tag = " (Lem.)" if cur_prop is not None else ""
                pending = (f"E {roman}, Ax. {n}{tag}", None, [body])
            elif mode == "postulate":
                pending = (f"E {roman}, Post. {n}", None, [body])
            elif mode == "affectdef":
                cur_aff = n
                pending = (f"E {roman}, Aff. Def. {n}", None, [body])
            elif mode == "appendix":
                pending = (f"E {roman}, App. {n}", None, [body])
            else:
                # Numbered item with no active section context — keep as body
                # under the part so nothing is dropped.
                pending = (f"E {roman}, {n}", None, [body])
            continue

        # Unlabeled continuation paragraph — append to the current unit.
        if pending is not None:
            pending[2].append(t)
        # else: stray pre-content line; ignore.

    ch = flush()
    if ch:
        yield ch
