"""`minerva serve` must survive a bad `data/metrics.sqlite`.

`metrics.open_db` was called unguarded, so a truncated or non-SQLite file
raised `sqlite3.DatabaseError: file is not a database` and the server died
before `write_serve_lock` — the operator losing a working reader because a
metrics file went bad. Same principle as the Recorder dropping a sample it
cannot write: timing history is an accessory, not a precondition.
"""

from __future__ import annotations

from minerva.cli.serve_cmd import _open_metrics_db


def test_a_corrupt_metrics_file_does_not_stop_the_server(tmp_path, capsys):
    bad = tmp_path / "metrics.sqlite"
    bad.write_bytes(b"this is not a database, it is a truncated file")
    assert _open_metrics_db(bad) is None
    err = capsys.readouterr().err
    assert str(bad) in err
    assert "--no-metrics" in err


def test_a_usable_metrics_file_opens_normally(tmp_path):
    conn = _open_metrics_db(tmp_path / "metrics.sqlite")
    assert conn is not None
    try:
        # The schema is created on open, so the store is ready to write.
        assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 0
    finally:
        conn.close()


def test_the_guard_only_catches_sqlite_errors(tmp_path, monkeypatch):
    # A programming error inside open_db must still crash loudly rather
    # than degrade into "serving without timing history".
    from minerva.cli import serve_cmd

    def boom(*args, **kwargs):
        raise TypeError("wrong arguments")

    monkeypatch.setattr(serve_cmd.metrics, "open_db", boom)
    try:
        _open_metrics_db(tmp_path / "metrics.sqlite")
    except TypeError:
        return
    raise AssertionError("TypeError should have propagated")
