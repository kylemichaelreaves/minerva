# Reader → Syntax Entry Point Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dependency-syntax overlay reachable from the Reader's selection toolbar, and make its German-only scope true in code rather than by accident.

**Architecture:** Two halves. Server: `load_or_parse` reads the chunk's language and refuses anything but `deu` before parsing or writing. Client: `SelectionToolbar` gains an optional `Syntax` action; the Reader supplies it only for a German edition and navigates to the route that already exists.

**Tech Stack:** Python 3.13 + SQLite (backend, pytest); SolidJS + TypeScript (frontend, Vitest + `@solidjs/testing-library`).

**Spec:** `docs/superpowers/specs/2026-08-05-reader-syntax-entry-point-design.md`
**Issues:** #231 (ungated parser). The unreachable-overlay problem has no issue of its own — this plan closes it and #231 together.

## Global Constraints

- **German only.** The supported language is exactly `"deu"`. Reject other languages; do **not** dispatch a model per language (explicitly out of scope in `docs/syntax-annotation-plan.md:38`).
- **The guard lives in `load_or_parse`, not in the HTTP handler.** `load_or_parse` is the function that parses and then calls `save_parse`; putting the check there means the handler, the CLI, and any future caller inherit it.
- **A refusal writes nothing.** No `chunk_syntax` row, no `chunk_syntax_state` row.
- **A refusal must return before `from .parse import ...`.** CI does not install the `[lemma]` extra, so Stanza is absent; a guard placed after the import would pass locally and fail in CI.
- **400 for a non-German chunk; 404 for a chunk that does not exist.** The two must stay distinguishable.
- **Keyboard shortcut is `S`.** Verified free — the single-letter keys bound anywhere in `web/src` are `f/F`, `j/k`, `l/L`, `r/R`, `t/T`.
- **`SelectionToolbar` stays presentational.** It receives `onSyntax?: () => void` and never learns the chunk id or the language.
- Run `make check` before the final commit of each task that touches Python or TypeScript.

---

## File Structure

**Modified — backend**
- `src/minerva/syntax/queries.py` — new `UnsupportedSyntaxLanguage` exception; `load_or_parse` gains the language guard.
- `src/minerva/http/handlers/syntax.py` — `_handle_chunk_syntax` maps that exception to 400.

**Modified — frontend**
- `web/src/Reader/components/SelectionToolbar.tsx` — optional `onSyntax` prop + button. Presentational only.
- `web/src/Reader/useSelectionToolbar.tsx` — `commitSyntax`, the `S` key, two new props, plus two extractions of existing code: `closeSelection()` and the pure `toolbarKeyAction()`.
- `web/src/Reader/index.tsx` — computes `syntaxEnabled()`, wires the hook and the button.

**Modified — tests**
- `tests/conftest.py` — `populated_db` gains one German chunk.
- `tests/test_syntax_endpoint.py`, `tests/test_syntax_corrections_endpoint.py`, `tests/test_api_contract.py` — repointed at the German chunk.

**Created — tests**
- Cases appended to `tests/test_syntax_endpoint.py`, `web/tests/SelectionToolbar.test.tsx`, `web/tests/useSelectionToolbar.test.ts`.

### Why Task 1 exists

`make_chunk` in `tests/conftest.py:32` defaults to `lang="eng"`, and `rep-509d` — the chunk every syntax test uses — is English prose from the *Republic*. The moment the guard lands, every test that reaches `load_or_parse` through an English chunk starts failing. Three files do:

```
$ grep -rln "load_or_parse\|_handle_chunk_syntax" tests/
tests/test_syntax_endpoint.py
tests/test_syntax_corrections_endpoint.py
tests/test_api_contract.py
```

`tests/test_syntax_queries.py` and `tests/test_server_syntax_transport.py` are **not** affected — they call `load_parse` / `save_parse` directly, or only the corrections endpoints, none of which are guarded.

Task 1 does that migration on its own, with no behaviour change, so the guard in Task 2 lands against a suite that is already green for the right reason.

---

### Task 1: German fixture chunk, and repoint the syntax tests at it

**Files:**
- Modify: `tests/conftest.py:107-140` (the `chunks` list in `populated_db`)
- Modify: `tests/test_syntax_endpoint.py:17`
- Modify: `tests/test_syntax_corrections_endpoint.py:25`
- Modify: `tests/test_api_contract.py` (the syntax chunk constant — locate it in step 3)

