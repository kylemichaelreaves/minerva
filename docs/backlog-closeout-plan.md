# Backlog close-out plan

Plan of record for closing the twelve issues open on 2026-08-08. Written
so the work survives session boundaries: it names the batches, the order,
the decisions already taken, and the verification each PR owes.

**The open issue list is the progress bar.** An issue still open is still
to do; this document does not track state separately, because a second
tracker rots. Start any session by re-reading it against reality:

```
gh issue list --state open
gh pr list --state open
```

## Context

All twelve issues were verified against `main` at `dd30678` and against
the live `data/index.sqlite` on 2026-08-08. None had been silently fixed,
and every measured number in every issue body still reproduced — the
`refs_scan_state` orphan count (31,629 / 460,235), the lemma residue
(419 eng / 299 fra / 126 deu / 15 grc), the 753 chunks over 8,000 chars,
`terms`/`term_occurrences` at 0/0, and Agamemnon (eng) as a single
82,256-character chunk.

Six of the twelve came out of a single operator re-ingest (#262, #263,
#264, #274) or out of PRs merged the same week (#272, #276). That context
is expensive to rebuild, which is what sets the ordering.

Decisions taken 2026-08-08 by the repo owner:

- **#136 fact 2** — split the reformat into separate PRs. Measured: this
  works, but the cut is by *file coverage*, not by directory.
- **#182** — build the named-passage table; do not park or close.
- **#176** — add the gate, then re-chunk the worst parser failures only.
- **Delivery** — one PR per batch, each carrying both issues' `Closes`
  lines.

Still owed by the repo owner as of 2026-08-09, and neither belongs to a
batch:

- **#299** — accept the projekt-gutenberg block, ask the operator to
  allowlist a research UA, or re-source the six works elsewhere. Its
  premise was corrected in batch 5-bis and the recommendation there is to
  accept; whichever way it goes, it must not be resolved by rotating the
  User-Agent.
- **The Marx chrome audit** — whether it happens at all, and it is
  timing-sensitive rather than urgent. See the note above 4-op's step
  list; if it happens, it happens *before* that window.

### Scope check, measured 2026-08-09

Two days in, the open-issue count had gone from twelve to thirteen, which
reads as a treadmill: **26 issues filed, 22 resolved**. Split by *which
backlog they belong to*, it is not one, and the difference is worth
having written down because the raw count will keep suggesting otherwise.

**Of the original twelve, nine are done.** The three still open are
#176, #182 and #136 — which are, in that order, the last three this
document has scheduled since it was written. Nothing is behind; the
remainder is the tail it always had. Every other open issue was filed
*by* this work.

**And the filed-along-the-way ones are decaying fast.** Today's chain,
each found verifying the fix above it, measured by corpus rows affected:

| issue | rows affected |
|---|---:|
| #307 | 241,736 |
| #311 | 203,610 |
| #314 | 214 |
| #316 | 0 — tech-debt |
| #317 | 0 — tech-debt, and no defect demonstrated |

Three orders of magnitude in a day, ending at two that touch no data at
all. That is what convergence looks like from inside a
verification-driven round: each fix's verification finds the next layer
and the layers thin out. `chunk_lemmas` now satisfies
`text[surface_start:surface_end] == surface_form` on every language
except `ara`, which is #314.

**So the risk is not the discovery rate. It is absorption.** "A found
issue joins a batch" is the right rule for keeping findings cheap — it is
why #297 cost one session rather than two — but it quietly converts
"close the twelve open on 2026-08-08" into "close everything this work
ever finds", and nothing above says the effort cannot finish before that.

### Decision taken 2026-08-09 by the repo owner: the scope is capped at the original twelve

**This document finishes when the twelve issues open on 2026-08-08 are
resolved. Everything it spawned is filed and graduates to ordinary
backlog, prioritised on its own merits.** Three remain: #182, #176 and
#136 — batches 6, 4-op and 7.

What does *not* change: findings still get filed the moment they are
found, and still get placed in a batch row. Grouping is what made #297
cost one session instead of two, and it costs nothing to keep. What
changes is that a spawned issue no longer holds this document open.

Two consequences, and the second is a real cost rather than bookkeeping.

**1. One prerequisite is pulled back in, on correctness grounds.** #314
is out of scope by the cap and must still land before 4-op. That window
re-lemmatizes, and #314 is a defect in the lemma *writer*, so running the
window first bakes its output in and the fix afterwards needs a second
pass over the same corpus. It is two lines plus a measurement. Treat it
as part of 4-op's setup, not as a batch of its own.

**2. 4-op loses its free ride, and that is a bill.** The sequencing note
below pairs 4-op with 6-bis (#285) because #285 re-derives every
`chunk_id`, so #176's re-chunk churn is subsumed and one rebuild covers
both.

> **Corrected 2026-08-15.** "#285 re-derives every `chunk_id`" is true of
> only one of the three remedies #285 offers, and it is the one the issue
> itself rules out: "Hash the whole text into `chunk_id`. Correct, but
> churns **every** id in the corpus once… Almost certainly not worth it."
> Its recommended fix is option 1 — give `embeddings` the `text_hash`
> treatment `chunk_lemma_state` already has, and re-encode on mismatch —
> which churns nothing. So the pairing this paragraph prices was never
> available at the recommended fix, and the "bill" the cap creates is
> mostly notional. Material because it cuts both ways: a session that
> scheduled 4-op *and* #285 together to "take the saving" would have
> found there was no saving to take, and might have reached for option 3
> to create one — buying a full-corpus rebuild to justify a pairing. #285 is spawned, so the cap puts it out of scope — which leaves
#176 part 2 to pay a full refs rebuild plus the llm-verify tail on its
own, and #285 to pay it again whenever it is scheduled. The coupling was
always an optimisation, never a correctness requirement, so this is
affordable; it is simply paid twice.

Recommended, and reversible: run 4-op alone unless #285 is going to be
scheduled inside the same effort. If it is, run them together as the note
below describes and take the saving. Whoever picks up #285 should check
this first — it is the one place where an out-of-scope issue changes what
an in-scope one costs.

**Everything else is genuinely free of this document.** #298's corpus
half, #291, #299, #316 and #317 hold nothing open. #298 in particular is
now an ordinary backlog item whose repair happens to be cheapest inside
whatever operator window runs next; it does not need one of its own.

## Standing gates

From [CLAUDE.md](../CLAUDE.md) — not optional, and each has failed a PR
before:

- **Every round ends with a PR.** A batch is not finished when the code
  works locally; it is finished when there is a pushed branch and an open
  PR against `main` carrying its `Closes`/`Refs` lines. Work that stops at
  a local commit is invisible to CI, to Sonar, and to the next session —
  the same failure mode this document exists to prevent. This applies to
  every round, including doc-only ones like the one that added this file.
- `make check` before every push, and **again after any edit made while
  fixing its output**.
- `check-diff-coverage` ≥80% **including branches** — Sonar scores a
  one-line guard's untested false branch 3/4, not 100% (#250).
- `Closes #N` in the PR **body**, base `main`, then verify the link
  registered. A stacked PR records nothing, and retargeting does not
  backfill.
- Duplication ≤3% on new code. Copying a component wholesale fails at any
  coverage (#254).
- Anything found along the way that isn't tracked gets its own issue
  before moving on, **and is slotted into a batch in the same round** —
  see "A found issue joins a batch" below. A correction to a wrong claim
  goes **on the source** — a comment on the issue, or a fix to the doc in
  the same PR — never into a new issue. That includes correcting your own
  earlier comment when a later measurement overturns it.
- Most of these gates are enumerated with their exit conditions in
  `.claude/commands/close-out.md`; duplication ≤3% and the reliability rating
  have no exit condition there — the command names them but cannot gate them.
  The command is the executable form; this list is the reasoning behind it. If
  they disagree, the disagreement is a bug in one of them — say which.

## A found issue joins a batch; it does not join a queue

**Every issue filed during this work gets slotted into a batch in the
table below, at the time it is filed — grouped with the batch that shares
its files or its theme wherever one exists.** Decided by the repo owner
2026-08-08, after batches 1–5 produced eleven issues that sat outside the
plan entirely.

The reason is context, which is the same reason that sets the original
ordering. Batches 1–5 each found defects a few lines from the code they
were already reading: #297 is in the file batch 5 edited, #288 is the
mirror image of the bug batch 3 fixed, #291 is the floor batch 4 moved. A
list of unslotted issues loses exactly what made them cheap — whoever
picks up #297 cold pays again for everything batch 5 learned.

So a found issue is never merely filed. It is filed **and** placed, and
placing it is part of the same round. Three rules:

- **Group by file or theme, not by severity.** A defect in a file an
  existing batch owns belongs to that batch's follow-up, even if it is
  less urgent than something in another.
- **A landed batch takes an `N-bis` follow-up** rather than a new number
  at the end, so the grouping stays legible after the fact — batch 5's
  four findings are batch 5-bis, not batch 8.
- **If nothing groups, say so explicitly** and give it its own row with a
  reason. #282 and #285 are like that; both rows below say why.

The open issue list is still the progress bar. This table is not a second
tracker of *state* — it records *grouping*, which the issue list cannot
express.

## Order

Batches 1–5 have landed. `-bis` rows are follow-ups found while working
the batch above them, and inherit its context.

**Status `backlog` means the scope cap of 2026-08-09 moved that row out
of this document.** The row stays — the grouping is the expensive part
and is worth keeping — but the issue is now ordinary backlog and holds
nothing open here. Only three rows are still in scope: **6, 4-op and 7**.
The one exception was 2-quinquies, out of scope by the cap and still a
hard prerequisite for 4-op because 4-op re-lemmatizes and #314 is a
defect in the lemma writer. **It landed 2026-08-15 as PR #382, so the
prerequisite is discharged and 4-op is unblocked on that axis.**

| # | Batch | Issues | Status | Why here |
|---|---|---|---|---|
| 0 | CI unblock | #282 | **landed** | **Groups with nothing** — a HuggingFace 429 fails *any* PR, so it taxes every batch below. Cheap, and first because it is a tollgate rather than a theme. Merged 2026-08-09 as PR #302; the row said `todo` until 2026-08-09. |
| 1 | refs verify follow-ups | #272, #276 | **landed** | Deferred scope from PRs #271/#277, merged 2026-08-08. Decays fastest. |
| 2 | `terms lemmatize` | #262, #263 | **landed** | Blocks the next Latin-touching re-ingest; #262 is a 19-minute silent hang. |
| 2-bis | lemma-row hygiene | ~~#284~~ | **landed** | `terms lemmatize --all` left stale `chunk_lemmas` rows. Same file and same predicate batch 2 rewrote. Merged 2026-08-09 with 3-ter; the issue's suggested fix was scoped to `--all` and had to be widened — see batch 2-bis. |
| 2-ter | surface offsets | ~~#307~~, ~~#309~~ | **landed** | Found verifying 2-bis, in the writer batch 2 rewrote. #307 is `lat` offsets indexing the tokenizer's rewritten string; #309 is the stale-row residue the same query exposed, which is #285's damage rather than #307's and needs an operator repair either way. Paired because one `terms lemmatize` pass over the affected languages settles both, which is what happened: PR #310 fixed the writer and the operator step below ran the pass. #311 is its residue. |
| 2-quater | NFC-layer offsets | ~~#311~~ | **landed** | Found verifying 2-ter. `terms lemmatize` fed `NFC(text)` and stored offsets against `chunks.text`; 16,032 non-NFC chunks. Same defect class as #307 one layer up, in the file batch 2 rewrote, and the last thing between `chunk_lemmas` and the invariant #310 established. The issue's "1,866 rows" is one of two failure modes; the real figure is 203,610 — see batch 2-quater. |
| 2-quinquies | Stanza's rewritten surface | ~~#314~~ | **landed — was 4-op's prereq** | Found verifying 2-quater, one function away from it. `ara`'s `surface_form` holds Stanza's rewrite of the word rather than the corpus slice — 214 rows whose span is right and whose text is not. Not the same defect: these offsets never moved, so a fix churns stored text instead. **Landed 2026-08-15 as PR #382**, ahead of 4-op exactly as the cap decision required. One line: `surface = w.text if inherited else source[start:end]`, lifted out of the `offsets is not None` branch it was wrongly nested in — the condition that matters is whether a word has a span of its *own*, not whether the text needed mapping. **The issue's own risk estimate is corrected there**: it feared the fix "rewrites `surface_form` for every non-MWT `ara` row … possibly a large fraction of the 87,478", but 72,178 of those rows already satisfy `source[start:end] == surface_form`, so the assignment is the identity for them and cannot move them. Ceiling 1,429 rows (1.63%), floor 214 (0.24%), every one of them wrong today. Trusting the estimate would have bought this its own operator window instead of a two-line change. |
| 3 | reset preservation | #274, #264 | **landed** | Same file as each other; low risk, no data migration. |
| 3-bis | refs scan cache | ~~#288~~, ~~#287~~ | done | The `refs_scan_state` pair batch 3 opened: the cache was under-kept inside `--reset` (#288) and over-kept outside it (#287). **#288 landed 2026-08-08, #287 on 2026-08-09**, as separate PRs — see batch 3-bis. #289 was grouped here and is **closed as accepted, not fixed**; #304 is #287's recorded residue. |
| 3-ter | rules fingerprint residue | ~~#304~~ | **landed** | Found while working 3-bis, landed 2026-08-09 with 2-bis as the theme pairing predicted (both are a derived-state marker that fails to invalidate when its input changes). The row said it "may resolve as a *decision*, like #299", and on the frequency measurement it would have — 0 logic-only rules edits in 13 commits. It was **built anyway**, because the second measurement showed the issue's reason not to build was false. See batch 3-ter. |
| 4 | chunk-length gates | #268, #176 (part 1) | **landed** | #268 is the only user-visible bug in the set. #176's re-chunk needs an operator window. |
| 4-bis | the length floor's own rationale | #291 | **backlog** | The `min_chunk_chars=60` floor does not exclude the Nietzsche signatures its docstring cites — they are 66–113 chars. Same constant batch 4 moved; the exemption work is already in context. |
| 4-op | #176 part 2 — re-chunk | #176 | todo, operator — **scope corrected, see below** | Needs a DB window, a full refs rebuild, and `known_coarse` pruning. Sequenced after 4-bis so the retrieval floor is settled before chunk boundaries move. **Its stated scope does not survive measurement (2026-08-15): two of the four works it names as "clear parser failures" are documented design decisions, and the affected set is five parsers rather than one.** See "4-op's scope, corrected" below before opening the window. |
| 4-op-ter | apparatus ingested as text | #385 | **backlog** | Found scoping 4-op across the four non-XML ingest paths, 2026-08-15. The PDF-sourced Hegel volumes merge bibliography, editor's notes and the alphabetical index into the **last body section**: `§244` is 118,716 chars of which roughly 1,300 are Hegel, and it ends `…Zeno of Elea, 145, 164 Zeus, 120, 221`. **Deliberately not folded into #176**, which is the granularity issue that surfaced it: #176's units are too coarse but are the right *text*, and re-chunking §244 into ten pieces would produce ten index chunks instead of one. It is #177's class one layer down — that was back matter as a standalone *work* and is fixed; this is the same material inside a section, wearing a legitimate citation label. Rides 4-op's re-ingest because it is the same corpus and the same refs rebuild, but it is a separate fix and wants its own explanation for why the numbers moved. **Landed 2026-08-15. It was two defects, not one, and the issue's framing hid the second.** Back matter: only the *last* section's body runs to end-of-file, so the volume's apparatus accretes onto it — cut at the heading that starts it (`Bibliography`; `Index to Translation and Commentary` in the sibling), taking §244 from 118,716 chars to 953 and §577 from 43,001 to 1,810. A size threshold could not have done this: Philosophy of Mind's two largest chunks are 119,857 characters of genuine Hegel, and §577 legitimately ends with his quotation of *Metaphysics* XII.7. Front matter: §24 and §82 are `ord=0` and `ord=1`, spurious `^§ N` matches inside the editors' introduction, and §82's 84,516 chars are **76% Hegel** — all three of his prefaces, 64,134 characters that the obvious fix would have deleted. `front_matter_headings` existed for exactly this and was **inert for both works**; wiring it needed a last-match rule (each heading is also in the contents) and ligature tolerance (`Preface to the ﬁrst edition`). Also cost: 44 cross-references anchored into the deleted apparatus, deleted here — and querying for them corpus-wide found **66 more that predate this**, plus 270 whose snapshot no longer matches, filed as #407. |
| 4-op-bis | what 4-op's prerequisite audit found | #383 | **backlog** | Filed 2026-08-15 by the Marx chrome audit **this document called for** ("decide whether the Marx corpus gets a chrome audit, and decide it now… the audit itself is read-only measurement"). Layer (b) of the 2026-05-31 cleanup is not closed: 33 chunks of Internet Archive crawl-provenance boilerplate survive in *Die deutsche Ideologie*, carrying 198 `chunk_lemmas` rows and 33 embeddings. **Layers (a) and (c) are clean** — 0 Gutenberg chrome chunks, 0 duplicate Marx paragraphs ≥60 chars — which is worth recording so nobody re-audits them. `cross_references` on the 33 is **0**, so nothing needs re-anchoring: this is the cheapest thing in the batch and it should ride 4-op's re-ingest rather than buy its own window, exactly as the audit note predicted. Grouped here rather than with 5-bis (#298) because #298 is an mlwerke edition note and this is Wayback viewer residue — same corpus, different source and different cleaner. |
| 4-op-quater | the two pairs the `.xml` half left | ~~#395~~, #394 | **part landed; rest blocked on nothing** | The residue of PRs #393/#396, paired below since 2026-08-09 as "blocked on the same locator question". **They were not, and the pairing is corrected here.** #395's *Fragmenta* had its citable unit sitting unused in its own markup — 111 milestones, 36 `unit="Fragment"` and 75 `unit="Sententia"`, discarded by a three-name allowlist that the issue read as the milestones having no `unit` at all. Honouring them takes the pair from 1 chunk to 111 (mean 226, max 1,066, none over the gate, 111 distinct locators, zero churn in the other five Epictetus works) and out of `known_coarse` — **which is 64 pairs → 63, not the 94 → 93 that PR #406's body and commit message claim.** That number was read off CLAUDE.md instead of counted; it was accurate when the gate landed (#292) and had shrunk by 30 since. Corrected in CLAUDE.md, which no longer quotes a count. **Landed 2026-08-15.** #394's *Discourses* eng has genuinely nothing to chunk on — 0 milestones, no numbering below `chapter` — so its locator had to be decided rather than discovered: **`IV.1a` / `IV.1b`, taken by the repo owner 2026-08-15**, because synthesised `18.1` collides with the Greek's real third citation level. What remains there is mechanical, lifting the packer from `tei_drama.py`. |
| 4-op-quinquies | what the gate and the detector cannot see | ~~#404~~, ~~#405~~ | **landed** | Both found closing 4-op-quater, and both are the same shape: a check that runs and reports nothing. #404 — every threshold in `manifest.yaml`'s `granularity` block is a ceiling, and the generated snapshot only lists pairs that trip one, so Babrius eng's 44-char median and 2,139 chunks are invisible while its coarser Greek sibling is baselined. No value of any existing key would list it. Named in passing by #399 and deliberately left unfiled there, so it existed only inside an issue about a different defect. #405 — `_detect_chunk_boundary_units` returns `frozenset()` both for a body with no milestones and for one whose milestones are all unrecognized, with no warning either way; that ambiguity is what #395 was misdiagnosed from. ~~Sizing #404 needs a measurement nobody has taken (how many verse pairs a floor would list), so it is not a one-liner despite reading like one.~~ **Both landed 2026-08-15.** The sizing was taken and the fear was right about a naive floor — 110 pairs, mostly Quran suras — and wrong about the fix: `retrieve.py` had already solved it for its own floor via `works.citation_system`, and reusing that exemption brings a 100-char floor down to **one** pair (#417, fixed first for exactly this reason). **What the floor caught on landing was not over-fragmented verse but two works that are not there**: *Über den Gemeinspruch* at 2 chunks and the *Erste Einleitung* at 3, both title pages over zeno landing pages rather than texts — filed as #420 and baselined in `known_fine`, so the gate's stale-entry check forces their removal the day #420 is fixed. #405 emits a line when a body's milestones carry only unrecognized units, and stays silent both for a body with no milestones (three of Epictetus's English works) and for a stray unknown unit inside a body that chunks fine (the allowlist working). |
| 4-op-quinquies-bis | #420's own cause was wrong too | #420 | **part landed (PR #438); rest blocked on zeno.org** | #420 named the same failure mode as #404 in miniature: a link count of "0 internal work links" that was never taken, and a page that is a genuine table of contents (3 chapter links for *Gemeinspruch*, 12 for the *Erste Einleitung*), not a zeno parking page. **Corrected on the issue.** The real cause: `download_kant_de.py`'s `title_to_path()` left `:`/`[`/`]` unescaped while zeno.org percent-encodes all three in its own hrefs, so `extract_links`'s `path.startswith(root_path)` matched zero of either work's own chapter links and the BFS crawler silently stopped at page 1 — reproduced directly against both files (0 children before the fix, 4 and 13 after). Same bug, independently found in `download_schiller_de.py`, fixed in the same PR — latent there, since `kallias_de.html`'s bracketed title already fits on zeno's single root page. **The code fix and its tests landed in #438; the re-fetch, re-ingest, and `known_fine` baseline removal are blocked on zeno.org, which has returned `503 Wartungsarbeiten` for the entire session.** |
| 4-op-octies | what the Davies scan will not give up | #412 | **backlog** | Found landing #399, and the reason its PR claims 131 of ~143 rather than completeness. ~12 fables still carry no detectable boundary; 11 of the 131 recovered have no title, because the all-caps line above their Perry ref was mangled past the detector; 2 have a Roman numeral as their title (`LXXIII`, `XLVILI`) because a page ornament outranked the real line, and the title is prepended to the chunk text. The obvious repair — recover titles from the Greek by Perry number — is blocked by the same measurement that killed Perry as a locator in #399: one captured number is outside the index's 584 entries and three collide. Recorded because 131/143 is a coverage figure someone will otherwise plan against as if it were 143. |
| 4-op-nonies | the refs debt the four ingest fixes left | #415, ~~#414~~ | **part landed; #415 backlog** | Found answering whether the DB needed re-ingesting after #385/#395/#398/#399. It did not — the live index matches a fresh parse exactly for Aesop, Epictetus and Hegel, zero orphans, `foreign_key_check` clean. What it does have is **551 chunks never scanned for cross-references**: Aesop 416 (Babrius, both halves), Epictetus 111 (the *Fragmenta*), Hegel 24 (the *Encyclopaedia* prefaces, captured for the first time by #385 and the likeliest of the three to carry real references). Each PR said a refs pass was outstanding; nothing reads a PR body after the merge, which is the actual gap. #414 is the other half of #407's headline number — 212 rows where `source_form_snapshot` records the scripture formula (`in Psalmo:`) that the span excludes. Nothing mis-points. **Landed 2026-08-15 in 4-op-septies**, decided by measurement rather than preference: the column is part of the shadow address that makes references recoverable across a re-ingest, so narrowing it was ruled out and only the `refs review` display changed. **Run #415's window together with #407's recoverable 22**, and delete #407's 62 dead rows rather than re-scanning them — measured, they cannot come back. |
| 4-op-septies | the ingest path cannot replace an edition | ~~#410~~, ~~#412~~, ~~#414~~ | **landed** | Found landing #398's re-source, which it stopped dead. `store/chunks.py:98-114` resolves an edition by `(work_id, name, language, year)` and inserts on a miss; uniqueness is enforced by `editions_canonical_unique` on `(work_id, language) WHERE is_canonical = 1`. Change an edition's name or year — which is what a re-source *is* — and the lookup misses, the insert collides, and `make reingest-only` aborts (atomically; the index was untouched). Recovered by deleting the superseded edition by hand: 498 chunks, 65,144 `chunk_lemmas`, 498 embeddings cascade cleanly and 0 `cross_references` were touched. **Only reachable from an existing database** — `index --reset` rebuilds `editions` and never sees it, which is why CI is green on the very PR that hit it. Filed rather than fixed because the two candidate fixes (replace in place vs demote-and-add) answer different questions about what a re-source means for edition history, and #50's switcher has a stake in the answer. **Settled and landed 2026-08-15.** The stake turned out to be imaginary: 827 editions, **zero** non-canonical, **zero** works with more than one edition in a language — the multi-edition model has never been exercised. And the two candidates are not alternatives: replace-in-place is what a *re-source* needs (the old edition ends with no chunks), demote-and-add is what *adding a parallel edition* needs, which is #50's separate problem. Landed with #412 (Babrius's residue accepted: Gutenberg has no Babrius and archive.org's only other English is the in-copyright 1965 Loeb, so Davies is the only PD text — coverage recorded in the work config as 131/~143) and #414 (`source_form_snapshot` kept as the wider extent, because it is a column of the shadow address that makes references recoverable across a re-ingest; only the `refs review` display changed). |
| 4-op-decies | a work in the index and unreachable | ~~#417~~ | **landed** | Found sizing #404, which is what makes it batch A's starting point rather than a loose end. *Dionysos-Dithyramben* was 783 chunks at a 27-character median — one per verse line — and 779 fell below the 60-char retrieval floor, so 99% of the work was indexed, embedded, lemmatized and **unreachable**. Same class as #268, where it was 31% of the Quran. **My own filed hypothesis was wrong and is corrected on the issue:** it proposed a new `verse_line` citation system to inherit the floor's exemption — a CHECK-constraint migration, a `locations.py` handler and a second migration to update the row, all to make 783 one-line chunks reachable while each stayed useless to retrieve on. The chunks were the defect. `min_paragraph_chars`, the mirror of #397's cap, packs paragraphs within a heading: 783 → 40 chunks, median 612, 39 of 40 above the floor, churn confined to the one work. Measured as a single case — no other non-verse-classified work with ≥20 chunks is above 70% below the floor, and Aeschylus, Sophocles, Lucretius, Aesop and Hesiod have no work over 15%. |
| 4-op-sexies | references anchored to text that is gone | #407 | **backlog** | Found landing 4-op-ter, and it belongs with #404/#405 above by shape rather than by subsystem: a third invariant nothing checks. 336 of 66,068 `cross_references` no longer point at the text they record — 66 whose span runs past the end of their chunk, 270 whose span is in range but whose `source_form_snapshot` no longer matches the slice. `Elements of the Philosophy of Right` `§140` is 850 chars and carries a reference anchored at offset 29,526. Underneath it is #285 (`chunk_id` hashes `text[:120]`, so a chunk can shrink without its derived rows noticing); `chunk_lemmas` has the same exposure and *is* audited, `cross_references` is not. The 44 this batch created were cleaned up in its own PR — the 66 and the 270 predate it and want a repair pass whose shape is unverified, which is why the issue proposes the audit invariant first. |
| 5 | perseus verification | #151, #152 | **landed** | Network-only, `perseus/**` is coverage-excluded, no gate risk. |
| 5-bis | perseus follow-ups | ~~#297~~, #298, #299, ~~#300~~ | **part landed; rest backlog** | All four found in batch 5. #297 is shared-extractor code every scraper depends on; #298 is chrome in 18 live chunks, whose source was **not** the sibling scraper this row assumed; #300 is the batch loop that loses a work at exit 0. #299 is a **decision, not a fix** — do not close it with code, and its premise moved: see batch 5-bis. |
| 5-ter | perseus follow-ups, second round | #316, #317 | **backlog** | Both found working 5-bis, in the files it edited. #316 is #300's accounting fix un-generalized — 12 more downloaders swallow a lost work and exit 0. #317 is the part of #297 that PR #315 scoped out: two private extractor copies that inherit none of the shared class's fixes. Neither touches the DB. |
| 6 | named-passage index | #182 | todo | Largest design surface; nothing depends on it. Phase 0 measured — see batch 6. |
| 6-bis | content-derived `chunk_id` | #285 | **backlog** | **Groups only loosely.** `chunk_id` hashes `text[:120]`, so derived rows survive an edit past that point with stale offsets. Placed here because batch 6 is the last batch that adds a table keyed on `chunk_id`, and because #263's `text_hash` column exists precisely to work around it — but it is a schema change with its own blast radius and may deserve to stand alone. |
| 7 | ruff reformat tranches | #136 | todo | Last, deliberately — see batch 7. |
| 8 | PR-gate tooling | ~~#320~~, ~~#321~~, #322, ~~#330~~, ~~#331~~ | **part landed; #322 todo** | **Groups with nothing in batches 1–7** — it is the harness those batches are worked *with*, not a defect in the corpus. A tollgate, like batch 0, and numbered 8 rather than `N-bis` for that reason: no batch above it found it. See batch 8. |
| 8-bis | the gate's own blind spots | #333, ~~#334~~ | **part landed; #333 backlog** | Both found working #330/#331 as PR #332, in the file it edited. #333 is the merge-commit question that PR deliberately left unmeasured. #334 was `main()`, where the retry's only real caller sat untested — landed as PR #336, and its verdict was `CORRECTED` because one of the four risks it listed does not exist. Neither touches the DB or the coverage gate. |
| 8-quinquies | a guard satisfied by commented-out source | ~~#349~~ | **in review** | Found working #342 as PR #347, and grouped **by theme rather than by file** — it is in `web/tests/`, not `scripts/`, but it is the 8-series question ("does this gate check what it claims?") rather than a frontend defect. `routeConstruction.test.ts` decides reachability by regex over source text with no comment stripping, so commenting out the one line that navigates to a route keeps it green — measured, on the case PR #347 added. One-directional: the reachability half can pass on dead code, the hash-drift half can only over-report. |
| 8-ter | worked examples cite live numbers | #335 | **backlog** | Found working #334, by an unrelated grep. Four wrong PR/issue numbers across two files, and the second pair survived the PR that fixed the first pair. **May resolve as a decision not to gate it**, like #299 — the alternative is to stop citing real numbers at all. |
| 9 | reader latency | ~~#339~~, ~~#340~~, ~~#342~~ | **landed** | **Groups with nothing in batches 0–8** — the first row here that is a *performance* defect rather than a corpus, ingest or harness one, and it was found by timing the app for a demo rather than by working any batch above. Numbered 9 rather than `N-bis` for that reason. All three are one user-visible symptom (a Reader page load) decomposed by layer: #339 the missing access paths, #340 the lock that stopped the reads overlapping, #342 the route model that unmounts the Reader. Landed across PRs #341 (indexes + lock release), #343 (client read cache), #346 (#339 part 2) and #347 (#342's route model, frontend-only). See batch 9. |
| 9-bis | what the latency fixes left behind | #344, #345 | **backlog** | Both found verifying #339 part 2, and neither is a corpus defect. #344 is `/api/health`, the last full scan of `chunks` on the read path (~210 ms) — named and scoped out by #339, so it needed its own row once #339 closed, and part 2 pushed it 9% the wrong way. #345 is the coverage-exclusion divergence the same PR hit and half-fixed: `pyproject.toml`'s `omit` and `sonar.coverage.exclusions` disagree, so a locally-omitted file arrives at the blocking gate scored 0%. Both **may resolve as decisions rather than repairs**, like #299 — #344's three options trade staleness against ingest cost, and #345's turns on whether the shim deserves a bar at all. |
| 9-ter | the other three side routes | ~~#348~~ | **landed** | Found working #342 as PR #347, in the file it edited (`AppRoutes.tsx`) — it is the half #342 explicitly did not survey. `ConcordanceRoute`, `NetworkRoute` and `RefsRoute` still unmount the Reader; measured after #347, `.reader` is absent after each of the three and present after the syntax layer. It resolved **half as a decision and half as a repair**, which the row anticipated: the entry points settle it — the Reader rail links into the concordance twice and into neither of the other two, so the concordance keeps the Reader and network/refs stay destinations that release it. See batch 9-ter. |
| 9-quater | what the hoist left armed | ~~#352~~ | **landed** | Found working 9-ter, in the files it edited. The `suspended` flag added there gates the two global listeners whose misfire was measured; four more in the Reader subtree stayed armed while the Reader is retained off-screen. The row predicted this "may resolve as a decision rather than a repair" and that only one of the four loses user state — **both halves were wrong**, and measuring is what showed it: a third listener (`useDialogFocus`) hijacks every shift-Tab on the concordance, so the count that costs the user is two, not one. Verdict `CORRECTED` — three of the issue's explanations did not survive phase 1. Landed as PR #355; see batch 9-quater. |
| 9-quinquies | the popover shell's uneven dismissal | ~~#356~~ | **landed** | Found working 9-quater, in the files it edited, and grouped **by file rather than by theme** — it is not a retained-Reader defect at all. `ReferenceCard` shares `PopoverCard` and its anchoring but nothing gave it an outside-click listener: `useClickOutside` has six consumers and `useXrefCard` is not one. Placed here because 9-quater is the batch that audited every listener these two cards own, so the context is already loaded, and because its fix decided where the gate for `useClickOutside` lives — which is the first thing #356 had to not contradict. Two claims above are **corrected**, and the first was this row's whole reason to expect a decision: it said "nothing records either way" and "shares … both its other dismissal affordances", and *three* comments in two files describe the missing listener as existing behaviour while the shared close button does not exist at all. Verdict `CORRECTED`; landed as PR #359. See batch 9-quinquies. |
| 9-sexies | what the shell inherited | ~~#357~~, ~~#358~~ | **landed** | Both found working 9-quinquies, in the files it edited, and both are the shell rather than either card — which is the difference from the row above, where the defect was one card missing what the other had. #357 is `PopoverCard`'s `stopPropagation()` shim: it names the outside-click listener as the thing it stops and cannot reach it (capture-phase on `document`, and on a different event), and no ancestor of the card binds a bubble-phase click handler either — the only thing that fails without it is a test supplying the parent the app lacks. #358 is what 9-quinquies' correction 2 exposed rather than fixed: both cards are `aria-modal="true"` with no visible close control, and `TermCard`'s renders only in the load-error state. Neither touches the DB. This row said **#358 "may resolve as a decision rather than a repair", the decision being to drop the attribute** — that is **corrected**: the popovers *do* trap focus, unconditionally, so dropping the attribute would unannounce a trap that stays put. #357 `CONFIRMED`, #358 `CORRECTED`; landed as PR #362. See batch 9-sexies. |
| 9-septies | the close control's own residue | ~~#360~~, ~~#361~~ | **in review** | Both found working 9-sexies. Grouped with each other rather than with the row above because neither is about dismissal: #360 is comments citing `project/reference-card/*.html` as the design of record for a path that has never been in the repository — **eight of them across eight files, not the four-in-three the issue measured**: its grep searched for the `project/` prefix, which cannot see `term-wireframes/` (`termcard.css:2`, `TermCard.tsx:2`) or `mobile-wireframes.html` (`Landing.stories.tsx:31`, `mobile.css:6`), and that last file is the worst to leave since the "mobile model" it defers to a missing file is the spec for the whole ≤768px layer. Correction posted on the issue — it is filed rather than corrected in place because the replacement reference is the repo owner's to name. #361 is the part of #358 scoped out: the shell's `×` and `TermCard`'s error-state "Dismiss" button now both render in the load-error state, doing the same thing. #360 **may resolve as a decision** to stop citing local mockups at all, which makes it #335's failure class applied to paths instead of issue numbers. |
| 9-octies | the error state nothing could reach | ~~#426~~ | **in review** | Found working 9-septies' #361, and it is the reason that issue's stated consequence does not happen. Solid **rethrows** when an errored resource is read, so `TermCard`'s sibling `<Show when={term()}>` threw inside the update the rejection triggered and aborted it: the error branch never mounted, `Loading…` never unmounted, and the rejection escaped a component tree that mounts **no `ErrorBoundary` anywhere** (`grep -rn ErrorBoundary web/src` → exit 1). Measured, with the DOM dumped: `.termcard-error` absent, `.termcard-loading` still present, one button, one uncaught error. #361's own site is fixed in that PR by gating the read. This row said the remainder was **11 `createResource` sites across 5 files**; it is **3 call sites**, and the 11 counted imports and comments — four of which name `createResource` precisely to say the code does *not* use it. `useAbortableFetch`, which is what the list surfaces actually use, is built on plain signals and a `try/catch` and cannot throw on read. And `Syntax/index.tsx` was already fixed for this exact mechanism under **#235**, which #426's precedent list omitted. So the audit surface was one site — `ConcordanceTabPanel` — and it was genuinely broken, with its guard in the wrong **order**: `data() && !data.error` calls `data()` first, so the throw beat the check. Correction on the issue. Grouped separately from 9-septies because that row is about dismissal and this is about a whole failure class — and it is the second issue in this batch whose defect was invisible to reading and only showed up when something ran (see #365).
| 10 | reader ↔ chat handoff | ~~#350~~ | **in review** | **Groups with nothing in batches 0–9** — not a defect at all, and not found by working one: it is the half of a directly-requested feature (Escape leaves the Reader for the landing) that turned out to be unbuildable as agreed. The landing composer takes no scope chip and `startFromLanding` clears the scope by design, so the back arrow can hand the work over to a conversation and the landing cannot receive it. Numbered rather than `9-quater` because batch 9 is a latency batch and this shares neither its files nor its theme. |
| 10-bis | what the landing chip needed | ~~#428~~ | **in review** | Found working batch 10, and **pre-existing rather than caused by it** — the back arrow has had it all along; #350's PR gave Escape the same seeding and so the same window. Both Reader exits seed the chat scope from `currentWork()`, which resolves the route against the **lazily**-loaded `works()` list, while the Reader itself renders from the route (`ReaderRoute.tsx:35`). Leaving inside the `/api/works` round-trip therefore seeds `null` and silently drops the work — the exact outcome #350 set out to stop. Observed while writing #350's integration test, which failed for this reason before it failed for the right one and needed `/api/works` seeded to get past it. **The window's width is unmeasured**: the Reader path does issue the request, so this is a race and not a permanent gap, and it is not reachable by hand on localhost. Filed rather than fixed because the two real options — retain the resolved work, or carry `work_id` on the route — are both design calls about where it should live.
| 11 | type-to-filter the concordance pickers | ~~#363~~ | **landed** | **Groups with nothing in batches 0–10** — a directly-requested feature, like batch 10, and numbered rather than `10-bis` because it shares neither #350's files nor its theme. The Author and Work pickers held up to ~964 options in a 320px scroll list with no filter field; `Select` gained an opt-in `filterable` mode, and the lemma-search `q` predicate gained the same diacritic fold server-side. See batch 11. |
| 11-bis | what the filter work found | ~~#364~~, ~~#365~~, ~~#366~~, ~~#367~~, ~~#369~~ | **part landed; #365 in review** | All five found working #363, none caused by it, and they do not group with each other beyond that — which is stated rather than fudged. (This row said "all four" until 2026-08-16; #369 was found last and appended without the count following it.) #366 is the serious one and is **not a frontend defect at all**: `merge_case` groups Greek lemmas by folded *first character*, so the leaderboard's Greek counts are inflated and its labels name the wrong word (`στηλογραφία` merges into `συλλογισμός`). It is one line once #363's whole-string folder exists, but it changes user-visible numbers and wants its own PR. #364 is the other three concordance dropdowns having no keyboard access at all. **The last three landed together 2026-08-16, and two of them were corrected before being worked** — the corrections are on the issues themselves, and both would have produced a wrong fix. #367 is the script detectors answering `true` for any combining mark, which #363 works around rather than fixes; filed as an NFD problem, it is not one — niqqud and tashkeel have no precomposed forms, so pointed Hebrew and vocalized Arabic are Greek in **NFC**, the form the corpus stores. Measured over all 625,658 distinct (lemma, lang) labels in the live index, `containsGreek` claimed 182,061 and should claim 85,737: **96,324 wrong**, 77,775 Hebrew and 18,544 Arabic. Its proposed fix — split the shared constant, "same for the other two modules" — holds only for `greek.ts`, where `TOKEN_RE` genuinely shares it; `HEBREW_RE` and `ARABIC_RE` have one consumer each, so splitting there leaves dead constants and the arm is simply deleted. ~~#365 is `Select`'s panel lacking the mobile-sheet containment rule its neighbour has~~ — **corrected twice, and the second correction reopened it.** #364's port moved all three local `Dropdown`s onto `Select` and retargeted the rule with them, so the grep #365 rests on (reported as returning nothing) returns five hits and the rule it reports as absent is at `concordance.css:1275`. The defect survives one layer in: the rule is scoped `.fbar-drop`, which comes from `FbarSelect`, and the Author and Work pickers are bare `<Select>`s in a `.grp`. PR #423 scoped it to `.fbar` — **and that changed nothing, because the rule is dead at every width.** Confirmed visually 2026-08-16, which is the check the issue asked for and neither the filing nor #423 performed: `mobile.css:1119` forces every `.minerva-select__panel` to `position: fixed !important` with a full-viewport `inset`, under the same `(max-width: 768px)` query, and `!important` beats specificity. Measured live at 375×812, the Work picker's panel (no `.fbar-drop`) and Language's (inside it) are both `fixed`, z-index 80, 375×764 — identical. The rule was load-bearing as `.fbar-drop .menu`, since `mobile.css` has no `.menu` rule; #364's port retargeted it onto a class `mobile.css` already overrides, and it has been inert since. #423's concordance half is reverted and #365 reopened to decide whether the rule is deleted or kept with its inertness recorded — **resolved 2026-08-17 by deleting it**, on the reasoning that a no-op which reads as protection is what let #423 ship a fix that changed nothing. Verified in the running app at 375×812 afterwards: the Work picker's panel (never had the rule), the Author's, and Language's (inside `.fbar-drop`, so it did) are all `fixed`, z-index 80, 375×768 at top 41 — identical, and all three inside the viewport. **The lesson is the test:** it asserted the selector matches the panel, which is true and does not imply containment, so it passed on dead CSS — jsdom applies no external stylesheet, so the only instrument that could catch this was the running app. #369 was found last, working the trigger redesign: `check-pr-link` retried only on a `missing` link because `unexpected` "will not un-register", and it does — measured on PR #368, where the check asserted the PR was broken seconds after GitHub had already dropped the link. The retry now covers both directions, gated on the PR's own text so a number the body still carries a keyword for is never re-read. It belongs to the 8-series question rather than to this batch's theme, and is grouped here only because this is what found it. |
| 11-ter | the index page's own claims | ~~#370~~, ~~#371~~ | **landed** | Both reported from use, one sitting after 11: the leaderboard sparkline showed an identical full block on every row at single-work scope (#370, PR #372), and the list stopped at 200 rows while the header printed the true total beside it — 135,047 for German (#371, PR #374). Neither is a filter defect; they are the same *kind* of defect as each other, which is why they group: **the page displaying something that is not what the reader takes it to mean.** #370 corrected a false comment in `aggregate.py` that had claimed the read path ignores the degenerate shape; #371 corrected the one in `IndexPage.tsx` claiming a 200-row cap is "plenty for any narrowed filter" (Hegel + letter B is 1,318). |
| 11-quater | what the index page found | ~~#373~~, ~~#375~~, ~~#376~~, ~~#377~~ | **in review** | All four found working 11-ter, and **#373 is the one to read first**: `merge_case` groups on SQLite's `LOWER()`, which is ASCII-only, so `Übergehen` and `übergehen` stay separate groups and then render the *same* display label — one lemma reported twice, 78 and 59 where the truth is 137, across 113 German group pairs. With #366 (the Greek group key) and #363's `q` fold, that is **three case-folding defects in one file from one cause**: SQLite's case functions do not handle non-ASCII. #373 and #366 want fixing together — same replacement, and both move visible counts. The others are display and access: #377 the header total that is not a row count (6,797 printed above 3,163 rows, measured, under the default `min_count`), #376 the A–Z rail whose "has hits" dots are folded from the fetched rows so a 12,715-lemma letter can render empty, #375 the leaderboard rows that are `role="link"` with no `tabindex` — the same pattern Sonar blocked #368 over, unflagged here only because the lines are not new. |
| 11-quinquies | what the rail counts found | ~~#381~~ | **in review** | One issue, found working 11-quater, and it takes its own row because **nothing in 11-bis or 11-quater groups with it**: those are a group key, two keyboard gaps and two displayed numbers, and this is a *filter* that cannot address part of its own domain. The A–Z rail offers 26 keys and the corpus has more initials than that — **914** German rows, **1,344** French and **571** English begin with a character that has no rail key, and `lemma LIKE 'A%'` does not fold to reach them, so they are unreachable from the rail entirely. (This row said 934 / 1,339 / 557 until 2026-08-17, quoting the issue; those were re-measured against the live index while working it and only `lat: 0` still matched.) It is a **consequence of the fix above rather than of the defect**: `letter_counts` reports one key per initial actually present, which made the 45-vs-26 gap visible the first time it was printed; the client-side fold it replaced could only ever see letters already on the rail. Of the two riders the issue carried, only the second survived contact. **`ü` and `Ü` are no longer separate buckets** — that was already fixed by #366, because the letter key is computed on `lemma_key` (= `lower_uni(lemma)`) at `index_queries.py:278`, so it is the *same* appearance of the #373/#366 cause and not a third one; the issue's 365-and-255 reproduce only with `merge_case=0`, which is not the default. The one that held is that the frontend already folds diacritics for its alpha-sort section headers, so display and filter disagreed (a reader saw `Ähnlich` under an `A` heading, clicked `A`, and did not get it) — and closing that gap is what the fix did. **Resolved as option 1, not option 3**: the filter folds for every language now, and the correction is on the issue. What option 2 would have shipped is the reason the correction mattered — `Ä`/`Ö`/`Ü` have bucket **0**, so adding them to the rail would have put three empty keys next to three lowercase ones holding 865 of the 914 rows. |
| 11-sexies | the mark the split did not reach | ~~#422~~ | **in review** | Found verifying 11-bis's #367 fix, in the file it edited and fourteen lines below the line it changed — the same splitter/classifier pair, for the any-script tokenizer rather than the Greek one. `ANY_LETTER_RE` and `ANY_TOKEN_RE` are both `[\p{L}\p{M}]`, so a mark standing between non-letters becomes its own run and `tokenizeWords` types it `word: true`. Measured over every chunk in the live index rather than sampled: **4,367 such runs across 2,643 of 426,514 chunks**, and the examples are all Quran waqf marks (U+06DB, U+06D6, U+06D7, U+06DA) — recitation pause signs getting the Reader's per-word hover affordance. **Deliberately left out of the PR that fixed #367**, which is a detector change with no rendering consequence; this is a change to the Reader's hover model on one corpus and wants its own before/after rather than riding a PR whose evidence is a truth table. The open question the issue names, and the reason it is not a one-liner despite reading like one: an all-mark run rendered as punctuation is right for a waqf mark and may be wrong for a mark orphaned by upstream mis-encoding, and the two are indistinguishable at this layer. All 4,367 measured are the first kind. |
| 11-septies | what the fold cost and what it could not reach | ~~#425~~, ~~#427~~ | **in review** | Both found working 11-quinquies' #381, and they are the two halves of what that fix did not settle. **#425 is a regression the fix caused**: `fold_initial(lemma) = ?` cannot use `lemma_counts_by_alpha`'s `lemma` range the way `LIKE 'A%'` could, so a letter click scanned the whole partition — the query plan lost exactly its `lemma>? AND lemma<?` bounds. **The millisecond figures this row used to quote (272.5 → 475.1 ms, 1.74×) were taken on a warm page cache and do not reproduce**; re-measured cold the same SQL reads 2.75 vs 56.88 ms, a 20.7× gap rather than 8.5×, so the plan is the durable evidence and the clock is not. Correction on the issue. Fixed by storing the fold: migration 0031 adds an indexed `lemma_counts.lemma_initial`, taking the raw SQL to **3.23 ms (17.6×)** and deu `letter=A` end-to-end to **364.0 ms from 449.3**, with byte-identical output. ~0.9 µs/row is SQLite→Python callback overhead, not folding work, so the fix is a stored folded-initial column, not a faster fold. **#427 is what the fold correctly does not reach**: the residue is now **cross-script, not cross-diacritic** — 892 Latin lemmas in `grc` (`sibi`, `sed`, `Solon`) and 431 Greek-script lemmas in `eng`, where `_fold_initial('Επιστήμη')` is `Ε` and should be. The fold recovered the diacritic cases and only those: deu 914 → 8, fra 1,344 → 23, eng 571 → 431, grc 905 → 905. **#427 turned out not to be a rail problem, and is closed as mis-scoped.** Its own investigation step answered neither of its two hypotheses: the Latin is *clustered* (Theognidea 24.2%, Economics 21.2%, DK fragments 11–20%, against 0.1% for Physics) and it is *legitimate content* — DK prints its testimonia in Latin and *Oeconomica* III survives only in Latin — so nothing is mis-partitioned and nothing should move. The defect is that this text is **lemmatized under the Greek model**, which is #430; Theognidea additionally has OCR corruption unrelated to script, which is #431. Building #427's own option 2 — a script-aware rail — would have made `et`/`in`/`ad` first-class navigable vocabulary in a Greek concordance and legitimised 10,474 rows of apparatus and OCR noise. The `Œ` tail (12 French rows) is accepted and recorded on the issue rather than tracked.
| 11-octies | what the cross-script residue really was | #430, #431 | **backlog** | Both extracted from #427 when its investigation showed the rail was the messenger, not the defect — so this row **replaces** that half of 11-septies rather than following from it. They are grouped because one measurement produced both and separated because they share no cause. **#430 is a policy question at the lemmatize stage**: non-Greek text inside `grc` works is lemmatized under the Greek model, so `et`, `in`, `ad`, `ut`, `est` enter `lemma_counts` as Greek vocabulary — 10,474 `grc` rows across 60 of 202 works, plus the `eng` mirror (431 Greek-script lemmas in English editions). The text is legitimate (DK testimonia; *Oeconomica* III survives only in Latin), so the three options are skip non-dominant-script runs, lemmatize them under the right model, or tag and exclude — and it moves user-visible counts for 60 works, so it wants its own before/after. **#431 is a source-quality defect**: *Theognidea* is OCR-corrupted, with Latin letters and digits substituted into Greek words (`vívovra` for γίνονται, `oÀfog` for ὄλβος, `xar&` for κατὰ) and Welcker's 1826 Latin apparatus interleaved with the poems. **26.9% of its letters are Latin against 0.0–0.1% for a clean `grc` work**, and it alone supplies 5,553 of #430's 10,474 rows — more than the next four works combined. Likely resolves as a **re-source**, the same conclusion as Kapital MEW and the Spinoza *Ethica*; explicitly NOT an in-place OCR repair, which would produce text that looks trustworthy and is not. Note its extent was already corrected once (2,237 misattributed chunks trimmed) without its quality being examined.

Reformatting last is a measured choice, not a default. Batches 1–4 add
tests to files that currently sit *below* the 80% gate and are therefore
un-reformattable, so running them first shrinks batch 7's blocked tranche
instead of fighting it — and batches 1–6 never rebase across a 130-file
diff. The `-bis` batches add tests to the same files, so they shrink it
further; run 2-bis, 3-bis and 4-bis before re-cutting tranche 1.

### Sequencing measured 2026-08-09, after every numbered batch had landed

The rows above are grouped by *what found them*, which is what makes them
cheap to pick up. What follows is the order to run them in, which is now
set by different things — the numbered batches are all landed, so "whose
context is freshest" no longer discriminates. Nothing above is superseded;
this only says which row goes next and why.

**Run order: 2-bis + 3-ter → 5-bis → 4-bis → 6 → (4-op + 6-bis) → 7.**

> **Superseded 2026-08-09 by the scope cap.** Everything left of `6` has
> landed, and `4-bis` and `6-bis` are spawned rows that the cap moves out
> of scope. **The remaining order is: 6 → (#314 as 4-op's setup) → 4-op →
> 7.** The `(4-op + 6-bis)` pairing below is the one thing the cap
> changes rather than merely reorders — see "Decision taken" above. The
> rest of this section still explains *why* the order is what it is, and
> is left standing for that.

Three measurements set it, and two of them correct claims made higher up
this page:

- **4-bis is no longer a coverage lifter, and the paragraph above says it
  is.** That claim was true when written. Measured today, #291's code is
  `retrieve.py`, which batches 3 and 4 carried to **89.0%** — above the
  gate, so 4-bis no longer shrinks batch 7's blocked tranche and its
  position ahead of 7 needs some other reason. 2-bis still does the work
  that paragraph describes: #284's code is `lemmatize.py` at **38.7%**
  (235 statements, the largest blocked file left) and
  `cli/terms/lemmatize.py` at 76.1%. Had we trusted the paragraph, 4-bis
  would have been run early to unblock a reformat it cannot unblock.

  **Corrected 2026-08-09, having run 2-bis: it is not a coverage lifter
  either, and the sentence above names the wrong file.** #284's code is
  `cli/terms/lemmatize.py`; `src/minerva/lemmatize.py` is the *library*
  the CLI imports `is_valid_lemma` and `Token` from, and #284's defect is
  not in it. Measured after 2-bis landed, with its four new tests:

  | file | before | after |
  |---|---|---|
  | `src/minerva/lemmatize.py` | 38% | 38% — untouched |
  | `src/minerva/cli/terms/lemmatize.py` | 76% | 75% |

  So both `-bis` rows are now in the same position: neither shrinks batch
  7's blocked tranche, and both keep their place ahead of 7 for the
  original reason — they are cheap while their batch's context is still
  loaded. The lifter that remains is the `corpus/split_*.py` cluster in
  the 4-op + 6-bis window. This is the second time this page has claimed
  a coverage benefit that measurement did not support; the pattern is
  that the claim is made from the issue's title rather than from the
  diff, and #284's title says `terms lemmatize`.

- **4-op and 6-bis are one operator window, not two.** #285 changes how
  `chunk_id` is computed, so *every* id in the corpus churns — a full refs
  rebuild, an embed re-encode and the llm-verify tail. #176 part 2
  re-chunks a handful of works, churning a subset. Run separately, that
  rebuild is paid twice for no gain; run together, #176's churn is
  subsumed. This also picks up the `corpus/split_*.py` cluster (four files
  at 18–26%), the other real lifter for batch 7.

- **6 stays ahead of that window**, which is the existing 6-bis argument
  doing double duty: batch 6 adds the last table keyed on `chunk_id`, so
  building it *before* the churn puts it in the rebind script. The
  alternative — churn first, build 6 on final ids — means designing 6
  against a scheme that is about to change anyway.

**5-bis is unordered on purpose.** `perseus/**` is coverage-excluded and
touches no DB, so it has no gate risk, no churn interaction and no
coverage debt. It can run at any point, including alongside another batch.
It is placed second above only because its context is the freshest.

---

## Batch 1 — refs verify follow-ups (#272, #276)

### #272 — `LLMError` counted as `parse_errors`, never retried

`src/minerva/refs/llm_verify.py:654` increments `n_parse_errors` on the
backend-error path. Two independent halves: do the counter split, decide
the retry separately.

- Add `backend_errors: int = 0` to `LLMVerifyStats`
  (`llm_verify.py:164-177`); count the `LLMError` path into it.
- Print it in the CLI summary (`src/minerva/cli/refs/build.py:317-326`).
- `tests/test_refs_llm_verify.py::TestBudgetAndErrorHandling::test_llm_error_counted_and_processing_continues`
  asserts `stats.parse_errors == 1` today. The test is correct about
  current behaviour and must be **updated, not deleted** — it is the pin.
- Bounded retry with backoff on `LLMError`: in scope only if it stays
  inside the existing `pending`-queue loop. `sleep_between_calls` is fixed
  pacing, not backoff. If it grows past ~20 lines, leave it and say so in
  the PR body — the counter split is worth landing alone.

### #276 — lexical quote binder picks arbitrarily on a tie

`refs/quote_match.py:178-240`. `best_lexical_match` keeps one winner and
breaks ties on lowest `chunk_id`. Two real Psalm ties exist today
(Ps 113:12 / Ps 134:15 both carry *simulacra gentium argentum et aurum,
opera manuum hominum*), and the count grows once the formulaic-quote rule
extends past the Psalter to the synoptics.

Approach — cosine among tied candidates only:

- Return every candidate tying at the winning `_sort_key`
  (`quote_match.py:243-247`). Either add `all_lexical_matches` beside
  `best_lexical_match` or have the latter return a list; the sole caller
  is `refs/embed_verify.py:320`, so either is cheap.
- In `embed_verify.py:320-350`, when more than one ties: score
  `phrases[i]` against each tied chunk's embedding via the existing
  `_load_embedding_for_chunk` and take the argmax. This is a legitimate
  use of cosine — the choice is between two known-correct texts, not a
  search over 2,527 verses, which is the distinction #269 turned on.
- Record the runner-up in `curator_note` via the existing `_lexical_note`,
  so the pick is visible rather than silent.
- Keep the `chunk_id` tie-break as final fallback when no tied candidate
  has an embedding — the stable-pick rationale (no parallel rows through
  `insert_candidate`'s dedup key) still holds.

Verification: the two ties are `chunk_id` 15474 and 53753. Re-run the
uniqueness audit from #276's body; both resolve by cosine among
{Ps 113:12, Ps 134:15}, and the 121 uniquely-determined rows are
unchanged.

---

## Batch 2 — `terms lemmatize` (#262, #263)

### #262 — `--n-process 4` default cannot run for `lat`

LatinCy's `la_core_web_sm` holds a module-level lambda and `spawn` cannot
pickle it. The traceback prints and the process then **hangs** — 18m47s
wall for 1.62s CPU, requiring `kill -9`.

**Corrected 2026-08-08 while implementing, on two counts. Both were
measured; the plan as written above would not have fixed the bug.**

1. *"Wrap the `nlp.pipe` call so `PicklingError` falls back."* This does
   not stop the hang. spaCy primes its worker queues (`sender.send()`
   twice) **before** `for proc in procs: proc.start()`, and its cleanup
   `try/finally` begins only after that loop — so a failed spawn leaks
   `mp.Queue` objects whose feeder threads
   `multiprocessing.util._exit_function` joins at interpreter shutdown,
   blocked forever in `os_write` on a pipe no child will drain.
   Demonstrated: a script that *caught* the `PicklingError`, printed, and
   ran off the end was still alive at 45 s and had to be killed. Had the
   plan been followed, the operator would have got a friendlier message
   and the same `kill -9`. The payload has to be checked **before** the
   pipe is entered — `Lemmatizer._safe_n_process`.
2. *"`la_core_web_sm` … cannot be parallelised"* / #262's "Latin only …
   it is `la_core_web_sm` that will not pickle". The **model** pickles
   fine. What does not is spaCy's process-global `Underscore.get_state()`
   extension registry, which importing `la_core_web_sm` poisons with a
   `Token.set_extension(..., getter=lambda …)` at
   `la_core_web_sm/functions.py:121-126`. Measured in one process, after
   that import, `en_core_web_sm`, `de_core_news_sm`, `fr_core_news_sm`
   and `grc_dep_web_sm` are *all* unpicklable, each reporting the
   *Latin* lambda; each is picklable in a fresh process. So a probe of
   the pipeline object alone — the natural reading of the plan — reports
   "picklable" and prevents nothing, and the defect is not confined to
   `lat`: any language lemmatized in a process that has already loaded
   LatinCy hangs the same way.

- Correct the help text at `src/minerva/cli/terms/__init__.py:303-313` —
  "4 is a safe default" is false. Changing the default to 1 is defensible
  but is the lesser fix alone: it leaves `--n-process 4` a trap. With the
  pre-flight probe in place the default stays at 4, since it is now
  honoured wherever it is safe and downgraded with a notice where it is
  not.

### #263 — zero-lemma chunks reprocessed forever, and miscounted

419 eng / 299 fra / 126 deu / 15 grc chunks re-tokenize on every
incremental pass. `chunk_lemmas` serves as both output table and
done-marker, so a chunk yielding no valid lemma writes no row and is never
recorded as attempted.

- Add a separate attempt marker. **Follow the `chunk_syntax_state` /
  `work_aliases` precedent, not `refs_scan_state`** — the latter is
  precisely what #264 is about: no FK, so it accumulates orphans forever.
  `chunk_lemma_state(chunk_id PK REFERENCES chunks(chunk_id) ON DELETE
  CASCADE, text_hash, token_count, lemmatized_at)` gets orphan reaping for
  free.
- Migration `0027_chunk_lemma_state.sql` — **corrected while
  implementing: it must be `.py`.** The table cannot ship empty. Moving
  the skip predicate off `chunk_lemmas` while no state rows exist means
  the next incremental pass sees the whole corpus as unattempted and
  re-lemmatizes 26M tokens. So the migration backfills a marker for every
  chunk that already has lemma rows, which needs `sha1` over
  `chunks.text` — and SQLite has no builtin for it. `.py` plus
  `sqlite_util.register_text_hash`, the same shape as 0021's
  canonicalizer.
- `text_hash` is not redundant with the content-derived `chunk_id`, which
  is the obvious objection to it: `tei._make_chunk_id` hashes only
  `text[:120]`, so a chunk edited past that point keeps its id and would
  inherit its stale marker.
- Add the new table to the preservation path in
  `src/minerva/store/preserved_state.py`. Otherwise the first
  `index --reset` annihilates it and the bug returns silently — the #192
  failure mode. Do not skip this.
- Amend the candidate predicate (`cli/terms/lemmatize.py:66-72`) to skip
  on the state table rather than on `chunk_lemmas`.
- Report productive chunks separately from attempted at
  `lemmatize.py:165-173`: `done · N chunks (M productive) · T tokens`.

Out of scope, and to be said in the PR body: why 126 clean German Plato
chunks (`KLEINIAS: Das ist recht von euch…`) produce zero lemmas. #263
records the observation without diagnosing it, and the caching fix is what
makes it visible. File the diagnosis as its own issue if this batch does
not answer it.

**Answered 2026-08-08 — no issue needed.** They were never attempted, not
attempted-and-failed; the deu pass had simply not been run over them, which
is the ambiguity the whole batch exists to remove. `KLEINIAS: Das ist recht
von euch…` yields 19 lemmas on its first actual pass. Of the 126 deu
candidates, 2 are productive and the other 124 are Marx footnote citations
(`(131) l.c.p. 35 u. p. 455, 456.`). The remaining residue is Cicero
apparatus (eng) and Renan/Gobineau OCR garbage (fra) — 857 chunks that are
legitimately unlemmatizable and now recorded as such. Correction filed on
the issue.

---

## Batch 2-bis — lemma-row hygiene (#284)

**Landed 2026-08-09**, with 3-ter, in the PR that closes both.

The fix is the delete the issue asked for, in `_flush`, in the same
transaction as the insert. Two things the issue did not have:

- **Its suggested fix is scoped too narrowly.** "Delete the chunk's rows
  before inserting in the `--all` path" leaves the defect live on the
  default path, which re-processes any chunk whose `text_hash` moved —
  and a chunk can keep its `chunk_id` across an edit past `text[:120]`
  (#285), which is the case `chunk_lemma_state.text_hash` was added to
  catch in the first place. Same stale rows, no `--all` involved. The
  delete is unconditional. Correction filed on the issue.

- **The delete keys off `attempts`, not off the rows being written.** A
  chunk that yields nothing this pass contributes no row to `inserts`,
  and it is exactly the chunk whose *entire* previous output is now
  stale. A delete driven by the insert batch would skip it — the one
  chunk where every surviving row is wrong rather than merely surplus.
  Tested directly (`test_a_chunk_that_becomes_barren_loses_its_earlier_rows`).

**An operator step IS owed — the issue's "no corpus damage" evidence is
wrong.** #284 states that its detection query "returns 0 rows on the live
index today, so no corpus damage has occurred through this path yet".
Run against `data/index.sqlite` while preparing this batch's operator
step, it returns **18 rows**: 18 chunks carrying **906 surplus lemma
rows** between them, every one of them Hobbes's *De Cive* (lat), all
stamped `lemmatized_at = 2026-08-08 20:46:56` — the first pass after
migration 0027 created `chunk_lemma_state` empty and made every chunk a
candidate.

The surplus rows are stale, not merely extra, and it is checkable rather
than inferred: their `surface_start`/`surface_end` address text that is
no longer there. Sampling three per chunk, 54 of 54 point past the end of
the current text or at a different string.

```
idx 1818: stored 'quoque'    at [13569:13575] -> text holds ''  MISMATCH
idx 1819: stored 'excepto'   at [13578:13585] -> text holds ''  MISMATCH
idx 1820: stored 'unomanda-' at [13586:13595] -> text holds ''  MISMATCH
```

`unomanda-` names the cause: the Latin Hobbes long-s/OCR repair shortened
the text, the `chunk_id` survived because it hashes only `text[:120]`
(#285), and the re-lemmatize produced fewer tokens than the rows already
present. **That is the incremental path, not `--all`** — so this is the
defect the issue's own suggested fix would have left in place, found in
the corpus rather than argued from the code.

Bounded: 906 of 26,156,875 lemma rows, 0.0035%, all in one work. No
orphaned lemma rows and no chunk carrying lemmas without a state row, so
this is the whole population.

Repair and the rules-hash rescan are one operator window — see
Verification.

---

## Batch 2-quater — NFC-layer offsets (#311)

**Landed 2026-08-09.** `terms lemmatize` handed the pipeline
`unicodedata.normalize("NFC", row["text"])` and stored the offsets that
came back against `chunks.text`. The normalization moves into
`Lemmatizer` — `lemmatize._pipeline_text` — where `_SourceOffsets`, built
for #307's tokenizer rewrite, maps the spans back onto the caller's
string. The CLI now yields `row["text"]` verbatim; the model sees exactly
what it saw before.

**The issue's proposed fix is the one thing that must not be done, and it
says so as an untested proposal.** #311's Hypothesis reads "pass
`row["text"]` unchanged and let the existing `_SourceOffsets` path handle
any rewrite the tokenizer performs", with the model-quality question
listed as a thing to check first. It was checked, and it fails: fed the
stored decomposed text, `grc_dep_web_sm`'s lookups miss and it falls back
to something close to the surface form. Over 300 live non-NFC grc chunks,
2,313 of 51,549 lemmas changed —

```
'λέγων'      -> NFC 'λέγω'      | raw 'λέγων'
'ἔφη'        -> NFC 'φημί'      | raw 'ἔφη·'      <- ano teleia in the lemma
'κρείττονος' -> NFC 'κρείσσων'  | raw 'κρείττονος'
'πράξεις'    -> NFC 'πρᾶξις'    | raw 'πράξης'
```

— so shipping it as written would have traded 203,610 wrong offsets for
roughly 4.5% of 2.9 million grc lemmas going wrong instead, in a table
whose only consumer is the concordance. The issue's own alternative
("keep feeding NFC and store `NFC(text)` in `chunks.text`") is the
corpus-wide migration it calls it. The third option — normalize for the
model, map the offsets — is the one both halves of the issue skip past,
and it is a dozen lines because #307 already built the map.

**The row count in the issue is one of two failure modes, and it is the
smaller one.** #311 measures 1,866 rows "wrong vs stored text" (grc
1,497, eng 369, deu 0). That reproduces exactly — but only for rows whose
*span* moved. Audited across the whole corpus:

| lang | non-NFC chunks | rows in them | span drifted | span right, form differs |
|---|---:|---:|---:|---:|
| grc | 16,010 | 837,850 | 1,497 | 201,722 |
| eng | 5 | 4,818 | 369 | 3 |
| deu | 17 | 4,654 | 0 | 19 |
| **all** | **16,032** | **847,322** | **1,866** | **201,744** |

203,610 rows fail `text[surface_start:surface_end] == surface_form`, not
1,866. The 201,744 are NFC's *singleton* mappings, which change a
character without changing the length — Greek's "oxia" letters fold onto
their "tonos" twins, U+1F7B → U+03CD:

```
eb3446f78ac9d3702a8d[16:22]
   stored surface_form 'κύριος'  [3ba, 03cd, 3c1, 3b9, 3bf, 3c2]
   chunks.text slice   'κύριος'  [3ba, 1f7b, 3c1, 3b9, 3bf, 3c2]
```

Same span, same word, different string — invisible when rendered and a
miss for any consumer comparing or searching on `surface_form`. So the
issue's "the exposure is length-changing composition, not non-NFC-ness as
such" is backwards for 99% of the population, and its "deu … 0" is 19.
Had it been trusted, the repair would have been scoped to the 103
length-changing chunks instead of all 16,032, and the verification query
would have been the drift query — reporting success with 201,744 rows
still wrong. The true grc rate is **93.09%**, not the 99.67% #311 quotes
from the 2-ter sampling. Correction filed on the issue.

**The two things #311 asked to check before assuming the map is safe,
answered.** Neither was a formality:

- *Model degradation on decomposed input* — real, and fatal to the
  proposed fix. Above.
- *The word-count invariant under NFC* — holds. Composition never merges
  or splits a whitespace-delimited word, and it was measured rather than
  argued: over all 16,032 non-NFC chunks, 853,894 words, **zero**
  unusable maps and zero words landing on the wrong span. Re-running the
  live `grc_dep_web_sm` over 400 affected chunks then gives
  54,330/54,330 spans reproducing the stored text, with the lemma
  sequence unchanged on every one.

**The Stanza path is fixed too, with nothing to repair.** heb/ara have no
non-NFC chunks, so this is not a live defect there — but the
normalization the CLI was doing applied to those models as well, and
moving it without giving `_tokens_from_stanza_doc` the same map would
have changed what they are fed. It takes the same `source` argument and
the same refuse-rather-than-guess rule. The one asymmetry is deliberate
and kept: a multi-word-token sub-word borrows its parent's span, so its
`surface` stays `w.text` rather than a slice that would hand every clitic
the whole parent word.

Operator step: see Verification. It found #314, which is batch 2-quinquies
below.

---

## Batch 2-quinquies — Stanza's rewritten surface (#314)

**Todo.** Found verifying 2-quater's operator pass, in the function this
batch gave a `source` argument to. Every language came back at 100.00%
except `ara` at 82.51%, and #311's "Not a defect, for the record" section
accounts for most of that gap and not all of it: 13,871 of the 15,300
mismatching rows share their span with a sibling (the documented
multi-word-token expansion), 1,215 more are the same case with the
sibling dropped by `is_valid_lemma`, and **214 in 210 chunks are neither**
— the span is right and the stored `surface_form` is Stanza's rewrite of
the word at it.

```
e6c65fb06d06331dc5fb[22:31]   stored 'تققوا۟'  span 'ٱتَّقُوا۟'
c2d883df3f1072926ee5[76:85]   stored 'مَرؤض'   span 'مَرْضَاتَ'
```

Grouped here because it is one function away from 2-quater and the whole
audit is already loaded, but it is **not** the same defect: `ara`'s
offsets were correct before this batch and still are. What is wrong is
the text stored beside them, so a fix churns `surface_form` for a
language whose spans never moved — which is why it was not folded into
PR #313. `heb` is clean, so it is `ara`'s pipeline rather than the Stanza
backend as such.

---

## Batch 3 — `index --reset` preservation (#274, #264)

### #274 — `reference_targets` restored only when xrefs exist

`src/minerva/store/preserved_state.py:115-128`. The outer gate ignores
`reference_targets` entirely, and both the `DELETE` and the restore sit
inside `if xref_count:`. A targets-only snapshot therefore keeps migration
0012's seed rows and loses the curator's `citation_system` and `notes`.

- Probe `target_count` alongside the other four counts
  (`preserved_state.py:105-112`).
- Add it to the outer early-return condition at line 115.
- Decouple the two `DELETE`/`_restore_from_snap` pairs so a targets-only
  snapshot round-trips. Restore `reference_targets` **before**
  `cross_references` — the FK direction requires it.
- #273's PR seeds an xref as a workaround, with a comment pointing here.
  Remove that workaround as part of this fix so it cannot become the
  expected behaviour.

**Corrected 2026-08-08 while implementing. The plan above names only the
restore gate, and fixing only that leaves the bug in place.** The
snapshot gate has to change too. `cmd_index` calls
`_maybe_snapshot_pre_index` and then `store.reset_db`, which *unlinks
the DB file* — so on a targets-only DB the probe's early return fires
(all five counts zero), no `.bak.pre-index` is written, and there is
nothing for the restore to replay however well-gated it is. Measured:
with only the restore fixed, the new regression test still failed
`the curated target did not survive --reset`. `reference_targets` must
be counted in **both** functions.

Consequence, accepted and filed as #289: migration 0012 seeds 20 targets
into every migrated DB, so the snapshot probe is now effectively
unconditional and its "no-op for fully-empty DBs" property is gone. A
narrower predicate cannot be made sound by row count or by which
`(author, work)` pairs are present — the case #274 names is a curator
editing a seed row's `notes` in place, which changes neither.

### #264 — `refs_scan_state` orphans (part 1 only)

31,629 of 460,235 rows point at deleted chunks. Because `chunk_id` is
content-derived, a chunk deleted and later recreated gets **the same id
back** and inherits the stale "already scanned" marker — so a rules module
edited in between never fires for it, and the run looks like a clean
exit 0.

- Reap at the end of `index`, beside where the other derived tables
  reconcile: `DELETE FROM refs_scan_state WHERE chunk_id NOT IN (SELECT
  chunk_id FROM chunks)`. Prefer this to adding an FK — the table rebuild
  needs the PRAGMA/view dance, which is separate risk for no extra benefit
  here.
- One-off cleanup of the existing 31,629 rows: `scripts/snapshot-db.sh`
  first, then the same `DELETE` inside a `BEGIN; … ROLLBACK;` preview with
  a verifying `SELECT` before committing for real.

**Part 2 is out of scope**: keying the skip predicate on a hash of the
loaded rules modules, so `refs build` rescans affected chunks itself
instead of relying on the operator remembering `--rescan-all`. That is a
design change. Either use `Refs #264` and state that part 1 landed and
part 2 did not, or file part 2 separately and close #264.

**Done 2026-08-08: filed separately as #287, so #264 closes.** Also
found while reaping: `refs_scan_state` is *not* on the `--reset`
preservation path, so a single `index --reset` discards all 428,606
markers and the next rules build is a full-corpus pass (#288). The two
defects are opposite — the cache is over-kept in the non-reset path and
under-kept in the reset path — and neither was visible from the other.

---

## Batch 3-bis — refs scan cache (#288, then #287)

Scouted 2026-08-08. **Not one batch.** #288 is a clean fix with no design
decision; #287 is a design change whose calls are now taken; #289 is
closed without code.

### #288 — `refs_scan_state` is not on the `--reset` preservation path

**Landed 2026-08-08.** Scouted as "a clean fix with no design decision"
and it was, with one thing the scout did not see: the guard is not
optional. `refs_scan_state.chunk_id` is a PRIMARY KEY and
`_restore_from_snap` is a plain `INSERT`, so adding the table to the
restore list *without* also adding it to the "live table is already
populated, leave it alone" tuple turns a non-reset re-index into an
`IntegrityError` for any DB whose refs are built but whose lemmas and
embeddings are not. `chunk_lemma_state` did not surface this because it
was added to both lists at once. The fourth test in
`tests/test_index_refs_scan_state_preservation.py` is that regression.

428,606 markers, discarded by one `index --reset`. Verified: the table
appears nowhere in `src/minerva/store/preserved_state.py` — not in the
probe, the summary, or the restore list.

**The obvious objection is that restoring 428,606 FK-less rows
reintroduces what #264 part 1 fixed. It does not, and the reason is why
this is landable now rather than a design question.** Both hazards are
already covered by work that shipped earlier:

- *Orphans* — swept by the end-of-index reap #264 part 1 added. Measured
  at 0 on the live DB today, so the reap holds.
- *Stale markers on a changed chunk* — invalidated by the `text_hash`
  comparison already in the skip predicate. This matters because
  `chunk_id` hashes only `text[:120]` (#285), so an edit past that point
  keeps the id; `text_hash` is what catches it.

So the fix is the `chunk_lemma_state` shape batch 2 established — add to
the probe counts, the summary line, and the restore list. Schema for
reference:

```
CREATE TABLE refs_scan_state (
    chunk_id   TEXT PRIMARY KEY,
    text_hash  TEXT NOT NULL,
    scanned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

### #287 — the skip predicate ignores rules changes

**Landed 2026-08-09**, as designed: a per-author hash of the compiled
rule set in a new nullable `refs_scan_state.rules_hash` (migration 0028),
compared alongside `text_hash`. `refs/rules/fingerprint.py` computes it;
51 authors fingerprint in ~25 ms, deterministically across processes.

Two things the design note did not anticipate, both found by building it:

- **"The compiled rule set" is three things, not one.** Rules keep
  behaviour-affecting configuration in instance fields (`forms`,
  `confidence`), in class-level `ClassVar`s (the scripture-cite
  `lexicon` and `cite_re`, which `dataclasses.fields` cannot see), and in
  plain module globals (`StructuralCommentaryRule` holds *no*
  configuration at all — its behaviour is `_COMMENTARY_TARGETS` and
  `_SECTION_LIB_RE` in `aquinas.py`). A fields-only digest — the obvious
  reading of "hash the compiled rule set" — would have shipped as a check
  that validates nothing for the rules most likely to need it. The
  globals are reached by walking method bytecode's `co_names` and
  recursing through project helper functions, which is what catches the
  Latin formulaic rule's quote bounds (read only by `_formulaic_pattern`)
  and the Quran rule's surah table (`minerva.authors.quran_works`).
- **`ALTER TABLE ADD COLUMN` is not free after all** — not for the table,
  for the *restore*. `_restore_from_snap` copies by the live column list,
  and the `.bak.pre-index` snapshot is taken before the fresh DB is
  migrated. So the first `--reset` after this migration would have raised
  `no such column: rules_hash` and taken the index run with it, losing
  the 428,606 markers #288 had just finished protecting. Fixed by
  intersecting the two column sets; this is the first column-add to an
  already-preserved table, so nothing had exercised it before.

The residue is #304: the fingerprint covers rule *configuration*, not
rule *logic*. 307 of 350 rules are pure configuration and fully covered;
the 43 that are not belong to eight classes shared across 16 of the 27
rule-carrying authors. `--rescan-all` stays for that case.

**Operator step run 2026-08-09** against the live DB, after
`scripts/snapshot-db.sh 287-rules-hash-migration`. Migration 0028 applied,
then the one-time NULL-driven rescan:

| | before | after |
|---|---|---|
| markers carrying `rules_hash` | 0 / 428,606 | 428,606 / 428,606 (28 distinct) |
| `cross_references` | 65,741 | 65,899 |
| a second `refs build --strategy rules` | — | `scanned 0 chunks` |

**The 158 new rows are the part worth reading.** They are references the
rules already knew how to find and had never emitted, because the chunks
were scanned before the rule existed and the cache never re-offered them:
Aquinas 133, Augustine 12, Plato 6, Hegel 2, Hobbes 2, and one each for
Epictetus, Nietzsche and Origen. That is the standing cost of the defect,
paid once — and it is a floor, not a total, since #304's logic-only edits
are still invisible.

Note also that 28 distinct fingerprints cover 51 authors: 24 authors have
no rules module at all and share the empty-tuple digest. A rules module
added for any of them invalidates only that author.

The original design note follows. Two of the issue's three open questions
turned on facts the issue did not have:

- **Granularity is not blocked.** The issue says per-module hashing "needs
  a mapping from rules module to the chunks it can match, which the loader
  does not currently expose". That mapping is already the dispatch key:
  `_rules_for_author(author)` selects by source author, modules are *named*
  for their author, `chunk.author` is read inside the rule classes, and
  `refs build --source-author` scopes the same way. Downgraded estimate,
  not a promise — shared `_figures.py` rules may need attribution care.
  Worth getting right because a global hash invalidates all 428,606
  markers whenever any one author's rules change, which is what
  `--rescan-all` already does.
- **Hashing `.py` source would validate nothing for some authors.** Not
  all rules are Python — `loader.py` exposes
  `load_author_rules_from_yaml` / `spec_path_for_author`. A source-text
  hash ignores every YAML-defined rule, so editing one leaves the cache
  valid and reproduces this exact bug for a subset of authors while
  appearing fixed. The compiled rule set is the one representation both
  sources converge on. The formatting-churn argument stands too, and has
  a date: batch 7 reformats these files.
- **Schema:** `ALTER TABLE ... ADD COLUMN`, no rebuild, so no PRAGMA/view
  dance. Nullable, where NULL means "scanned before hashing existed" and
  forces one rescan per author — bounded, and no migration has to
  synthesise hashes for 428,606 rows.

**Sequence #288 first.** There is little point teaching the cache to
invalidate itself precisely while a single `--reset` still discards all of
it.

### #289 — closed as accepted, not fixed

The observation is verified (273 live `reference_targets` against
migration 0012's 20 seeds, so the probe's early return is unreachable).
What was declined is building the sound predicate.

The cost of leaving it is one extra whole-file copy per `index --reset`,
only in the window where nothing else is populated — and any DB big enough
for that copy to hurt has left that window. The cost of fixing it is
structural and permanent: a constant shared between runtime code and a
*migration's data payload*, which means that migration can never be
squashed or superseded without silently changing the probe. The docstring
was already corrected in #274's PR, which is the part that mattered — an
unconditional-but-cheap snapshot is not a trap; a docstring claiming
otherwise was.

Reopen with a number: repeated `index --reset` during a large fresh ingest
measurably slower, with the snapshot copy identified as the cost.

**This is the one place the plan recommends *not* doing tracked work.**
Recorded here because "grouped into a batch" was starting to read as
"will be implemented", and for #289 the right outcome was a decision.

---

## Batch 3-ter — rules fingerprint residue (#304)

**Landed 2026-08-09**, with 2-bis. The row above says this "may resolve
as a decision, like #299 — the issue says to measure how often a rules
edit changes `scan` and not configuration before building anything." The
measurement was run and then a second one overturned the reason for not
building.

**Measurement 1 — frequency, as asked. Zero.** Every commit touching
`src/minerva/refs/rules/` was replayed: check out `C^` and `C`, drop
today's `fingerprint.py` into each tree, fingerprint every rules module
on both sides, and compare against the files the commit edited. 13
commits, and not one changed a rule's logic while leaving its
configuration alone. Two results are worth keeping:

- The three commits whose edits the digest did *not* see were all
  behaviour-preserving — a `_figures.py` extraction that moved 19
  authors' form tuples into shared constants without changing one of
  them, a ruff-format pass, and a comments-and-docstrings commit
  (dd30678). Not seeing those is the digest working. The one author that
  *did* move in the `_figures` refactor, Locke, moved on a reordered
  tuple that `_compile_forms` sorts anyway — a spurious invalidation, in
  the direction the module says to resolve unknowns.
- The single genuine gap in 14 months was 70183ed, which rewrote
  `insert_candidate` in `refs/rules/__init__.py`. That is scan-pipeline
  logic rather than a `scan` body, so it is adjacent to #304 rather than
  in it — but it is covered now, because the walk reaches it.

On frequency alone the answer was #289's: leave it, document it, keep
`--rescan-all`.

**Measurement 2 — the stated blocker, which is false.** #304's Hypothesis
says bytecode is unusable because "code objects carry line numbers … so a
reformat that moves a rule module's functions down a line changes every
digest in it — and batch 7 of the close-out plan reformats these files."
A code *object* does carry them; `co_code` does not, and an AST dumped
with `include_attributes=False` carries no position information at all:

```
firstlineno      A=2 B=5      (B is A with blank lines and comments added)
co_linetable ==  A/B False
A original       8624085b843e0efcfff830d7
B reformatted    8624085b843e0efcfff830d7  SAME
C logic edited   1e4a536194b950325b7ce22d  DIFFERENT
```

Had we trusted the issue, 3-ter would have closed as "cannot be fixed
without breaking batch 7" — declining a fix on a constraint that does not
exist. AST is used rather than `co_code` for the one cost bytecode really
does carry: it differs between CPython versions, which would make an
interpreter upgrade a full-corpus rescan.

**What shipped.** The digest gained a fourth input: the AST of every
method the rule can reach, over the same walk that already collected the
module globals it reads, with docstrings stripped first. Docstring
stripping is not fastidiousness — dd30678 is a commit in this very
directory that changed nothing else, and hashing prose would have
invalidated 16 authors' markers for it.

Two things found while building, both fixed here rather than filed:

- **The #287 digest already depended on CPython internals.** The walk
  seeded itself from every method in the MRO, which for a frozen
  dataclass includes the generated `__replace__` — whose module is
  `dataclasses`, and which dragged `MISSING`, `_FIELDS`,
  `_FIELD_CLASSVAR` and `_FIELD_INITVAR` into every author's
  fingerprint. A CPython release renaming any of those would have
  invalidated all 428,606 markers with no rules change at all. No rules
  class defines a dunder by hand, and a dataclass's generated methods
  derive from fields the digest already covers, so the walk now stops at
  them. Every input is project code (`test_digest_inputs_are_project_code_only`).
- **Cost measured, not assumed.** 51 authors, 28 distinct digests, 25.0 ms
  → 38.9 ms cold, 11.1 ms once the per-code-object memo is warm. Paid once
  per process. The distinct count is unchanged, so per-author invalidation
  is as sharp as it was.

**Operator step owed on the next rules pass.** All 27 rule-carrying
authors' digests move; the 24 authors with no rules module keep the
empty-set digest and stay skipped. So the next `refs build --strategy
rules` re-scans those 27 authors once and settles — the same one-time
shape #287's own landing had, and idempotent.

---

## Batch 4 — chunk-length gates (#268, #176)

### #268 — `min_chunk_chars=60` hides short chunks from search entirely

`src/minerva/retrieve.py:447`, applied to both BM25 and vector paths, with
nothing in the app overriding it (`agent/retrieval.py:221` omits it). The
floor's rationale is real — Nietzsche letter signatures outranked his
philosophy on queries naming him — so it cannot simply be dropped.

**Approach: exempt verse-addressed works via the existing
`works.citation_system` column.** Measured on the live index:

| citation_system | chunks under 60 chars |
|---|---:|
| `bcv` | 15,968 |
| `surah_ayah` | 1,937 |
| `paragraph` | 31,610 |
| others | 4,259 |

Exempting `citation_system IN ('bcv','surah_ayah')` makes 17,905
legitimately short verses reachable — all 1,937 Quran chunks, plus
`Non occides.` (Exod 20:13, 12 chars) and `Ego et Pater unum sumus.`
(John 10:30, 24 chars) — while leaving the 31,610 `paragraph` ones
filtered. Sampling confirms those are what the floor is for: Renan
footnote markers (`2. Zach., I, 1-6.`), French OCR garbage, running heads.

No new taxonomy and no hardcoded corpus list. `block_type` cannot carry
this — it is NULL on 49,728 of the 53,774 short chunks.

- BM25 (`retrieve.py:145-185`): widen `AND length(chunks.text) >= ?` to
  `AND (length(chunks.text) >= ? OR <exempt>)`. The work's citation system
  is **not** in `chunks_full`, and `<exempt>` must cover **both**
  `chunks.edition_id` and `chunks.translation_id`.

  **Corrected 2026-08-08 while implementing.** The reason given above —
  "scripture is present as editions (Vulgate, SBLGNT) *and* as translations
  (KJV, Luther), so a predicate on one silently misses half" — is false.
  Every short scripture chunk is on the **edition** side; the verse-addressed
  works have no `translations` rows at all, and the KJV and Luther are
  `editions.name` values, not translators:

  ```
  $ sqlite3 data/index.sqlite "SELECT count(*) FROM translations t
      JOIN works w ON w.id=t.work_id
      WHERE w.citation_system IN ('bcv','surah_ayah')"
  0
  ```

  17,905 short chunks on the edition side, 0 on the translation side. Both
  halves are still worth writing — a chunk reaches its work through exactly
  one of the two columns, and the next scripture ingest could land either
  way — but the *verification* changes: the translation half cannot be
  exercised against the live index and needs a fixture, which is what
  `_seed_verse_db` in `tests/test_retrieve.py` is for. Had the claim been
  trusted, "confirmed on both paths" would have been reported on the
  strength of a path that has no data in it.
- Vector (`retrieve.py:330-340`): filtering is numpy over
  `meta.text_lens`. Do **not** extend `EmbeddingMeta`
  (`src/minerva/store/embeddings.py:179`) — `meta.work_ids` is already
  there, so compute the exempt `work_id` set once and use
  `keep &= (meta.text_lens >= min_chunk_chars) | np.isin(meta.work_ids, exempt)`.
- `_reserved_term_ids` (`retrieve.py:250-306`) passes the floor through to
  `_fts_match` and should inherit the fix for free — confirm, don't assume.

Verification: both Latin verses above retrievable by exact phrase where
they were not before, and the regression the floor exists to prevent stays
fixed — a query containing "Nietzsche" must not surface letter signatures.

### #176 — chunk granularity: gate, then the worst outliers

**Part 1, the gate.** Reuse the existing snapshot pattern rather than
inventing one: `scripts/chunk_count_validation.py` already has
`build_snapshot` / `write_snapshot` / `validate_chunk_counts` against a
committed `data/authors/chunk_counts.json`, wired into
`make generate-authors` and validated in CI without the DB
(`.github/workflows/check.yml:133`). Add a granularity check the same
way — a committed snapshot of per-work/lang max and mean chunk length —
called from `scripts/check_author_ingest.py::main` beside
`validate_corpus_authors`.

**The gate must be baseline-pinned, failing only on new violations.** A
bare "no chunk over N characters" assertion fails immediately on all 753
existing ones and is unlandable — the same trap that has #229 stuck.

**Built 2026-08-08, with one addition the plan did not specify.** The
policy and the measurement had to go in *different* files, because the
counts pattern this copies regenerates its snapshot from the DB — and a
gate whose baseline is regenerated the same way blesses every new
violation and checks nothing. So: thresholds and the reviewed
`known_coarse` baseline live in `manifest.yaml` (hand-edited),
measurements in the generated `data/authors/chunk_granularity.json`. Both
dimensions the issue names are gated — per-pair `max` (8,000) and `mean`
(3,000) — because a max-only gate misses a uniformly coarse work, which is
the Epictetus asymmetry. 94 pairs are on the baseline; `tolerance_pct: 5`
keeps an ordinary text edit from failing CI, and a stale entry fails as
loudly as a new violation so the list shrinks as part 2 lands.

**Part 2, re-chunk the clear parser failures only**: Aeschylus
*Agamemnon* (eng), Hobbes *De Cive* and *Leviathan* (lat), Epictetus
*Discourses* (eng, where **four** chunks hold 97% of the text — see the
correction below). The Aquinas commentaries are **out of scope** — their
coarseness is a real structural level, and changing it is a
chunking-design decision, not a bug fix.

**Corrected 2026-08-08 while implementing #176's baseline.** This plan and
#176 both say "one chunk holds 97% of the English *Discourses*", from the
issue's `max=560,187`. No chunk that large exists, anywhere in the corpus:

```
$ sqlite3 data/index.sqlite "SELECT max(length(text)) FROM chunks"
151427
```

The work has 85 chunks (not 81) and its four largest are 151,427 /
146,461 / 131,035 / 129,821 = 558,744 characters, 97% of its 573,263 — so
the *proportion* holds and the *singular* does not. The earliest snapshot
on disk, `data/snapshots/20260808T013610Z-…`, already reads 85 / 151,427,
so this is not recent drift. Consequences, both material:

1. A part-2 fix verified by "the mega-chunk is gone" would have declared
   success with three 130,000-character chunks still in place.
2. The granularity baseline would have been pinned at 560,187 — a ceiling
   3.7× the real maximum, so a genuine regression up to half a million
   characters would have passed the gate silently. It is pinned at 151,427.

Corrected on the issue as well.

### 4-op's scope, corrected 2026-08-15 while scoping part 2

**Measured before opening the window, and it does not survive.** Three
findings, each changing what part 2 *is* rather than how it is run.
Recorded on #176 as well.

**1. Hobbes is not a parser failure.** Part 2's scope above reads
"re-chunk the clear parser failures only: Aeschylus *Agamemnon* (eng),
Hobbes *De Cive* and *Leviathan* (lat), Epictetus *Discourses* (eng)".
Two of those four are deliberate. `src/minerva/sources/hobbes_la.py` says
so in its module docstring — "Each chapter becomes one ``Chunk``. The OCR
is noisy enough that finer-grained per-article chunking would be
unreliable" — and the parser does exactly that:

```
Leviathan: 47 chunks   (I-XLVII = 47 chapters)   max=127,001 mean=17,632
De Cive:   18 chunks   (I-XVIII = 18 chapters)   max= 71,878 mean=26,356
```

47 for 47 and 18 for 18. Re-chunking these overrides a stated trade-off,
which is the same *kind* of decision this document already excludes
Aquinas for. **What would have gone wrong:** part 2 would have reversed a
documented choice as though it were a bug, and rediscovered the
OCR-reliability question from the output.

**2. The two genuine failures have different causes, and neither is the
one #176 names** ("a parser that found no structural divisions and
emitted the whole document"):

- *Aeschylus* — `tei_drama.py` chunks on leaf `<div type="textpart">`
  and its siblings prove the strategy works (Eumenides eng 54 chunks /
  avg 967; Persians eng 64 / avg 565). Agamemnon eng alone yields 1 chunk
  of 82,256. One file, not the strategy.
- *Epictetus* — a different path entirely, `tei.py`'s `_ChunkBuilder`.
  `discourses_en.xml` is TEI.2 with **no milestones at all**, so
  `_detect_chunk_boundary_units` returns an empty frozenset and the body
  becomes one chunk. Its docstring calls that case "rare". The structure
  it ignores is present: `div2[type=chapter]×96` in body0 alone. So the
  fix is a fallback to `div[type=chapter]`, not a re-source.

**3. It is five parsers, not one.** 111 work/lang pairs exceed the
8,000-char threshold (105 excluding Aquinas), across five ingest paths:

```
.txt 13,511 chunks · .html 11,949 · .xml 5,277 · .pdf 1,585 · .epub 754
```

**The useful discriminator is raggedness, not coarseness** — max/median
chunk size *within* a work. A working parser is uniform; a failure spikes:

```
ratio >= 20x:  59 pairs   ragged  -> parser dropping structure on an input
ratio <  20x:  31 pairs   uniform -> a granularity choice, Hobbes-shaped

  1211x Epictetus Discourses    eng  n=  85 median   125 max 151,427
   105x Nietzsche Nachg. Frag.  deu  n=3,345 median  311 max  32,778
    51x Hegel     Encyclopaedia eng  n= 246 median 2,311 max 118,716
```

Hobbes does not appear — its chapters are uniform, which is the point.

**Consequence.** "Re-chunk the outliers" is not one change. It is at
least five, one per ingest path, plus a per-work ragged/uniform judgment.

### The four non-XML paths, scoped 2026-08-15

The paragraph above said these "have not been investigated and cannot
currently be sized". **They now have been, and the answer is much smaller
than the pair count suggests.** Of 58 ragged pairs (max/median ≥ 20×),
**44 are `.xml`**. The other four paths hold 14 between them, and only
**5 are parser defects**:

```
ext      ragged>=20x  uniform<20x
.xml            44          15
.html            6           6
.txt             5           4
.pdf             2           1
.epub            1           0
```

**Genuine defects — 5 pairs, 3 parsers:**

| pair | evidence |
|---|---|
| Hegel *Encyclopaedia* eng (`.pdf`) | §244 is 118,716 chars ending `…Zeno of Elea, 145, 164 Zeus, 120, 221` — the volume's index. ~1,300 chars are Hegel. **#385** |
| Hegel ~~*Philosophy of Mind*~~ *Encyclopaedia* eng (`.pdf`) | §82 is 84,516 chars, ~~editorial footnotes at the head and the 1830 preface at the tail~~ — **corrected again 2026-08-15: it is ~76% Hegel**, holding all three prefaces (1817, 1827, 1830 — 64,134 chars), and it is a *front*-matter mis-split at `ord=1`, before §1, not accretion. **#385** — **corrected 2026-08-15: §82 is in the *Encyclopaedia* file, the same volume as §244, not the sibling.** *Philosophy of Mind*'s two largest chunks (§406 at 66,265 and §408 at 53,592) are genuine Hegel on mental illness; its back matter accretes onto **§577** (43,001), third in that volume. This matters because #385 proposes bounding section length as one of two fixes, and a size threshold tuned to catch §244 would relabel 119,857 characters of Hegel as apparatus. |
| Cicero *Brutus* eng (`.txt`) | 64 paragraphs, median 1,749, top five 33,241 / 28,156 / 17,701 / 15,936 / 12,604 — ~~paragraph detection failing repeatedly~~ **corrected: the source is sparsely paragraphed, see below** |
| Aesop *Babrius* grc (`.txt`) | section label is garbled apparatus criticus (`V. V1 πατὴρ conicias κἀσποίει \| 66 ἐτέρῳφϑη A, corr. Bgk`); the 22,615-char body is an index of fables — **corrected: #385's class, not this one, and the English half has the opposite defect. #398, #399** — **#398 landed 2026-08-15 by re-sourcing, not by filtering.** Babrius is First1KGreek **tlg0614**; our own `aesop_works.py` said no TEI existed because it probed **tlg1670**, which 404s. 498 chunks / 501,783 chars → 285 / 71,217, zero apparatus markers, real `1.N.¶M` locators, and the garbled `book` label disappears without a locator fix. **#399 landed the same day**: the English extractor's `_PERRY_REF` was dropping half the fable boundaries (81 of 142 matched), so 92 of ~143 fables were recovered; loosening it gives **131**, and a `fable` locator takes the pair from 2,139 chunks at a 44-char median to 131 at 796. |
| Hobbes *De Cive* eng (`.txt`) | the dedicatory epistle emitted as a single 10,709-char `¶1` |

**Faithful to a real source unit — not defects:**

- **Augustine *De civitate Dei*** — the apparent gaps are in the **source**,
  not the parser. Source markers: 600; corpus chapters: **600**; every book
  matches exactly. `[CIV.22.5]`–`[CIV.22.11]` and `[CIV.18.32]`–`[CIV.18.43]`
  are simply absent from `civitate_dei.txt`, and the 53,414-char chunk
  reproduces its source span (53,428, the difference being the marker line).
  Coarse addressing is a re-sourcing question, not a chunking one.
- **Spinoza** `E I, App.` — the real Appendix to Part I, one undivided unit.
- **Kant** *Anfangsgründe* — a real chapter.
- **Nietzsche** *Nachlass* `NF-1888,24[1]` — one fragment that happens to
  contain an entire *Ecce Homo* draft. The fragment id is the citable unit.
- **Hegel** *Elements* `§140 Remark` (`.epub`) — genuinely one of the longest
  Remarks in the work.
- **Locke** *Essay* — an 8,643-char paragraph, barely over the threshold.

**#385 is a different defect class and must not be folded into #176.**
#176 is granularity — units too coarse but the right *text*. #385 is
apparatus ingested *as* text: splitting §244 into ten 12,000-char pieces
would yield ten index chunks instead of one. Same window, separate fix,
separate issue — the relationship #177 already has to this family.

**Recommendation, not yet taken: narrow 4-op to the TEI path's ragged
pairs** (Epictetus and the tragedians, ~5,277 chunks, one parser), land
it with #298 and #383 in one window. The five non-XML defects are now
sized and can be scheduled on their own merits; three of them
(Cicero, Aesop, Hobbes eng) are single-work parser fixes, and two are
#385.

#### Cicero *Brutus*, worked 2026-08-15 — not a detection failure

The table above calls it "paragraph detection failing repeatedly". The
splitter detects every blank line the file has; the file is simply
paragraphed sparsely in one half and not the other:

```
BRUTUS: chars=251,812  blank-line breaks= 66  paras= 65  median=1,726  max=33,241
ORATOR: chars=206,726  blank-line breaks=205  paras=199  median=  744  max= 5,039
```

Same file, same splitter, same translator — Jones runs Cicero's dialogue
continuously, and the largest "paragraph" is 461 lines with no break in
it. There is nothing to detect better. **What would have gone wrong:**
the fix would have been sought in `_HEADING_RE` or the blank-line regex,
where the defect is not, and a working splitter would have been tuned
until something else broke.

What the source *does* carry is speech turns — `…"--"…`, 148 of them
across the Brutus — so a paragraph over the cap now splits there, and an
oversized turn splits again at its sentence ends. **The cap is opt-in per
work** (`CorpusWork.max_paragraph_chars`), because this same splitter
serves Hegel's `§244`: a global rule would have done to that section
exactly what the #385 row forbids. Measured: 270 → 288 chunks, max
33,241 → 7,958, chunks over 8,000 10 → 0, and 21 of the 22 Cicero
work/lang pairs byte-identical. The pair leaves `known_coarse` at the
window (mean 1,599, max 7,958 — under both thresholds).

#### Babrius, worked 2026-08-15 — one of the five "genuine defects" is two, and neither is this issue's

The row above lists Babrius grc among 4-op's parser defects, on evidence
that already describes a different defect class: "the 22,615-char body is
an index of fables". Read before writing a split for it, and the split
would have been wrong.

**Greek — #385's class, at 409 chunks rather than one.** Apparatus
criticus is interleaved with the verse throughout, because the source is
a critical edition that prints each fable's apparatus beneath it:

```
under 'V. V1 πατὴρ conicias κἀσποίει | 66 ἐτέρῳφϑη A, corr. Bgk':  409 chunks, 450,696 chars
elsewhere (¶1 … ¶89):                                               89 chunks,  51,087 chars
chunks with >=3 apparatus markers: 100 of the 409, and 25 of the other 89
```

Splitting the 22,615-char chunk yields three apparatus chunks instead of
one — the exact objection this document already records against folding
#385 into this issue. Filed as **#398**, which also carries the separable
locator half: `_HEADING_RE` matched an OCR'd apparatus line as a chapter
head, so those 409 chunks cite as `V. V1 πατὴρ conicias …, ¶N`.

**English — the opposite defect, and the gate cannot see it.** ~~1,823 of
2,239 chunks are under 100 characters, median 44~~ — **corrected
2026-08-15 verifying #399: that row is `Aesop|*|eng`, not Babrius.** It
sums in the 100 correctly-chunked Phaedrus eng chunks; Babrius alone is
`n=2,139 median=44 mean=71 under-100=1,813`, which is *finer* than the
figure quoted, not coarser. The cause holds — the Davies scan carries
OCR-inserted blank lines (2,307 breaks in 6,171 lines) and the splitter
emits one chunk per blank-line paragraph, correctly. Filed as **#399**,
where the correction is posted. Worth noting for the gate's own sake:
`max_chunk_chars` and `max_mean_chunk_chars` bound coarseness only, so a
work can fragment to 44-character chunks and pass. This page has been
treating the gate as covering granularity; it covers half of it. **Now
filed as #404** rather than left as an observation here.

~~**What would also have gone wrong:** #399 proposes accumulating lines to
the next `[Fable N]` marker. The file carries **92 markers for ~143
fables** … so that fix silently merges the ~51 unmarked fables into their
predecessors.~~ **Corrected 2026-08-15 while landing #399: that was my own
error, and it pointed away from the real fix.** The 92 markers are
consecutive 1–92 with no gaps, so nothing was there to merge. The missing
fables were absent from the *extraction*, not the scan: `_PERRY_REF`
matched 81 of the 142 Perry-index lines that mark fable boundaries, and
loosening it recovers 131. Trusting this paragraph would have sent the
next reader looking for a merge policy governing text that is not in the
file.

**What would have gone wrong:** applying #397's `max_paragraph_chars` to
Babrius — the obvious next step, since it was next in the same list —
would have made the Greek worse by multiplying apparatus chunks and done
nothing at all for the English, whose chunks are already 44 characters.

#### The `.xml` path, worked 2026-08-15 — and it is **three** parsers, not one

Taken, and the parenthesis above is wrong twice. The 44 ragged `.xml`
pairs are split across `tei_drama.py` (39, the tragedians — PR #393),
`tei.py` (3, Epictetus's English — PR #396) and `tei_p5.py` (2,
Aristotle's *Problems* and *Parts of Animals* in Greek). Both fixes are
parser-only; neither has touched the database.

**The two `tei_p5.py` pairs are not defects, and this section's own
discriminator says they are.** The table above reads "ratio >= 20x →
parser dropping structure on an input". Measured:

```
problems:         n=889 median=359 max=10,269  chunks over 8,000: 1
                     book='30' section='30.1.¶1' len=10,269
parts_of_animals: n=466 median=395 max= 8,474  chunks over 8,000: 1
                     book='4'  section='4.1.¶1'  len= 8,474
```

`tei_p5.py` emits **one chunk per `<p>`** — the finest unit these files
carry. Each work has exactly one paragraph over the ceiling, and the
ratio is high because the median paragraph is ~360 characters. That is
the Hobbes case in miniature: a real source unit that happens to be long,
which this document already excludes from part 2's scope. **What would
have gone wrong:** the `.xml` path would have been left open pending a
`tei_p5.py` fix that has nothing to fix, and the natural "fix" — splitting
a paragraph mid-sentence — would have damaged a working parser.

So the `.xml` half of 4-op is **done pending the window**: 42 pairs
re-chunked, 2 correctly left alone. What the two PRs deliberately left,
~~both blocked on the same locator question,~~ is #394 and #395.

**Corrected 2026-08-15, closing out #395: they were never blocked on the
same question, and treating them as one pair is what kept the cheap half
sitting in the backlog.** #395's *Fragmenta* was not missing a locator —
its body carries 111 milestones numbering Schenkl's fragments and the two
Stobaeus gnomologia, which `_detect_chunk_boundary_units` discarded for
not being `section`/`bekker page`/`card`. Honouring the source's own units
took it from one 25,244-char chunk to 111, and the "check the `<p>` runs
against Schenkl's numbering" the issue asked for was never needed. #394's
*Discourses* eng has no milestones at all and nothing numbered below
`chapter`, so its locator genuinely had to be chosen: **`IV.1a`, decided
2026-08-15** and recorded on the issue. **What would have gone wrong:**
whoever unblocked #395 from its markup would reasonably have expected the
same trick to unblock #394, and gone looking for sub-chapter markers that
are not there — after designing the fix around them. The property that
made the misdiagnosis reasonable is filed as #405.

**Two things to settle *before* this window opens, added 2026-08-09.
Both are cheap now and expensive afterwards, which is the whole reason
they are written here rather than left to whoever runs it.**

- ~~**#314 must land first.**~~ **Done — #314 landed 2026-08-15 as PR
  #382 and the issue is closed.** The reasoning stands and is worth
  keeping: this window re-lemmatizes, #314 was a defect in the lemma
  *writer*, and running the window first would have baked its output in.
  The batch table above has recorded it as landed since it merged; this
  line kept the imperative, which is the one a reader opening the window
  would act on. **Corrected 2026-08-15 while scoping that window.**

  Worth knowing if it is ever re-checked: the defect was `ara`-only —
  every other language measured 100.00% correct on the same audit — and
  no Arabic corpus churns in this window, so it would not in fact have
  gated *this* re-ingest even had it still been open. The prerequisite
  was right for the general case and over-broad for this one.
- ~~**Decide whether the Marx corpus gets a chrome audit, and decide it
  now.**~~ **Done — the audit ran on 2026-08-15 and its finding is #383.**
  This entry described an unexamined area with a deadline; the area has
  been examined. All three layers of the 2026-05-31 cleanup were checked
  in one read-only pass: **(a) Gutenberg site chrome — 0 chunks**,
  **(c) duplicate paragraphs ≥60 chars — 0**, and **(b) 33 chunks of
  Internet Archive crawl-provenance boilerplate**, all in *Die deutsche
  Ideologie*, carrying 198 `chunk_lemmas` rows, 33 embeddings and **0**
  `cross_references`. Row 4-op-bis above has recorded this since it was
  filed. **Corrected 2026-08-15 while scoping the window**, for the same
  reason as the entry above it: the batch table knew and the checklist
  did not, and the checklist is the half that gets acted on.

  The decision the entry asked for has therefore been taken, and it is
  the one this entry predicted: #383 costs nothing extra inside the
  window — same re-ingest, same refs rebuild, and with 0 cross-references
  nothing to re-anchor — so it rides along rather than buying its own
  slot.

  Kept from the original entry because it is still the reason the audit
  was worth running: #298 audited a single string,
  `Seitenzahlen verweisen auf:`, and the 2026-05-31 round had found
  **three** distinct chrome layers.

#298's own corpus repair rides here too — 745 Marx `chunk_id`s, for the
reason recorded in batch 5-bis.

Part 2 is an operator job needing its own session:

1. `scripts/snapshot-db.sh chunk-regranularize`
2. Measure churn by aligning parser output **positionally**. Never join
   before/after on `section` — it repeats per book and inflated a previous
   measurement 20×.
3. `minerva index --incremental --corpora <those>`
4. `minerva embed` (incremental by default), then `terms lemmatize`.
   **Corrected 2026-08-08: this step used to read "`--n-process 1` for
   `lat` until batch 2 lands".** Batch 2 has landed (PR #286), so the
   default `--n-process 4` is now correct for every language —
   `Lemmatizer._safe_n_process` (`src/minerva/lemmatize.py:560`) probes
   the payload before entering the pipe and downgrades to 1 with a notice
   on stderr where spawn cannot pickle it. Passing `--n-process 1` by
   hand now just makes the pass slower for no reason.
5. Full refs rebuild: rules, then `--strategy embed-verify`, then
   `--strategy llm-verify`. Source-side chunk churn invalidates anchors;
   `refs build` alone is not enough.
6. **Remove each re-chunked pair from `granularity.known_coarse` in
   `data/authors/manifest.yaml`.** The gate fails on a stale baseline
   entry as loudly as on a new violation, so a work that has been fixed
   but left on the allowlist breaks `make check-authors` — which is
   deliberate, and is what keeps the list shrinking. Keys are
   `author|title|lang`.
7. `make generate-authors` and commit, including the regenerated
   `data/authors/chunk_granularity.json`.

**Status, 2026-08-08: part 1 landed in PR #292; part 2 has not.** This is
the one place the document records state, against its own rule at the top,
because the open-issue list cannot express it: #176 is open, and reading
only the issue list would suggest the gate still needs building. Nothing
else here is tracked twice.

Part 1 carried `Refs #176`, so the issue is still open by design. Part 2's
PR is the one that should carry the closing keyword for it.

**Written that way on purpose, and the reason is worth reading.** An
earlier revision of this line spelled the keyword out next to the issue
number. That sentence went into a squash-merge commit message, GitHub's
parser read the keyword out of the surrounding prose — backticks are no
protection — and shut the issue on the spot, three minutes after the same
paragraph explained that it must stay open. Reopened by hand. Never put a
closing keyword adjacent to an open issue's number in any text that can
reach a commit message, including this document.

**And this paragraph broke its own rule until 2026-08-09**, which is the
best evidence that the rule is easy to break: the sentence above read
"…and clos&#101;d #176 on the spot", a closing keyword directly against an
open issue's number, sitting inside the warning against exactly that. It
never fired only because GitHub parses commit messages and PR bodies, not
file contents — so it was one quotation away from repeating the incident
it describes. Found by grepping this file for
`(close|fix|resolve)\w*\s+#\d+` before a commit; worth doing again
whenever this page gains a paragraph. Two hits are benign, so do not
spend the check on them again: one names #264, which is closed and
cannot be re-closed, and one names #229, which is a **pull request** —
closing keywords act on issues only.

**Corrected 2026-08-15: the sentence above said those were the only two
hits, and two more were live at the time it was written.** Both sat
against **open** issues, and both have been reworded in this edit:

| line | shape | issue |
|---|---|---|
| ~115 | a closing keyword used as a *noun* — "one of the three &lt;keyword&gt;s &lt;issue&gt; offers" | open |
| ~3054 | a sentence quoting the literal trigger, keyword against number | open |

Neither the keywords nor the numbers are reproduced here, and the HTML
character-entity escape this page uses two paragraphs up is **not** the
way to reproduce them. An entity spliced into the middle of a keyword
renders as that keyword, and *scans* as the keyword followed by the
entity's decimal code read as an issue number — `make check-pr-link`
rejected a body of that shape on PR #396, naming an issue number nobody
had typed. Safe in a file, which GitHub never parses; a fresh hazard the
moment the paragraph is quoted into a PR body, which is the one thing
this page's paragraphs are for. Describe the shape instead.

Neither had fired, for the same reason the paragraph above gives: GitHub
parses commit messages and PR bodies, not files. But this page is quoted
into PR bodies constantly — that is what it is *for* — and either
quotation would have shut an open issue silently. **What would have gone
wrong had the "both are benign" line been trusted:** the grep would have
been skipped as already-done, which is precisely how these two survived
the round that wrote the warning. Re-run it, and check each hit's issue
state rather than the list here — a benign hit stops being benign when
its issue reopens.

---

## Batch 5 — perseus scraper verification (#151, #152)

**Landed 2026-08-08.** Both issues closed; four new issues filed
(#297–#300) and corrections recorded on both. The measurements are in the
PR body and in each script's docstring; what follows is the plan as
written, annotated where it was wrong.

Both hold values written in #149 that were never checked against live
pages. Both scripts are manual one-shots nothing imports, and both raised
`NameError` before #149, so neither can have contaminated the corpus
through this path. `perseus/**` is coverage-excluded, so no Sonar gate
applies.

**Confirmed: no contamination, on every path checked.** The committed
`deutsche_ideologie.txt`, the six PG-DE files and all 14 Cicero Latin
files carry none of the chrome the broken skip-sets let through, and the
live index has none of it either. The defect was an *inert guard*, not a
dirty corpus.

**Corrected while implementing — `data/*` is gitignored, so "fetch the
missing work" is an operator action, not a commit.** The plan and #151
both describe fetching `de_officiis_lat.txt` as filling a gap in
`data/cicero/raw_la/` (15 declared, 14 present). It does — but in the
*local* data tree only:

```
$ git ls-files data/cicero | wc -l
0
$ git check-ignore -v data/cicero/raw_la/de_officiis_lat.txt
.gitignore:13:data/*	data/cicero/raw_la/de_officiis_lat.txt
```

So the file cannot ride along in the PR, CI cannot verify it, and a fresh
clone will not have it. Had this been trusted, the batch would have been
reported as "gap filled" on the strength of a file no reviewer could see.
The work is real and done locally (715 lines, 237,829 bytes, three Libri,
ending at the true `[121] Habes a patre munus, Marce fili`); it is staged
for the next ingest on that machine, and re-fetching it elsewhere is one
`--only` invocation.

- **#152** — fetch one page each from projekt-gutenberg.org (Marx) and the
  archived mlwerke.de `me03_NNN.htm`, inspect what `_extract_paragraphs`
  returns, and confirm or extend `_SKIP_CLASS_TOKENS` in
  `perseus/download_marx_pgde.py` and `perseus/download_marx_archive.py`.
  Expect layers: the Kapital MEW re-source found three (site chrome,
  Wayback wrapper, intra-file duplicate paragraphs). If the wrapper needs
  more than class tokens, note that in the docstring rather than widening
  the set — `"footer"` and `"navbar"` are already generic enough to eat
  real content.

  **Measured: worse than "some tokens are stale". Of the eleven tokens
  across the two scripts, exactly one matched anything.** All seven in
  `download_marx_archive.py` matched **zero** elements on all three of
  its sources, and three of four in `download_marx_pgde.py` did too
  (`site-header` was the only live one). The reason no widened class set
  can fix the wayback half: the toolbar carries **no class at all** — it
  is keyed on `id` (`id="wm-ipp"`, `id="donato"`). The guidance above was
  right that the wrapper needs markers beyond class tokens, and the
  answer was `skip_id_tokens` plus web.archive.org's own
  `<!-- BEGIN/END WAYBACK TOOLBAR INSERT -->` boundary comments, because
  attribute skipping alone still leaked — see #297.

  The predicted third layer was there: PG-DE renders each chapter body
  **twice**, text-identical, so the pre-fix parse emitted every Marx
  paragraph twice. Taking the body's own container
  (`div.book-reader__chapter-content-wrapper`) both de-duplicates it and
  survives WordPress theme churn, which enumerating chrome classes does
  not — after widening the set to every chrome class actually present,
  four paragraphs still came through.

  And the caution about generic tokens was well aimed: `sidebar` would
  have been harmless only by luck, since PG-DE's one `sidebar`-ish token
  is `no-sidebar` **on `<body>`** — a substring match there empties the
  document. Token matching is exact per whitespace-split token; there is
  now a test pinning that.
- **#151** — fetch the one genuine gap, `de_officiis_lat.txt` (15 declared
  works, 14 present), which exercises the multi-Liber path for real.
  Dry-run the other 12 works **to a scratch directory** and diff. Decide
  and encode whether per-Liber page titles and Arabic section markers are
  matched or deliberately diverged from; `_ROMAN_ONLY_RE` already filters
  the Roman ones and the Arabic are the same class of artifact.

  **Decided and encoded: filter the markers, and do *not* touch the
  titles.** `_ROMAN_ONLY_RE` was `^[IVXLC]+$`, which caught only the bare
  form — 18 of the 543 markers present across a full 15-work re-fetch,
  3%. The dotted Roman form (`XIII.`) is the commonest at 381, Arabic adds
  144, and De re publica carries 46 `(*****)` lacuna sigils. The
  committed files contain **zero** of any form, so the lost original
  filtered them all. The widened filter also had to be applied to the
  root page, not just sub-pages, which is where the 18 survivors were.
  Result: `de_amicitia` went from 70.5% to **100.0%** line-identical,
  `topica` stays 100%, and 11 of 14 works are now ≥97%.

  **Corrected: #151's "per-Liber page titles absent from the
  reconstruction" is false, and acting on it would have been actively
  harmful.** The reconstruction emits them correctly wherever the source
  still has them — `de_legibus` produces `M. TVLLI CICERONIS De legibus -
  Liber I` and `- Liber II` exactly as committed. Only De natura deorum's
  Liber II and III are missing, and those sub-pages now contain no
  `M. TVLLI` string at all upstream; the committed file preserves titles
  la.wikisource has since deleted. Had the issue been trusted, the fix
  would have synthesised per-Liber titles — fabricating source text, and
  injecting titles into the ~10 works that never had them, churning their
  `chunk_id`s to "fix" two lines in one work.

  Also worth not re-deriving: the committed Latin files are
  **post-cleanup** artifacts (`scripts/clean-cicero-chrome.py` strips a
  title/breadcrumb header after the fetch), so a raw scraper-vs-committed
  diff conflates two transformations.

**Do not re-run either script over the committed corpus.** Residual
differences would churn `chunk_id`s and cost those works their embeddings,
lemmas and cross-references. Byte-identity is unreachable in principle —
la.wikisource has changed since the May 2026 fetch — so the target is
"correct and structurally stable", not "reproduces the old bytes".
Honoured: every fetch in this batch went to a scratch `--data-root`, and
nothing was written under `data/` except the one missing work.

**One process note worth keeping.** A half-finished version of the
void-tag fix — guarding `handle_starttag` but not `handle_endtag` — turned
a latent bug into an active one, letting la.wikisource's `ws-noexport`
header chrome (`EPUB MOBI PDF RTF TXT`, `fons: incognitus`) into 15 of 15
Cicero files. The original code leaked none of it. The new fixture test
for the self-closed `<br/>` case is what caught it, before any of it
reached `data/`. Asymmetric guards on a paired counter are the failure
mode; test both halves.

Second process note: a background dry-run silently did nothing because
the backgrounded shell did not inherit an earlier `cd`, and
`grep -rl` over the missing output directory returned "0 chrome, 0
markers" — a clean bill of health measured against an empty set. Check
that a verification actually ran over files that exist before believing
its zero.

---

## Batch 5-bis — perseus follow-ups (#297, #298, #299, #300)

**#297 and #300 landed 2026-08-09. #298's parser half landed and its
corpus half is an operator step. #299 stays open, with its premise
corrected.**

### #297 — the skip-depth counter, replaced by a tag stack

The fix the issue calls "the real fix", and it is small: push the tag
name on entering a skip, and on an end tag unwind to the innermost
matching entry instead of decrementing. An end tag naming nothing open
is then dropped, which is what a browser does and what stops a stray
`</form>` from ending a `<div>` skip.

Two things the issue did not have, both found by writing the tests:

- **The counter fails in the opposite direction too, and no one had
  noticed.** `<div class=chrome><span><p>junk</div>` — unclosed
  descendants inside a skipped subtree — leaves the counter at 2 when
  `</div>` arrives, so the skip never ends and **the entire rest of the
  document is discarded**. #297 documents only the early-exit direction
  (chrome leaking out). Truncating the stack rather than popping one
  entry is what covers both, and a fix that only ignored unmatched end
  tags would have left this half live.
- **The blast radius is 5 scrapers, not 8.** The issue lists
  `download_descartes_wikisource`, `download_spinoza` and
  `download_augustine` among the callers passing `skip_class_tokens`.
  They do not — each carries its own private `_ParagraphExtractor` that
  predates the shared class and skips by tag name only:

  ```
  $ grep -rln "skip_class_tokens\|skip_id_tokens" perseus/*.py
  perseus/_download.py
  perseus/download_cicero_wikisource.py
  perseus/download_marx_archive.py
  perseus/download_marx_pgde.py
  perseus/download_pascal_fr.py
  perseus/download_rousseau_fr.py
  ```

  Material because a fix "verified across eight scrapers" would have
  been verified across three that cannot reach the code.

  **Corrected while filing 5-ter: it is *two* private copies, not
  three.** `download_spinoza.py` imports the shared class and defines
  none — the grep that found "three" hit its call site. The two real
  ones are `download_descartes_wikisource.py` and
  `download_augustine.py`, and neither carries #297's bug; they are
  tech-debt, filed as #317.

Verified on live pages: a two-work Cicero re-fetch to a scratch tree
differs from the committed files by trailing newline only, plus one
`FRAGMENTA` heading la.wikisource has since added. No chrome, nothing
lost.

### #298 — the mlwerke edition note: right defect, wrong file

The issue's Hypothesis names `perseus/download_kapital_mew.py` and
proposes reusing `_drop_mlwerke_chrome`. **Both are wrong, and neither
would have worked.** The scraper saves the raw `.htm` verbatim; the
chrome strip lives in `src/minerva/corpus/split_kapital_mew.py`, which
already has one — it just only sees `<small>`:

```
$ grep -rln "Seitenzahlen" perseus/ scripts/ src/
perseus/download_marx_archive.py
src/minerva/corpus/split_kapital_mew.py
```

The real cause is a markup variant, and it is narrower than "not in
`<small>`". 54 raw files carry the note; 37 of them wrap it in `<FONT
SIZE=2>` **outside** any `<p>`, where it never becomes a chunk. The 17
that leak open it with `<FONT SIZE=2><P>` and close the font *before*
the `</P>`, so it reaches the body loop as an ordinary paragraph:

```
</P>\n<FONT SIZE=2><P>Seitenzahlen verweisen auf: … S. 627 - 652<BR>
Dietz Verlag, Berlin/DDR 1983</FONT> </P>
```

Fixed by matching the note's own opening words, anchored to the start of
the paragraph — not by tag, because `<FONT SIZE=2>` also wraps ordinary
inline prose here, and not by substring, because Marx discusses page
references. Measured over the whole raw tree: the new rule removes
**exactly 17 paragraphs**, and a full re-split produces 7,113 chunks with
zero carrying the note.

**The 18th chunk is not this defect and needs no code.** `Lohnarbeit und
Kapital` comes from `data/marx/raw_deu/lohnarbeit_kapital.txt`, a
PG-DE-sourced text file, and `_drop_mlwerke_chrome` already removes that
line today — confirmed by feeding it the exact en-dash paragraph. It is
a stale artifact of a fetch predating the filter, which is also why its
dash differs; the issue reads the dash as evidence of a second live
code path.

**No Marx prose is contaminated — and the damage is nonetheless larger
than 18 chunks.** All 18 are *standalone* chunks of 141–162 characters
consisting only of the note; not one has real text appended to it. But
the note is a paragraph, so it takes `¶ 1` and pushes every real
paragraph in its chapter up by one. Chapter 37's opening paragraph is
`Siebenunddreissigstes Kapitel: Einleitendes, ¶ 2` in the live index and
becomes `¶ 1` once the note is gone:

```
$ sqlite3 data/index.sqlite "SELECT section, substr(text,1,40) FROM chunks
    WHERE section LIKE 'Siebenunddreissigstes Kapitel: Einleitendes, ¶ %' …"
Siebenunddreissigstes Kapitel: Einleitendes, ¶ 2 | Die Analyse des Grundeigentums …
```

So **745 chunks across the 17 chapters currently carry a paragraph
number one too high**, which is a citation defect rather than a text
one — the words are right, the address is not.

**Corrected 2026-08-09, same day, on this page and on PR #315: both said
"the 17 Band III `chunk_id`s change".** `section` is an input to
`_make_chunk_id`, so renumbering churns the id of every body paragraph in
those chapters, not only the 17 removed:

| | |
|---|---:|
| pre-fix chunks from the 17 files | 790 |
| post-fix chunks | 773 |
| **`chunk_id`s the fix introduces** | **745** |

The 28 that survive are footnote chunks, whose section is `Fn. (n)` and
carries no `¶`. Had the 17 figure been trusted, the operator step would
have been sized as a trivial repair and would have silently orphaned 745
chunks' embeddings, lemmas and cross-reference anchors.

**The corpus half is an operator step and did not land.** Repairing it
means re-ingesting the marx corpus — and `--only` replaces
`chunks.jsonl` per *corpus*, so all three marx sources have to go in
together or the siblings are wiped. 745 changed ids require a full refs
rebuild including the llm-verify tail. That is the same shape as 4-op and
belongs in a window with it, not at the end of a code round; the 745 also
ride free there, since #285 re-derives every `chunk_id` in the corpus
anyway. #298 accordingly carries `Refs`, not a closing keyword.

One thing checked and clean: the committed parser reproduces **7,130 of
7,130** live Kapital `chunk_id`s before the fix, so the index has not
drifted from the code by any other route.

### #299 — still a decision, but not the one the issue frames

**The premise moved and the issue's mechanism does not reproduce.** #299
concludes the 403 is "a deliberate signal from the site operator" whose
block "keys on the literal substring `minerva`". Measured 2026-08-09
across all six works, canonical UA against `foo/1.0`, every other header
held equal:

```
der-18-brumaire-des-louis-bonaparte                   minerva=200  foo=200
lohn-preis-und-profit                                 minerva=403  foo=200
lohnarbeit-und-kapital                                minerva=200  foo=200
das-elend-der-philosophie                             minerva=403  foo=200
die-heilige-familie-oder-kritik-der-kritischen-kritik minerva=403  foo=200
zur-kritik-der-politischen-oekonomie                  minerva=403  foo=200
```

The verdict is **per-URL and unstable**: `brumaire` is served to the
canonical UA on every attempt, and `lohnarbeit-und-kapital` returned 403
six times running and 200 a few minutes later. That behaves like a
bot-mitigation layer with a short-lived per-(UA, URL) verdict, not like
a substring blacklist — so "this script cannot fetch" is too strong, and
so is "the operator has decided". The docstring the batch-5 PR wrote is
corrected in this round.

**What does not change is the response.** Rotating the UA or giving this
script a private fetcher is still off the table. The three options in
the issue remain the repo owner's call; what the measurement changes is
that option 1 (accept) now costs less than it appeared to, since most of
the six are reachable most of the time. The durable engineering finding
is separate: 403 is not in `_RETRY_CODES`, so the script dies on its
first refused work with no partial output — the same gap #300 fixes for
the batch loop.

### #300 — both halves, and the redirect was checkable after all

Item 1 as the issue orders it: collect `(filename, reason)` per skip,
print a summary block, name the `--only` retry, and return non-zero.

Item 2 the issue hedges — "check *why* `urllib` did not follow it before
adding a retry". The 301 no longer reproduces, so the *why* is not
recoverable; but the redirect target is, and it is a drop-in.
`/api/rest_v1/page/html/<title>` is the deprecated endpoint and 301s to
`/w/rest.php/v1/page/<title>/html`. Measured byte-identical — same
sha1, same length — for De re publica, De officiis, Laelius de Amicitia,
Topica and the `De re publica/Liber I` sub-page, on both the space and
underscore spellings. So `_rest_url` points at the target directly,
which honours the redirect rather than masking it and removes the class
of failure instead of retrying it.

---

## Batch 5-ter — perseus follow-ups, second round (#316, #317)

**Todo.** Both filed 2026-08-09 while working 5-bis, both in files it
edited, and both are the *un-generalized* half of a 5-bis fix rather than
a new defect class.

### #316 — #300's accounting fix reached one script of fourteen

PR #315 taught `download_cicero_wikisource.py` to collect what it
dropped, print a summary and return non-zero. An AST walk over every
`main()` in `perseus/` says thirteen other downloaders swallow per-item
failures inside a loop, and **twelve cannot signal failure to their
caller at all** — no value-returning `return`, no `sys.exit`:

```
downloaders whose main() swallows per-item failures in a loop: 14
…of those, unable to signal failure to the caller: 12
```

Worse here than in the Cicero case, because several feed scripture and
Perseus corpora where a missing book does not show up in a file count.
The fix wants a small collector in `perseus/_download.py` rather than
twelve copies of #315's inline block — and #315's own copy retrofitted
onto it, so it does not become a thirteenth variant.

### #317 — the two private extractor copies, and what they are *not*

The part of #297 that PR #315 scoped out.
`download_descartes_wikisource.py` and `download_augustine.py` each carry
a private `_ParagraphExtractor` predating the shared class, so none of
its fixes — the void-tag guard, the tag stack, attribute skipping —
reach them.

**Filed with no demonstrated defect, deliberately.** They skip by tag
name only, so a stray end tag cannot desynchronise their counter, and on
unbalanced markup they behave exactly as the fixed shared class does:

```
html = "<p>FIRST</p><table><tr><td>junk<p>SECOND</p><p>THIRD</p>"

download_descartes_wikisource    -> ['FIRST']
download_augustine               -> ['FIRST']
shared, after PR #315            -> ['FIRST']
```

Two corrections to what this round first assumed, both caught by running
it rather than reading it. The plan and #297's comment said *three*
private copies: `download_spinoza.py` imports the shared class and has
none — the grep hit its call site. And the copies were assumed to carry
#297's bug; they do not, which is why this is tech-debt rather than a
second instance of it.

---

## Batch 6 — named-passage index (#182)

Two verified instances: the divided line (Politeia 509d–511e) and Meno's
slave boy (Menon 82b–85b). Both fail the same way — the query names no
work, and the passage is known by words its text never contains.

Two constraints already established on the issue, both of which hold:

- `terms` / `term_occurrences` is the **wrong** vessel. It is a
  lemma-keyed lexical glossary anchored on character offsets; "the divided
  line" has no lemma, no `source_form` in any source language, and no span
  to anchor to.
- Anything keyed on a surrogate id rots. `works.id` is reassigned by
  `--reset` (#193), and tables outside the preservation path get wiped
  (#192) — which is why `terms` is empty today despite a curator having
  authored nine Aristotle entries.

**Follow the `work_aliases` pattern** (migration 0025, issue #195). It was
built for this class of problem and satisfies both constraints: the data
lives in code (`src/minerva/authors/work_aliases.py`) keyed on the natural
key `(author, works.title)`, and is re-materialized into the DB on every
index run, so it cannot rot and cannot be wiped.

- **Phase 0 — measure before building.** `work_aliases` already resolves
  an arbitrary string to a `work_id`, and `detect_work`'s matcher requires
  every significant token of the name to appear in the query. On a scratch
  branch, add "the divided line" → Politeia and "slave boy" → Menon as
  aliases, then re-measure both queries through the real chat ordering.
  #182's own numbers suggest work-level scoping alone reaches rank ≤3
  (work-scoped queries already rank the divided line at 3), in which case
  the table's remaining value is semantic honesty plus section ranges for
  citation, not retrieval. Decide against that number, not in advance.

  **Measured 2026-08-08, and the answer is: build it. Work resolution is
  necessary and sufficient; the rank estimate above is optimistic.**
  Measured through `prepare_chat_turn`'s own sequence — `detect_corpus` →
  `strip_author_keywords` → `detect_work` → `retrieve_passages` — at
  `top_k=6`, `lang=eng`:

  | query | corpus | work_id | rank |
  |---|---|---|---:|
  | `the divided line` | None | None | absent |
  | `the divided line in the Republic` | plato | 941 | **6** |
  | `Where does Plato set out the divided line?` | plato | None | absent |
  | `Plato's divided line` | plato | None | absent |
  | `the slave boy` | None | None | absent |
  | `Meno's slave boy` | plato | 919 | **2** |
  | `Where does Socrates question the slave boy?` | None | None | **2** |
  | `the Copernican revolution` | None | None | absent |
  | `Kant's Copernican revolution` | kant | None | 5 |

  The failure tracks work resolution and nothing else: every query that
  resolved a `work_id` returned the passage, every one that did not is
  absent bar the Socrates phrasing, which is discriminating on its own.
  So Phase 1 as designed — a label consulted where `_best_title_matches`
  runs — is the fix, and **keeping the section range out of the retrieval
  filter stands**.

  Two corrections to the paragraph above. **Rank 6, not 3.** Inside
  `top_k` but at its edge; one more competing chunk pushes it out. That
  argues for having the range available as a tiebreak — an enhancement,
  not the fix. **And one of #182's two instances is already fixed:**
  `Meno's slave boy` resolves `work_id=919` today and returns the passage
  at rank 2 with zero apparatus in the top 6, and `the divided line in the
  Republic` — listed in #182 as absent — is now rank 6. Presumably #164's
  `title_local` work. So the live failing set is the queries naming
  *neither* author nor work, plus `Where does Plato set out the divided
  line?`, where the author is named and stripped but no work is.

  **Do not curate "the divided line" as a `work_aliases` entry**, which is
  the shortcut Phase 0 invites. `detect_work` requires every significant
  token, so it would scope *any* divided-and-line query to the Republic,
  and the alias file's own docstring rules this out: aliases are "names a
  reader would actually type" for the work. "The divided line" is not a
  name for the Republic. That is the semantic-honesty argument for a
  separate table, and it is load-bearing rather than decorative.

  **Method warning, learned the expensive way.** Three successive
  harnesses gave three different answers here. Calling
  `retrieve_passages` directly bypasses `strip_author_keywords`, which
  lives in the *caller* — and with it disabled the divided-line query
  returns 6/6 Shorey footnotes, which reads exactly like a real apparatus
  defect and is not one. A second harness compared every case's hits
  against one case's target set. Both produced confident, wrong
  conclusions that were briefly written into #182. Any measurement here
  must go through `prepare_chat_turn`'s sequence, print the resolved
  `corpus`/`work_id` beside every rank, and assert the target set is
  non-empty.
- **Phase 1** — `named_passages`: migration `0028_named_passages.sql`
  (0027 is taken by batch 2), source of truth
  `src/minerva/authors/named_passages.py` keyed on `(author, title)` →
  `(label, section_start, section_end, tradition)`, materialized in the
  index run next to `work_aliases`.
- **Phase 1 hook** — resolve labels where `_best_title_matches`
  (`src/minerva/agent/detect.py:190`) runs, so the same conservative
  token-matching applies and #194's corpus fallback gets it for free:
  "the divided line" with nothing else named then resolves both corpus and
  work in one step.
- Keep the section range **out of the retrieval filter** for now.
  `work_id` scoping already exists end to end; a section-range filter is a
  second change the measurements do not yet call for. Use the range for
  citation and display.

Do not curate broadly on the first pass. Seed the four labels the issue
names — divided line, Meno's slave boy, Kant's "Copernican revolution",
Hegel's "master and slave" — and measure the last two, which have never
been tested. Curation scope is a decision for after those numbers.

---

## Batch 7 — ruff reformat (#136 fact 2), last

Fact 1 is already fixed by #230: the `[tool.ruff.format]` exclusion is in
`pyproject.toml:148-156`, so `make format-py` no longer breaks
`make check`. Fact 2 is the drift plus the missing gate — **130 files**
would be reformatted as of 2026-08-08, up from 122 in the issue's audit
comment and 109 at filing. Draft PR #229 carries the full reformat and
fails Sonar at `new_coverage 64.9%` and
`new_duplicated_lines_density 3.7%`.

### Do not merge #229 as it stands

Re-checked 2026-08-08 after batch 4, because "BLOCKED" in a PR title is a
claim like any other. It holds — the gate is genuinely red, not stale:

```
$ gh pr checks 229
SonarCloud Code Analysis   fail   ...      # every other check passes
```

| condition | threshold | actual |
|---|---|---|
| `new_coverage` | ≥ 80 | **64.9** |
| `new_duplicated_lines_density` | ≤ 3 | **3.7** |

SonarCloud is a **required** check (#158), so merging this would mean an
admin bypass of a red gate — `enforce_admins` is false, so it is possible,
and it is still the wrong move. Two reasons:

1. **It is superseded by this batch's own plan.** #229 is the single
   130-file reformat; the tranche cut below exists precisely because that
   shape cannot pass. Merging it whole would land the version the plan was
   written to replace, and forfeit the one thing the tranches buy —
   knowing which files are safe.
2. **Its numbers predate batches 1–4** (last analysed 2026-08-06). Those
   batches added tests to several of the below-80% files, so 64.9% is
   stale in the *favourable* direction. Re-measure before deciding
   anything, including whether to close #229 in favour of tranche PRs.

**The drift keeps growing while this waits**, which is the argument
against deferring it forever. Measured on `main` at `38554e1`, after
batch 4:

```
$ ./.venv/bin/ruff format --check src tests | tail -1
136 files would be reformatted, 245 files already formatted
$ ./.venv/bin/ruff format --check src | grep -c '^Would reformat'
70
```

136 files / 70 under `src/`, against the 130 / 69 recorded above the same
day — every batch that adds a file adds to it.

**First move for whoever picks this up**, before writing any code:
`git rebase origin/main` on `fix/136-enforce-ruff-format`, then
`make check DIFF_BASE=origin/main` and read `check-diff-coverage`. That
evaluates the same thing Sonar does (#255), so the current coverage
position is knowable locally without burning a CI run — and the tranche-1
file list should be cut from *that* measurement, not from the 48/21 split
recorded below, which is itself from 2026-08-08.

**Separate PRs do work, but the cut is by file coverage, not by
directory.** Splitting by directory was already tested and cannot help:
`sonar.tests=tests` means the test files never counted toward coverage, so
the `src/` files were always the whole problem. Splitting by coverage is a
different cut, and the numbers are favourable:

- 69 `src/` files need reformatting.
- **48 are already at ≥80% coverage** on `main`. Reformatting those should
  clear the new-code gate, because the lines that become "new" carry their
  file's existing coverage.
- **21 are below 80%** and stay blocked: `lemmatize.py` (22.7%),
  `cli/terms/lemmatize.py` (68.4%), `llm.py` (70.6%), `refs/schema.py`
  (64.1%), `refs/spec.py` (75.9%), `reader/queries.py` (78.7%), the
  `authors/*_works.py` data modules at 0%, and the `corpus/split_*.py`
  scripts.

So:

- **Tranche 1** — the 48 files at or above 80%. Before pushing, run
  `make check DIFF_BASE=origin/main` and read `check-diff-coverage`: it
  evaluates the same thing Sonar does (#255), so the gate can be predicted
  locally without burning a CI run. Watch duplication too — #229 hit 3.7%
  against a 3% threshold and whether a smaller tranche clears it is
  unmeasured.
- **Tranche 2** — the 21 below-80% files, after batches 1–4, which add
  tests to several of them (`lemmatize.py`, `cli/terms/lemmatize.py`,
  `refs/schema.py`). Re-measure before assuming any specific file has
  crossed; batch tests may not lift a 22.7% module to 80%.
- **Residue** — whatever remains below 80% needs the gate decision the
  issue already frames: a Sonar-side exemption, or a visible admin push
  (`enforce_admins` is false). That is not a code problem.
- **The `ruff format --check src tests` gate lands with the final
  tranche.** It cannot be added while any file is unformatted, so #136
  fact 2 does not close until then; earlier tranches carry `Refs #136`.

One caveat to state in the PR: file-level coverage ≥80% is a strong
predictor, not a guarantee. Sonar measures the *changed lines*, and a
well-covered file's reformatted lines could still be its uncovered ones.
`check-diff-coverage` settles it per tranche before pushing.

---

## Batch 8 — PR-gate tooling (#320, #321, #322, #330, #331)

The one row here that is not about the corpus. Batches 1–7 fix Minerva;
this one fixes the harness they are worked with — the three deterministic
checks that had each failed at least once by being forgotten, and that
lived as prose competing for attention with the work itself.

Agreed with the repo owner 2026-08-09 as a round to run *before* resuming
the remaining batches, on the reasoning that a batch worked with a broken
gate has to be re-verified afterwards anyway. **Recorded here 2026-08-11**,
having previously existed only in session memory — which is precisely the
failure this document is for.

| # | what | state |
|---|---|---|
| #320 | whole-corpus invariant audit script | landed as PR #323, commit `7439713` |
| #321 | the `/close-out` command | landed as PR #328 |
| #322 | move the gates into `.claude/` hooks | **todo** — the next thing in this row |
| #330 | `scan_closing_refs` missed a documented closing form | landed as PR #332 |
| #331 | `check-pr-link` reported a false `[missing]` | landed as PR #332 |

### What #330 and #331 turned out to be

Both were found in the whole-branch review of #321's PR, and both are the
same shape one level up from the gate's own subject: **the check's inputs
are not final when it runs.** #331 is the API half — `closingIssuesReferences`
is eventually consistent, so a single read fails a correct PR. #330 is the
text half — the scanner's separator could not see a form GitHub documents.

#330's verdict was `CORRECTED`, twice, and the second correction is the
useful one:

- **In phase 1**, its framing — a hole "exactly the width of one word" —
  understated it. `KEYWORD OWNER/REPOSITORY#N` is documented closing
  syntax and the scanner matched none of it, no experiment required. Its
  proposed fix gated everything on an experiment that merges a throwaway
  PR into `main`, which does not gate the fix at all: `scan_closing_refs`
  feeds the `hazard` check and nothing else, so its error directions cost
  differently and widening is right either way.
- **Mid-implementation**, that asymmetry argument turned out to be half an
  argument. It says over-matching is cheap without ever pricing it. Priced
  across all 760 PR texts in the repo, a one-word filler matches 6 texts
  the shipped scanner does not — **all 6 false positives**, against zero
  real occurrences of the form it was meant to catch. Two shapes are
  endemic: a `Refs` line after a sentence ending in "fixed.", and this
  repo's own `/close-out` command name before a bracketed number. A gate
  that flags the sanctioned non-closing form is a gate people learn to
  override, so the filler was built, measured and removed.

The documented qualifier stayed: **zero** behaviour change across the same
760 texts, so it is purely additive.

The lesson for the rest of this page, which has now happened twice: an
argument about which direction an error should lean is not a measurement,
and this document has a track record of claims made from an issue's title
rather than from the diff. Both #330 corrections came from running the
thing over the whole corpus of PR texts rather than over the examples in
the issue.

### Batch 8-bis — the gate's own blind spots (#333, #334)

Found working the above, in the file it edited.

- **#333** — whether GitHub's *merge-commit* parser acts on
  `KEYWORD <word> #N`. Still unmeasured, deliberately: the answer needs a
  merge into a default branch, and `main` should not carry a junk commit
  for it. Run it in a scratch repo. The PR-body path is backstopped by the
  `unexpected` check; the merge-commit path is backstopped by nothing.
- **#334** — `main()` had no test, so the retry's only real caller was
  unwatched. `scripts/**` is coverage-excluded, so neither
  `check-diff-coverage` nor Sonar had anything to say about it. **Landed as
  PR #336**, which extracted a `GitHubReader` seam and added nine tests.

Neither touches the DB or the coverage gate, so like 5-bis this row is
**unordered** — it can run at any point, including alongside another batch.

#### What #334 got wrong, and the pattern it belongs to

Verdict `CORRECTED`. The defect was real and is now *demonstrated* rather
than argued: mutating the retry's `reads == 1` branch to answer from the
cache forever left all 40 tests passing while a live run printed `read the
link 3x` having issued exactly one query. A gate reporting that it
outwaited a lag it never waited for.

But of the four risks the issue listed as unexercised, the most concrete —
that a `--json` field typo raises `KeyError` and reports
"indistinguishable, in output, from GitHub being down" — **does not
exist**. `gh` validates the field list itself and refuses the call, so the
operator gets the most specific message the tool produces anywhere,
including the correct spelling. No `KeyError` is reachable that way at all.

Taking it at face value, the natural first test pins the `--json` string —
an assertion that a literal equals the literal on the next line. It passes
by construction, fails the day someone legitimately adds a field, and would
have crowded out the one test the mutation proves is needed. The `--json`
list is therefore deliberately **not** asserted, and `GitHubCLI`'s docstring
says why.

That is now three rows on this page whose *diagnosis* needed correcting
while the *defect* held: #262's fix would not have stopped the hang, #330's
fix would have left the documented hole open, and #334 named a risk that
`gh` already covers. In all three the pointer was durable and the
explanation was not — which is the reason the `## Measured` / `##
Hypothesis` split exists, and #334 is the first where the author of the
wrong half was the same session that filed it.

### Batch 8-ter — worked examples cite live numbers (#335)

Found working 8-bis, by a grep for something else.

Four wrong PR/issue numbers across two files: `scripts/check_pr_link.py`'s
usage block claimed `328` closes nothing (it closed two issues) and cited
`330` as a PR (it is an issue), and `Makefile:160-161` carried the identical
pair. PR #332 fixed the first pair and did not grep for duplicates, so the
second pair survived it. A third instance of the same confusion — `PR #320`
for what is PR #323 — was in this document.

Nothing in `make check` sees any of it; the numbers are prose to every gate
in the repo. **May resolve as a decision not to gate it**, like #299: the
cheap fix is to stop citing real numbers, which costs the one property that
made the examples worth having — you can paste them and watch them pass,
which is how three of the four errors surfaced.

#### What 8-ter turned out to be — the wrong population

Verdict `CORRECTED`, and the correction is about *which text rots*. Landed as
PR #338, which built `make check-pr-citations`.

All four measured numbers reproduced, and all four were already fixed. The live
question was the issue's own option 2: gate the worked examples. Sweeping the
repo first — the step the issue itself flagged as "unmeasured and worth knowing
first" — showed that option would have been **green on the day it was written**.
Every runnable example was already correct, because an example is
self-correcting: paste it, watch it fail, fix it. That is how three of the
original four were found at all.

The same sweep found issue #297 cited as the pull request that carried #297 and
#300 — in `tests/test_check_pr_link.py`, in a design spec, and in the plan doc
the spec came from. PR #315 is the one. A sentence is never executed by anyone,
so nothing was ever going to catch it, and the gate's first live run found all
three: 60 citations across 201 files.

So the class is not "worked examples cite live numbers". It is **any prose
citation of a live number**, of which the runnable examples are the small,
self-correcting minority. The issue named the population that had the visible
errors rather than the one that retains them.

Two false-positive traps were priced rather than argued, which is the lesson
this page has now recorded three times. Test fixtures at 999000+ are skipped by
rule, because flagging the repo's own sanctioned numbering is how #330's filler
earned its removal. And a sentence *reporting* a wrong citation has to contain
one, so exemptions are hand-written entries with reasons — backticks cannot be
the discriminator (#293) — and a fixed entry must be removed. Exactly one entry
exists: this page's own account of the defect, three paragraphs up.

That makes four rows here whose *diagnosis* needed correcting while the
*defect* held.

### Batch 8-quater — the citation gate's blind spots (#337)

Found building 8-ter, in the globs it had just written.

- **#337** — `check-pr-citations` scans five globs and one direction.
  `src/minerva/refs/rules/quran_cite_fr.py:7` and `.github/dependabot.yml:34`
  both cite a PR and sit outside it, and the mirror-image error — a PR number
  called an issue — is unchecked. Both measure at **zero defects today**, so
  this is hardening, not a bug fix, and the cheap half is widening the globs.

Same shape as 8-bis one level down: the blind spots of a gate, found while
building the gate. Touches neither the DB nor the coverage gate, so this row is
**unordered** and can run at any point.

---

## Verification

Per PR:

```
make check          # after every edit, not only at the end
gh pr view <n> --json closingIssuesReferences \
  --jq '[.closingIssuesReferences[].number]'      # must be non-empty
```

Per batch, the end-to-end check:

1. Re-run #276's uniqueness audit — the 2 ties resolve by cosine among the
   tied pair, the 121 unique rows unchanged. Force an `LLMError` and
   confirm `backend_errors=1, parse_errors=0`.
2. `minerva terms lemmatize --lang lat --skip-aggregate` at the default
   `--n-process` completes (or warns and falls back) instead of hanging.
   Run an incremental pass twice; the second reports 0 candidates, not 419.
3. Create a `reference_targets` row with no xref, `index --reset`, confirm
   it survives. `refs_scan_state` orphan count is 0 after an index run.
4. `Non occides.` and `Ego et Pater unum sumus.` retrievable by phrase; a
   "Nietzsche" query still free of letter signatures; the granularity gate
   fails on an injected oversized chunk and passes on `main`'s 753.
5. `de_officiis_lat.txt` present and structurally consistent with its
   siblings; scratch-dir diffs for the other 12 reviewed; nothing written
   into `data/`.
6. Both measured queries reach the target passage corpus-wide with only
   the label in the query; `index --reset` does not lose the table.
7. `ruff format --check src tests` exits 0, and `make format-py &&
   make check` both pass.

Before any DB-mutating step in batches 3, 4 (part 2) or 6:
`scripts/snapshot-db.sh <reason>`. For any cleanup running more than one
`UPDATE`/`DELETE`, preview inside `BEGIN; … ROLLBACK;` with verifying
`SELECT`s first. See [MEMORY.md](MEMORY.md) for the operator rules.

### Operator step run 2026-08-09 — batches 2-bis and 3-ter

After `scripts/snapshot-db.sh 284-304-operator`
(`data/snapshots/20260809T142513Z-284-304-operator`), and after PR #306
merged so the repair matched the code that would now produce it.

**2-bis — the 906 stale rows.** Previewed inside `BEGIN; … ROLLBACK;`
first; the rollback restored both counts exactly, then the same statement
was committed.

| | before | after |
|---|---|---|
| `chunk_lemmas` | 26,156,875 | 26,155,969 |
| chunks where `token_count != COUNT(rows)` | 18 | **0** |
| *De Cive* (lat) lemma rows | 66,723 | 65,817 |
| `lemma_counts` | — | rebuilt, 4,575,612 rows in 142.2s |

**A larger defect surfaced while verifying, and it is not this one.** The
preview checked that surviving rows still address text that exists. They
do not: 241,736 rows across 32,842 chunks have `surface_end` past the end
of their own chunk. Sampling 400 chunks per language, `lat` offsets
reproduce the stored text **40.0%** of the time, `grc` 95.2%, and
deu/eng/fra 100%. Filed as #307.

> **Corrected 2026-08-09 while fixing #307 — two claims above were
> wrong, and both were mine.**
>
> **"every one of those chunks has a `text_hash` matching its current
> text — so the offsets were wrong when written rather than stale."**
> The equality is real and the inference from it is not. Every one of
> the 428,606 `chunk_lemma_state` rows carries `lemmatized_at =
> 2026-08-08 20:44:01` — one timestamp, which is migration 0027's
> backfill, not a lemmatize pass. That backfill sets `text_hash =
> text_hash(c.text)` and `token_count = COUNT(*)` from whatever rows
> already existed, so the hash certifies the text as of the migration
> and says nothing about when the offsets were written. Staleness was
> never ruled out — and it is in fact the whole of the largest
> contributor. Hegel's *Philosophy of Right* (eng) supplies 93,504 of
> the 241,736 rows, in a language whose pipeline rewrites nothing: its
> chunk `26a0b85e…` stores 516 characters and carries 6,409 lemma rows
> reaching offset 38,139, and 85.8% of them reproduce against that
> chunk concatenated with its 37 successors. It was one ~39.6 k
> chunk when it was lemmatized, was later split, and the head kept its
> `chunk_id` because that id hashes only `text[:120]` (#285). Those
> rows are #284/#285 residue, not #307. Had the "not staleness" claim
> been trusted, the #307 fix would have been scoped to make the eng
> rows correct and could not have done it.
>
> **"the hypothesis is LatinCy's deliberately-enabled
> `normer/harmonizer/uv_normalizer/remorpher` rewriting the doc."**
> Those four do not rewrite the doc: `normer` assigns `token.norm_`
> (`la_core_web_sm/functions.py:508`) and leaves `token.text` alone.
> The rewriting is in `LatinTokenizer.preprocess()`
> (`functions.py:1052`), which runs before tokenization — ligature
> expansion, macron and combining-mark removal, v→u/j→i, and
> `norm_spacing`, which **collapses every whitespace run to one space**
> and is what actually shifts the bulk of the offsets. It is the
> tokenizer, so it cannot be switched off through `spacy.load(...,
> disable=[...])` at all. The issue's third suggested direction —
> "disable the normalizers and accept worse lemmas" — would have paid
> the measured lemma-quality loss and fixed nothing.
>
> The per-language split of the 241,736 (`chunk_lemmas` joined to
> `chunks`, not sampled): eng 93,504 / lat 89,648 / grc 55,574 / heb
> 2,766 / fra 162 / deu 82. Only the lat share is #307; the rest is
> residue. And the over-run count was never a good measure of #307
> anyway — most wrong lat offsets land *inside* the chunk.

This is worth reading as a process result, not just a bug. #284's
detection query cannot see it — those chunks' `token_count` agrees with
their row count, because the pass wrote a consistent number of rows at
wrong offsets. It was only found because the repair preview asserted
something the issue never claimed.

**3-ter — the rules-hash rescan.**

| | before | after |
|---|---|---|
| authors rescanned | — | **27**, as predicted; 196,460 chunks |
| candidates emitted | — | 30,222 |
| **new `cross_references` rows** | — | **0** |
| `cross_references` | 65,899 | 65,899 |
| markers carrying `rules_hash` | 428,606 | 428,606 (28 distinct) |
| a second `refs build --strategy rules` | — | `scanned 0 chunks` |

**The zero is the result worth keeping.** #287's landing surfaced 158
references the rules already knew how to find and had never emitted,
because the cache had been hiding genuine rule changes. This rescan
emitted 30,222 candidates and inserted none of them: every one deduped
against a row already present. That is the correct outcome and it was the
prediction — no rule's *behaviour* changed here, only what the digest is
computed from — but it is worth having measured, because "the digest now
covers more" and "the digest now finds more" are different claims and
only the first is true.

Every author's stored hash equals a freshly computed
`rules_fingerprint(author)` for all 27; 0 disagree.

### Operator step run 2026-08-09 — batch 2-ter

After `scripts/snapshot-db.sh 307-309-surface-offsets`
(`data/snapshots/20260809T153108Z-307-309-surface-offsets`), and after PR
#310 merged so the pass wrote offsets the fixed code produces.

`minerva terms lemmatize --lang <l> --all` for all seven languages, one
process each, then one `terms aggregate-lemmas`. **`--all` was not
optional**: `chunk_lemma_state.text_hash` matched the current text for
every affected chunk, so an incremental pass would have skipped all of
them. One language per process, because loading LatinCy's
`la_core_web_sm` poisons the spawn payload for every later model in the
same process (#262).

| | before | after |
|---|---|---|
| `chunk_lemmas` | 26,155,969 | 26,005,053 |
| `lemma_counts` | 4,575,612 | 4,527,497 |
| **rows with `surface_end` past their chunk** | **241,736** | **0** |
| `chunk_lemma_state` rows written by a real pass | 0 | 428,606 |

`text[surface_start:surface_end] == surface_form`, 400 chunks per
language:

| lang | before | after |
|---|---|---|
| lat | 27.69% | **100.00%** |
| grc | 95.85% | 99.67% |
| heb | 98.87% | **100.00%** |
| deu / eng / fra | 100% | 100% |
| ara | 81.99% | 81.99% |

Chunks and tokens: lat 67,370 / 4,608,336 · deu 115,078 / 6,185,648 ·
eng 86,300 / 8,715,850 · fra 73,696 / 3,108,629 · grc 56,713 · heb
23,213 / 356,768 · ara 6,236 / 87,478. Wall clock ≈ 50 min end to end,
`lat` about 15 of it.

**The 150,916-row drop is the point, not a loss.** Almost all of it is
#309's residue: rows written against a pre-split, longer text that
survived because `chunk_id` hashes only `text[:120]` and nothing deleted
them. #284's delete-before-insert, landed the day before, is what let a
re-pass reclaim them.

**Neither of the two languages short of 100% is this defect, and both are
explained.**

- **`grc` 99.67% is #311**, filed from this verification. `terms
  lemmatize` feeds the model `NFC(text)` but stores the offsets against
  `chunks.text`, and 16,010 of 56,713 grc chunks are not NFC. Every one
  of the 1,497 mismatching rows reproduces against the NFC form —
  1,497/1,497 — so the accounting is exact rather than approximate.
  Corpus-wide the same defect costs 369 eng rows and 0 deu rows.

  **Corrected 2026-08-09 while working batch 2-quater: 99.67% and
  "1,497" are both this sampling's artifact, and the real numbers are
  much worse.** The 400-chunk-per-language sample is drawn in `ord`
  order, so for `grc` it lands almost entirely outside the affected
  works; and the mismatch it counts is only the subset whose *span*
  moved. Audited over every grc lemma row: 203,219 of 2,942,344 fail
  `text[surface_start:surface_end] == surface_form`, i.e. **93.09%, not
  99.67%** — 1,497 drifted spans plus 201,722 rows where NFC's
  oxia→tonos singleton mapping changes the character without changing
  the length. deu is 19, not 0. Had the sampled figure been trusted,
  2-quater would have been scoped as a 1,866-row cleanup. See batch
  2-quater.
- **`ara` 81.99% is intended behaviour.** Stanza's multi-word-token
  expansion gives a clitic sub-word the parent token's span, because
  `w.start_char` is `None` for the expansion;
  `_tokens_from_stanza_doc` documents the fallback. 234 of 246 sampled
  mismatches share their span with another row, and the other 12 are the
  same thing with the sibling dropped by `is_valid_lemma`. Nothing to
  fix; recorded so the number is not re-investigated.

A second point worth keeping: **`lemmatized_at` is now evidence again.**
Before this pass every one of the 428,606 state rows carried migration
0027's timestamp, which is what made #307's "not staleness" reading
possible. All 428,606 now carry a real pass, so the next time that column
is consulted it means what it says.

### Operator step run 2026-08-09 — batch 2-quater

After `scripts/snapshot-db.sh 311-nfc-offsets`
(`data/snapshots/20260809T204241Z-311-nfc-offsets`), from the #313 branch
so the pass wrote offsets the fixed code produces.

**`--all` was the wrong tool here, and the targeted alternative is worth
keeping.** `chunks.text` never changed, so `chunk_lemma_state.text_hash`
still matched for every affected chunk and an incremental pass would have
skipped all 16,032 — the same trap 2-ter hit. But `--all` re-lemmatizes
258,091 chunks across three languages to repair 16,032. Deleting just
those chunks' state rows makes exactly them candidates, and the
incremental pass then does the rest:

```
non-NFC chunks: 16032
chunk_lemma_state : 428606 -> 412574 (-16032)
chunk_lemmas      : 26005053 -> 26005053 (must be unchanged)
ROLLED BACK (preview)
```

Previewed under `BEGIN … ROLLBACK` with the `chunk_lemmas` count asserted
unchanged — the delete must not cascade — then committed. Then
`minerva terms lemmatize --lang grc|eng|deu --skip-aggregate`, one
process each, then one `terms aggregate-lemmas`. grc 16,010 chunks /
837,850 tokens, eng 5 / 4,818, deu 17 / 4,654; ≈9 min end to end against
2-ter's 50.

| | before | after |
|---|---|---|
| `chunk_lemmas` | 26,005,053 | 26,005,053 |
| `lemma_counts` | 4,527,497 | 4,527,497 |
| rows failing `text[start:end] == surface_form` | 203,610 | **0** |

**Nothing churned, which is the confirmation.** The token counts come
back identical to the row counts the audit found in those same chunks
(grc 837,850, eng 4,818, deu 4,654), and both aggregates are unmoved —
the pipeline saw the same input it saw before, so only the offsets and
the surfaces were rewritten. That is what separates this fix from the one
#311 proposed, which would have moved 4.5% of the grc lemmas.

Whole-population verification, every row rather than 400 per language —
the sampling is what made 2-ter report grc at 99.67%:

| lang | rows | wrong | ok |
|---|---:|---:|---:|
| lat | 4,608,336 | 0 | **100.00%** |
| grc | 2,942,344 | 0 | **100.00%** (was 93.09%) |
| eng | 8,715,850 | 0 | **100.00%** |
| deu | 6,185,648 | 0 | **100.00%** |
| fra | 3,108,629 | 0 | **100.00%** |
| heb | 356,768 | 0 | **100.00%** |
| ara | 87,478 | 15,300 | 82.51% |

**`ara` is the only language short of 100%, and it is not all the MWT
case #311 says it is.** 13,871 of the 15,300 share their span with a
sibling and 1,215 more are that case with the sibling dropped by
`is_valid_lemma` — both intended. The remaining **214 in 210 chunks** are
a third class: the span is right and the stored `surface_form` is
Stanza's rewrite of the word at it. Filed as #314, batch 2-quinquies.

One operational note for the next round: `--n-process 1` was silently
dropped from the `grc` invocation because **zsh does not word-split an
unquoted parameter**, so `$N` holding `"--n-process 1"` reached argparse
as a single token and the language was skipped with
`unrecognized arguments`. It failed loudly and was re-run, but a loop
that built flags in a variable and piped through `tail` also hid the
failure from `set -e`. Write the flags literally.

---

## Batch 9 — reader latency (#339, #340, #342)

Found by timing the two calls a demo would show — loading a text, loading
a syntax diagram — rather than by working any batch above. That is why it
groups with nothing: batches 0–8 are corpus, ingest or harness defects,
and this is the first row where the defect is *how long the product
takes*.

One symptom, three layers. A Reader page load cost **357.9 ms** against
the live 428,606-chunk index, and each issue owns a different reason:

| | |
|---|---|
| #339 | `chunks` had no secondary index, so every page full-scanned it 4–6 times |
| #340 | one global `corpus_lock` serialized the reads, and held across the Stanza parse |
| #342 | the Reader is a `<Switch>` branch, so every side route unmounts it |

### What landed, in order

- **PR #341** — migration 0029 (`chunks(edition_id, translation_id, ord)`),
  the Stanza parse moved outside `corpus_lock`, and a startup warm-up.
  Page load 511 → 346 ms; first syntax request 4,499 → 248 ms; the
  cross-request stall 1,078 → 36 ms. Carried `Refs`, not `Closes`, on
  both issues — correctly, since both were partial.
- **PR #343** — `readCache`, a module-scope response cache keyed on the
  full request path, so returning from a side route stops refetching.
  Covers all four side routes — three of them after PR #347, which
  removes the syntax overlay from that set entirely. `Refs #342`.
- **#339 part 2** — migration 0030 denormalises `works.id` onto `chunks`.
  This is the one that mattered: the reader path went **172.09 ms →
  0.42 ms** and the end-to-end page load **357.9 ms → 14.5 ms**, measured
  on the live corpus with a server attached.

### The two things this batch got wrong, and they point the same way

Both were corrections to *proposed fixes*, not to measurements — the
pattern CLAUDE.md predicts, and the reason `## Measured` and
`## Hypothesis` are kept apart.

- **#339's ledger for part 2 was short by half, and its cost estimate was
  13x too high.** It accounted 89 ms (two statements) and omitted
  `_default_edition` at 80.4 ms — predicting 0029 would fix it "because
  it filters on edition_id/translation_id", when it filters on
  `work_id`. It also priced the migration at ~107 s; measured, it is
  **~8 s**, because 22.3 s of the stated backfill was the FTS triggers
  firing on an `UPDATE` that touches neither `text` nor `text_norm`.
  Dropping them around the backfill is 4.6x faster and avoids ~83 MB of
  churn.
- **#340's fix 1 was killed by #339's fix.** Thread-local read
  connections were the larger, riskier half of #340. Once part 2 landed,
  concurrency across the Reader's three fetches buys **0.4 ms of a
  14.5 ms page load**. #340's own "Unverified" note predicted exactly
  this; PR #341's body then asserted the opposite ("worth doing after the
  column lands, when the queries are cheap enough that the queueing is
  what's left"), which inverts the relationship. Not built, and #340
  closed on that measurement.

The transferable lesson is the second one: **a deferred fix's value is
not stable while its neighbours are still being fixed.** #340 fix 1 was
worth 2.7 ms when filed and 0.4 ms three PRs later, and nothing would
have re-measured it if the deferral note had been trusted.

### An index that was correctly inert and stopped being so

0029 deliberately omitted `works(title, author)`, and the correction on
#339 explains why: measured at 1.0x, because the statement's cost was the
`SCAN c` on chunks, and "the only access path it genuinely adds is
title-without-author".

**0030 adds it.** Nothing above was wrong — removing the `SCAN c` is what
promotes that access path from unused to load-bearing, and `author` is
optional on the reader route, so every legacy bookmark takes it.
Author-less `resolve work_id`: 73.7 ms before part 2, 31.6 ms with part 2
alone, **0.53 ms** with both. The reasoning in 0029's header is what made
the reversal legible rather than contradictory, which is the argument for
writing the reasoning down and not just the verdict.

### #342 — the route model, landed as PR #347

Frontend only, and the largest design surface of the three: "syntax open"
is now a modifier on the reader route (`#/r/<work>?...&syntax=<chunk>`)
rather than a route kind, so the reader location stays resolved and the
Reader stays mounted under the overlay. The legacy
`#/syntax/<chunk>?work=` hash parses into the new shape; a work-less
`#/syntax/<chunk>` has no reader location to lay a layer over and
resolves to the landing, which is a deliberate narrowing. No CSS changed
— `.syn` was already `position: fixed; inset: 0; z-index: 40`.

Deliberately split from the #339 part-2 PR: that one is a migration plus
one line of view SQL, verifiable against the live corpus; this one shares
none of its files.

**The half nobody had measured was Solid's identity semantics.** Every
field the Reader's window is keyed on is read out of the route, and each
hashchange installs a *new* `Route` object — so `useWorkRange`'s load
effect re-ran on any route change at all and began with `setRange(null)`.
Adding `?syntax=` would have blanked and reloaded the window exactly as
the unmount did, and the fix would have looked like it had done nothing.
Keying the effect on a memo of the four window fields is what makes the
modifier free, and it fixed a live instance of the same bug in passing:
opening a term card (`?term=<id>`) reloaded the whole window.

**#342's `~190 ms` was stale, and #346 is why.** Part 2 denormalised
`chunks.work_id` — the exact filter #342 named as the reason
`occurrence_map` and `references_map` still scanned. Re-measured, the
return trip is ~15–35 ms, not ~190 ms: the range still costs its 20 ms,
but the two companion maps went 81 → ~1 ms and 89 → ~9–53 ms. Same
lesson as #340 fix 1 above, from the other direction — **a number in an
issue decays while its neighbours are being fixed**, and here it decayed
between the issue being filed and the issue being worked, four days. The
figure was also copied into `readCache.ts` and its test, so the
correction had to be made in three places; PR #347 makes all three.

## Batch 9-ter — the other three side routes (#348)

#342 fixed one of four. The syntax overlay became a modifier on the reader
route, so the Reader stayed mounted under it; the concordance, the network
dashboard and the refs browser were left as peer `<Match>` branches of the
same `<Switch>`, and #342 recorded that it had not surveyed whether they
should get the same treatment. #348 is that survey.

**The issue was right about everything it measured, and its framing
understated the count by one.** All three unmount the Reader, reproduced
after PR #347 with the same harness `readerSyntaxLayer.test.tsx` uses:

```
× probe concordance        expected { readerPresent: false } to equal { readerPresent: true }
× probe concordance-lemma  expected { readerPresent: false } to equal { readerPresent: true }
× probe network            expected { readerPresent: false } to equal { readerPresent: true }
× probe refs               expected { readerPresent: false } to equal { readerPresent: true }
```

`concordance-lemma` is a fourth route kind, not a fourth route: `App.tsx:92`
folds it and `concordance` into one `onConcordance()` predicate, so it shares
the branch and needed no separate handling. Worth writing down only because
"three routes" is how the issue names the problem and there are four kinds.

### The decision came from the entry points, not from the routes

#348 refused to name a mechanism until each route's intent was decided, and
the question turns out to be answerable by grep rather than by taste. What
links into each:

| Route | From the Reader | From the nav |
|-------|-----------------|--------------|
| `concordance-lemma` | **yes** — `Reader/index.tsx:389`, the rail's lemma card | yes |
| `concordance` | **yes** — `Reader/index.tsx:400`, the work-concordance link | yes (`ChatRoute.tsx:80`) |
| `network` | none | yes (`ChatRoute.tsx:77`) |
| `refs` | none | yes (`ChatRoute.tsx:73`, `NetworkRoute.tsx:49,74,81`) |

The concordance is the only one you step out to *from a passage*, which is the
shape the syntax overlay has. The other two are arrived at. So the concordance
keeps the Reader alive and the other two release it — and "release it" is what
they already did, which is why half of this batch is a set of tests over
unchanged behaviour.

### Mechanism: a retained location, not a wider route

Both mechanisms #348 offered would have worked. The one not taken —
concordance-as-a-reader-modifier, symmetric with #342 — would have pulled
seven concordance parameters (`scope`, `scopeAuthors`, `scopeWorks`, `case`,
`number`, `surface`, `lang`) onto the reader route and made `ConcordanceRoute`
render from two route shapes, which is duplication the Sonar gate scores
independently of coverage.

What landed instead: the Reader moves out of the `<Switch>` and renders from
`readerWork() ?? retainedWork()`, inside a `display: contents` host carrying
`hidden` + `inert`. `retainedWork` holds the last reader location while
`keepsReaderAlive(route)` is true and drops it everywhere else, so no URL
shape changes at all and a concordance opened cold from the top nav mounts no
hidden Reader. The props the Reader sees do not move across the step-out,
so PR #347's `windowKey` memo — the prerequisite #348 named — sees no reason
to reload, which is what makes the whole thing free.

### The hoist's own hazard, which the tests found and not the design

Keeping a component mounted keeps its listeners mounted, and `inert` is a
focus-and-pointer mechanism that reaches neither `window` nor `document`.
Two misfires, both caught red:

- Escape on `#/concordance/Ware` navigated to `#/`. The Reader's own
  `useEscape` exit handler answered a key that belonged to the concordance,
  and threw the user out to the landing.
- `t` on the concordance committed a translate, from a selection toolbar
  still open behind the page and invisible.

A `suspended` flag gates both. **It gates only those two**, which is #352 —
four more global listeners in the Reader subtree stay armed, and two of them
close the retained term card on any click. That is the state this batch set
out to preserve, so the follow-up is not optional decoration.

The transferable part: *"the component survives the route" is a change to
every listener it owns, not just to its rendering.* #342 made that true for
one overlay and paid for it once (`App.tsx` went `inert` under the syntax
layer). #348 made it true for a whole route class and paid for it twice more.
Nothing enumerates the debt — it is found one failing test at a time, and
#352 exists because the third and fourth payments have not been made yet.

## Batch 9-quater — what the hoist left armed (#352)

Found working 9-ter, in the files it edited, and worked immediately after it
merged. One sentence carries the batch: **making a component survive its route
is a change to every listener it owns**, and #342 → #348 → #352 is that debt
being paid one failing test at a time rather than enumerated once.

### The row above it predicted a decision, and the measurement refused it

9-quater said this "may resolve as a decision rather than a repair, like
#299", on the grounds that "only one of the four loses user state". Both
halves are wrong, and the second is what falsifies the first:

| listener | what it does to a retained Reader | cost |
|---|---|---|
| `useTermCard` → `useClickOutside` | any click on the concordance dismisses the open term card | user state |
| `PopoverCard` → `useEscape` | Escape destroys the card, which the route change then rebuilds at the sentinel anchor | user state |
| `PopoverCard` → `useDialogFocus` | **every shift-Tab on the concordance is cancelled** and redirected into a `display: none` dialog | keyboard nav, app-wide |
| `PopoverCard` → `usePopoverPosition` | recomputes a correct value from a stored rect | nothing |

Two listeners cost user state, not one, and the third is worse than either:
it breaks shift-Tab on a route the Reader is not even on. With three of four
defective there is no "fix one, leave the rest" to decide between.

### What #352 got wrong, and the shape of the error

Verdict `CORRECTED`. The four listeners are all real, at the exact lines
cited, and grep 1 reproduces exactly — but three *explanations* do not, which
is the split CLAUDE.md predicts: the pointer survives, the diagnosis does not.

- **"`PopoverCard` … used on the concordance itself"** — false, and it was the
  stated reason a context "may be too broad". `PopoverCard`'s only consumers
  are `TermCard` and `ReferenceCard`, both rendered solely from
  `Reader/index.tsx:444,455`. Only `Select` is genuinely shared, and it
  reaches exactly one of the four hooks. Trusting it would have priced the
  context approach as needing subtree discrimination for all four, and pushed
  the work to option 2 — the one the issue itself notes gives "no protection
  against the fifth".
- **Item 3's `getBoundingClientRect()` "all zeros"** — nothing measures.
  `computePopoverPosition(anchor: DOMRect, …)` takes a rect captured at click
  time and reads `window.inner*`; the file contains no
  `getBoundingClientRect` at all. Item 3 is not "corrected on return", it is
  never wrong. The zeroing is real for item 4 (`offsetWidth`/`offsetHeight`),
  which has `|| 240` / `|| 40` fallbacks.
- **"`PopoverCard`'s ungated `useEscape` would win instead"** — nothing wins.
  `useEscape` calls `preventDefault()` and not `stopPropagation()`, and every
  handler is a bubble-phase `window` listener, so one Escape runs both the
  card's dismissal and the concordance's navigation.

### The trap that the third correction sets, and why the test asserts identity

This is the transferable part. Written as the issue framed it — "the
concordance's Escape handler still wins" — the regression test **passes on
the unfixed branch**, because the navigation does happen. So does the
obvious repair, `expect(card).not.toBeNull()`. Measured before the fix:

```
D before esc, card: true
E after esc,  card: true | SAME NODE: false | hash: #/concordance
```

Escape destroys the card; the concordance's own navigation then changes the
route, which re-runs `useTermCard`'s URL-resume effect — `?term=` is still 7,
because `setOpenTermId` early-returns off the reader route (`readerCtrl.ts:237-239`)
and so `close()` never cleared it — and rebuilds the card at the sentinel
anchor, viewport top. Presence: identical. Anchor, fetch and focus: gone.

Vitest says it plainly: `Compared values have no visual difference.` The test
asserts **node identity**, the same way `readerKeepAlive` does for the Reader
itself and for the same reason. A presence assertion here is a green test over
a live bug.

### Mechanism: a scoped context, plus one threaded flag

The scoping is the whole argument for a context over a global flag. The
provider wraps the Reader's keep-alive host only, so `useContext` answers *"am
I inside the suspended subtree?"* and never *"does the app have a suspended
subtree somewhere?"* — the distinction #352 named as the hard part. Everything
in the sibling `<Switch>` reads the default `false` and stays live, including
`useListKeyboardNav`, a fifth `window` keydown binder that the issue's own
grep output omitted and that the concordance depends on for j/k/Escape.

Placement is load-bearing: the provider sits **above** `ReaderRoute`, not
inside the Reader's JSX, because hooks called in the Reader's component body
(`useTermCard`, both `useEscape`s) resolve `useContext` at that point and
would not see a provider nested in the returned tree.

`useClickOutside` is deliberately left out of the context and takes the flag
through the `isActive` accessor it already had. It is the one hook shared with
a surface that must stay live while the Reader is suspended, so keeping it
context-free makes `Select` provably unaffected wherever a future provider
lands.

### What was deliberately not fixed

`usePopoverPosition` is untouched, said out loud rather than by omission —
which is what 9-quater's row asked for, applied to the item that earned it
instead of the item it guessed. Correction 2 shows it recomputes a correct
value from a stored rect, so there is no defect to gate and gating it would
add production code no test can fail on. If a future popover does measure
live, the context is already there to consult.

## Batch 9-quinquies — the popover shell's uneven dismissal (#356)

Found working 9-quater, in the files it edited. One sentence carries the
batch: **an affordance wired per-caller is an affordance the next caller
will not have**, and the shell was already the right owner — it held Escape
and the focus trap the whole time.

### The row above it expected a decision, and the code had already made it

9-quinquies said #356 "may resolve as a comment rather than a listener, like
#299", because "nothing records either way, which is the defect". Nothing
records it is the one claim in the issue that is false in the most direct way
possible: three comments in two files describe the missing listener as
existing behaviour, and one of them claims to defend against it.

| where | what it says | true? |
|---|---|---|
| `ReferenceCard.tsx:16-21` | "Esc / outside-click dismisses" | Esc yes, outside-click no |
| `ReferenceCard.tsx:64-67` | "dismisses the card (Esc / outside click / the close affordance)" | one of three |
| `XrefMarker.tsx:35-41` | "Stop the document-level outside-click handler (registered while a ReferenceCard is open)" | there was no such handler |

Had we trusted it, the comment-only option would have been on the table. It
is not: writing "dismissal by clicking away is deliberately omitted" would
contradict three comments already in the tree, and reconciling all four is
more editing than adding the listener.

### The second correction, and why it raises the severity

The issue's affordance table credits both cards with a close button. Neither
has one in the state a reader is normally in:

```
$ grep -c "button" web/src/components/ReferenceCard.tsx
0
$ grep -rn "close" web/src/components/referencecard.css
$ echo $?
1
```

`TermCard`'s `.termcard-close` is real but sits inside `<Show
when={Boolean(term.error)}>` (`TermCard.tsx:76-86`) — it renders only when the
term fetch failed. So the reference card was not missing one affordance of
three with a button as a fallback; it was missing one of two, and there was no
fallback. Corrected:

| | Escape | click away | re-click anchor | visible close control |
|---|---|---|---|---|
| `TermCard` (loaded) | yes | yes | yes | no |
| `ReferenceCard`, before | yes | **no** | yes | no |
| `ReferenceCard`, after | yes | **yes** | yes | no |

The last column is #358: exposed by this correction, not fixed by this batch.

### Mechanism: the shell owns the listener, the card names its anchor

`PopoverCard` calls `useClickOutside` rooted on the `cardRef` it already
holds, and takes a new required `anchorSelector` prop — `.term-mark` for the
term card, `.xref-pin` for the reference card. Required rather than optional
so a third popover has to answer "what anchors me?" instead of inheriting a
listener that fights its own opener: the mousedown half of the click that
opens a card is, geometrically, a click outside it.

`useTermCard`'s copy is deleted, along with the `suspended` prop #352 threaded
into it. That is the part of the issue's constraint 2 that wanted settling —
it warned the two mechanisms "would then disagree about which hook owns the
gate", and deleting one of them is what stops the disagreement. The gate now
reads `useSuspendedSubtree()` inside `PopoverCard` and folds it into the
`isActive` accessor, so `useClickOutside` itself stays context-free and
`components/Select.tsx` stays provably unaffected — the property
`suspendedSubtree.tsx:26-32` exists to preserve. #352's four suspended-listener
tests pass unchanged.

### The test that had to be watched failing twice

The ignore predicate got its own red. Implemented without it, "leaves the card
open when the click lands on its own anchor" fails:

```
FAIL  tests/PopoverCard.test.tsx > leaves the card open when the click lands on its own anchor
AssertionError: expected "vi.fn()" to not be called at all, but actually been called 1 times
```

`XrefMarker`'s own `e.stopPropagation()` cannot supply that guard, which is
the fourth thing its comment gets wrong and is now #357: it is on a
bubble-phase `click`, and the listener is a capture-phase `mousedown` on
`document`, which runs first.

### The refactor had no guard, so one was built first

Nothing covered the term card's outside-click dismissal end to end — deleting
`useTermCard`'s copy left the affordance entirely absent and every existing
test green. `Reader.test.tsx` gains "clicking away from the open term card
closes it" for that, and it is not vacuous: with `PopoverCard`'s listener
disabled, exactly the three positive tests fail and the four suspended-listener
tests still pass.

```
× calls onClose when a click lands outside the card
× a click away calls onClose
× clicking away from the open term card closes it
Test Files  3 failed | 1 passed (4)
      Tests  3 failed | 38 passed (41)
```

Adding it meant hoisting the three term-card fixtures to module scope: the
trio ran ~40 lines a copy in two tests already, and a third copy is what
failed Sonar's duplication gate on #254.

### What was deliberately not fixed

`PopoverCard`'s `onCardClick` shim stays, as #357 rather than a deletion in
this PR. It is inert — capture-phase listener, different event, no ancestor
handler — but `ReferenceCard.test.tsx:262` asserts it, and whether it is dead
weight or a pre-emptive guard for a backdrop nobody has built is a decision,
not a repair. The same fork #356 itself resolved by measuring.

## Batch 9-sexies — what the shell inherited (#357, #358)

Found working 9-quinquies, in the files it edited. Both are the shell rather
than either card, which is the difference from 9-quinquies: there the defect
was one card missing what the other had, here it is what `PopoverCard` gives
*both* of them. One sentence carries the batch: **a shell that owns an
affordance also owns the claims made about it** — #356 moved dismissal into the
shell, and these are the two things that move became responsible for.

### #357 — confirmed, and firmer than filed

Verdict `CONFIRMED`. The issue argued "no ancestor bubble-phase click handler"
from a grep of four files. Measured across the whole app, there is exactly one
document-level listener in the click family:

```
$ grep -rn 'addEventListener("click"|addEventListener("mousedown"|addEventListener("pointerdown"' web/src | grep -v "\.test\."
web/src/hooks/useClickOutside.tsx:33:    document.addEventListener(eventName, onDoc, capture);
```

All six of its call sites pass `mousedown` or `pointerdown`, and all get
capture phase (`capture = options.capture ?? true`, `useClickOutside.tsx:18`).
So the shim had nothing to stop anywhere in the app — not merely nothing in the
files the issue happened to grep.

The deletion is a real behaviour change even so, and that is what made a red
test possible: an inside click used to be swallowed and now bubbles.

```
FAIL  tests/ReferenceCard.test.tsx > a click inside the card reaches an ancestor handler
AssertionError: expected "vi.fn()" to be called 1 times, but got 0 times
```

The test that asserted the mechanism through a synthetic parent is replaced by
two that assert behaviour: an inside click does not dismiss (containment, which
is what was always doing the work), and an inside click reaches an ancestor
(the deletion, made deliberate rather than incidental).

### #358 — the cheap option was strictly worse than doing nothing

Verdict `CORRECTED`. The defect is real and the issue's own preferred fix is
what landed; what did not survive is its alternative. It offered dropping
`aria-modal="true"` instead of adding a button, on the grounds that "a popover
that does not trap the page is arguably not modal" and that this "costs nothing
visually".

The popovers trap. `PopoverCard` calls `useDialogFocus(cardRef, () => true)`
unconditionally, and the trap is a two-way Tab cycle for as long as the card is
open (`useDialogFocus.tsx:36-53`). #352 exists *because* that trap is real — its
third finding was every shift-Tab on the concordance being redirected into a
`display: none` copy of this dialog. So option B would have removed the
announcement of a trap that stays in place, leaving a keyboard user cycling
inside a card with no visible exit and nothing telling their AT why. It reads
as the cheap resolution and is worse than leaving the issue open.

With the trap established, the WAI-ARIA dialog pattern's recommendation of a
visible close control in the tab sequence applies directly, and #358 is a
repair.

### The instrument that broke, and what it teaches

The issue's evidence was `grep -c "button" web/src/components/ReferenceCard.tsx`
→ `0`. On the branch this batch built on it returns **2** — both hits comments
that **PR #359 added**, documenting the absence of a close button. The count
moved because the file started describing itself.

```
$ grep -c "button" web/src/components/ReferenceCard.tsx
2
$ grep -c "<button" web/src/components/ReferenceCard.tsx
0
$ git show origin/main:web/src/components/ReferenceCard.tsx | grep -c "button"   # pre-#359
0
```

Anyone re-running the issue's own evidence after #359 landed would read `2` as
"a close button was added" — i.e. as *fixed*. The transferable part: **an
evidence command that counts a word rather than a construct can be falsified by
a comment**, and the record-correction half of a previous batch is exactly the
kind of edit that adds comments. `grep -c "<button"` is the form that survives.

### Placement: the corner was not free, and the choice made on that was wrong

Scoping picked "top-right ×, and the pending pill moves down when both show".
That premise was wrong in a way worth recording, because it came from this
work's own phase-1 comment. `.refcard-chip` — the reference-type pill — is
absolutely positioned at `top: 16px; right: 20px` and renders in **every**
state, not just pending (`referencecard.css:59-62`). The element that has to
yield is the always-present chip, and moving it down pushes it into the citation
line it labels.

Built instead: the `×` takes the corner, and the chip and the pending pill both
shift **left** of it, reading as one header row. `.refcard-head`'s
`padding-right` grows 92px → 118px so a long author + work still wraps clear.

### What was deliberately not fixed

`TermCard`'s error-state "Dismiss" button stays, so the load-error state now has
two controls doing the same thing — the shell's `×` and its own. Filed as #361
rather than resolved here: a bare glyph is a weaker affordance than a labelled
button next to an error message, and the error state is where a stuck reader is
most likely to be, so which one goes is a design call.

The four `project/reference-card/*.html` citations are untouched and filed as
#360. #358's case for treating the close control as a decision leaned on that
directory being "a faithful-port design"; it has never been in the repository,
so the naming of a durable replacement is the repo owner's call and not a
correction this PR can make.
## Batch 11 — type-to-filter the concordance pickers (#363)

A directly-requested feature, not a defect found by working a batch. One
sentence carries it: **the Work picker held up to ~964 options in a 320px
scroll list and the only way to narrow it was to scroll.**

### Scope, decided by counting the options

The Concordance has five dropdowns. Two got a filter field and three did not,
and the split is a measurement rather than a preference:

| control | component | options | filter? |
|---|---|---|---|
| Language | local `Dropdown` | 5 | no |
| Sort | local `Dropdown` | 3 | no |
| POS | local `Dropdown` | 10 | no |
| Author | shared `Select` | dozens | **yes** |
| Work | shared `Select` | ~964 corpus-wide | **yes** |

The three short lists are also a *different* component — `FilterBar.tsx:85-125`,
whose trigger is a `<span>` with no `tabindex`. That they cannot be operated
from the keyboard at all is #364, filed rather than folded in.

### `Select`, not `PickerShell`

`Syntax/components/PickerShell.tsx` already does everything asked for —
filter field, wraparound arrows, Enter-commits-the-highlight, `n of N` footer,
13 tests. It was still the wrong host: it is a modal `<dialog>` on `--syn-*`
tokens, and turning an inline filter-bar dropdown into a modal is a change
nobody asked for. Its *lessons* were copied deliberately, above all **"the
field filters; it never accepts"** — an accepted non-existent work title would
enter the URL, look valid, and return an empty concordance.

### The obstacle that made it more than a text input

`Select` indexed everything positionally against `props.options` — `activeIdx`,
`commit(i)`, `optionId(i)`, and the scroll effect's `listboxRef.children[i]`.
A filtered view breaks that correspondence: filtered to Gamma alone, DOM row 0
is `options[2]`, so a click committed `"a"`.

The fix that avoids a parallel index map — which is where this class of bug
actually comes from — is a `view()` memo that returns **`props.options` by
reference** whenever there is nothing to filter. Every index helper reads
`view()`, and for the five non-filterable call sites the two are the same
array, so their behaviour cannot have changed. `selected` is the deliberate
exception: it resolves against the full list, because a filtered-out option is
still the selected one and the trigger has to keep showing it.

### ARIA: the combobox role follows real focus

`aria-activedescendant` is only announced on the element that holds focus, so
leaving `role="combobox"` on the trigger while the field is focused would
announce nothing as the highlight moved — and two elements claiming the role at
once is invalid. While a filterable panel is open the field is the combobox and
the trigger steps down to `role="button"`. A test asserts there is exactly one.

### Matching: fold measured against the live corpus

`logos`, `λογος`, `λόγος` and `ΛΟΓΟΣ` all had to find `λόγος`. Client-side that
is `utils/fold.ts` + `utils/searchFold.ts`; server-side it is a whole-string
`_fold_text` sharing `_fold_initial`'s implementation.

Two things the fold exposed rather than introduced:

- **SQLite's `LOWER()` is ASCII-only.** `q=ΛΟΓΟΣ` matched **0** lemmas before
  and 37 after, so the docstring's "case-insensitive substring filter" was
  false for every non-Latin script in the corpus.
- **`merge_case` groups Greek by folded first character** — #366, and the
  serious find of this batch. Not fixed here: it changes visible counts.

Measured on `data/index.sqlite`, distinct lemmas matched, `count >= 2`:

| | before | after |
|---|---|---|
| grc `q=λογος` | 19 | **37** |
| grc `q=ΛΟΓΟΣ` | **0** | 37 |
| deu `q=grosse` | 2 | **58** |

### No migration, and the measurement that settles it

`EXPLAIN QUERY PLAN` shows the index seek covering
`(lang, scope_kind, scope_value)` with the `LIKE` as a residual filter — so
`q` already scanned its partition before the fold existed, and a leading
wildcard cannot seek an index even on a stored column. A folded column would
therefore buy nothing here while costing a rebuild of a 4,527,497-row
materialized table in an operator window.

The fold's whole cost is a Python callback per row, and memoizing it is what
makes that affordable — the vocabulary is tiny next to the row count. End to
end, against the live index:

| | folded `q` | the page's own unfiltered request |
|---|---|---|
| grc | 100 ms | 269 ms |
| deu | 145 ms | 266 ms |

The search field is debounced 250 ms, and the folded query is roughly twice as
fast as the request the page already issues on every load.

### What was deliberately not done

No debounce and no memoized haystack on the client: folding 964 labels measures
0.607 ms, so both would be complexity bought with nothing. No sort and no
rendered-row cap either — `WorkScopeControl` caps at 60, but capping silently
hides options and sorting would reorder the list for the callers that did not
ask for a filter.

### The redesign, and the two things measuring caught

Shipped first with the filter field **inside the panel**, which the repo owner
rejected on sight: the field should be the select, not a second input below it.
The trigger is now the input — ARIA's combobox pattern — which deleted the
`role="combobox"` handoff between two elements, the focus-on-open effect, and a
seeding branch that existed only because the field did not exist yet when the
first character arrived.

Mobile is the exception, and it is measured rather than cautious.
`styles/mobile.css:1119-1134` makes the panel a full-screen sheet at `z-index:
80` while `.mobile-sheet` is at 71, so below 768px an editable trigger is covered
by its own dropdown. There the trigger stays a button and the field renders at
the top of the sheet.

Two things the tests caught that the plan had got wrong:

- **The integration test did not survive untouched, as predicted.** With the
  trigger as the input, both pickers own a field permanently, so a
  `container`-wide `querySelector(".minerva-select__filter-input")` landed on the
  *author* picker and silently filtered the wrong list. The lookup is now scoped
  to the picker under test.
- **`check-pr-link` reported a defect that did not exist** — #369. Rewriting the
  PR body tripped the hazard check on a sentence putting a closing keyword
  directly against #365's number; after
  fixing the wording, the check still read the stale link and asserted "this is a
  bug in the PR, not in the check." It was not: seconds later the API returned
  `[363]` and the unchanged command passed. The script's premise that only a
  `missing` link is lag-fabricable holds in one direction only.

## Batch 11-ter — the index page's own claims (#370, #371)

Both reported from use rather than found by working a batch, and they group by
kind rather than by file: **each is the page displaying something that is not
what the reader takes it to mean.**

### #370 — a chart that was right and said nothing

`Sparkline` scales each bar against the *row's own* maximum, so the tallest bar
is always 100% at every scope. At work scope `per_work` collapses to one entry
whose `n` equals the row's `count` — measured, every row returns
`distinct_works=1, per_work=[{work, n}]` — so every row drew one identical
filled block. The reader's words: "I thought it was broken, although it's
technically doing its job."

`LbRow`'s `<Show>` already had the right shape, its fallback keeping the 130px
grid track occupied, so the fix was the predicate: at least two works. The count
stays. Landed as PR #372.

The transferable part is *why nobody had noticed*: `aggregate.py` claimed "read
path ignores it when scope_kind='work'" of the degenerate shape it writes. The
read path does not ignore it — one branch passes it through verbatim, the other
sums it. The writer's author believed the shape was inert downstream and the
renderer's author had no reason to check.

### #371 — a list that stopped, next to a total that did not

200 rows hardcoded, no offset ever sent, and the header printing the real total
beside it. The A–Z rail is a filter, not a pager — top 200 *per letter* — and the
narrowest combination the UI offers short of a text query is 1,318 lemmas.

| scope | total lemmas | reachable before |
|---|---|---|
| corpus deu | 135,047 | 200 |
| author Hegel | 19,409 | 200 |
| corpus deu, letter=S | 12,715 | 200 |
| Hegel + letter B | 1,318 | 200 |

**The cursor had to come from the server**, and establishing that is the useful
part. `total_lemmas` cannot drive `hasMore`: it ignores the frequency range, and
on one branch counts `DISTINCT lemma` while rows are per `(lemma, pos)`. Measured
on one work scope, walking to exhaustion:

```
  min_count=1: reachable rows=  6797   total_lemmas=6797
  min_count=2: reachable rows=  3163   total_lemmas=6797   ← the DEFAULT
```

So the default view's total overstates the reachable set 2×, and a
`rows.length < total` pager would have requested pages forever. `next_offset` is
derived from returned rows instead — which is exactly where it departs from the
KWIC endpoint it otherwise mirrors, whose total *does* describe its rows.

### A correction to my own reasoning, mid-implementation

Walking the live index to check pages were disjoint tripped on `('Übergehen',
'NOUN')` appearing twice, and I diagnosed unstable `LIMIT/OFFSET` over a partial
sort order. **Wrong.** Those are two genuinely different groups that render the
same label, because SQLite's `LOWER()` is ASCII-only — now #373.

The sort-order hardening shipped anyway (805 German groups really do tie on the
whole `freq` key and differ only in `pos`, and `LIMIT/OFFSET` over a partial
order has no stability guarantee), but **relabelled as hardening rather than as a
fix for an observed duplicate**, in the code comment and in both test docstrings
that had cited the wrong cause. Worth recording as a pattern: the dedup key was
the *display* string, and a display string is not an identity.

The tie-order tests say out loud that they are a regression net and not a
reproduction — a four-row fixture cannot make SQLite's planner change its mind.
Better a test that admits what it does not prove than one that implies it does.
