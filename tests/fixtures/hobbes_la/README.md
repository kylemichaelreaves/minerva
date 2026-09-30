# `molesworth_sample.txt`

An 80-line excerpt in the shape of the Internet Archive OCR of
Molesworth's 1839 *Opera Latina*, which is what
`src/minerva/sources/hobbes_la.py` parses. Every line shape in it is
taken from the real `leviathan_lat.txt`; the chapters are renumbered and
shortened so the whole file fits on a screen.

## Why it exists

`data/*` is gitignored, so `data/hobbes/raw_lat/*.txt` is not in any
checkout but a developer's. Tests gated on those files **skip silently in
CI**, and the gap is invisible locally because the files are always
there. Measured on PR #573: coverage of `hobbes_la.py` read **97%** on a
machine holding the corpus and **63%** in CI, and SonarCloud failed the
PR on it.

This is the second time the repo has hit exactly this. `../README.md`
records the first: the e2e suite ran against `data/index.sqlite`, "every
data-dependent assertion skipped itself there and only ever executed on
a developer's machine — where three of them had been failing against a
renamed corpus for some time before anyone noticed (#133)".

## What it exercises, and why each piece is there

| shape | in the fixture | what would break without it |
|---|---|---|
| `CAPUT <roman>.` heading | Caput I, II, III | nothing — the easy case |
| `CAPUT. <roman>.` with a stray period | `CAPUT.  V.` | De Cive's Caput XIV is absorbed into XIII |
| chapter with **no heading at all** | Caput IV | its paragraphs are silently mislabelled as Caput III's — worse than missing, because a mislabelled chapter reads as correct |
| marginal `cap. <roman>.` run into a line head | `cap.  i.  contrapressio` | the marker becomes the first word of a paragraph |
| …and into a line tail | `deinde  cap.  i.` | same, at the end |
| the same string **mid-line**, as a body citation | `(cap. i. et ii.)`, `1 Cor. ix. 9`, `Deut. xxv. 4`, `Prov. ix. 10` | an unanchored stripper deletes scripture references — the highest-consequence rule in the parser |
| page running head, both flanks | `6  DE  HOMINE.`, `DE  HOMINE.  15` | running heads land in the middle of paragraphs |
| printer's signature | `VOL.  III.  D` | same |
| orphaned marginal gloss beside a page break | `Deimagmauone.`, `De sermone.` | gloss debris is spliced into a paragraph that spans the break |
| paragraph continuing across a page break | Caput I ¶3 into the next page | one paragraph becomes two, cut at the page edge |
| hyphenated word split across lines | `acci-` / `dentis`, `ob-` / `jectum` | `acci- dentis` instead of `accidentis` |

Caput IV is the load-bearing one. It has no heading and two `cap. iv.`
marginal markers, which is exactly the shape of the real Leviathan's
Caput XXXV — the one chapter of forty-seven whose heading and title both
failed to survive the scan.

## Maintaining it

It is hand-written, not generated, so nothing regenerates it. If the
parser gains a rule, add the line shape that rule exists for and a row
above saying what breaks without it. Keep it short: the point is that
every rule has a cheap, CI-visible witness, not corpus coverage.

# `appendix_sample.txt`

Real lines from the *Appendix ad Leviathan* (#575), trimmed: the UofT scan
of vol. III, after `scripts/clean-hobbes-latin.py`. It exists for the two
rules only that work uses.

| shape | in the fixture | what would break without it |
|---|---|---|
| running head with an OCR-mangled page number | `APPENDIX  AD  LEVIATHAN.  53/`, `…  5a3` | the head lands mid-paragraph |
| …splitting a hyphenated word | `exerce-` / head / `rent` | `exerce- APPENDIX … rent` |
| chapter title over `_RUNNING_HEAD_RE`'s width | `DE  QUIBUSDAM  OBJECTIONIBUS  CONTRA  LEVIATHAN.` | nothing today (the floor drops it), but it is the rule's widest real hit |
| short dialogue turns | `A.  Quid  est  secta  ?`, `B.  Ita  est.` | dropped by the 80-char floor, leaving answers without questions |
| …isolated beside a page break | `A.  Quid  est  secta  ?` before `540  APPENDIX …` | blanked as a margin orphan before the floor is even reached |
| short non-turn line | `DB  HiERRSI.` | must still be dropped, and must not break the carry |