**Interfaces:**
- Consumes: nothing.
- Produces: chunk id `"hegel-p17"` in `populated_db`, `lang="deu"`, text `"Der Geist entwickelt sich nur in der Zeit."` — every later task's German fixture.

- [ ] **Step 1: Add the German chunk to `populated_db`**

In `tests/conftest.py`, inside the `chunks` list in `populated_db`, after the `phaedo-72e` entry:

```python
        # German, for the syntax tests. The dependency parser is
        # German-only (`syntax/parse.py:_LANG = "de"`) and `load_or_parse`
        # refuses anything else, so a syntax fixture cannot be one of the
        # English Plato chunks above.
        make_chunk(
            chunk_id="hegel-p17",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="¶17",
            book=None,
            text="Der Geist entwickelt sich nur in der Zeit.",
        ),
```

- [ ] **Step 2: Run the full suite to catch any count assertion that this breaks**

Run: `./.venv/bin/python -m pytest tests/ -q --tb=short`
Expected: PASS. `populated_db` gains a row, so a test asserting a corpus-wide total would fail here. If one does, update its expected number — the new chunk is intentional.

- [ ] **Step 3: Find every syntax test pinned to the English chunk**

Run: `grep -rn '"rep-509d"' tests/test_syntax_endpoint.py tests/test_syntax_corrections_endpoint.py tests/test_api_contract.py`

Expected: a `CHUNK = "rep-509d"` constant in each of the first two, plus one or more literals in `test_api_contract.py`.

- [ ] **Step 4: Repoint them**

In `tests/test_syntax_endpoint.py` and `tests/test_syntax_corrections_endpoint.py`, change the constant:

```python
# The syntax path is German-only (see `load_or_parse`); an English chunk
# is refused, so this cannot be one of the Plato fixtures.
CHUNK = "hegel-p17"
```

In `tests/test_api_contract.py`, replace the syntax-related `"rep-509d"` literals with `"hegel-p17"`. Leave any non-syntax use of `"rep-509d"` alone — that chunk still exists and other contracts still use it.

- [ ] **Step 5: Run the three files**

Run: `./.venv/bin/python -m pytest tests/test_syntax_endpoint.py tests/test_syntax_corrections_endpoint.py tests/test_api_contract.py -q`
Expected: PASS. Nothing about behaviour changed — the parser is monkeypatched in these tests, so the text's actual language is irrelevant to them today. This step only removes the dependency on a language the guard is about to reject.

- [ ] **Step 6: Full suite + commit**

Run: `./.venv/bin/python -m pytest tests/ -q`
Expected: PASS.

```bash
git add tests/conftest.py tests/test_syntax_endpoint.py \
        tests/test_syntax_corrections_endpoint.py tests/test_api_contract.py
git commit -m "test: give the syntax tests a German fixture chunk

The dependency parser is German-only and \`load_or_parse\` is about to
enforce that. Every syntax test ran against \`rep-509d\`, English prose from
the Republic, because \`make_chunk\` defaults to \`lang=\"eng\"\`.

No behaviour change: the parser is monkeypatched in these tests, so the
text's language was never load-bearing for them. This only removes the
dependency on a language the guard will reject."
```

---

### Task 2: German-only guard in `load_or_parse`, 400 at the endpoint

**Files:**
- Modify: `src/minerva/syntax/queries.py:196-224` (`load_or_parse`) + a new exception near the top
- Modify: `src/minerva/http/handlers/syntax.py:62-66` (`_handle_chunk_syntax`)
- Test: `tests/test_syntax_endpoint.py`

**Interfaces:**
- Consumes: `"hegel-p17"` (`deu`) and `"rep-509d"` (`eng`) from `populated_db`.
- Produces: `queries.UnsupportedSyntaxLanguage(chunk_id: str, lang: str)`, raised by `load_or_parse`; `_handle_chunk_syntax` raises `_HTTPError(HTTPStatus.BAD_REQUEST, ...)` for it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_syntax_endpoint.py`:

```python
def test_non_german_chunk_is_refused_with_400(deps) -> None:
    """The parser is German-only (`syntax/parse.py:_LANG = "de"`). Without
    this guard the German model parses Greek or English and the result is
    cached as authoritative (#231)."""

    with pytest.raises(_HTTPError) as exc:
        _handle_chunk_syntax(deps, "rep-509d")  # English

    assert exc.value.status == 400
    assert "eng" in exc.value.message


