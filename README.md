# Minerva

A retrieval-grounded reader and agent over a multilingual corpus of
philosophy, biblical texts, and related primary sources. Chunks are keyed
to scholarly locators; retrieval is BM25 + optional sentence-transformer
embeddings; answers use a citation-strict prompt with pluggable LLM backends
(Anthropic / OpenAI / Ollama).

Corpus metadata (slugs, languages, chat keywords, sidebar order, atlas)
is authored in [`data/authors/manifest.yaml`](data/authors/manifest.yaml)
and generated into `corpus_registry.py`, `author_ordering.py`, and the
Landing atlas (`make generate-authors`).

## Corpus (by era)

| Era | Authors / corpora | Typical sources |
|-----|-------------------|-----------------|
| Foundational / epic | Hebrew Bible (MT), Homer | openscriptures/morphhb (WLC), Perseus TEI |
| Greek tragedy / fable / elegy | Aeschylus, Sophocles, Euripides, Aesop (Babrius), Theognis | Perseus TEI, First1KGreek, el.wikisource, archive.org |
| Pre-Socratics | Presocratic philosophers (Diels) | OCR text |
| Classical | Plato, Aristotle, Lucretius, Cicero, Epictetus, Marcus Aurelius | Perseus, PG, Wikisource |
| Biblical translations | Septuagint, New Testament, Vulgate | First1KGreek, SBLGNT, Clementine Vulgate (BibleGet mirror) |
| Vernacular Bibles | King James, Luther 1545 & 1912, Sacy | gratis-bible/bible |
| Patristic / medieval | Augustine, Origen, Quran, Aquinas | Wikisource, CCEL, Corpus Thomisticum, Tanzil XML |
| Early modern | Descartes, Hobbes, Pascal, Spinoza, Locke, Hume, Rousseau | PG, Wikisource, zeno.org |
| Modern | Kant, Hegel, Schiller, Marx, Nietzsche | zeno.org, local PDFs/EPUBs, PG, eKGWB |
| 18th–19th-c. French | Boulainvilliers, Gobineau, Renan | archive.org / Gallica OCR |

