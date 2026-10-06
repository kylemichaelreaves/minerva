"""Cross-reference read queries — re-export facade.

Implementation lives in focused submodules (``filters``, ``map_queries``,
``list_queries``, ``network_queries``, ``review_queries``,
``update_queries``). Import paths like ``from minerva.refs import queries``
stay stable for handlers and tests.
"""

from __future__ import annotations

from .list_queries import references_list, references_sources
from .map_queries import work_references_map
from .network_queries import network_summary
from .review_queries import review_queue
from .row_utils import xref_row_to_dict
from .update_queries import parse_reference_update_body, update_reference

__all__ = [
    "network_summary",
    "parse_reference_update_body",
    "references_list",
    "references_sources",
    "review_queue",
    "update_reference",
    "work_references_map",
    "xref_row_to_dict",
]