def test_refusing_writes_nothing(deps) -> None:
    """Asserted against the table, not the return value. A guard placed
    after `save_parse` would pass a return-value test and still write the
    row this issue is about."""

    with pytest.raises(_HTTPError):
        _handle_chunk_syntax(deps, "rep-509d")

    for table in ("chunk_syntax", "chunk_syntax_state"):
        n = deps.conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE chunk_id = ?", ("rep-509d",)
        ).fetchone()[0]
        assert n == 0, f"{table} was written for a refused chunk"


def test_refusal_does_not_call_the_parser(deps) -> None:
    """The refusal must return before `from .parse import ...`. CI does not
    install the `[lemma]` extra, so a guard after the import would pass
    locally and fail in CI."""

    with pytest.raises(_HTTPError):
        _handle_chunk_syntax(deps, "rep-509d")

    assert deps.parse_calls == []


def test_unknown_chunk_is_still_404(deps) -> None:
    """400 and 404 must stay distinguishable — 'wrong language' and 'no such
    chunk' are different problems with different fixes."""

    with pytest.raises(_HTTPError) as exc:
        _handle_chunk_syntax(deps, "no-such-chunk")

    assert exc.value.status == 404


def test_german_chunk_still_parses(deps) -> None:
    """The guard must not break the supported path."""

    body = _handle_chunk_syntax(deps, CHUNK)
    assert len(body["sentences"]) == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_syntax_endpoint.py -q -k "refused or writes_nothing or does_not_call or still_404 or still_parses"`
Expected: `test_non_german_chunk_is_refused_with_400`, `test_refusing_writes_nothing` and `test_refusal_does_not_call_the_parser` FAIL — the English chunk parses happily today. `test_unknown_chunk_is_still_404` and `test_german_chunk_still_parses` should already PASS.

- [ ] **Step 3: Add the exception**

In `src/minerva/syntax/queries.py`, after the `CORRECTABLE` constant (around line 21):

```python
#: The only language the dependency parser handles. `syntax/parse.py` builds a
#: Stanza German pipeline (`_LANG = "de"`); there is no per-language dispatch,
#: and adding one is explicitly out of scope in the annotation plan.
SUPPORTED_LANG = "deu"


class UnsupportedSyntaxLanguage(Exception):
    """Raised when a chunk is not in a language the parser handles.

    Its whole purpose is to stop the German model from parsing Greek or
    Latin and `save_parse` caching the output as authoritative (#231). The
    caller decides how to surface it; the HTTP layer answers 400.
    """

    def __init__(self, chunk_id: str, lang: str) -> None:
        super().__init__(
            f"syntax parsing is {SUPPORTED_LANG}-only; "
            f"chunk {chunk_id!r} is {lang!r}"
        )
        self.chunk_id = chunk_id
        self.lang = lang
```

- [ ] **Step 4: Guard `load_or_parse`**

Replace the body of `load_or_parse` (`src/minerva/syntax/queries.py:209-224`) with:

```python
    # Language first, before the cache read and before the Stanza import.
    #
    # Before the cache, because a cached tree for a non-German chunk could
    # only have come from the German model and should not be served either.
    # Before the import, because CI has no `[lemma]` extra — a guard placed
    # after it would pass locally and fail there.
    row = conn.execute(
        "SELECT text, lang FROM chunks WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if row is None:
        return None
    lang = str(row["lang"])
    if lang != SUPPORTED_LANG:
        raise UnsupportedSyntaxLanguage(chunk_id, lang)

    cached = load_parse(conn, chunk_id)
    if cached is not None:
        return cached

    # Imported here, not at module scope: `stanza` is in the optional
    # `[lemma]` extra, and every other function in this module must keep
    # working without it.
    from .parse import parse_text, parser_id

    tokens = parse_text(str(row["text"]))
    save_parse(conn, chunk_id, tokens, parser=parser_id())
    return tokens
```

Also update the docstring's "Returns None when no such chunk exists" paragraph by appending:

```
    Raises :class:`UnsupportedSyntaxLanguage` for a chunk the parser cannot
    handle — checked before the cache read and before Stanza is imported.
```

- [ ] **Step 5: Map it to 400 at the endpoint**

In `src/minerva/http/handlers/syntax.py`, replace lines 63-65:

```python
    try:
        tokens = syntax_queries.load_or_parse(deps.conn, chunk_id)
    except syntax_queries.UnsupportedSyntaxLanguage as exc:
        # 400, not 404: the chunk exists, the request is the problem. A 404
        # here would send the caller looking for a missing chunk.
        raise _HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
    if tokens is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "chunk not found")
