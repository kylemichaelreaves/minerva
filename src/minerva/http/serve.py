"""HTTP transport: request parsing, CORS, ``ChatHandler``, static SPA, ``serve()``."""

from __future__ import annotations

import json
import logging
import mimetypes
import sqlite3
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .. import embed as embed_mod
from .. import llm
from ..errors import MinervaError
from ..metrics.recorder import Recorder, current_span
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

# Sent on every response (#124). The threat model is the operator's own
# browser visiting a hostile page while `minerva serve` is up — the same
# one the cross-origin refusal above addresses — and it gets sharper on a
# non-loopback bind.
#
# The policy can be this tight because the SPA is entirely self-hosted:
# the built index.html loads one module script and one stylesheet, both
# from /assets, and carries no inline <script>. The outbound links the
# Reader offers (Logeion, Perseus, archive.org) are <a href> navigations,
# which CSP does not restrict.
#
# `style-src` keeps 'unsafe-inline' because the components set inline
# style attributes in ~100 places; `script-src` does not need it, which
# is the half that matters for XSS.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'"
    ),
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


def _require_json_content_type(headers: Any) -> None:
    """Reject a request body that isn't declared ``application/json``.

    This is the load-bearing half of the CSRF defence (issue #118). The three
    CORS-safelisted content types — ``text/plain``,
    ``application/x-www-form-urlencoded`` and ``multipart/form-data`` — make a
    cross-origin POST a "simple request", which the browser sends with no
    preflight at all. Requiring ``application/json`` forces a preflight, and
    the preflight already withholds ``Access-Control-Allow-Origin`` from
    unlisted origins, so the real request is never issued.

    A browser cannot suppress ``Content-Type`` on a body-bearing request, so
    there is no way to sidestep this from a page.
    """

    raw = headers.get("Content-Type") or ""
    mime = raw.split(";", 1)[0].strip().lower()
    if mime != "application/json":
        raise _HTTPError(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "request body must be sent as Content-Type: application/json",
        )


def _same_origin_forms(host: str | None) -> frozenset[str]:
    """The origins that are same-origin with a request sent to ``host``."""

    if not host:
        return frozenset()
    return frozenset({f"http://{host}", f"https://{host}"})


def _origin_allowed(deps: ServerDeps, origin: str | None, host: str | None) -> bool:
    """Whether a state-changing request may proceed.

    No ``Origin`` means no browser: curl, the CLI and the e2e harness send
    none, and a browser *always* sends one on POST/PATCH/DELETE. Absence is
    therefore not evidence of a cross-origin request.

    Beyond the configured allowlist, a request whose ``Origin`` is the very
    host it was addressed to is same-origin by definition. Without that,
    `serve --host 0.0.0.0 --static` would reject every POST from its own SPA
    unless the operator also passed a matching `--allow-origin` — turning a
    documented warning into a broken app.
    """

    if origin is None:
        return True
    return origin in deps.allowed_origins or origin in _same_origin_forms(host)


def _read_json_body(headers: Any, rfile: Any) -> dict[str, Any]:
    """Read and parse a JSON object request body."""

    te = (headers.get("Transfer-Encoding") or "").strip().lower()
    if te and te != "identity":
        raise _HTTPError(
            HTTPStatus.LENGTH_REQUIRED,
            f"Transfer-Encoding {te!r} is not supported; send Content-Length",
        )
    length = _parse_content_length(headers.get("Content-Length"))
    # Only gate requests that actually carry a body. A bodyless POST parses to
    # `{}` and every handler rejects it on validation, so there is nothing to
    # protect — and demanding a Content-Type for no content would be pedantry.
    if length:
        _require_json_content_type(headers)
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


def _translate_route_exception(label: str, exc: BaseException) -> _HTTPError:
    """Map handler exceptions to HTTP errors consistently across verbs."""

    if isinstance(exc, _HTTPError):
        return exc
    if isinstance(exc, MinervaError):
        return domain_error_to_http(exc)
    if isinstance(exc, llm.LLMError):
        _log.exception("LLM error", exc_info=exc)
        return _HTTPError(HTTPStatus.BAD_GATEWAY, "LLM backend error")
    if isinstance(exc, json.JSONDecodeError):
        return _HTTPError(HTTPStatus.BAD_REQUEST, "invalid JSON")
    _log.exception("%s error", label, exc_info=exc)
    return _HTTPError(HTTPStatus.INTERNAL_SERVER_ERROR, "server error")


