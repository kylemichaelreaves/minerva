"""Tests for the baseline-pinned chunk-granularity gate (#176 part 1).

The gate's whole difficulty is that it has to land on a corpus that already
violates it 753 times, so the tests that matter are the pair: it passes on
the recorded baseline, and it fails on anything the baseline does not
already excuse.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import chunk_granularity as cg  # noqa: E402


@pytest.fixture
def manifest() -> dict:
    return {
        "granularity": {
            "max_chunk_chars": 8000,
            "max_mean_chunk_chars": 3000,
            "tolerance_pct": 5,
            "known_coarse": {
                # The parser-failure case: an entire play in one chunk.
                "Aeschylus|Agamemnon|eng": {"max": 82256, "mean": 82256},
                # The real-structural-level case, out of scope for #176.
                "Aquinas|In libros Physicorum|lat": {"max": 34120, "mean": 10861},
            },
        }
    }


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Minimal edition/translation shape, because `measure` joins through
    both — the real schema puts exactly one of them on every chunk."""

    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE works (id INTEGER PRIMARY KEY, author TEXT, title TEXT,
                            citation_system TEXT DEFAULT 'paragraph');
        CREATE TABLE editions (id INTEGER PRIMARY KEY, work_id INTEGER);
        CREATE TABLE translations (id INTEGER PRIMARY KEY, work_id INTEGER);
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            edition_id INTEGER,
            translation_id INTEGER,
            lang TEXT,
            text TEXT
        );
        """
    )
    return c


def _add_work(
    conn: sqlite3.Connection,
    work_id: int,
    author: str,
    title: str,
    *,
    lang: str,
    lengths: list[int],
    as_translation: bool = False,
    citation_system: str = "paragraph",
) -> None:
    conn.execute(
        "INSERT INTO works VALUES (?, ?, ?, ?)", (work_id, author, title, citation_system)
    )
    table = "translations" if as_translation else "editions"
    conn.execute(f"INSERT INTO {table} VALUES (?, ?)", (work_id, work_id))
    for i, n in enumerate(lengths):
        conn.execute(
            "INSERT INTO chunks VALUES (?, ?, ?, ?, ?)",
            (
                f"{work_id}-{lang}-{i}",
                None if as_translation else work_id,
                work_id if as_translation else None,
                lang,
                "x" * n,
            ),
        )


# ---------- measure ----------


def test_measure_records_only_pairs_over_a_threshold(conn, manifest):
    _add_work(conn, 1, "Aeschylus", "Agamemnon", lang="eng", lengths=[82256])
    _add_work(conn, 2, "Plato", "Politeia", lang="eng", lengths=[400, 500, 600])
    got = cg.measure(conn, cg.granularity_policy(manifest))
    assert set(got) == {"Aeschylus|Agamemnon|eng"}
    assert got["Aeschylus|Agamemnon|eng"] == {"chunks": 1, "max": 82256, "mean": 82256}


def test_measure_catches_a_uniformly_coarse_work_under_the_max(conn, manifest):
    """The mean threshold is not redundant with the max. Epictetus's English
    *Discourses* averages 6,744 characters across 85 chunks — coarse enough
    that a passage query competes whole chapters against paragraph-sized
    chunks — and a max-only gate would miss the same shape at 7,999."""

    _add_work(conn, 1, "Epictetus", "Discourses", lang="eng", lengths=[7000] * 5)
    got = cg.measure(conn, cg.granularity_policy(manifest))
    assert got["Epictetus|Discourses|eng"]["mean"] == 7000
    assert got["Epictetus|Discourses|eng"]["max"] < 8000


def test_measure_separates_languages_of_one_work(conn, manifest):
    """Epictetus is in the index twice, chunked at section level in Greek and
    chapter level in English on the same content — a 32x asymmetry that a
    work-level key would average away."""

    _add_work(conn, 1, "Epictetus", "Discourses", lang="eng", lengths=[20000])
    conn.execute("INSERT INTO editions VALUES (99, 1)")
    for i in range(4):
        conn.execute(
            "INSERT INTO chunks VALUES (?, 99, NULL, 'grc', ?)",
            (f"grc-{i}", "x" * 174),
        )
    got = cg.measure(conn, cg.granularity_policy(manifest))
    assert "Epictetus|Discourses|eng" in got
    assert "Epictetus|Discourses|grc" not in got


def test_measure_reaches_chunks_on_the_translation_side(conn, manifest):
    """`chunks` carries the work through exactly one of `edition_id` or
    `translation_id`; a measurement joining only editions would report a
    translated work as having no chunks at all."""

    _add_work(
        conn, 1, "Hegel", "Encyclopaedia", lang="eng", lengths=[66265], as_translation=True
    )
    got = cg.measure(conn, cg.granularity_policy(manifest))
    assert got["Hegel|Encyclopaedia|eng"]["max"] == 66265


# ---------- validate_snapshot: the gate ----------


def test_recorded_baseline_passes(manifest):
    """The landability requirement. A bare threshold assertion fails on all
    753 existing oversized chunks and cannot be merged (#229)."""

    snapshot = {
        "Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 82256, "mean": 82256},
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
    }
    assert cg.validate_snapshot(snapshot, manifest) == []


def test_new_violation_fails(manifest):
    snapshot = {
        "Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 82256, "mean": 82256},
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
        "Plato|Politeia|eng": {"chunks": 2, "max": 40000, "mean": 20000},
    }
    errs = cg.validate_snapshot(snapshot, manifest)
    assert len(errs) == 1
    assert "Plato|Politeia|eng" in errs[0]
    assert "not in granularity.known_coarse" in errs[0]


def test_regression_on_a_listed_pair_fails(manifest):
    """Being on the baseline excuses the coarseness measured when it was
    reviewed, not any coarseness whatsoever."""

    snapshot = {
        "Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 200000, "mean": 200000},
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
    }
    errs = cg.validate_snapshot(snapshot, manifest)
    assert any("chunking regressed" in e for e in errs)


def test_small_drift_inside_the_tolerance_passes(manifest):
    """A gate that fails when a mean moves by one character gets switched
    off. 82,256 + 4.9% is still the same reviewed defect."""

    snapshot = {
        "Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 86000, "mean": 86000},
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
    }
    assert cg.validate_snapshot(snapshot, manifest) == []


def test_stale_baseline_entry_fails(manifest):
    """Once a work is re-chunked (#176 part 2) its entry must come out, or
    the allowlist only ever grows — the rot `SKIP_RULES` avoids by the same
    meta-check (#70)."""

    snapshot = {
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
    }
    errs = cg.validate_snapshot(snapshot, manifest)
    assert len(errs) == 1
    assert "stale baseline entry" in errs[0]
    assert "Aeschylus|Agamemnon|eng" in errs[0]


def test_missing_granularity_block_falls_back_to_defaults():
    """A manifest predating this gate must still validate rather than
    crash — but with no `known_coarse`, everything measured is a
    violation, which is the honest reading of an absent baseline."""

    policy = cg.granularity_policy({})
    assert policy.max_chunk_chars == cg.DEFAULT_MAX_CHUNK_CHARS
    assert policy.max_mean_chunk_chars == cg.DEFAULT_MAX_MEAN_CHUNK_CHARS
    assert policy.known_coarse == {}
    errs = cg.validate_snapshot({"A|T|eng": {"chunks": 1, "max": 9999, "mean": 9999}}, {})
    assert len(errs) == 1


def test_malformed_known_coarse_entries_are_ignored():
    manifest = {"granularity": {"known_coarse": {"A|T|eng": "not-a-mapping", "B|U|eng": {}}}}
    assert cg.granularity_policy(manifest).known_coarse == {}


def test_zero_tolerance_is_honoured_not_treated_as_missing():
    """`tolerance_pct: 0` is a real choice — pin the baseline exactly. A
    falsy-check would silently substitute the 5% default."""

    manifest = {
        "granularity": {
            "tolerance_pct": 0,
            "known_coarse": {"A|T|eng": {"max": 10000}},
        }
    }
    policy = cg.granularity_policy(manifest)
    assert policy.tolerance_pct == 0.0
    assert policy.ceiling("A|T|eng", "max", 8000) == 10000
    errs = cg.validate_snapshot({"A|T|eng": {"chunks": 1, "max": 10001}}, manifest)
    assert any("chunking regressed" in e for e in errs)


def test_ceiling_falls_back_to_the_threshold_for_unlisted_pairs(manifest):
    policy = cg.granularity_policy(manifest)
    assert policy.ceiling("Nobody|Nothing|eng", "max", 8000) == 8000


def test_missing_field_on_a_listed_pair_is_skipped_not_crashed(manifest):
    """A hand-edited baseline may carry only the dimension that was the
    problem, and a snapshot key may lack it too."""

    snapshot = {
        "Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 82256},
        "Aquinas|In libros Physicorum|lat": {"chunks": 121, "max": 34120, "mean": 10861},
    }
    assert cg.validate_snapshot(snapshot, manifest) == []


# ---------- drift: the committed file cannot fossilise ----------


def test_snapshot_drift_reports_a_stale_committed_file(conn, manifest):
    _add_work(conn, 1, "Aeschylus", "Agamemnon", lang="eng", lengths=[82256])
    stale = {"Aeschylus|Agamemnon|eng": {"chunks": 1, "max": 40000, "mean": 40000}}
    errs = cg.snapshot_drift(conn, manifest, stale)
    assert len(errs) == 1
    assert "run `make generate-authors`" in errs[0]


def test_snapshot_drift_reports_a_pair_absent_from_the_snapshot(conn, manifest):
    _add_work(conn, 1, "Aeschylus", "Agamemnon", lang="eng", lengths=[82256])
    errs = cg.snapshot_drift(conn, manifest, {})
    assert len(errs) == 1
    assert "snapshot says absent" in errs[0]


def test_snapshot_drift_reports_a_pair_absent_from_the_db(conn, manifest):
    """The other direction, which the count-band drift check misses: a work
    that has been re-chunked or removed leaves an entry behind."""

    errs = cg.snapshot_drift(
        conn, manifest, {"Gone|Work|eng": {"chunks": 1, "max": 9000, "mean": 9000}}
    )
    assert len(errs) == 1
    assert "DB has absent" in errs[0]


def test_snapshot_drift_silent_when_fresh(conn, manifest):
    _add_work(conn, 1, "Aeschylus", "Agamemnon", lang="eng", lengths=[82256])
    fresh = cg.build_snapshot(conn, manifest)
    assert cg.snapshot_drift(conn, manifest, fresh) == []


# ---------- snapshot round-trip ----------


def test_snapshot_round_trips_through_disk(tmp_path: Path, conn, manifest):
    _add_work(conn, 1, "Aeschylus", "Agamemnon", lang="eng", lengths=[82256])
    snapshot = cg.build_snapshot(conn, manifest)
    path = tmp_path / "chunk_granularity.json"
    cg.write_snapshot(snapshot, path)
    assert cg.load_snapshot(path) == snapshot
    payload = json.loads(path.read_text())
    assert "_comment" in payload  # the do-not-hand-edit warning
    assert list(payload["pairs"]) == sorted(payload["pairs"])


def test_load_snapshot_tolerates_an_empty_pairs_map(tmp_path: Path):
    """What the file looks like once #176 part 2 has re-chunked everything:
    no offenders left. It must load as empty, not raise."""

    path = tmp_path / "g.json"
    path.write_text(json.dumps({"_comment": "x"}))
    assert cg.load_snapshot(path) == {}


def test_make_key_is_the_natural_key_not_a_surrogate_id():
    """`works.id` is reassigned by every `index --reset` (#193), so a
    snapshot keyed on it would silently point at other works."""

    assert cg.make_key("Aeschylus", "Agamemnon", "eng") == "Aeschylus|Agamemnon|eng"


# ---------- the committed files, exactly as CI reads them ----------


def test_committed_snapshot_satisfies_the_committed_baseline():
    """This is the CI check itself, run with no DB.

    It fails if `make generate-authors` wrote a newly-coarse work into
    data/authors/chunk_granularity.json and nobody added it to
    `granularity.known_coarse` — which is the review step the gate exists
    to force. It also fails if a re-chunk left a stale baseline entry.
    """

    from chunk_count_validation import load_manifest

    assert cg.validate_snapshot(cg.load_snapshot(), load_manifest()) == []


def test_check_author_ingest_wires_in_the_granularity_gate(tmp_path: Path):
    """The gate is worthless unless `main` calls it. Loaded the same way
    `test_check_author_ingest_imports_chunk_validation` does, then driven
    with no DB — the CI shape."""

    import importlib.util

    path = SCRIPTS / "check_author_ingest.py"
    spec = importlib.util.spec_from_file_location("check_author_ingest_gran", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from chunk_count_validation import load_manifest

    assert mod._granularity_errors(None, load_manifest()) == []

    # A snapshot carrying an unreviewed pair must fail, and the failure
    # must reach `main`'s exit status rather than only being printed.
    bad = tmp_path / "chunk_granularity.json"
    cg.write_snapshot({"Nobody|Nothing|eng": {"chunks": 1, "max": 99999, "mean": 99999}}, bad)
    real = cg.SNAPSHOT_PATH
    try:
        cg.SNAPSHOT_PATH = bad
        errs = mod._granularity_errors(None, load_manifest())
    finally:
        cg.SNAPSHOT_PATH = real
    assert errs and "Nobody|Nothing|eng" in errs[0]


def test_granularity_errors_demands_a_snapshot_rather_than_passing_silently():
    """The #157 failure mode: a missing file must be an error, never a
    silent skip that is indistinguishable from a passing check."""

    import importlib.util

    path = SCRIPTS / "check_author_ingest.py"
    spec = importlib.util.spec_from_file_location("check_author_ingest_missing", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    real = cg.SNAPSHOT_PATH
    try:
        cg.SNAPSHOT_PATH = Path("/nonexistent/chunk_granularity.json")
        errs = mod._granularity_errors(None, {})
    finally:
        cg.SNAPSHOT_PATH = real
    assert len(errs) == 1
    assert "no granularity snapshot" in errs[0]


# ---------- the fineness floor (#404) ----------


def test_measure_records_a_pair_whose_mean_is_under_the_floor(conn, manifest):
    """Every threshold in the block was a ceiling, so a work could
    fragment without limit and pass. Babrius eng sat at a 44-character
    median across 2,139 chunks and never appeared (#404)."""

    _add_work(conn, 1, "Kant", "Über den Gemeinspruch", lang="deu", lengths=[13, 91])
    _add_work(conn, 2, "Plato", "Politeia", lang="eng", lengths=[400, 500, 600])
    got = cg.measure(conn, cg.granularity_policy(manifest))
    assert "Kant|Über den Gemeinspruch|deu" in got
    assert "Plato|Politeia|eng" not in got


def test_verse_addressed_works_are_exempt_from_the_floor(conn, manifest):
    """A Quran sura is one āyah per chunk at a 26-character mean, and
    that is correct. `retrieve.py` already exempts verse-addressed works
    from its own length floor on `works.citation_system`; reusing the
    same signal means a new scripture edition is exempt the day it is
    ingested, with no second list to remember (#268)."""

    _add_work(conn, 1, "Quran", "An-Nas", lang="ara", lengths=[26, 27, 25],
              citation_system="surah_ayah")
    _add_work(conn, 2, "Bible", "Genesis", lang="heb", lengths=[30, 28], citation_system="bcv")
    assert cg.measure(conn, cg.granularity_policy(manifest)) == {}


def test_a_too_fine_pair_not_in_the_baseline_fails(manifest):
    manifest["granularity"]["known_coarse"] = {}
    snapshot = {"Kant|Über den Gemeinspruch|deu": {"chunks": 2, "max": 91, "mean": 52}}
    errs = cg.validate_snapshot(snapshot, manifest)
    assert len(errs) == 1
    assert "below" in errs[0]
    assert "known_fine" in errs[0]


def test_a_too_fine_pair_in_the_baseline_passes(manifest):
    manifest["granularity"]["known_coarse"] = {}
    manifest["granularity"]["known_fine"] = {
        "Kant|Über den Gemeinspruch|deu": {"mean": 52},
    }
    snapshot = {"Kant|Über den Gemeinspruch|deu": {"chunks": 2, "max": 91, "mean": 52}}
    assert cg.validate_snapshot(snapshot, manifest) == []


def test_a_stale_known_fine_entry_fails(manifest):
    """Same meta-check the coarse side has: a baseline that only ever
    grows stops being read. Re-chunking a work must force its removal."""

    manifest["granularity"]["known_coarse"] = {}
    manifest["granularity"]["known_fine"] = {"Kant|Über den Gemeinspruch|deu": {"mean": 52}}
    errs = cg.validate_snapshot({}, manifest)
    assert len(errs) == 1
    assert "stale" in errs[0]
