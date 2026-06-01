"""HTTP transport: request parsing, CORS, ``ChatHandler``, static SPA, ``serve()``."""

from __future__ import annotations

import json
import logging
import mimetypes
import sqlite3
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .. import embed as embed_mod
from .. import llm
from ..errors import MinervaError
from .errors import domain_error_to_http
from .handlers import _handle_chat_stream
from .router import (
    _match_route,
    build_delete_routes,
    build_get_routes,
    build_patch_routes,
    build_post_routes,
)
from .server_core import ServerDeps, _HTTPError

_MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB; chat payloads are tiny
_log = logging.getLogger(__name__)

_BASE_CORS_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Max-Age": "600",
}


def _parse_content_length(raw: str | None) -> int:
    """Validate the Content-Length header and return the byte count."""

    if raw is None:
        return 0
    raw = raw.strip()
    if raw == "":
        return 0
    try:
        n = int(raw, 10)
    except ValueError:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "invalid Content-Length header") from None
    if n < 0:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "negative Content-Length header")
    if n > _MAX_REQUEST_BYTES:
        raise _HTTPError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            f"request body too large (limit {_MAX_REQUEST_BYTES} bytes)",
        )
    return n


def _read_json_body(headers: Any, rfile: Any) -> dict[str, Any]:
    """Read and parse a JSON object request body."""

    te = (headers.get("Transfer-Encoding") or "").strip().lower()
    if te and te != "identity":
        raise _HTTPError(
            HTTPStatus.LENGTH_REQUIRED,
            f"Transfer-Encoding {te!r} is not supported; send Content-Length",
        )
    length = _parse_content_length(headers.get("Content-Length"))
    raw = rfile.read(length) if length else b"{}"
    payload = json.loads(raw.decode("utf-8")) if raw else {}
    if not isinstance(payload, dict):
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "request body must be a JSON object")
    return payload


def _dispatch_json_mutation(
    handler: Callable[..., Any],
    args: tuple[Any, ...],
    payload: dict[str, Any],
) -> Any:
    """Run a JSON mutation handler with shared error translation."""

    try:
        return handler(*args, payload)
    except MinervaError as exc:
        raise domain_error_to_http(exc) from exc


def _cors_headers(deps: ServerDeps, origin: str | None) -> dict[str, str]:
    """Return the CORS headers for one response."""

    out = dict(_BASE_CORS_HEADERS)
    if deps.cors_wildcard:
        out["Access-Control-Allow-Origin"] = "*"
        return out
    if origin and origin in deps.allowed_origins:
        out["Access-Control-Allow-Origin"] = origin
        out["Vary"] = "Origin"
    return out


class ChatHandler(BaseHTTPRequestHandler):
    deps: ServerDeps  # bound by make_handler

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
        line = f"{self.address_string()} - - [{self.log_date_time_string()}] {fmt % args}"
        print(line, flush=True)

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, exc: _HTTPError) -> None:
        self._send_json(exc.status, {"error": exc.message})

    def _send_sse(
        self,
        status: HTTPStatus,
        events: Any,
    ) -> None:
        """Write a Server-Sent Events response, flushing after each event."""

        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            for name, data in events:
                payload = json.dumps(data, ensure_ascii=False)
                chunk = f"event: {name}\ndata: {payload}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        matched = _match_route(path, build_post_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        if not self.deps.rate_limiter.allow(path, self.client_address[0]):
            self.log_message("rate-limited: %s from %s", path, self.client_address[0])
            self._send_error_json(_HTTPError(HTTPStatus.TOO_MANY_REQUESTS, "rate limit exceeded"))
            return
        try:
            payload = _read_json_body(self.headers, self.rfile)
            if path == "/api/chat" and payload.get("stream"):
                self._send_sse(HTTPStatus.OK, _handle_chat_stream(self.deps, payload))
                return
            body = _dispatch_json_mutation(handler, args, payload)
        except _HTTPError as exc:
            self._send_error_json(exc)
            return
        except json.JSONDecodeError:
            self._send_error_json(_HTTPError(HTTPStatus.BAD_REQUEST, "invalid JSON"))
            return
        except llm.LLMError as exc:
            _log.exception("LLM error", exc_info=exc)
            self._send_error_json(_HTTPError(HTTPStatus.BAD_GATEWAY, "LLM backend error"))
            return
        except Exception as exc:
            _log.exception("%s error", label, exc_info=exc)
            self._send_error_json(_HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "server error"))
            return
        self._send_json(HTTPStatus.OK, body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs: dict[str, str] | None = None

        def _qs() -> dict[str, str]:
            nonlocal qs
            if qs is None:
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            return qs

        routes = build_get_routes(self.deps, _qs)
        matched = _match_route(path, routes)
        if matched is not None:
            label, handler, args = matched
            try:
                body = handler(*args)  # type: ignore[arg-type]
                self._send_json(HTTPStatus.OK, body)
            except MinervaError as exc:
                self._send_error_json(domain_error_to_http(exc))
            except _HTTPError as exc:
                self._send_error_json(exc)
            except Exception as exc:
                _log.exception("%s error", label, exc_info=exc)
                self._send_error_json(
                    _HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "server error")
                )
            return

        if path.startswith("/api/"):
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        self._serve_static(path)

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        matched = _match_route(path, build_patch_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        try:
            payload = _read_json_body(self.headers, self.rfile)
            body = _dispatch_json_mutation(handler, args, payload)
        except _HTTPError as exc:
            self._send_error_json(exc)
            return
        except json.JSONDecodeError:
            self._send_error_json(_HTTPError(HTTPStatus.BAD_REQUEST, "invalid JSON"))
            return
        except Exception as exc:
            _log.exception("%s error", label, exc_info=exc)
            self._send_error_json(_HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "server error"))
            return
        self._send_json(HTTPStatus.OK, body)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        matched = _match_route(path, build_delete_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        try:
            removed = handler(*args)
        except MinervaError as exc:
            self._send_error_json(domain_error_to_http(exc))
            return
        except _HTTPError as exc:
            self._send_error_json(exc)
            return
        except Exception as exc:
            _log.exception("%s error", label, exc_info=exc)
            self._send_error_json(_HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "server error"))
            return
        if not removed:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, "conversation not found"))
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        self.end_headers()

    def _serve_static(self, request_path: str) -> None:
        root = self.deps.static_dir.resolve()
        if not root.is_dir():
            self.log_message("static dir not found: %s", root)
            self._send_error_json(
                _HTTPError(
                    HTTPStatus.NOT_FOUND,
                    "static assets not available (run `npm run build` in web/)",
                )
            )
            return
        rel = request_path.lstrip("/") or "index.html"
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self._send_error_json(_HTTPError(HTTPStatus.FORBIDDEN, "path traversal"))
            return
        if not candidate.is_file():
            candidate = (root / "index.html").resolve()
            if not candidate.is_file():
                self.log_message("static asset missing: %s", rel)
                self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, "asset not found"))
                return
        ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if "/assets/" in request_path:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)


