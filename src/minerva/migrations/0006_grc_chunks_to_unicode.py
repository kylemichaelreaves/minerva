"""0006_grc_chunks_to_unicode.py — fold Perseus beta-code Greek chunks
into polytonic Unicode in-place.

Perseus's TEI bundles ship Greek as beta-code (ASCII transliteration:
``pa=sa te/xnh kai\\ pa=sa me/qodos``). The First1KGreek bundles ship
already-NFC polytonic Unicode (``πᾶσα τέχνη καὶ πᾶσα μέθοδος``). The
mixed storage was fine while the reader was the only consumer — the
HTTP handler transliterated on the way out (see
``minerva.transliterate.display_text``).

Once term occurrences arrived (migration 0001 onwards), the
transliterate-on-egress shim became load-bearing in a way it wasn't
designed for: term_occurrences records ``source_start`` /
``source_end`` byte offsets into the chunk text. Recording offsets
against the beta-code stored form, while the UI sees the
transliterated form, misaligns highlights. The clean fix is to make
the stored form match what the UI displays — convert beta-code Greek
to Unicode once, server-side, here.

Effects of this migration
-------------------------
* Every chunk with ``lang='grc'`` whose text carries beta-code marker
  characters (``*()/\\=|+``) is rewritten to NFC polytonic Unicode.
* chunk_id is NOT recomputed — it's the canonical row identity used
  by every FK (term_occurrences, occurrence_renderings, embeddings).
  chunk_id's blake2b recipe (see ``minerva.tei._make_chunk_id``)
  derives from text[:120] at INGEST time; once a row exists its id
  is opaque.
* chunks_fts is refreshed automatically via the existing
  ``chunks_au`` UPDATE trigger (see ``store.SCHEMA``).
* Embeddings are NOT recomputed. Cross-lingual embedders mostly
  treated beta-code as gibberish anyway; re-embedding is a separate
  ``minerva embed`` step the operator can run when they care about
  vector search hits on Greek.

After this runs the runtime ``display_text`` shim is a no-op for the
migrated rows (no beta-code markers left to detect). It stays in
place as a safety net for any future ingest that lands beta-code data
before the next migration takes its turn.
"""

from __future__ import annotations

import sqlite3

# Absolute import: migration modules are loaded via
# importlib.util.spec_from_file_location (see migrations/__init__.py),
# not through the package's normal import path. Relative imports
# raise here because the module's `__package__` is unset.
from minerva.transliterate import betacode_to_unicode, looks_like_betacode


def apply(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT chunk_id, text FROM chunks WHERE lang = 'grc'"
    ).fetchall()
    updated = 0
    for chunk_id, text in rows:
        if not text or not looks_like_betacode(text):
            continue
        new_text = betacode_to_unicode(text)
        if new_text == text:
            continue
        conn.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = ?",
            (new_text, chunk_id),
        )
        updated += 1
    # The runner prints rows ran but not their internal effects. A
    # one-line report makes the size of the in-place rewrite visible
    # in operator logs.
    if updated:
        print(f"0006: rewrote {updated} grc chunks from beta-code to polytonic Unicode")
