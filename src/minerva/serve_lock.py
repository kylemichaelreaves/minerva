"""Detect a running ``minerva serve`` bound to the corpus index DB."""

from __future__ import annotations

import os
from pathlib import Path


def serve_lock_path(db: Path) -> Path:
    return db.with_name(db.name + ".serve.lock")


def write_serve_lock(db: Path, *, host: str, port: int) -> Path:
    path = serve_lock_path(db)
    path.write_text(f"{os.getpid()}\n{host}\n{port}\n", encoding="utf-8")
    return path


def clear_serve_lock(db: Path) -> None:
    serve_lock_path(db).unlink(missing_ok=True)


def find_running_server(db: Path) -> str | None:
    """Return a human-readable description when a live server holds ``db``."""

    path = serve_lock_path(db)
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        pid = int(lines[0])
        host = lines[1] if len(lines) > 1 else "?"
        port = lines[2] if len(lines) > 2 else "?"
    except (OSError, ValueError, IndexError):
        path.unlink(missing_ok=True)
        return None
    if pid == os.getpid():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return None
    except PermissionError:
        # Process exists (e.g. pid 1) but this user cannot signal it.
        return f"pid {pid} on {host}:{port}"
    except OSError:
        path.unlink(missing_ok=True)
        return None
    return f"pid {pid} on {host}:{port}"
