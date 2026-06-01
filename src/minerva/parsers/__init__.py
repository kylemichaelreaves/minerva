"""Corpus text parsers — re-exports from package root during migration."""

from minerva import tei
from minerva.sources import hebrew_mt, quran, sblgnt, vulgate

__all__ = ["hebrew_mt", "quran", "sblgnt", "tei", "vulgate"]