```

- [ ] **Step 6: Run the tests**

Run: `./.venv/bin/python -m pytest tests/test_syntax_endpoint.py tests/test_syntax_corrections_endpoint.py tests/test_syntax_queries.py -q`
Expected: PASS, all files.

- [ ] **Step 7: Full gate + commit**

Run: `make check`
Expected: `All checks passed!` and pytest green.

```bash
git add src/minerva/syntax/queries.py src/minerva/http/handlers/syntax.py \
        tests/test_syntax_endpoint.py
git commit -m "fix(syntax): refuse to parse non-German chunks (#231)

\`syntax/parse.py\` hardcodes a German Stanza pipeline and nothing between the
endpoint and it checked the chunk's language, while \`load_or_parse\` parses on
demand and \`save_parse\` caches the result. A request for a Greek or Latin
chunk therefore ran the German model over it and persisted the output as
authoritative.

The guard is in \`load_or_parse\`, not the handler: that is the function which
parses and then writes, so the handler, the CLI and any future caller inherit
it. It runs before the cache read (a cached non-German tree could only have
come from the German model) and before the Stanza import (CI has no
\`[lemma]\` extra).

400, kept distinct from the existing 404 for an unknown chunk.

Closes #231."
```

---

### Task 3: The `Syntax` button in `SelectionToolbar`

**Files:**
- Modify: `web/src/Reader/components/SelectionToolbar.tsx:20-29` (props) and `:96-113` (buttons)
- Test: `web/tests/SelectionToolbar.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SelectionToolbar` prop `onSyntax?: () => void`. Rendered only when supplied. Task 4 supplies it.

- [ ] **Step 1: Write the failing tests**

In `web/tests/SelectionToolbar.test.tsx`, extend the helper's `overrides` type and body to accept `onSyntax`:

```tsx
function renderToolbar(
  overrides: Partial<{
    singleWord: boolean;
    onLookup: () => void;
    onSyntax: () => void;
  }> = {},
) {
  const onTranslate = vi.fn();
  const onCopy = vi.fn();
  const onDismiss = vi.fn();
  const onLookup = overrides.onLookup ?? vi.fn();
  const utils = render(() => (
    <SelectionToolbar
      anchor={{ rect: new DOMRect(100, 10, 40, 20) }}
      count="4 words"
      singleWord={overrides.singleWord ?? false}
      onTranslate={onTranslate}
      onLookup={onLookup}
      onSyntax={overrides.onSyntax}
      onCopy={onCopy}
      onDismiss={onDismiss}
    />
  ));
  return { onTranslate, onCopy, onDismiss, onLookup, ...utils };
}
```

Then append these cases inside the existing `describe("<SelectionToolbar />", ...)`:

```tsx
  it("omits the syntax action when no handler is supplied", () => {
    const { container } = renderToolbar();
    expect(container.textContent).not.toContain("Syntax");
  });

  it("renders the syntax action and calls it on click", () => {
    const onSyntax = vi.fn();
    const { container } = renderToolbar({ onSyntax });
    expect(container.textContent).toContain("Syntax");

    const btn = Array.from(container.querySelectorAll(".st-btn")).find((b) =>
      b.textContent?.includes("Syntax"),
    );
    fireEvent.click(btn!);
    expect(onSyntax).toHaveBeenCalledTimes(1);
  });

  it("keeps the other actions working when syntax is present", () => {
    const { container, onTranslate, onCopy } = renderToolbar({ onSyntax: vi.fn() });
    const byText = (s: string) =>
      Array.from(container.querySelectorAll(".st-btn")).find((b) =>
        b.textContent?.includes(s),
      )!;
    fireEvent.click(byText("Translate"));
    fireEvent.click(byText("Copy"));
    expect(onTranslate).toHaveBeenCalledTimes(1);
    expect(onCopy).toHaveBeenCalledTimes(1);
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web run test:unit -- SelectionToolbar`
Expected: the two syntax cases FAIL (no "Syntax" text; the `onSyntax` prop is not accepted). The third may fail to compile for the same reason.

- [ ] **Step 3: Add the prop**

In `web/src/Reader/components/SelectionToolbar.tsx`, add to the props object (after `onLookup?`):

```tsx
  /** Supplied only when the syntax overlay is available for this
   *  selection — the Reader withholds it for non-German editions, since
   *  the dependency parser is German-only. Absent means no button. */
  onSyntax?: () => void;
```

- [ ] **Step 4: Add the button**

In the same file, between the Translate button's closing `</button>` and the `<div class="st-sep" />` that precedes Copy:

