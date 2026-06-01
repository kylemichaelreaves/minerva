"""Lock decorators for HTTP handlers."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from ...errors import MinervaError
from ..errors import domain_error_to_http
from ..server_core import ServerDeps

F = TypeVar("F", bound=Callable[..., Any])


def map_domain_errors(fn: F) -> F:
    """Convert :class:`MinervaError` to :class:`_HTTPError` at the boundary."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except MinervaError as exc:
            raise domain_error_to_http(exc) from exc

    return wrapper  # type: ignore[return-value]


def with_corpus_lock(fn: F) -> F:
    """Acquire ``deps.corpus_lock`` before delegating to *fn*."""

    @map_domain_errors
    @functools.wraps(fn)
    def wrapper(deps: ServerDeps, *args: Any, **kwargs: Any) -> Any:
        with deps.corpus_lock:
            return fn(deps, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def with_conv_lock(fn: F) -> F:
    """Acquire ``deps.conv_lock`` before delegating to *fn*."""

    @map_domain_errors
    @functools.wraps(fn)
    def wrapper(deps: ServerDeps, *args: Any, **kwargs: Any) -> Any:
        with deps.conv_lock:
            return fn(deps, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
