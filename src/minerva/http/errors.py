"""Map domain exceptions to HTTP error envelopes."""

from __future__ import annotations

from http import HTTPStatus

from ..errors import BadRequestError, MinervaError, NotFoundError, PayloadTooLargeError
from .server_core import _HTTPError


def domain_error_to_http(exc: MinervaError) -> _HTTPError:
    if isinstance(exc, NotFoundError):
        return _HTTPError(HTTPStatus.NOT_FOUND, str(exc))
    if isinstance(exc, BadRequestError):
        return _HTTPError(HTTPStatus.BAD_REQUEST, str(exc))
    if isinstance(exc, PayloadTooLargeError):
        return _HTTPError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
    return _HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc) or "server error")