```tsx
      <Show when={props.onSyntax}>
        <div class="st-sep" />
        <button
          type="button"
          class="st-btn"
          onClick={() => { props.onSyntax!(); }}
          title="Syntax (S)"
        >
          <span>Syntax</span>
          <span class="kbd">S</span>
        </button>
      </Show>
```

`Show` is already imported in this file.

- [ ] **Step 5: Update the shape comment**

The header comment at `:6-8` describes two toolbar shapes and predates the Copy button. Replace it with:

```tsx
// Shapes, driven by `singleWord` and by which optional handlers are given:
//   • multi-word:  [ Translate phrase · T ] [ Syntax · S ]? [Copy] [ <count> ]
//   • single-word: [ Look up · L ] [ Translate · T ] [ Syntax · S ]? [Copy] [ <count> ]
// `?` = rendered only when the corresponding handler is supplied.
```

- [ ] **Step 6: Run the tests**

Run: `npm --prefix web run test:unit -- SelectionToolbar`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/Reader/components/SelectionToolbar.tsx web/tests/SelectionToolbar.test.tsx
git commit -m "feat(reader): add an optional Syntax action to the selection toolbar

Presentational only — the button renders when \`onSyntax\` is supplied and is
absent otherwise. The toolbar never learns the chunk id or the language; the
Reader decides whether the action exists.

Also corrects the header comment, which listed two shapes and predated the
Copy button."
```

---

### Task 4: Wire the action — `commitSyntax`, the `S` key, and the German gate

**Files:**
- Modify: `web/src/Reader/useSelectionToolbar.tsx:39-57` (api type), `:59-78` (props), `:192-213` (commits), `:252-280` (keys)
- Modify: `web/src/Reader/index.tsx:144` (hook call) and `:338-350` (toolbar render)
- Test: `web/tests/useSelectionToolbar.test.ts`

**Interfaces:**
- Consumes: `SelectionToolbar`'s `onSyntax?: () => void` from Task 3; the 400 guard from Task 2 as the server-side backstop.
- Produces: `SelectionToolbarApi.commitSyntax(t: SelToolbar): void`; `SelectionToolbarProps.onSyntaxRequest?: (chunkId: string) => void`; `SelectionToolbarProps.syntaxEnabled?: () => boolean`; exported `toolbarKeyAction(e, opts): ToolbarKeyAction | null`.

**Two refactors of existing code are part of this task**, decided before execution:

1. **`closeSelection()`** — all three commit paths clear the toolbar and drop
   the browser selection. `commitTranslate` does it as
   `removeAllRanges()` then `setSelToolbar(null)`; `commitLookup` does the
   same pair in the opposite order. Extracting one helper removes the
   duplication `commitSyntax` would otherwise add a third copy of, and
   normalises the inconsistent ordering. The two operations are independent
   and synchronous, so order was never load-bearing.
2. **`toolbarKeyAction()`** — the keydown handler currently mixes its
   form-field guards with its dispatch, inside a `createEffect` that only
   runs once `selToolbar()` is non-null, which requires a real DOM `Range`.
   That is why the existing test file states it does not exercise the
   Selection API helpers, and it would have left the `S` key untestable.
   Extracting the decision as a pure function makes the whole key map
   testable — `t`, `l`, `Escape` included, which are untested today — without
   any Range scaffolding. The effect becomes a thin dispatcher.

- [ ] **Step 1: Write the failing tests**

Append to `web/tests/useSelectionToolbar.test.ts`, as a **new `describe` block** after the existing `describe("useSelectionToolbar persistence", ...)`. This reuses the file's existing `buildToolbar` helper and its `createRoot` pattern — do not invent new ones.

```ts
describe("useSelectionToolbar syntax action", () => {
  it("commitSyntax reports the chunk of the first pinned span", () => {
    createRoot((dispose) => {
      const onSyntaxRequest = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
        syntaxEnabled: () => true,
        onSyntaxRequest,
      });
      const toolbar = buildToolbar("Der Geist", "¶17", [
        { chunkId: "hegel-p17", start: 0, end: 9 },
      ]);

      api.commitSyntax(toolbar);

      expect(onSyntaxRequest).toHaveBeenCalledWith("hegel-p17");
      dispose();
    });
  });

  it("commitSyntax is inert when the selection has no pinned span", () => {
    createRoot((dispose) => {
      const onSyntaxRequest = vi.fn();
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
        syntaxEnabled: () => true,
        onSyntaxRequest,
      });
      const toolbar = buildToolbar("Der Geist", "¶17", []);

      api.commitSyntax(toolbar);

      expect(onSyntaxRequest).not.toHaveBeenCalled();
      dispose();
    });
  });

  it("commitSyntax does nothing when no handler is supplied", () => {
    createRoot((dispose) => {
      const api = useSelectionToolbar({
        getStage: () => undefined,
        workId: () => "Phänomenologie des Geistes",
        onTranslateRequest: vi.fn(),
        onLookupRequest: vi.fn(),
      });
      const toolbar = buildToolbar("Der Geist", "¶17", [
        { chunkId: "hegel-p17", start: 0, end: 9 },
      ]);

      // Must not throw — `onSyntaxRequest` is optional.
      expect(() => { api.commitSyntax(toolbar); }).not.toThrow();
      dispose();
    });
  });
});
```

