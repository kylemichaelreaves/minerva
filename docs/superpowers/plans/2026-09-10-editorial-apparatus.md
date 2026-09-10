# Editorial Apparatus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop presenting editors' apparatus as Hegel's own words — mark it, cap it in search, and collapse it in the Reader.

**Architecture:** Four independent layers, in dependency order. A fuzzy pass on the editorial-heading predicate (`heading_clean.py`) so OCR damage stops defeating it; a policy change in the paragraphic splitter from *delete apparatus* to *tag apparatus*; a page-furniture pass that separates running heads, footnote blocks and page numbers from body text; then the two consumers — a one-line retrieval change that inherits the existing ⅓ cap, and the Reader's first collapsible block. Data migration comes last, behind a snapshot.

**Tech Stack:** Python 3.13 (`./.venv/bin/python`), pytest, SQLite, SolidJS + TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-09-10-editorial-apparatus-design.md`

## Global Constraints

- Run Python via `./.venv/bin/python` and `./.venv/bin/minerva`. `direnv exec . python` fails; `timeout` is not available on this machine.
- Run `gh` as `direnv exec . gh …`. Never `gh auth switch`.
- `make check` must pass before every commit that touches code. Re-run it after *any* edit made while fixing its output.
- SonarCloud gates new code at **80% coverage including branches**. A one-line guard whose false branch is untested scores 3/4, not 100%.
- No DB-mutating command without `scripts/snapshot-db.sh <reason>` first.
- The PR body carries `Closes #533`, `Closes #534`, targets `main`, and the link is verified with `make check-pr-link`.
- Do not touch De Cive (#535) or the `block_type` vocabulary gate (#536). Both are explicitly out of scope.

---

### Task 1: Fuzzy editorial-heading matching

Make `_is_editorial_heading` survive OCR letter substitution. Measured: across all 94,424 distinct heading labels in the corpus this rule newly matches exactly two, both real, with zero false positives.

**Files:**
- Modify: `src/minerva/heading_clean.py` (add helper + extend `_is_editorial_heading` at :298-310)
- Test: `tests/test_heading_clean.py` (append after `test_editorial_heading_catches_ocr_variants`, ~:283)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_is_editorial_heading(label: str) -> bool` — same signature, wider recall. Task 2 depends on this behaviour, not on any new name.

- [ ] **Step 1: Write the failing test**

```python
def test_editorial_heading_catches_ocr_letter_substitution():
    # Spacing damage was already handled; letter substitution was not.
    # Both labels are real, from work 712 (Hegel, Lectures on the
    # Philosophy of World History), ords 10 and 475.
    assert corpus_parse._is_editorial_heading("Editorial Introouctjon") is True
    assert corpus_parse._is_editorial_heading("Bjbljography") is True


def test_editorial_heading_fuzzy_does_not_fire_on_real_headings():
    # The length>=12 floor is load-bearing: _EDITORIAL_PHRASES holds short
    # substring-matched entries ("contents", "glossary", "foreword") that
    # would otherwise fuzzy-match ordinary chapter titles.
    for label in [
        "The Consummate Religion",
        "Conscience",
        "The Content of Religion",
        "Second Part: Determinate Religion",
        "The Oriental World",
        "Introduction",
        "Preface",
        "Chronology of Hegel's Life",
    ]:
        assert corpus_parse._is_editorial_heading(label) is False, label


def test_editorial_heading_fuzzy_rejects_truncated_labels():
    # Truncation, not substitution. Too short to tell from a real heading,
    # so deliberately NOT matched.
    assert corpus_parse._is_editorial_heading("Editoria L Int") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_heading_clean.py -k ocr_letter_substitution -v`
Expected: FAIL — `assert False is True` on `"Editorial Introouctjon"`.

- [ ] **Step 3: Write the implementation**

Add above `_is_editorial_heading` in `src/minerva/heading_clean.py`:

```python
#: Only phrases this long get the fuzzy pass. The short entries in
#: `_EDITORIAL_PHRASES` ("contents", "glossary", "foreword") are matched by
#: substring, and letting them match approximately fires on ordinary chapter
#: titles — "The Content of Religion" is not a table of contents.
_FUZZY_MIN_PHRASE_LEN = 12
#: Edit distance allowed on the whole normalized label. Measured over all
#: 94,424 distinct heading labels in the corpus: d<=2 newly matches exactly
#: two, "Bjbljography" and "Editorial Introouctjon", both genuine. d<=3
#: starts admitting real headings.
_FUZZY_MAX_DISTANCE = 2


def _within_distance(a: str, b: str, cap: int) -> bool:
    """True when `a` and `b` are within `cap` edits (Levenshtein).

    Banded and early-exiting: the caller runs this against every long phrase
    for every heading in an ingest, so the common case must reject on the
    length check alone.
    """

    if abs(len(a) - len(b)) > cap:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return False
        prev = cur
    return prev[-1] <= cap
```

Then extend `_is_editorial_heading`, replacing its final `return`:

```python
    if any(phrase in norm for phrase in _EDITORIAL_PHRASES):
        return True
    # Fuzzy fallback for OCR letter substitution — "introouctjon" for
    # "introduction", "bjbljography" for "bibliography". The exact pass above
    # already handles spacing and punctuation damage, which is all
    # `_EDITORIAL_NORM_RE` can absorb on its own.
    if len(norm) < _FUZZY_MIN_PHRASE_LEN:
        return False
    return any(
        _within_distance(norm, phrase, _FUZZY_MAX_DISTANCE)
        for phrase in _EDITORIAL_PHRASES
        if len(phrase) >= _FUZZY_MIN_PHRASE_LEN
    )
```

Also add the two phrases that miss even when spelled correctly — into `_EDITORIAL_PHRASES`, alphabetically near their neighbours:

```python
        "secondaryworks",
        "sourcesusedoralludedtoby",
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_heading_clean.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Re-verify against the whole corpus**

The false-positive claim is the load-bearing one, so re-measure rather than trust the fixture list:

```bash
./.venv/bin/python - <<'PY'
import sqlite3, re
from minerva.heading_clean import _is_editorial_heading
c = sqlite3.connect('data/index.sqlite')
labels = set()
for (s,) in c.execute("SELECT DISTINCT section FROM chunks WHERE section IS NOT NULL"):
    h = re.split(r',\s*¶', s)[0].strip()
    if h and not re.fullmatch(r'[¶§\d.\s]+', h):
        labels.add(h)
hits = sorted(l for l in labels if _is_editorial_heading(l))
print(f"{len(labels):,} labels, {len(hits)} matched")
for h in hits:
    print("   ", h)
PY
```

Expected: exactly 3 matched — the 1 that already matched, plus `Bjbljography` and `Editorial Introouctjon`. Any other name in that list is a false positive: stop and investigate before continuing.

- [ ] **Step 6: Commit**

```bash
make check
git add src/minerva/heading_clean.py tests/test_heading_clean.py
git commit -m "fix(ingest): match editorial headings through OCR letter substitution

Refs #534"
```

---

### Task 2: Tag apparatus instead of deleting it

Change the splitter's policy from *drop label and body* to *emit body tagged `editorial`*, and add the value to the TS union.

**Files:**
- Modify: `src/minerva/corpus/split_paragraphic.py:96-131` (`_emit`), `:469-480` (`_split_chapter_block`), `:348-395` (the heading sweep inside **`split_by_chapter`** — that is the splitter work 712 uses, via `locator="chapter"`)
- Modify: `web/src/api/types/reader.ts:19-29` (`BlockType` union)
- Test: `tests/test_corpus_parse.py`

**Interfaces:**
- Consumes: `_is_editorial_heading` from Task 1.
- Produces:
  - `_emit(work, path, section, text, book_label=None, block_type=None) -> Chunk | None`
  - `_split_chapter_block(work, path, heading, body, block_type=None) -> Iterator[Chunk]`
  - Chunks with `block_type == "editorial"`. Tasks 4 and 5 consume that string.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_corpus_parse.py`:

```python
def test_editorial_heading_body_is_tagged_not_dropped(tmp_path):
    """Apparatus is kept and marked, so a reader can see it and search can
    demote it. Before #534 the body was deleted outright."""
    text = (
        "CHAPTER ONE\n\n"
        "The owl of Minerva spreads its wings only with the falling of dusk.\n\n"
        "EDITORIAL INTRODUCTION\n\n"
        "Hegel delivered these lectures five times between 1822 and 1831.\n"
    )
    # `_make_work` is the existing helper at tests/test_corpus_parse.py:47.
    # `locator="chapter"` selects `split_by_chapter`, the splitter work 712
    # uses and the one carrying the editorial-heading sweep.
    chunks = list(
        corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf")
    )

    by_type = {c.block_type: c for c in chunks}
    assert "editorial" in by_type, [c.section for c in chunks]
    assert "Hegel delivered these lectures" in by_type["editorial"].text
    # The body chapter is untouched and still untagged.
    assert any(c.block_type is None and "owl of Minerva" in c.text for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_corpus_parse.py -k editorial_heading_body_is_tagged -v`
Expected: FAIL — `assert "editorial" in by_type`, because the body was dropped.

- [ ] **Step 3: Thread `block_type` through the two emitters**

In `_emit`, add the parameter and pass it to `Chunk`:

```python
def _emit(
    work: CorpusWork,
    path: Path,
    section: str,
    text: str,
    book_label: str | None = None,
    block_type: str | None = None,
) -> Chunk | None:
```

and in the `Chunk(...)` construction, add `block_type=block_type,`.

In `_split_chapter_block`, add the parameter and forward it:

```python
def _split_chapter_block(
    work: CorpusWork,
    path: Path,
    heading: str,
    body: str,
    block_type: str | None = None,
) -> Iterator[Chunk]:
```

and change the `_emit` call to `chunk = _emit(work, path, section=section, text=piece, book_label=heading or None, block_type=block_type)`.

- [ ] **Step 4: Flip the policy at the heading sweep**

Replace the `if skip: continue` branch in the emit loop (`split_paragraphic.py:387-388`) with:

```python
    for i, (_h_start, h_end, label, editorial) in enumerate(headings):
        start = h_end
        end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        body = text[start:end]
        # Apparatus is TAGGED, not dropped (#534). Dropping it lost real
        # scholarship silently and left no way to tell a missing editorial
        # introduction from one that was never in the source.
        yield from _split_chapter_block(
            work, path, label, body, block_type="editorial" if editorial else None
        )
```

Update the two-stage comment above the sweep (`:356-366`) — it currently says "drop BOTH the label AND the body", which is no longer true:

```python
    #   * Editorial / front-matter labels ("Editorial Introduction",
    #     "Glossary", "Bibliography", "List of Abbreviations", indices) —
    #     keep the body but tag it `block_type='editorial'`, so retrieval
    #     can cap it and the Reader can collapse it. This replaced an
    #     outright drop in #534.
```

- [ ] **Step 5: Add `editorial` to the TS union**

In `web/src/api/types/reader.ts`, add to `BlockType`:

```typescript
  // Editors' / translators' apparatus hosted in the work — an editorial
  // introduction, bibliography, or front matter. Capped in retrieval
  // (retrieve.py `_APPARATUS_TYPES`) and collapsed in the Reader.
  | "editorial"
```

Nothing enforces that this union matches Python (see #536), so `make check` passing is not evidence this step was done. Verify by eye.

- [ ] **Step 6: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_corpus_parse.py -v`
Expected: PASS. Pay attention to `tests/test_corpus_parse.py:672`, which asserts apparatus is stripped from the end of a work — it encodes the OLD policy and will need updating to assert `block_type == "editorial"` instead of absence. Read it before assuming it is a regression.

- [ ] **Step 7: Commit**

```bash
make check
git add src/minerva/corpus/split_paragraphic.py web/src/api/types/reader.ts tests/test_corpus_parse.py
git commit -m "feat(ingest): tag editorial apparatus instead of deleting it

Refs #534"
```

---

### Task 3: Separate running heads, footnotes and page numbers

The page-furniture pass. Each chunk of work 712 is roughly one PDF page: `[running head] [body] [footnote block] [page number]`.

**Files:**
- Create: `src/minerva/corpus/page_furniture.py`
- Create: `tests/test_page_furniture.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure text functions).
- Produces:
  - `strip_running_head(text: str, heads: tuple[str, ...]) -> str`
  - `split_trailing_notes(text: str) -> tuple[str, str | None]` — returns `(body, note_block_or_None)`
  - `strip_trailing_page_number(text: str) -> str`
  - `RUNNING_HEADS_LWH: tuple[str, ...]` — the four patterns for work 712

- [ ] **Step 1: Write the failing test**

```python
"""Page-furniture separation for PDF-extracted works (#533)."""

from minerva.corpus import page_furniture as pf


def test_strips_a_leading_running_head():
    text = "THE LECTURES OF 1822-3 This is the new and ultimate banner."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == (
        "This is the new and ultimate banner."
    )


def test_running_head_strip_tolerates_ocr():
    # Real forms from work 712: 'l' for 'L', 'R' for '8', 'f' for 'F'.
    for head in ("THE lECTURES OF 1822-3", "THE LECTURES OF 1R22-3", "THE LECTURES Of 1822-3"):
        assert pf.strip_running_head(f"{head} Body text.", pf.RUNNING_HEADS_LWH) == "Body text."


def test_leaves_text_alone_when_there_is_no_running_head():
    text = "In addition ro these two large constellations in Eucope."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == text


def test_splits_a_trailing_note_block_when_the_marker_is_present():
    # Marker '.4' upstream is what licenses treating '4.' as a note.
    text = "Caesar's Commentaries, belong here too.4 In particular. 4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert body == "Caesar's Commentaries, belong here too.4 In particular."
    assert notes == "4. On Herodotus, see the Fragment."


def test_refuses_to_split_when_no_marker_licenses_it():
    # Without an upstream marker this is prose, not a note. Refusing is the
    # safe direction: a bad split silently deletes Hegel.
    text = "He names three writers. 4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_strips_a_trailing_page_number():
    assert pf.strip_trailing_page_number("…and obtain a picture of the age. 135") == (
        "…and obtain a picture of the age."
    )


def test_does_not_strip_a_number_that_ends_a_sentence():
    text = "The lectures were delivered in 1822."
    assert pf.strip_trailing_page_number(text) == text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_page_furniture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'minerva.corpus.page_furniture'`.

- [ ] **Step 3: Write the implementation**

Create `src/minerva/corpus/page_furniture.py`:

```python
"""Separate page furniture from body text in PDF-extracted works.

The extractor walks each PDF page in reading order, so one chunk is roughly
one page and arrives as `[running head] [body] [footnote block] [page number]`
concatenated into a single string (#533). These three functions pull the
furniture back off. They are pure and take plain strings so they can be tested
without a PDF.

The note split is deliberately conservative. A trailing `4. ` only starts a
note block if marker `4` appears glued to a word earlier in the same chunk
(`too.4`); otherwise the text is left alone. An over-eager split deletes
Hegel's prose silently, which is far worse than leaving a note in place.
"""

from __future__ import annotations

import re

#: Running heads in Hegel's *Lectures on the Philosophy of World History*
#: (work 712), OCR-tolerant. `1R22` and `1&28` for `1822`, `l`/`I` for `L`,
#: `f` for `F` are all attested in that extraction.
RUNNING_HEADS_LWH: tuple[str, ...] = (
    r"TH[EF]\s+[lLI]ECTURES\s+O[FfP]\s+1[R8&]22\s*[-–]\s*3",
    r"INTRODUCTORY\s+FRAGMENT[,.\s]+1[R8&]22[,.\s]+1[8&][0-9]{2}",
    r"M[A.]{1,3}N[UV]SCR[Il1]PTS\s+OF\s+THE\s+[lI1]NTRODUCT[Il1]ON",
    r"INTRODUCTION[,.\s]+1[8&][0-9O]{2}\s*[-–]{1,2}\s*[0-9l]+",
)

#: A note block opens with `<n>. ` and a capital, an opening bracket, or a
#: quote. Anchored to a sentence boundary so a decimal or a list item
#: mid-sentence does not qualify.
_NOTE_OPEN_RE = re.compile(r"(?:(?<=\.)|(?<=^)|(?<=\s))(\d{1,3})\.\s+(?=[A-Z(\[\"'])")

#: A bare page number at the very end, not preceded by a sentence-ending
#: period (which would make it a year or a quantity).
_TRAILING_PAGE_RE = re.compile(r"(?<![.\d])\s+(\d{2,3})\s*$")


def strip_running_head(text: str, heads: tuple[str, ...]) -> str:
    """Remove a leading running head. Returns *text* unchanged if absent."""

    for pattern in heads:
        m = re.match(rf"\s*{pattern}\s*", text, re.IGNORECASE)
        if m:
            return text[m.end() :].lstrip()
    return text


def _marker_present(text: str, number: str, before: int) -> bool:
    """Is footnote marker *number* glued to a word before offset *before*?

    The printed marker is superscript; the extractor renders it as a bare
    digit run against the preceding word — `too.4`, `religion, 76`,
    `Saxony67`. Requiring it is what keeps the split honest.
    """

    upstream = text[:before]
    return re.search(rf"[a-zA-Z,.]{re.escape(number)}(?![0-9])", upstream) is not None


def split_trailing_notes(text: str) -> tuple[str, str | None]:
    """Split a trailing editors' note block off *text*.

    Returns `(body, notes)`; `notes` is None when nothing qualifies, in which
    case `body is text`.
    """

    for m in _NOTE_OPEN_RE.finditer(text):
        number = m.group(1)
        if not _marker_present(text, number, m.start()):
            continue
        body = text[: m.start()].rstrip()
        notes = text[m.start() :].strip()
        if not body or not notes:
            return text, None
        return body, notes
    return text, None


def strip_trailing_page_number(text: str) -> str:
    """Remove a bare page number at the end of *text*."""

    return _TRAILING_PAGE_RE.sub("", text).rstrip()
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_page_furniture.py -v`
Expected: PASS, all seven.

- [ ] **Step 5: Measure against the real corpus before trusting it**

The fixtures are hand-picked; the corpus is not. Run the pass over all 477 chunks and read the output:

```bash
./.venv/bin/python - <<'PY'
import sqlite3
from minerva.corpus import page_furniture as pf
c = sqlite3.connect('data/index.sqlite'); c.row_factory = sqlite3.Row
rows = c.execute("SELECT chunk_id, ord, text FROM chunks WHERE work_id=712 ORDER BY ord").fetchall()
heads = notes = pages = 0
refused = []
for r in rows:
    t = r['text']
    t2 = pf.strip_running_head(t, pf.RUNNING_HEADS_LWH)
    if t2 != t: heads += 1
    body, note = pf.split_trailing_notes(t2)
    if note: notes += 1
    else: refused.append(r['ord'])
    body2 = pf.strip_trailing_page_number(body)
    if body2 != body: pages += 1
print(f"running heads stripped : {heads} (expect ~216)")
print(f"note blocks split      : {notes} (expect <=279)")
print(f"page numbers stripped  : {pages} (expect ~391)")
print(f"chunks with no note split: {len(refused)}")
PY
```

Expected: heads ≈ 216, notes ≤ 279, pages ≈ 391. **A note count materially above 279 means the marker check is not doing its job — stop.** Spot-read five split note blocks and confirm each really is an editor's note.

- [ ] **Step 6: Commit**

```bash
make check
git add src/minerva/corpus/page_furniture.py tests/test_page_furniture.py
git commit -m "feat(ingest): separate running heads, footnotes and page numbers

Refs #533"
```

---

### Task 4: Cap `editorial` in retrieval

One tuple, one dict. The ⅓ share cap and its reasoning already exist.

**Files:**
- Modify: `src/minerva/retrieve.py:160-161` (`_APPARATUS_TYPES`, `_APPARATUS_LABEL`)
- Test: `tests/test_retrieve.py`

**Interfaces:**
- Consumes: the `"editorial"` `block_type` string from Task 2.
- Produces: nothing new. `_CAPPED_TYPES` at :445 derives from `_APPARATUS_TYPES` automatically.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_retrieve.py`:

```python
def test_editorial_apparatus_is_capped_like_notes(tmp_path):
    """An editors' introduction may not crowd out the author (#534).

    Same policy as notes and cast lists: apparatus supports the text, so it
    takes at most `_APPARATUS_MAX_SHARE` of a result set.
    """
    assert "editorial" in retrieve._APPARATUS_TYPES
    assert "editorial" in retrieve._CAPPED_TYPES


def test_editorial_locator_names_the_editor_not_the_author():
    loc = retrieve.format_locator(
        {
            "author": "Hegel",
            "work": "Lectures on the Philosophy of World History",
            "section": "Editorial Introduction, ¶1",
            "block_type": "editorial",
            "translator": "Hodgson / Brown",
        }
    )
    assert "editorial" in loc.lower()
    assert "Hodgson" in loc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_retrieve.py -k editorial -v`
Expected: FAIL — `assert "editorial" in retrieve._APPARATUS_TYPES`.

- [ ] **Step 3: Write the implementation**

In `src/minerva/retrieve.py`:

```python
_APPARATUS_TYPES = ("note", "cast", "editorial")
_APPARATUS_LABEL = {
    "note": "editorial note",
    "cast": "cast list",
    "editorial": "editorial apparatus",
}
```

`_APPARATUS_LABEL.get(block_type, "editorial")` at :689 would already have produced a sensible label by falling through to its default. Naming it explicitly is deliberate: behaviour that depends on a default happening to match is one refactor away from being wrong.

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_retrieve.py -v`
Expected: PASS, including the pre-existing cap tests at `:206` and the `note1` fixture at `:298`.

- [ ] **Step 5: Commit**

```bash
make check
git add src/minerva/retrieve.py tests/test_retrieve.py
git commit -m "feat(retrieve): cap editorial apparatus like notes and cast lists

Refs #534"
```

---

### Task 5: Collapse editorial blocks in the Reader

The Reader's first collapsible block. `data-block` styles today; this adds behaviour.

**Files:**
- Create: `web/src/Reader/components/EditorialBlock.tsx`
- Modify: `web/src/Reader/components/Lines.tsx:75-105`
- Modify: `web/src/Reader/reader.css` (after the `objection` rules, ~:375)
- Test: `web/src/Reader/components/EditorialBlock.test.tsx`

**Interfaces:**
- Consumes: `chunk.block_type === "editorial"` from Tasks 2 and 4.
- Produces: `<EditorialBlock label={string} count={number}>{children}</EditorialBlock>`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, fireEvent } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { EditorialBlock } from "./EditorialBlock";

describe("EditorialBlock", () => {
  it("is closed on first render", () => {
    const { queryByText } = render(() => (
      <EditorialBlock label="Editorial Introduction" count={3}>
        <p>Hegel delivered these lectures five times.</p>
      </EditorialBlock>
    ));
    expect(queryByText(/delivered these lectures/)).toBeNull();
  });

  it("names what is hidden, so the reader can decide", () => {
    const { getByRole } = render(() => (
      <EditorialBlock label="Editorial Introduction" count={3}>
        <p>body</p>
      </EditorialBlock>
    ));
    const summary = getByRole("button");
    expect(summary.textContent).toContain("Editorial Introduction");
    expect(summary.textContent).toContain("3");
  });

  it("expands on click and collapses again", () => {
    const { getByRole, queryByText } = render(() => (
      <EditorialBlock label="Editorial Introduction" count={1}>
        <p>Hegel delivered these lectures five times.</p>
      </EditorialBlock>
    ));
    const summary = getByRole("button");
    fireEvent.click(summary);
    expect(queryByText(/delivered these lectures/)).not.toBeNull();
    fireEvent.click(summary);
    expect(queryByText(/delivered these lectures/)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/Reader/components/EditorialBlock.test.tsx`
Expected: FAIL — cannot resolve `./EditorialBlock`.

- [ ] **Step 3: Write the component**

Create `web/src/Reader/components/EditorialBlock.tsx`:

```tsx
import { createSignal, type JSX, Show } from "solid-js";

interface Props {
  /** What is hidden, in the reader's words — "Editorial Introduction". */
  label: string;
  /** How many chunks are inside, so the reader can judge before opening. */
  count: number;
  children: JSX.Element;
}

/**
 * A run of editors' apparatus, collapsed by default.
 *
 * The Reader's first collapsible block. Apparatus is real scholarship and is
 * kept, but it is not Hegel — presenting it inline is what made the corpus
 * misleading (#534). Closed by default states the priority: the author first,
 * the editors on request.
 *
 * Open/closed is per-viewer UI state and deliberately not persisted; it says
 * nothing about the corpus.
 */
export function EditorialBlock(props: Props) {
  const [open, setOpen] = createSignal(false);
  return (
    <div class="editorial-block" data-open={open() ? "" : undefined}>
      <button
        type="button"
        class="editorial-block-summary"
        aria-expanded={open()}
        onClick={() => setOpen(!open())}
      >
        <span class="editorial-block-caret" aria-hidden="true">
          {open() ? "▾" : "▸"}
        </span>
        <span class="editorial-block-label">{props.label}</span>
        <span class="editorial-block-count">
          {props.count} {props.count === 1 ? "section" : "sections"}
        </span>
      </button>
      <Show when={open()}>
        <div class="editorial-block-body">{props.children}</div>
      </Show>
    </div>
  );
}
```

- [ ] **Step 4: Run the component test**

Run: `cd web && npx vitest run src/Reader/components/EditorialBlock.test.tsx`
Expected: PASS, all three.

- [ ] **Step 5: Group consecutive editorial chunks in `Lines.tsx`**

`Lines.tsx` renders a flat list. Editorial chunks arrive in consecutive runs (ords 8–10, 474–476), and each run becomes one collapsed block rather than three. Before the render loop, group the chunk list:

```tsx
/** Consecutive runs of one block_type, so an apparatus run collapses as a
 *  single disclosure rather than one per chunk. */
function groupEditorialRuns<T extends { block_type?: string | null }>(
  chunks: T[],
): Array<{ editorial: boolean; items: T[] }> {
  const out: Array<{ editorial: boolean; items: T[] }> = [];
  for (const chunk of chunks) {
    const editorial = chunk.block_type === "editorial";
    const last = out[out.length - 1];
    if (last && last.editorial === editorial) last.items.push(chunk);
    else out.push({ editorial, items: [chunk] });
  }
  return out;
}
```

Then restructure the render into two branches. **Do not retype the existing
per-chunk markup** — move the current `<For each={...}>` body into a local
`renderLine(chunk)` and call it from both branches, so the `<div class="line">`
with its `data-chunk-id`, `data-block`, `data-speaker` and `<WordRun>` stays
byte-identical. Selection, highlighting and the xref map all key off
`data-chunk-id`; losing it breaks them silently.

```tsx
<For each={groupEditorialRuns(chunks())}>
  {(run) => (
    <Show when={run.editorial} fallback={<For each={run.items}>{renderLine}</For>}>
      <EditorialBlock
        label={run.items[0].section?.split(",")[0] ?? "Editorial material"}
        count={run.items.length}
      >
        <For each={run.items}>{renderLine}</For>
      </EditorialBlock>
    </Show>
  )}
</For>
```

Add `EditorialBlock` and Solid's `Show` to the imports.

- [ ] **Step 6: Style it**

Append to `web/src/Reader/reader.css`, after the `objection` rules:

```css
/* Editors' apparatus (#534) — an editorial introduction, bibliography or
   front matter. Collapsed by default: it is real scholarship, but it is not
   the author, and rendering it inline is what made the corpus misleading.
   The visual language matches Remarks and Objections — subordinate, softer,
   set in from the text column. */
.reader .editorial-block {
  margin: 18px 0;
  border-left: 2px dotted var(--r-accent-mark);
  padding-left: 20px;
}
.reader .editorial-block-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  width: 100%;
  padding: 6px 0;
  background: none;
  border: 0;
  cursor: pointer;
  font: inherit;
  font-size: 0.93em;
  color: var(--r-ink-soft);
  text-align: left;
}
.reader .editorial-block-summary:hover .editorial-block-label {
  text-decoration: underline;
}
.reader .editorial-block-count {
  font-size: 0.85em;
  opacity: 0.7;
}
.reader .editorial-block-body .line .text {
  font-size: 0.93em;
  color: var(--r-ink-soft);
}
```

- [ ] **Step 7: Run the frontend suite**

Run: `cd web && npx vitest run`
Expected: PASS. `Lines.test.tsx` may assert a flat structure — read any failure before assuming it is a regression.

- [ ] **Step 8: Commit**

```bash
make check
git add web/src/Reader/components/EditorialBlock.tsx web/src/Reader/components/EditorialBlock.test.tsx web/src/Reader/components/Lines.tsx web/src/Reader/reader.css
git commit -m "feat(reader): collapse editorial apparatus behind a disclosure

Refs #534"
```

---

### Task 6: Wire the furniture pass into the Hegel extractor

Task 3 built the functions; nothing calls them yet.

**Files:**
- Modify: `src/minerva/corpus/split_paragraphic.py` (call the pass in `_emit`, gated per work)
- Modify: `src/minerva/corpus_works.py:71` area (add a `page_furniture` field to `CorpusWork`)
- Modify: `src/minerva/authors/hegel_works.py:214-228` (set it for `lwh`)
- Test: `tests/test_corpus_parse.py`

**Interfaces:**
- Consumes: `page_furniture.strip_running_head`, `.split_trailing_notes`, `.strip_trailing_page_number`, `.RUNNING_HEADS_LWH` (Task 3); `_emit(..., block_type=...)` (Task 2).
- Produces: sibling note chunks with `section` suffixed `.note` and `block_type="note"`.

- [ ] **Step 1: Write the failing test**

```python
def test_page_furniture_is_separated_for_works_that_opt_in(tmp_path):
    text = (
        "CHAPTER ONE\n\n"
        "THE LECTURES OF 1822-3 Caesar's Commentaries, belong here too.4 "
        "In particular. 4. On Herodotus, see the Fragment. 135\n"
    )
    # `_make_work` does not take `page_furniture`; build the work directly.
    work = corpus_works.CorpusWork(
        code="lwh",
        title="Lectures",
        translator="T",
        edition_year="2011",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="chapter",
        page_furniture=True,
    )
    chunks = list(corpus_parse.split_by_chapter(text, work, tmp_path / "x.pdf"))

    body = [c for c in chunks if c.block_type is None]
    notes = [c for c in chunks if c.block_type == "note"]
    assert len(body) == 1 and len(notes) == 1
    assert body[0].text == "Caesar's Commentaries, belong here too.4 In particular."
    assert notes[0].text == "4. On Herodotus, see the Fragment."
    # Sibling numbering, NOT a renumbered ¶ — `section` feeds `chunk_id`, so
    # renumbering would churn every chunk after the insertion.
    assert notes[0].section.endswith(".note")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_corpus_parse.py -k page_furniture_is_separated -v`
Expected: FAIL — `TypeError: CorpusWork.__init__() got an unexpected keyword argument 'page_furniture'`.

- [ ] **Step 3: Add the opt-in field**

In `src/minerva/corpus_works.py`, on `CorpusWork` beside `skip_headings`:

```python
    #: Run the page-furniture pass (`corpus/page_furniture.py`) over each
    #: chunk: strip the running head, split a trailing editors' note block
    #: into a sibling chunk, drop the page number. Opt-in per work because it
    #: is only correct for page-image PDF extractions where one chunk is
    #: roughly one page (#533).
    page_furniture: bool = False
```

In `src/minerva/authors/hegel_works.py`, on the `lwh` entry, add `page_furniture=True,`.

- [ ] **Step 4: Call the pass**

In `_split_chapter_block`, after computing `piece` and before `_emit`, when `work.page_furniture` is set:

```python
            if work.page_furniture:
                piece = page_furniture.strip_running_head(
                    piece, page_furniture.RUNNING_HEADS_LWH
                )
                piece, note_text = page_furniture.split_trailing_notes(piece)
                piece = page_furniture.strip_trailing_page_number(piece)
            else:
                note_text = None
            chunk = _emit(
                work, path, section=section, text=piece,
                book_label=heading or None, block_type=block_type,
            )
            if chunk is not None:
                yield chunk
            if note_text:
                note = _emit(
                    work, path, section=f"{section}.note", text=note_text,
                    book_label=heading or None, block_type="note",
                )
                if note is not None:
                    yield note
```

Add `from . import page_furniture` to the imports.

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_corpus_parse.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
make check
git add src/minerva/corpus/split_paragraphic.py src/minerva/corpus_works.py src/minerva/authors/hegel_works.py tests/test_corpus_parse.py
git commit -m "feat(ingest): run the page-furniture pass for the World History lectures

Refs #533"
```

---

### Task 7: Correct the two wrong sources

Both are claims that would mislead the next reader. Per the repo's "don't trust a stated cause" rule, a correction goes on the thing that was wrong.

**Files:**
- Modify: `src/minerva/heading_clean.py:298-306` (docstring)
- Modify: `scripts/clean-hobbes-latin.py:20-30` (docstring)

- [ ] **Step 1: Correct the `_is_editorial_heading` docstring**

It claims OCR tolerance it does not have; its example is drawn from the one damage class the exact pass handles. Replace the second paragraph:

```python
    """Detect headings naming editor / translator material rather than
    Hegel's own text.

    Two passes. The exact pass matches on a normalized form (lowercased,
    non-letters removed), which absorbs *spacing and punctuation* damage —
    "Editorial Intr O Duction" collapses to "editorialintroduction". It does
    NOT absorb letter substitution, which is what OCR mostly produces:
    "Introouctjon", "Bjbljography". Those are caught by the fuzzy pass below,
    bounded to phrases of length >= `_FUZZY_MIN_PHRASE_LEN` so the short
    substring-matched entries ("contents", "glossary") cannot fire on real
    chapter titles. See #534.
    """
```

- [ ] **Step 2: Correct the `clean-hobbes-latin.py` docstring**

It reports the long-s residue as "10 chunks — already low", which reads as *small*. It is *unmeasured*: the heuristic gates `lang` to `{eng,fra,deu}` and so excludes `lat`, the only affected language. Replace that sentence:

```python
#     That residual long-s contamination is NOT measured by the
#     audit's `long_s_misread` count. That count reads 10 chunks
#     only because the misread heuristic gates lang to
#     {eng/fra/deu} — it excludes `lat`, which is the only
#     language with the problem. The Latin is in fact severely
#     corrupted (`Cbrifti`, `$eniet`, `Dabid`, `triwmphum`); see
#     #535, which proposes re-sourcing rather than repairing.
```

- [ ] **Step 3: Commit**

```bash
make check
git add src/minerva/heading_clean.py scripts/clean-hobbes-latin.py
git commit -m "docs: correct two claims about OCR tolerance and long-s coverage

Refs #534
Refs #535"
```

---

### Task 8: Re-ingest, re-derive, and open the PR

The only task that mutates the live database. Everything above is code and is reversible; this is not.

**Files:** none — operational.

- [ ] **Step 1: Snapshot first**

```bash
./scripts/snapshot-db.sh editorial-apparatus
```

Do not proceed without output confirming the snapshot was written.

- [ ] **Step 2: Re-ingest the Hegel corpus**

`ingest --only` replaces `chunks.jsonl` **per corpus**, not per file — passing only the one PDF would silently drop every other Hegel work. Pass all Hegel sources together.

```bash
./.venv/bin/minerva ingest --only hegel
```

- [ ] **Step 3: Measure the churn against the prediction**

```bash
./.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect('data/index.sqlite'); c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) FROM chunks WHERE work_id=712").fetchone()[0]
by = c.execute("SELECT block_type, COUNT(*) n FROM chunks WHERE work_id=712 GROUP BY block_type").fetchall()
print("chunks:", n, "(was 477; expect more — note siblings are added)")
for r in by:
    print(f"   {str(r['block_type']):<12} {r['n']}")
PY
```

Expected: an `editorial` count of roughly 14 and a `note` count at or below 279. A wildly different shape means Task 3 or 6 misfired — stop and diagnose rather than continuing into the re-derivation.

- [ ] **Step 4: Re-derive**

```bash
./.venv/bin/minerva index --incremental --corpora hegel
./.venv/bin/minerva embed
./.venv/bin/minerva lemmatize --corpora hegel
```

- [ ] **Step 5: Rebuild and verify references**

`refs build` alone is not enough — it must be followed by both verifiers.

```bash
./.venv/bin/minerva refs build --corpora hegel
./.venv/bin/minerva refs embed-verify
./.venv/bin/minerva refs llm-verify
```

- [ ] **Step 6: Regenerate the committed author snapshots**

The chunk count and per-work granularity both move, and CI validates against these files rather than the index.

```bash
make generate-authors
git add data/authors/chunk_counts.json data/authors/chunk_granularity.json
```

If `make check-authors` fails on granularity, the work has become newly coarse: either re-chunk it or add it to `granularity.known_coarse` in `data/authors/manifest.yaml` by hand. The manifest is policy and is never regenerated.

- [ ] **Step 7: Full gate, then push**

```bash
make check
git commit -m "chore(data): regenerate author snapshots after the apparatus re-ingest"
git push -u origin feat/533-editorial-apparatus
```

- [ ] **Step 8: Open the PR and verify the issue links registered**

```bash
direnv exec . gh pr create --base main \
  --title "feat: mark, cap and collapse editorial apparatus (#533, #534)" \
  --body "$(cat <<'BODY'
## What

Editors' apparatus in Hegel's *Lectures on the Philosophy of World History*
was indexed as Hegel's own prose. It is now tagged, capped in retrieval, and
collapsed in the Reader.

Measured before: 7.6% of the work's body text (~101,000 chars) was editorial
annotation; 279 of 477 chunks carried a trailing footnote block, 391 ended in
a page number, 216 carried a running head, and 14 chunks were apparatus end to
end.

## Root cause

`_is_editorial_heading` already carried `editorialintroduction` and
`bibliography`, and already ran on this work. Its normaliser is `[^a-z]`,
which absorbs spacing damage but not letter substitution — so
`Introouctjon` and `Bjbljography` walked past it. Fixed with a bounded
edit-distance pass, measured over all 94,424 distinct heading labels in the
corpus: it newly matches exactly two, both real, zero false positives.

Also changed the policy from *delete apparatus* to *tag apparatus*. Deleting
lost real scholarship silently and left no way to tell a missing editorial
introduction from one that was never in the source.

## Corrections to the record

- `_is_editorial_heading`'s docstring claimed OCR tolerance it does not have;
  its example was drawn from the one damage class the exact pass handles.
- `clean-hobbes-latin.py` reported the long-s residue as "10 chunks — already
  low". It is low because the heuristic gates lang to {eng,fra,deu} and so
  excludes `lat`, the only affected language. See #535.

## Not fixed here

- #535 (De Cive's Latin) — a re-source, not a cleanup.
- #536 (`block_type` has no enforced vocabulary) — found while planning this.

Closes #533
Closes #534

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
```

Then verify the links registered, substituting the PR number the command printed:

```bash
make check-pr-link PR=<the number gh printed> ISSUES="533 534"
```

`make check-pr-link` must exit 0. An empty `closingIssuesReferences` on a PR that fixes something is a bug in the PR, not a formality.
