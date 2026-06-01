"""Leaf corpus & scripture source parsers.

Each module turns one corpus's raw files (TEI, Zefania/OSIS XML,
OCR text, …) into ``minerva.tei.Chunk`` records. Wired into the
ingest pipeline by ``minerva.ingest.registry`` (by dotted name,
e.g. ``sources.vulgate``)."""