def _cors_headers(deps: ServerDeps, origin: str | None) -> dict[str, str]:
    """Return the CORS headers for one response."""

    out = dict(_BASE_CORS_HEADERS)
    if origin and origin in deps.allowed_origins:
        out["Access-Control-Allow-Origin"] = origin
        out["Vary"] = "Origin"
    return out


class ChatHandler(BaseHTTPRequestHandler):
    deps: ServerDeps  # bound by handler factory
    timeout = 60  # slow-loris guard on non-loopback binds

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter logs
        line = f"{self.address_string()} - - [{self.log_date_time_string()}] {fmt % args}"
        print(line, flush=True)

    def version_string(self) -> str:
        """Don't advertise the exact BaseHTTP/CPython build."""

        return "minerva"

    def _send_common_headers(self) -> None:
        """CORS + hardening headers, shared by every response path.

        One helper rather than a loop per path: the headers in #124 are
        only worth anything if nothing can answer without them, and the
        404/204 paths are exactly the ones an edit forgets.
        """

        for k, v in _cors_headers(self.deps, self.headers.get("Origin")).items():
            self.send_header(k, v)
        for k, v in _SECURITY_HEADERS.items():
            self.send_header(k, v)

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._send_common_headers()
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
        self._send_common_headers()
        self.end_headers()
        it = iter(events)
        try:
            while True:
                try:
                    name, data = next(it)
                except StopIteration:
                    break
                payload = json.dumps(data, ensure_ascii=False)
                chunk = f"event: {name}\ndata: {payload}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
                active = current_span()
                if active is not None:
                    active.first_event()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            it.close()

    def _refused_cross_origin(self) -> bool:
        """Answer and return True when a state-changing request comes from an
        origin we don't trust.

        Runs before routing: this is a transport-level policy, and it also
        avoids telling a hostile origin which routes exist.
        """

        origin = self.headers.get("Origin")
        if _origin_allowed(self.deps, origin, self.headers.get("Host")):
            return False
        self.log_message("cross-origin refused: %s from %s", self.path, origin)
        self._send_error_json(_HTTPError(HTTPStatus.FORBIDDEN, "cross-origin request refused"))
        return True

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if self._refused_cross_origin():
            return
        path = urlparse(self.path).path
        matched = _match_route(path, build_post_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        # By label, not path — see `_RATE_LIMITS`. `/api/chunks/<id>/syntax/
        # corrections` has a different path per chunk and would otherwise get
        # a fresh bucket for every chunk, which is no limit at all.
        if not self.deps.rate_limiter.allow(label, self.client_address[0]):
            self.log_message("rate-limited: %s from %s", path, self.client_address[0])
            self._send_error_json(_HTTPError(HTTPStatus.TOO_MANY_REQUESTS, "rate limit exceeded"))
            return
        try:
            with self.deps.metrics.record(label, "POST") as span:
                payload = _read_json_body(self.headers, self.rfile)
                if path == "/api/chat" and payload.get("stream") is True:
                    span.status = HTTPStatus.OK
                    self._send_sse(HTTPStatus.OK, _handle_chat_stream(self.deps, payload))
                    return
                body = _dispatch_json_mutation(handler, args, payload)
        except Exception as exc:
            self._send_error_json(_translate_route_exception(label, exc))
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
            # GET routes rate-limit by label, not path: theirs carry ids and
            # would never match a fixed key. Most have no entry and sail past.
            if not self.deps.rate_limiter.allow(label, self.client_address[0]):
                self.log_message("rate-limited: %s from %s", label, self.client_address[0])
                self._send_error_json(
                    _HTTPError(HTTPStatus.TOO_MANY_REQUESTS, "rate limit exceeded")
                )
                return
            try:
                # `total` covers handler execution only, not the response
                # write: including the socket write would make `total`
                # depend on client network speed, so a slow or distant
                # client would inflate p95 and read as a server-side
                # regression — the exact misdiagnosis this feature exists
                # to prevent. TTFE is a different `kind`, deliberately
                # measured at the first SSE write instead (see `_send_sse`).
                with self.deps.metrics.record(label, "GET"):
                    body = handler(*args)  # type: ignore[arg-type]
                self._send_json(HTTPStatus.OK, body)
            except Exception as exc:
                self._send_error_json(_translate_route_exception(label, exc))
                return
            return

        if path.startswith("/api/"):
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        self._serve_static(path)

    def do_PATCH(self) -> None:
        if self._refused_cross_origin():
            return
        path = urlparse(self.path).path
        matched = _match_route(path, build_patch_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        try:
            with self.deps.metrics.record(label, "PATCH"):
                payload = _read_json_body(self.headers, self.rfile)
                body = _dispatch_json_mutation(handler, args, payload)
        except Exception as exc:
            self._send_error_json(_translate_route_exception(label, exc))
            return
        self._send_json(HTTPStatus.OK, body)

    def do_DELETE(self) -> None:
        if self._refused_cross_origin():
            return
        path = urlparse(self.path).path
        matched = _match_route(path, build_delete_routes(self.deps))
        if matched is None:
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"no route for {path}"))
            return
        label, handler, args = matched
        try:
            # Only the status assignment lives inside the `with` — the
            # response writes below stay outside the `try` entirely, as
            # they did before metrics existed. A client that disconnects
            # mid-write (closed tab, aborted fetch) would otherwise raise
            # BrokenPipeError *inside* the `with`, which `Recorder.record`
            # treats as a handler failure and overwrites `span.status` to
            # 500 — recording a successful (or correctly-404'd) delete as a
            # server error, then attempting a second response on a
            # half-written connection.
            with self.deps.metrics.record(label, "DELETE") as span:
                removed = handler(*args)
                span.status = HTTPStatus.NO_CONTENT if removed else HTTPStatus.NOT_FOUND
        except Exception as exc:
            self._send_error_json(_translate_route_exception(label, exc))
            return
        if not removed:
            # Name the thing the route deletes. Router labels read
            # "<noun> delete", so dropping the verb gives "conversation",
            # "syntax correction". This was hardcoded to "conversation" while
            # that was the only DELETE route, and silently lied once it wasn't.
            noun = label.removesuffix(" delete")
            self._send_error_json(_HTTPError(HTTPStatus.NOT_FOUND, f"{noun} not found"))
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
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
        self._send_common_headers()
        self.end_headers()
        self.wfile.write(data)


