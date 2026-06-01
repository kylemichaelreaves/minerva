"""Domain-level exceptions — no HTTP coupling."""

from __future__ import annotations


class MinervaError(Exception):
    """Base class for recoverable domain errors."""


class NotFoundError(MinervaError):
    """Requested entity does not exist."""


class BadRequestError(MinervaError):
    """Malformed or invalid client input."""


class PayloadTooLargeError(MinervaError):
    """Request body or field exceeds allowed size."""
