#!/usr/bin/env python3
"""Generate corpus_registry, author_ordering, and atlasData from manifest.yaml."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data" / "authors" / "manifest.yaml"
CORPUS_REGISTRY = REPO_ROOT / "src" / "minerva" / "corpus_registry.py"
AUTHOR_ORDERING = REPO_ROOT / "src" / "minerva" / "author_ordering.py"
ATLAS_DATA = REPO_ROOT / "web" / "src" / "Landing" / "atlasData.ts"

BEGIN_CORPORA = "# BEGIN CORPORA"
END_CORPORA = "# END CORPORA"
BEGIN_ORDINAL = "# BEGIN AUTHOR_ORDINAL"
END_ORDINAL = "# END AUTHOR_ORDINAL"
BEGIN_ATLAS = "// BEGIN ATLAS_AUTHORS"
END_ATLAS = "// END ATLAS_AUTHORS"

# Chunk ``author`` field → corpus id when not 1:1 with display name.
DISPLAY_TO_CORPUS: dict[str, str] = {
    "Hebrew Bible": "hebrew_mt",
    "Homer": "homer",
    "Theognis": "theognis",
    "Aesop": "aesop",
    "Plato": "plato",
    "Aristotle": "aristotle",
    "Aeschylus": "aeschylus",
    "Sophocles": "sophocles",
    "Euripides": "euripides",
    "Lucretius": "lucretius",
    "Cicero": "cicero",
    "Epictetus": "epictetus",
    "Marcus Aurelius": "marcus_aurelius",
    "Septuagint": "septuagint",
    "New Testament": "new_testament",
    "Vulgate": "vulgate",
    "Origen": "origen",
    "Augustine": "augustine",
    "Quran": "quran",
    "Aquinas": "aquinas",
    "Luther Bibel 1545": "luther_1545",
    "Luther Bibel 1912": "luther_1912",
    "King James Bible": "kjv",
    "Sacy": "sacy",
    "Descartes": "descartes",
    "Hobbes": "hobbes",
    "Pascal": "pascal",
    "Spinoza": "spinoza",
    "Locke": "locke",
    "Boulainvilliers": "boulainvilliers",
    "Hume": "hume",
    "Rousseau": "rousseau",
    "Kant": "kant",
    "Hegel": "hegel",
    "Gobineau": "gobineau",
    "Renan": "renan",
    "Marx": "marx",
    "Nietzsche": "nietzsche",
    "Thales": "presocratic",
    "Anaximander": "presocratic",
    "Anaximenes": "presocratic",
    "Pythagoras": "presocratic",
    "Xenophanes": "presocratic",
    "Heraclitus": "presocratic",
    "Parmenides": "presocratic",
    "Zeno of Elea": "presocratic",
    "Empedocles": "presocratic",
    "Anaxagoras": "presocratic",
    "Melissus": "presocratic",
    "Diogenes of Apollonia": "presocratic",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install pyyaml") from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump_yaml(data: dict[str, Any], path: Path) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def _parse_atlas_ts(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    m = re.search(
        r"export const ATLAS_AUTHORS.*?=\s*\[(.*?)\];",
        text,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError(f"Could not parse ATLAS_AUTHORS from {path}")
    block = m.group(1)
    entries: list[dict[str, Any]] = []
    for obj_m in re.finditer(r"\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", block):
        chunk = obj_m.group(1)
        name_m = re.search(r'name:\s*"([^"]+)"', chunk)
        if not name_m:
            continue
        year_m = re.search(r"year:\s*(-?\d+)", chunk)
        trad_m = re.search(r'tradition:\s*"([^"]+)"', chunk)
        row_m = re.search(r"row:\s*(\d+)", chunk)
        x_m = re.search(r"xShift:\s*(-?\d+)", chunk)
        work_m = re.search(r'work:\s*"([^"]*)"', chunk)
        comment_lines = [
            ln.strip()
            for ln in chunk.splitlines()
            if ln.strip().startswith("//")
        ]
        entry: dict[str, Any] = {
            "display_name": name_m.group(1),
            "year": int(year_m.group(1)) if year_m else 0,
            "tradition": trad_m.group(1) if trad_m else "classical",
            "row": int(row_m.group(1)) if row_m else 0,
            "x_shift": int(x_m.group(1)) if x_m else 0,
            "work_hint": work_m.group(1) if work_m else "",
        }
        if comment_lines:
            entry["atlas_comment"] = "\n".join(
                c.removeprefix("//").strip() for c in comment_lines
            )
        entries.append(entry)
    return entries


def _corpus_comments_from_source() -> dict[str, str]:
    """Extract inline comments preceding CorpusEntry blocks."""
    text = CORPUS_REGISTRY.read_text(encoding="utf-8")
    comments: dict[str, str] = {}
    pattern = re.compile(
        r"(# ───[^\n]*\n(?:#[^\n]*\n)*)"
        r'\s*CorpusEntry\(\s*\n\s*"([^"]+)"',
        re.MULTILINE,
    )
    for block, cid in pattern.finditer(text):
        lines = [
            ln.strip().removeprefix("#").strip()
            for ln in block.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith("# ───")
        ]
        if lines:
            comments[cid] = "\n".join(lines)
    # Tragedian comment is inline inside CorpusEntry for aeschylus
    if "aeschylus" not in comments:
        m = re.search(
            r'CorpusEntry\(\s*\n\s*"aeschylus".*?'
            r"(# Lowercase initials.*?)\n\s*\"a\",",
            text,
            re.DOTALL,
        )
        if m:
            comments["aeschylus"] = m.group(1).strip().removeprefix("# ").strip()
    return comments


def bootstrap_manifest() -> dict[str, Any]:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from minerva import author_ordering, corpus_registry

    atlas_rows = _parse_atlas_ts(ATLAS_DATA)
    atlas_by_name = {r["display_name"]: r for r in atlas_rows}
    corpus_comments = _comments_from_corpus_registry()
    ordinal_comments = _comments_from_author_ordering()

    corpora: list[dict[str, Any]] = []
    for entry in corpus_registry.CORPORA:
        row: dict[str, Any] = {
            "id": entry.id,
            "original_lang": entry.original_lang,
            "citation_system": entry.citation_system,
            "dominant_code": entry.dominant_code,
            "keywords": list(entry.keywords),
        }
        if entry.id in corpus_comments:
            row["comment"] = corpus_comments[entry.id]
        corpora.append(row)

    authors: list[dict[str, Any]] = []
    for display_name, ordinal in sorted(
        author_ordering.AUTHOR_ORDINAL.items(),
        key=lambda kv: kv[1],
    ):
        corpus_id = DISPLAY_TO_CORPUS.get(display_name)
        if corpus_id is None:
            corpus_id = display_name.lower().replace(" ", "_")
        row: dict[str, Any] = {
            "display_name": display_name,
            "corpus_id": corpus_id,
            "ordinal": ordinal,
        }
        if display_name in ordinal_comments:
            row["ordinal_comment"] = ordinal_comments[display_name]
        if display_name in atlas_by_name:
            a = atlas_by_name[display_name]
            row["year"] = a["year"]
            row["tradition"] = a["tradition"]
            row["row"] = a["row"]
            row["x_shift"] = a["x_shift"]
            row["work_hint"] = a["work_hint"]
            if a.get("atlas_comment"):
                row["atlas_comment"] = a["atlas_comment"]
        authors.append(row)

    return {
        "atlas_order": [r["display_name"] for r in atlas_rows],
        "corpora": corpora,
        "authors": authors,
    }


def _comments_from_corpus_registry() -> dict[str, str]:
    text = CORPUS_REGISTRY.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    parts = re.split(r"CorpusEntry\(\s*\n\s*\"([^\"]+)\"", text)
    for i in range(1, len(parts), 2):
        cid = parts[i]
        before = parts[i - 1]
        lines = []
        for ln in before.splitlines()[-8:]:
            s = ln.strip()
            if s.startswith("#") and not s.startswith("# ───"):
                lines.append(s.removeprefix("#").strip())
        if lines:
            out[cid] = "\n".join(lines)
    return out


def _comments_from_author_ordering() -> dict[str, str]:
    text = AUTHOR_ORDERING.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(
        r"(# [^\n]+(?:\n# [^\n]+)*)\n\s+\"([^\"]+)\":\s*(\d+)",
        text,
    ):
        comment = "\n".join(
            ln.strip().removeprefix("#").strip() for ln in m.group(1).splitlines()
        )
        if comment and not comment.startswith("───"):
            out[m.group(2)] = comment
    return out


def _py_str(s: str) -> str:
    return repr(s)


def _py_tuple_str(items: list[str]) -> str:
    if not items:
        return "()"
    inner = ",\n        ".join(_py_str(x) for x in items)
    return f"(\n        {inner},\n    )"


def generate_corpora_block(corpora: list[dict[str, Any]]) -> str:
    lines = ["CORPORA: tuple[CorpusEntry, ...] = ("]
    for c in corpora:
        if c.get("comment"):
            for ln in str(c["comment"]).splitlines():
                lines.append(f"    # {ln}")
        lines.append("    CorpusEntry(")
        lines.append(f"        {_py_str(c['id'])},")
        lines.append(f"        {_py_str(c['original_lang'])},")
        lines.append(f"        {_py_str(c['citation_system'])},")
        dom = c["dominant_code"]
        if "\n" in dom or "#" in dom:
            lines.append(f"        {_py_str(dom)},")
        else:
            # Preserve inline comments on dominant_code (luther, tragedians)
            dom_line = _py_str(dom)
            extra = c.get("dominant_comment")
            if extra:
                lines.append(f"        {dom_line[:-1]},  # {extra}")
            else:
                lines.append(f"        {dom_line},")
        kws = c.get("keywords") or []
        lines.append(f"        {_py_tuple_str(kws)},")
        lines.append("    ),")
    lines.append(")")
    return "\n".join(lines)


def generate_ordinal_block(authors: list[dict[str, Any]]) -> str:
    lines = ["AUTHOR_ORDINAL: dict[str, int] = {"]
    for a in sorted(authors, key=lambda x: x["ordinal"]):
        if a.get("ordinal_comment"):
            for ln in str(a["ordinal_comment"]).splitlines():
                lines.append(f"    # {ln}")
        lines.append(f"    {_py_str(a['display_name'])}: {a['ordinal']},")
    lines.append("}")
    return "\n".join(lines)


def generate_atlas_block(
    authors: list[dict[str, Any]],
    atlas_order: list[str],
) -> str:
    by_name = {a["display_name"]: a for a in authors if "year" in a}
    lines = ["export const ATLAS_AUTHORS: AtlasAuthor[] = ["]
    for name in atlas_order:
        a = by_name.get(name)
        if not a:
            raise KeyError(f"atlas_order references unknown author: {name!r}")
        if a.get("atlas_comment"):
            for ln in str(a["atlas_comment"]).splitlines():
                lines.append(f"  // {ln}")
        work = a.get("work_hint", "").replace("\\", "\\\\").replace('"', '\\"')
        if len(work) > 40 or "'" in work:
            work_field = f'work: "{work}"'
        else:
            work_field = f'work: "{work}"'
        if (
            a["row"] == 0
            and a["x_shift"] == 0
            and len(name) < 20
            and not a.get("atlas_comment")
        ):
            lines.append(
                f'  {{ name: "{name}", year: {a["year"]}, tradition: "{a["tradition"]}", '
                f"row: 0, xShift: 0, {work_field} }},"
            )
        else:
            lines.append("  {")
            lines.append(f'    name: "{name}",')
            lines.append(f"    year: {a['year']},")
            lines.append(f'    tradition: "{a["tradition"]}",')
            lines.append(f"    row: {a['row']},")
            lines.append(f"    xShift: {a['x_shift']},")
            lines.append(f"    {work_field},")
            lines.append("  },")
    lines.append("];")
    return "\n".join(lines)


def _replace_region(path: Path, begin: str, end: str, new_block: str) -> str:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    replacement = f"{begin}\n{new_block}\n{end}"
    if not pattern.search(text):
        raise RuntimeError(f"Markers {begin!r}/{end!r} not found in {path}")
    return pattern.sub(replacement, text, count=1)


def generate_all(manifest: dict[str, Any]) -> dict[str, str]:
    corpora = manifest["corpora"]
    authors = manifest["authors"]
    atlas_order = manifest.get("atlas_order") or [
        a["display_name"] for a in authors if "year" in a
    ]
    return {
        "corpus_registry": generate_corpora_block(corpora),
        "author_ordering": generate_ordinal_block(authors),
        "atlasData": generate_atlas_block(authors, atlas_order),
    }


def apply_writes(manifest: dict[str, Any]) -> None:
    blocks = generate_all(manifest)
    cr = _replace_region(
        CORPUS_REGISTRY,
        BEGIN_CORPORA,
        END_CORPORA,
        blocks["corpus_registry"],
    )
    CORPUS_REGISTRY.write_text(cr, encoding="utf-8")
    ao = _replace_region(
        AUTHOR_ORDERING,
        BEGIN_ORDINAL,
        END_ORDINAL,
        blocks["author_ordering"],
    )
    AUTHOR_ORDERING.write_text(ao, encoding="utf-8")
    ad = _replace_region(
        ATLAS_DATA,
        BEGIN_ATLAS,
        END_ATLAS,
        blocks["atlasData"],
    )
    ATLAS_DATA.write_text(ad, encoding="utf-8")


def check_sync(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    blocks = generate_all(manifest)
    for path, begin, end, key in [
        (CORPUS_REGISTRY, BEGIN_CORPORA, END_CORPORA, "corpus_registry"),
        (AUTHOR_ORDERING, BEGIN_ORDINAL, END_ORDINAL, "author_ordering"),
        (ATLAS_DATA, BEGIN_ATLAS, END_ATLAS, "atlasData"),
    ]:
        text = path.read_text(encoding="utf-8")
        m = re.search(
            re.escape(begin) + r"(.*?)" + re.escape(end),
            text,
            re.DOTALL,
        )
        if not m:
            errors.append(f"{path}: missing markers")
            continue
        current = m.group(1).strip()
        expected = blocks[key].strip()
        if current != expected:
            errors.append(f"{path}: generated block differs from manifest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Write manifest.yaml from current source files",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate marked regions in target files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if targets are out of sync with manifest",
    )
    args = parser.parse_args()
    if args.bootstrap:
        _dump_yaml(bootstrap_manifest(), MANIFEST_PATH)
        print(f"Wrote {MANIFEST_PATH}")
        return 0
    if not MANIFEST_PATH.is_file():
        print(f"Missing {MANIFEST_PATH}; run with --bootstrap first", file=sys.stderr)
        return 1
    manifest = _load_yaml(MANIFEST_PATH)
    if args.write:
        apply_writes(manifest)
        print("Updated corpus_registry, author_ordering, atlasData")
        return 0
    if args.check:
        errors = check_sync(manifest)
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            return 1
        print("Author artifacts in sync with manifest")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