def make_handler(deps: ServerDeps):
    class _Bound(ChatHandler):
        pass

    _Bound.deps = deps
    return _Bound


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _default_loopback_origins(port: int) -> frozenset[str]:
    """Dev-server origins allowed when bound to loopback.

    Vite (`npm run dev`) serves the UI on :5173 and proxies `/api` to
    this process, so the browser's Origin is the Vite port — not the
    API port. Same-origin production (`--static`) uses the API port.
    """

    bases = (
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )
    return frozenset(bases)


def _start_syntax_warmup() -> threading.Thread:
    """Load the Stanza pipeline in the background while the server accepts traffic.

    The pipeline costs ~4.5 s to build and is process-wide. Left lazy, that
    lands on whoever first opens a syntax diagram (measured: 4,499 ms for a
    request whose parse was 111 ms). Doing it here overlaps the load with
    startup and with early requests, which need no parser.

    Daemon thread on purpose: a warm-up in flight must not keep the process
    alive at ctrl-c, and nothing waits on the result. `warm_pipeline` handles
    its own failures — a missing `[lemma]` extra or an undownloaded model
    just leaves the endpoint on its old lazy path.
    """

    def _warm() -> None:
        from ..syntax.parse import warm_pipeline

        if warm_pipeline():
            print("syntax: parser ready.", flush=True)

    thread = threading.Thread(target=_warm, name="syntax-warmup", daemon=True)
    thread.start()
    return thread


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
    metrics_conn: sqlite3.Connection | None = None,
) -> None:
    is_loopback = host in _LOOPBACK_HOSTS
    origins = allowed_origins
    if is_loopback:
        origins = _default_loopback_origins(port) | allowed_origins
    # One lock instance shared between the Recorder (which writes through
    # metrics_conn) and Task 6's read handlers (which query the same
    # connection from other worker threads). A private lock inside the
    # Recorder would not serialize against those readers.
    metrics_lock = threading.Lock()
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
        metrics=Recorder(metrics_conn, metrics_lock),
        metrics_conn=metrics_conn,
        metrics_lock=metrics_lock,
        cors_wildcard=False,
        allowed_origins=origins,
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
    origins_repr = ",".join(sorted(origins)) if origins else "(none)"
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
    _start_syntax_warmup()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
        server.shutdown()
        server.server_close()
