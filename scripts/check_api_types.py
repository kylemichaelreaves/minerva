#!/usr/bin/env python3
"""Verify API contract fixture keys exist on TS wire types (api/types/*.ts).

Role: workflow
"""

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
    "chunk_context": (TS_TYPES / "reader.ts", "ChunkContextResponse"),
    "word_lookup": (TS_TYPES / "reader.ts", "WordLookup"),
    "references_list": (TS_TYPES / "refs.ts", "ReferencesListResponse"),
    "refs_review": (TS_TYPES / "refs.ts", "ReviewQueueResponse"),
    "refs_sources": (TS_TYPES / "refs.ts", "RefsSourcesResponse"),
    "concordance_index": (TS_API / "concordanceApi.ts", "LemmaIndexResponse"),
    "concordance_lemma": (TS_API / "concordanceApi.ts", "LemmaDetailResponse"),
    "network_summary": (TS_API / "networkApi.ts", "NetworkSummary"),
    "landing_stats": (TS_API / "landingApi.ts", "LandingStats"),
    "chunk_syntax": (TS_API / "syntaxApi.ts", "ChunkSyntax"),
    "syntax_correction": (TS_API / "syntaxApi.ts", "CorrectionAccepted"),
    "metrics_summary": (TS_API / "metricsApi.ts", "MetricsSummaryResponse"),
    "metrics_series": (TS_API / "metricsApi.ts", "MetricsSeriesResponse"),
    "metrics_requests": (TS_API / "metricsApi.ts", "MetricsRequestsResponse"),
}

# Fixtures with no TS interface to check against, and why. An entry here is a
# deliberate exemption; anything else unmapped is an error (see `main`).
UNTYPED_FIXTURES: dict[str, str] = {}


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

    # A fixture with no mapping used to be skipped in silence, which is how
    # `terms_list` sat unchecked from the day it was added. Adding a fixture
    # must now either map it to an interface or say why it can't — otherwise
    # the next one drifts the same way.
    on_disk = {p.name[: -len(".keys.json")] for p in FIXTURES.glob("*.keys.json")}
    unmapped = on_disk - set(FIXTURE_TYPES) - set(UNTYPED_FIXTURES)
    for stem in sorted(unmapped):
        errors.append(
            f"{stem}.keys.json has no FIXTURE_TYPES entry — add one, or record "
            f"an exemption with its reason in UNTYPED_FIXTURES"
        )
    declared = set(FIXTURE_TYPES) | set(UNTYPED_FIXTURES)
    for stem in sorted(declared - on_disk):
        errors.append(f"{stem} is mapped but {stem}.keys.json does not exist")

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