Then append a second new `describe` block for the extracted key map. Add `toolbarKeyAction` to the existing import from `~/Reader/useSelectionToolbar`:

```ts
describe("toolbarKeyAction", () => {
  const ev = (key: string, target?: EventTarget) => {
    const e = new KeyboardEvent("keydown", { key });
    if (target) Object.defineProperty(e, "target", { value: target });
    return e;
  };
  const opts = (over: Partial<{ singleWord: boolean; syntaxEnabled: boolean }> = {}) => ({
    singleWord: over.singleWord ?? false,
    syntaxEnabled: over.syntaxEnabled ?? false,
  });

  it("maps S to syntax only when syntax is enabled", () => {
    expect(toolbarKeyAction(ev("s"), opts({ syntaxEnabled: true }))).toBe("syntax");
    expect(toolbarKeyAction(ev("S"), opts({ syntaxEnabled: true }))).toBe("syntax");
    expect(toolbarKeyAction(ev("s"), opts({ syntaxEnabled: false }))).toBeNull();
  });

  it("maps L to lookup only for a single-word selection", () => {
    expect(toolbarKeyAction(ev("l"), opts({ singleWord: true }))).toBe("lookup");
    expect(toolbarKeyAction(ev("l"), opts({ singleWord: false }))).toBeNull();
  });

  it("maps T to translate and Escape to dismiss", () => {
    expect(toolbarKeyAction(ev("t"), opts())).toBe("translate");
    expect(toolbarKeyAction(ev("T"), opts())).toBe("translate");
    expect(toolbarKeyAction(ev("Escape"), opts())).toBe("dismiss");
  });

  it("yields to form fields and editable regions", () => {
    for (const tag of ["input", "textarea", "select"]) {
      const el = document.createElement(tag);
      expect(toolbarKeyAction(ev("t", el), opts())).toBeNull();
    }
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    // jsdom does not derive isContentEditable from the attribute.
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(toolbarKeyAction(ev("t", editable), opts())).toBeNull();
  });

  it("ignores unrelated keys", () => {
    expect(toolbarKeyAction(ev("x"), opts({ singleWord: true, syntaxEnabled: true }))).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web run test:unit -- useSelectionToolbar`
Expected: FAIL — `commitSyntax` does not exist on the api, and `syntaxEnabled` / `onSyntaxRequest` are not accepted props.

- [ ] **Step 3: Extend the props and api types**

In `web/src/Reader/useSelectionToolbar.tsx`, add to `SelectionToolbarApi`:

```ts
  /** Open the dependency-syntax overlay for the selection's chunk.
   *  No-op when the selection has no pinned span. */
  commitSyntax: (t: SelToolbar) => void;
```

and to `SelectionToolbarProps`:

```ts
  /** Whether the syntax overlay applies to what is on screen. The parser is
   *  German-only, so the Reader passes `() => sourceLang === "deu"`. Gates
   *  the `S` key; the button is gated by the caller withholding `onSyntax`.
   *  The server refuses non-German independently — this is convenience, not
   *  the guarantee. */
  syntaxEnabled?: () => boolean;
  /** Navigate to the syntax overlay for `chunkId`. */
  onSyntaxRequest?: (chunkId: string) => void;
```

- [ ] **Step 4: Extract `closeSelection`, and use it in the two existing commits**

Above `commitTranslate` (around `:170`):

```ts
  /** Close the toolbar and drop the browser selection. Every commit path
   *  does this before handing off; the two operations are independent and
   *  synchronous, so the order the call sites used to differ in never
   *  mattered. */
  function closeSelection() {
    setSelToolbar(null);
    window.getSelection()?.removeAllRanges();
  }
```

In `commitTranslate`, replace:

```ts
    const sel = window.getSelection();
    sel?.removeAllRanges();
    setSelToolbar(null);
```

