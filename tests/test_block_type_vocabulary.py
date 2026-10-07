"""``chunks.block_type`` has one vocabulary, enforced on both sides (#536).

Python owns it (`block_types.BLOCK_TYPES`); a `Chunk` carrying any other
value fails at construction, and `check_api_types.py` fails `make check`
when the TS `BlockType` union disagrees in either direction. Before this the
union had drifted three ways: two arms nothing emitted (`body`,
`blockquote`) and one emitted value with no arm (`signature`).
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

from minerva import tei
from minerva.block_types import APPARATUS_TYPES, BLOCK_TYPES

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_api_types", REPO / "scripts" / "check_api_types.py"
)
assert _spec is not None
assert _spec.loader is not None
cat = importlib.util.module_from_spec(_spec)
sys.modules["check_api_types"] = cat
_spec.loader.exec_module(cat)


def _chunk(block_type: str | None) -> tei.Chunk:
    return tei.Chunk(
        chunk_id="c",
        corpus="hegel",
        author="Hegel",
        work="W",
        lang="deu",
        section="§1",
        book=None,
        page=None,
        speaker=None,
        text="t",
        source_file="f",
        translator=None,
        edition_year=None,
        block_type=block_type,
    )


@pytest.mark.parametrize("value", [None, *sorted(BLOCK_TYPES)])
def test_chunk_accepts_every_vocabulary_value(value):
    assert _chunk(value).block_type == value


@pytest.mark.parametrize("value", ["blockquote", "body", "Remark", ""])
def test_chunk_rejects_a_value_outside_the_vocabulary(value):
    with pytest.raises(ValueError, match="block_type"):
        _chunk(value)


def test_typing_post_passes_are_checked_too():
    # Post-passes type with dataclasses.replace, which re-runs __init__.
    with pytest.raises(ValueError, match="block_type"):
        dataclasses.replace(_chunk(None), block_type="sig")


def test_apparatus_types_are_part_of_the_vocabulary():
    assert set(APPARATUS_TYPES) <= BLOCK_TYPES


# ---------- the TS gate ----------


def test_ts_union_members_reads_a_multiline_union_with_comments(tmp_path: Path):
    ts = tmp_path / "t.ts"
    ts.write_text(
        'export type Other = "x";\n'
        "export type BlockType =\n"
        '  | "remark"\n'
        '  // a comment naming "note" is not an arm\n'
        '  | "addition";\n'
        'export type After = "y";\n'
    )
    assert cat._ts_union_members(ts, "BlockType") == {"remark", "addition"}


def test_ts_union_members_ignores_a_semicolon_inside_a_comment(tmp_path: Path):
    ts = tmp_path / "t.ts"
    ts.write_text('export type BlockType =\n  | "note"\n  // set apart; capped\n  | "spurious";\n')
    assert cat._ts_union_members(ts, "BlockType") == {"note", "spurious"}


def test_block_type_errors_reports_both_directions():
    errors = cat.block_type_errors(python={"remark", "signature"}, ts={"remark", "body"})
    assert any("signature" in e and "no TS arm" in e for e in errors)
    assert any("body" in e and "not in" in e for e in errors)


def test_block_type_errors_is_empty_when_the_sets_agree():
    assert cat.block_type_errors(python={"remark"}, ts={"remark"}) == []


def test_the_repo_union_matches_python():
    ts = cat._ts_union_members(cat.TS_TYPES / "reader.ts", "BlockType")
    assert cat.block_type_errors(python=set(BLOCK_TYPES), ts=ts) == []