def make_handler(deps: ServerDeps):
    class _Bound(ChatHandler):
        pass

    _Bound.deps = deps
    return _Bound


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def serve(
    *,
    host: str,
    port: int,
    static_dir: Path,
    conn: sqlite3.Connection,
    conversations_conn: sqlite3.Connection,
    translations_conn: sqlite3.Connection,
    concept_cache_conn: sqlite3.Connection | None,
    backend: llm.LLMBackend,
    embedder: embed_mod.Embedder | None,
    lang: str | None,
    corpus: str | None,
    speaker: str | None,
    top_k: int,
    allow_client_rewrite: bool = True,
    force_rewrite: bool = True,
    enable_concept_expand: bool = True,
    allowed_origins: frozenset[str] = frozenset(),
) -> None:
    is_loopback = host in _LOOPBACK_HOSTS
    deps = ServerDeps(
        conn=conn,
        conversations_conn=conversations_conn,
        translations_conn=translations_conn,
        concept_cache_conn=concept_cache_conn,
        backend=backend,
        embedder=embedder,
        lang=lang,
        corpus=corpus,
        speaker=speaker,
        top_k=top_k,
        static_dir=static_dir,
        allow_client_rewrite=allow_client_rewrite,
        force_rewrite=force_rewrite,
        enable_concept_expand=enable_concept_expand,
        cors_wildcard=is_loopback,
        allowed_origins=allowed_origins,
    )
    if not is_loopback:
        print(
            f"WARNING: binding to {host} exposes the API beyond localhost. "
            "Anyone who can reach this port can drive chat / translate "
            "(and incur LLM billing). Consider --no-client-rewrite, an "
            "upstream gateway with auth, and a narrow --allow-origin.",
            flush=True,
        )
        if not allowed_origins:
            print(
                "WARNING: no --allow-origin set. CORS responses will omit "
                "Access-Control-Allow-Origin entirely; browser clients on "
                "other origins won't be able to read responses.",
                flush=True,
            )
    server = ThreadingHTTPServer((host, port), make_handler(deps))
    origins_repr = (
        ",".join(sorted(allowed_origins)) if allowed_origins else "*" if is_loopback else "(none)"
    )
    print(
        f"minerva serve  http://{host}:{port}  "
        f"backend={backend.name} lang={lang or 'any'} corpus={corpus or 'any'} "
        f"speaker={speaker or 'any'} top_k={top_k} static={static_dir} "
        f"client_rewrite={'on' if allow_client_rewrite else 'OFF'} "
        f"auto_rewrite={'on' if force_rewrite else 'OFF'} "
        f"concept_expand={'on' if enable_concept_expand else 'OFF'} "
        f"concept_cache={'on' if concept_cache_conn is not None else 'OFF'} "
        f"cors_origins={origins_repr}",
        flush=True,
    )
    print("ctrl-c to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        server.shutdown()
        server.server_close()