with `closeSelection();`.

In `commitLookup`, replace:

```ts
    setSelToolbar(null);
    const sel = window.getSelection();
    sel?.removeAllRanges();
```

with `closeSelection();`.

- [ ] **Step 5: Run the existing tests to prove the extraction changed nothing**

Run: `npm --prefix web run test:unit -- useSelectionToolbar`
Expected: the existing persistence tests still PASS. They drive `commitTranslate`, so they cover the extraction. The new syntax tests still fail — `commitSyntax` does not exist yet.

- [ ] **Step 6: Implement `commitSyntax`**

After `commitLookup`:

```ts
  function commitSyntax(t: SelToolbar) {
    // The chunk comes off the first pinned span — the one the selection
    // started in — same derivation as commitLookup.
    closeSelection();
    const p = t.pinned[0];
    if (p === undefined) return;
    props.onSyntaxRequest?.(p.chunkId);
  }
```

Add `commitSyntax` to the object the hook returns, next to `commitLookup`.

- [ ] **Step 7: Extract the key map as a pure function**

At module scope in `web/src/Reader/useSelectionToolbar.tsx`, above the hook:

```ts
export type ToolbarKeyAction = "dismiss" | "translate" | "lookup" | "syntax";

/** Which toolbar action a keydown should trigger, or null for none.
 *
 *  Pure, and exported, because the listener that consumes it lives in a
 *  `createEffect` gated on an open toolbar — which requires a real DOM
 *  Range to produce. Keeping the decision separate from the dispatch is
 *  what makes the key map testable at all; it was untested before. */
export function toolbarKeyAction(
  e: KeyboardEvent,
  opts: { singleWord: boolean; syntaxEnabled: boolean },
): ToolbarKeyAction | null {
  // Don't hijack keys while the user is typing in a form field or an
  // editable region — let those widgets keep their keystrokes.
  // (instanceof, not a cast: e.target can be the Document itself, which
  // has no tagName.)
  const el = e.target instanceof HTMLElement ? e.target : null;
  const tag = el?.tagName.toLowerCase();
  if (tag === "textarea" || tag === "input" || tag === "select") return null;
  if (el?.isContentEditable) return null;

  if (e.key === "Escape") return "dismiss";
  if (e.key === "t" || e.key === "T") return "translate";
  if ((e.key === "l" || e.key === "L") && opts.singleWord) return "lookup";
  if ((e.key === "s" || e.key === "S") && opts.syntaxEnabled) return "syntax";
  return null;
}
```

- [ ] **Step 8: Reduce the effect to a dispatcher**

Replace the body of `onKey` inside the keydown `createEffect` with:

```ts
    const onKey = (e: KeyboardEvent) => {
      const action = toolbarKeyAction(e, {
        singleWord: t.singleWord,
        syntaxEnabled: props.syntaxEnabled?.() ?? false,
      });
      if (action === null) return;
      if (action === "dismiss") {
        setSelToolbar(null);
        return;
      }
      e.preventDefault();
      if (action === "translate") commitTranslate(t);
      else if (action === "lookup") commitLookup(t);
      else commitSyntax(t);
    };
```

Leave the `addEventListener` / `onCleanup` pair below it untouched — the
comment there explains why cleanup is registered that way, and this change
does not affect it.

Note `Escape` keeps its no-`preventDefault` behaviour, matching the original.

- [ ] **Step 9: Run the hook tests**

Run: `npm --prefix web run test:unit -- useSelectionToolbar`
Expected: PASS.

- [ ] **Step 10: Wire it in the Reader**

In `web/src/Reader/index.tsx`, above the `useSelectionToolbar` call at `:144`:

```tsx
  // The dependency parser is German-only (`syntax/parse.py:_LANG = "de"`),
  // so the action is offered only on a German edition. The server refuses
  // non-German independently (400) — this keeps a dead button off screen,
  // it is not the safety property.
  const syntaxEnabled = () => props.sourceLang === "deu";
```

Add to the options object passed to `useSelectionToolbar({ ... })`:

```tsx
    syntaxEnabled,
    onSyntaxRequest: (chunkId: string) => {
      // Direct hash write, matching `onOpenWorkConcordance` above: a
      // single-purpose CTA does not justify threading the routing
      // controller through readerCtrl.
      window.location.hash =
        `#/syntax/${encodeURIComponent(chunkId)}` +
        `?work=${encodeURIComponent(props.workId)}`;
    },