**Adding a new author?** See [`docs/INGESTION.md`](docs/INGESTION.md) for the full
checklist (downloader → splitter → ingest → index → embed → cross-references →
**chat/retrieval integration**). There is no LLM fine-tuning step; after ingest
you must wire `corpus_registry` keywords and run the §14 smoke tests or chat
will miss the new text even when it is in the index. **`minerva serve` defaults
to `--lang any`** (multilingual retrieval); narrow with `--lang deu` etc. only
for experiments.

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/INGESTION.md](docs/INGESTION.md) | Add-an-author checklist |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Routes, DBs, HTTP API |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Fresh-machine setup, `make check` |
| [docs/MEMORY.md](docs/MEMORY.md) | Operator rules (snapshots, re-ingest) |
| [docs/SCRIPTS.md](docs/SCRIPTS.md) | Every script in `scripts/`, workflow vs one-off (generated) |
| [docs/syntax-annotation-plan.md](docs/syntax-annotation-plan.md) | Dependency-syntax reader overlay — design, derivations, known gaps |
| [FigJam — Application Architecture](https://www.figma.com/board/3EXl1NgThKiIs2sBeEKHOz) | Canonical board — corpus, pipeline, stores, API, frontend, refs |
| [FigJam — App Flow + Ingestion](https://www.figma.com/board/9yBqT8fZSPFwcARJrnBy26) | Superseded; user journeys + pipeline diagram |
| [FigJam — Author Ingest Wave](https://www.figma.com/board/uaeZ5hqmEClhmBQf4Gv0xA) | Ingest checklist visual |

## Layout

**In git**

- `src/minerva/` — ingest, store, retrieve, agent, HTTP handlers, CLI
- `web/` — SolidJS + TypeScript frontend (Vite)
- `tests/` — Python backend tests
- `perseus/download_*.py` — corpus fetchers (see `perseus/` for full list)
- `docs/` — architecture, ingestion, contributing guides
- `data/glossary/` — curator YAML for the term glossary

**Gitignored, rebuilt locally**

- `data/index.sqlite`, `data/chunks.jsonl`, embeddings
- `perseus/raw_*/` — fetched TEI/XML/text dumps
- `data/hegel/`, `data/kant/`, etc. — local PDFs/EPUBs/scrapes

**Key modules**

| Module | Role |
|--------|------|
| `data/authors/manifest.yaml` | Author/corpus metadata SSoT (codegen → registry, ordering, atlas) |
| `corpus_registry.py` | Generated corpus slugs, languages, `AUTHOR_KEYWORDS` |
| `ingest/registry.py` / `store/` | Parse → JSONL → SQLite + FTS5 |
| `authors/*_works.py` | Per-author work tables for PDF/EPUB/HTML ingest |
| `retrieve.py` / `embed.py` | Hybrid search |
| `agent/` | Citation-strict prompts + answer composition |
| `http/` (`serve.py` · `router.py` · `handlers/`) | REST API for the SPA |

Download scripts are grouped under `perseus/` — biblical (`download_hebrew_mt.py`,
`download_first1kgreek_lxx.py`, `download_sblgnt_nt.py`, `download_vulgate.py`,
`download_quran.py`), classical Perseus TEI, early modern PG batch, zeno.org
German (Kant, Hegel, Nietzsche, Marx), and Wikisource Latin/French.

## Quickstart

Targets Python **3.13** (`3.13.18` pinned via `.python-version`).
The upper bound (`<3.14` in `pyproject.toml`) is held by the
Ancient Greek / Latin lemmatizer chain — LatinCy's spaCy wheels
(`grc_dep_web_sm`, `la_core_web_sm`) and the Stanza fallback don't
yet publish wheels compatible with 3.14. `pyenv`/`uv` will pick up
the `.python-version` automatically; if neither is wired in, point
the venv at a 3.13 binary directly.
An older `uv` may not know the pinned patch release (uv 0.11.7 stops at
3.13.13; 0.13.9 has 3.13.18) — run `uv self update` if `uv venv` reports
"No download found".

**Corpus data is not in git.** After install, run the downloaders below
(or restore a tarball), then `ingest` / `index`.

```bash
# 1. Create a venv on 3.13 and install
uv venv -p 3.13                             # uv (recommended)
uv pip install -e '.[embed,hegel,lemma]'    # everything; see pyproject.toml
make install-lemma-models                   # model wheels; pinned in lemma-models.txt

npm install -g npm@11.12.1                  # npm pinned in web/package.json (#605)
npm ci --prefix web                         # frontend (make check / make run)

cp .envrc.example .envrc                    # optional — LLM keys; then: direnv allow

# …or with stdlib venv:
~/.pyenv/versions/3.13.18/bin/python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[embed,hegel,lemma]'
.venv/bin/pip install -r lemma-models.txt

# 2. Download the Perseus corpus (first time only)
python3 perseus/download_perseus_plato.py --lang both --skip-existing
python3 perseus/download_perseus_aristotle.py --lang both --skip-existing

# 2b. (optional) Latin originals
python3 perseus/download_spinoza.py            # Ethica + TIE + TP   (Wikisource)
python3 perseus/download_augustine.py          # Conf. + Civ. Dei + Trin.  (Wikisource)
python3 perseus/download_aquinas.py            # Summa Theol. + Summa c. Gent.  (Corpus Thomisticum)

# 3. (optional) Add Hegel English translations to data/hegel/
#    Drop your local PDFs/EPUBs (Pinkard PhG, Wood/Nisbet PR, etc.)
#    and add an entry per file in src/minerva/authors/hegel_works.py.

# 4. (optional) Scrape German originals from zeno.org
python3 perseus/download_hegel_de.py    # ~25 min: PhG, PR, Enz, SoL
python3 perseus/download_kant_de.py     # ~45 min: KrV, KpV, KU, GMS, …
# Both scripts accept `--jobs 2-3` for parallel BFS with per-host rate limiting.

# 5. Build the index
.venv/bin/minerva ingest
.venv/bin/minerva index --reset
.venv/bin/minerva stats

# After the first build, iterate on one source without re-parsing everything:
#   make reingest-only ONLY=plato
# See docs/INGESTION.md §6 (parser-development cycle).

# 6. Ask questions (no LLM = retrieval-only output)
.venv/bin/minerva ask --llm none "Where is the divided line introduced?"
.venv/bin/minerva ask --llm none --corpus hegel "what is Sittlichkeit"
.venv/bin/minerva ask --llm none --corpus kant "synthetic a priori"

# 7. With Anthropic, OpenAI, or local Ollama
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/minerva ask --llm anthropic --llm-model claude-sonnet-5-5 \
    "Compare Aristotle on friendship with Hegel's account of recognition."

# 8. Run the locate-the-passage eval (Plato gold set)
.venv/bin/minerva eval

# 9. Dev UI (API :8000 + Vite :5173)
make run
```

## Optional: enable hybrid (vector + lexical) retrieval

```bash
.venv/bin/pip install -e '.[embed]'
.venv/bin/minerva embed --lang any      # ~15 minutes for the full corpus on CPU
.venv/bin/minerva ask --use-vectors --llm none "..."
```

The default embedding model is `paraphrase-multilingual-MiniLM-L12-v2`,
chosen because the corpus spans Greek, English, German, Latin, French,
Hebrew, and Arabic. Cross-language retrieval surfaces relevant passages
across editions — an English query about *Aufhebung* can pull German
originals alongside English commentary.

## Citation contract

The agent prompt enforces:

1. Use only the passages provided to the model in this turn.
2. Every non-trivial claim ends with `[Author, Work Section]` —
   e.g. `[Plato, Republic 514a]`, `[Hegel, Elements of the Philosophy
   of Right §258]`, `[Kant, Kritik der reinen Vernunft, Einleitung]`,
   `[Augustine, Confessiones VIII.7.16]`, `[Aquinas, ST I, q. 2, a. 3]`.
3. Distinguish paraphrase from interpretation; label interpretation.
4. Abstain if the retrieval scores are below the threshold rather than
   inventing section numbers.

When `--llm none`, the agent skips generation entirely and prints the
top retrieved passages with their locators so you can verify what is
actually in scope.

## Design notes

- **Why retrieval and not training**: faithfulness to specific passages
  is the primary product requirement. RAG keeps the source of truth on
  disk where it can be checked; fine-tuning shifts behavior toward
  format/tone but is not a substitute for grounded citation.
- **Chunk granularity, per author**:
  - Plato/Aristotle — one chunk per section milestone (Stephanus letter
    for Plato, Bekker page+column for Aristotle).
  - Hegel English — `§N` for Philosophy of Right and Encyclopedia,
    `¶N` for Pinkard's Phenomenology, chapter heading + paragraph index
    elsewhere (Inwood's PhG, SoL, Lectures, ETW).
  - Hegel/Kant German — chapter heading derived from each zeno.org
    URL path, then per-paragraph index inside that chapter.
  - Descartes — `Med. I §3` (Meditationes / Méditations / Discours) or
    `Pars I, art. 7` (Principia / Principes). The Principes Parts II–IV
    are OCR'd from Cousin Tome III with paragraph-level approximation;
    article numbering there is sequential within each Partie rather
    than canonical Picot.
  - Spinoza — geometric structure: `E I, Def. 1`, `E I, Ax. 3`,
    `E II, Post. 5`, `E I, P7`, `E I, App.`; TIE numbers paragraphs
    `TIE §17`; TP is `TP III, art. 5`.
  - Augustine — canonical Book.Chapter.Paragraph: `Conf. VIII.7.16`,
    `Trin. IX.4.7`. De civitate Dei is `Civ. Dei XIX.13` — chapter
    is the smallest unit Wikisource carries for that work, so the
    paragraph component is absent there.
  - Aquinas — Summa Theologiae is one chunk per article: section
    `ST I, q. 2, a. 3` (Pars + quaestio + articulus), with the
    article's sub-sections inlined as `[arg. 1] … [s. c.] … [co.] …
    [ad 1] …` labels inside the chunk body so the dialectical
    structure stays visible. Question prooemia are their own chunks
    keyed `ST I, q. 2, pr.`. Summa contra Gentiles is one chunk per
    chapter (`SCG I, cap. 13`), with each `[n. K]` sub-paragraph
    inlined.
  - Biblical / Quran — book:chapter:verse or surah:ayah locators.
- **Bilingual storage**: Greek beta-code is preserved as supplied by
  Perseus; downstream consumers can transliterate to polytonic Unicode.
  German is decoded from zeno's ISO-8859-1 source into UTF-8 at scrape
  time; umlauts and ß round-trip cleanly through the index.
- **Why SQLite**: full-text indexing, vector blobs, and metadata all
  live in one file with no daemon. 427k chunks across 40 corpora are
  well within brute-force cosine in numpy.
- **Request-timing observability**: `#/metrics` shows a per-route
  leaderboard sorted by p95, a trend chart per route, and a sub-span
  breakdown. History lives in its own `data/metrics.sqlite`
  (`--metrics-db`), deliberately separate from the corpus index —
  `minerva index --reset` unlinks the index file outright, and a
  `--reset` re-index is exactly the event this history exists to
  bracket, so storing it there would erase it silently (the same
  reasoning `--conversations-db` uses for chat history). `--no-metrics`
  turns persistence off while leaving the in-memory recent-request ring
  on. Percentiles are estimated from log-scale histogram buckets, so a
  p95 carries up to one bucket-width of error, while `sum_ms`/`count`
  are exact — the mean is the precise trend signal, the p95 the
  tail-shape signal. For the streaming route (`chat`) both `total` and
  time-to-first-event are recorded; `/api/translate` is an ordinary JSON
  POST and has no TTFE. `llm_call` sub-span counts are per attempt, not
  per request, because the LLM client retries and each attempt is a real
  round-trip — and the span currently closes when the LLM's response
  *headers* arrive, not when its body has been consumed, so on the
  streaming chat route it reads as time-to-headers and accounts for far
  less of `total` than the call really costs.

## Licensing

The corpus spans three licensing regimes; they don't all share posture:

- **Perseus TEI bundles** ship with a `<publicationStmt>` clause; current
  Plato/Aristotle volumes allow free non-commercial distribution with
  attribution. Read each bundle's TEI header before redistributing.
- **Hegel German originals** (PhG 1807, PR 1820, Enz 1830, SoL 1812-32)
  and **Kant German originals** are public domain (both authors died
  pre-1900); zeno.org carries them under standard PD terms.
- **Augustine Latin originals** (4th–5th c.) are unambiguously public
  domain; la.wikisource.org carries them under standard PD terms.
  The transcriptions are sourced from thelatinlibrary.com for the
  Confessions and from Migne's *Patrologia Latina* for De Trinitate.
- **Aquinas Latin originals** (13th c.) are unambiguously public
  domain. The Corpus Thomisticum edition is the Leonine text
  (Vatican 1882–) recognized by Roberto Busa SJ and curated by
  Enrique Alarcón at the University of Navarra; it is freely
  available for personal study. Re-distribution of the resulting
  index falls under the standard PD posture for the underlying text;
  retain attribution to Corpus Thomisticum in any derived dataset.
- **Modern English translations of Hegel** (Pinkard, Wood/Nisbet,
  Brinkmann/Dahlstrom, Di Giovanni, Inwood, Knox, etc.) are under
  publisher copyright. Indexing personal copies for local research
  use is widely treated as fair-use-adjacent; redistributing the
  resulting `data/index.sqlite` or hosting a public chat over it is
  a different matter.

If you publish a derivative dataset or expose `minerva serve` beyond
`127.0.0.1`, the second and third points are operationally yours to
negotiate.

## Status

- Multi-source ingest CLI: done (Perseus TEI + local PDF/EPUB + zeno HTML).
- Hybrid BM25 + vector retrieval with neighbor expansion: done.
- Agent CLI with cite-required prompt + pluggable LLM backends
  (Anthropic, OpenAI, Ollama, null): done.
- HTTP server + SolidJS frontend: done (`minerva serve --static web/dist`).
- Gold QA / locator eval and scorer: done. Baseline (BM25 only,
  English Plato) is **work recall 0.933, section recall 0.733,
  section MRR 0.579** on 30 questions (`minerva eval`, re-measured
  2026-09-07; the figures this line carried until then dated from the
  initial commit and no longer reproduce — see #526).
- LoRA / format fine-tuning: **deferred by design**. The retrieval
  baseline passes the gating threshold; fine-tuning remains a follow-up
  only if format/tone defects show up that cannot be fixed by prompting.
