#!/usr/bin/env python3
"""Verify API contract fixture keys exist on TS wire types (api/types/*.ts)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "api"
TS_TYPES = REPO / "web" / "src" / "api" / "types"
TS_API = REPO / "web" / "src" / "api"

# fixture stem -> (types file, interface name)
FIXTURE_TYPES: dict[str, tuple[Path, str]] = {
    "chat_response": (TS_TYPES / "chat.ts", "ChatResponse"),
    "chat_stream_meta": (TS_TYPES / "chat.ts", "ChatStreamMeta"),
    "work_range": (TS_TYPES / "reader.ts", "WorkRange"),
    "references_list": (TS_TYPES / "refs.ts", "ReferencesListResponse"),
    "refs_review": (TS_TYPES / "refs.ts", "ReviewQueueResponse"),
    "refs_sources": (TS_TYPES / "refs.ts", "RefsSourcesResponse"),
    "concordance_index": (TS_API / "concordanceApi.ts", "LemmaIndexResponse"),
}


def _interface_fields(path: Path, name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"export interface {re.escape(name)}\s*\{{", text)
    if not m:
        raise SystemExit(f"interface {name} not found in {path}")
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    block = text[start : i - 1]
    fields: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("}"):
            continue
        if ":" in stripped and not stripped.startswith("|"):
            key = stripped.split(":")[0].strip()
            if key and key not in ("export", "import"):
                fields.add(key)
    return fields


def main() -> int:
    errors: list[str] = []
    for stem, (ts_path, iface) in FIXTURE_TYPES.items():
        keys_path = FIXTURES / f"{stem}.keys.json"
        if not keys_path.is_file():
            errors.append(f"missing fixture {keys_path}")
            continue
        required = set(json.loads(keys_path.read_text(encoding="utf-8")))
        fields = _interface_fields(ts_path, iface)
        missing = required - fields
        if missing:
            errors.append(f"{iface}: fixture keys not in TS: {sorted(missing)}")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("check-api-types: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