```

And in the `SelectionToolbar` JSX at `:340-348`, add after `onLookup`:

```tsx
            onSyntax={
              syntaxEnabled() ? () => { selection.commitSyntax(t()); } : undefined
            }
```

- [ ] **Step 11: Verify the hash format matches the router**

Run: `grep -n 'kind === "syntax"' -A2 web/src/routing.ts`
Expected: `#/syntax/${encodeURIComponent(route.chunkId)}` with `?work=${encodeURIComponent(route.workId)}` — the same shape written in step 7. If they differ, the router is the authority; change step 7 to match.

- [ ] **Step 12: Full gate**

Run: `make check`
Expected: `All checks passed!`, pytest and vitest green.

- [ ] **Step 13: Manual check**

Run: `make run`, open a German work (Hegel or Nietzsche), select a phrase.
Expected: the toolbar shows `Syntax · S`; clicking it opens the arc diagram for that chunk; closing returns to the Reader at the same work. Then open an English or Greek work and select a phrase: no Syntax action.

- [ ] **Step 14: Commit**

```bash
git add web/src/Reader/useSelectionToolbar.tsx web/src/Reader/index.tsx \
        web/tests/useSelectionToolbar.test.ts
git commit -m "feat(reader): open the syntax overlay from the selection toolbar

The overlay has been complete since #138 and unreachable the whole time —
nothing in the app navigated to \`#/syntax/<chunkId>\`. Counting route-kind
references outside the routing plumbing found three doorless routes; the
annotation plan told us to follow the \`#/network/arc\` pattern, and that
pattern is itself doorless, which is how a seven-phase feature shipped
without an entry point.

Offered only on a German edition, since the parser is German-only. The
server refuses non-German independently (#231); this keeps a dead button
off screen rather than being the safety property."
```

---

## Self-Review

**Spec coverage.** Each spec section maps to a task:

| Spec section | Task |
|---|---|
| The change (button, shortcut `S`, prop shape) | 3, 4 |
| Why the selection toolbar | 4 (step 7 comment) |
| Language gate (UI) | 4 |
| Server-side guard (#231), placement in `load_or_parse` | 2 |
| Data flow | 4 (step 7) |
| Error handling (400 vs 404, no write, pre-import) | 2 |
| Testing — `SelectionToolbar` | 3 |
| Testing — selection controller | 4 |
| Testing — `load_or_parse` | 2 |
| Acceptance criteria | 2 (steps 6-7), 4 (steps 9-10) |

Out-of-scope items (per-language dispatch, `network-arc` / `network-coverage`, new morphology surface) have no tasks, correctly.

**Placeholder scan.** No TBD/TODO. Every code step carries the code, written against the helpers the target files actually have (`buildToolbar` and `createRoot` in `useSelectionToolbar.test.ts`, `renderToolbar` in `SelectionToolbar.test.tsx`, the monkeypatched `deps` fixture in `test_syntax_endpoint.py`).

**No coverage gaps.** An earlier revision left the `S` key untested, because its listener sits behind a `createEffect` gated on a selection that needs a real DOM `Range`. Rather than accept that, Task 4 extracts the key map as a pure `toolbarKeyAction`, which makes the whole map testable without any Range scaffolding — `t`, `l` and `Escape` included, none of which had tests before.

**Two refactors of existing code, decided pre-flight rather than discovered mid-review.** `closeSelection()` deduplicates the toolbar/selection teardown that all three commit paths share (and normalises the inconsistent ordering between `commitTranslate` and `commitLookup`); `toolbarKeyAction()` separates the key decision from its dispatch. Both are in Task 4, each with a step that runs the existing tests to prove the extraction changed nothing before new behaviour is added on top.

**Type consistency.** `UnsupportedSyntaxLanguage(chunk_id, lang)` is defined in Task 2 step 3 and used in step 5 with the same signature. `SUPPORTED_LANG = "deu"` is defined once and used in the guard and the message. `commitSyntax(t: SelToolbar)` is declared in Task 4 step 3 and implemented in step 4 with the same signature; `onSyntaxRequest(chunkId: string)` and `syntaxEnabled(): boolean` match across steps 3, 4, 5 and 7. `onSyntax?: () => void` is the same in Task 3 (definition) and Task 4 step 7 (supply).

**Known risk, stated rather than hidden.** The UI gate reads `props.sourceLang` — the edition's language — while the server guard reads the chunk's own `lang`. For a Reader showing one edition these agree. If they ever diverge, the server wins and the user sees a 400 from a button that should not have been there. That is the safe direction, and the server guard is the property that matters.
