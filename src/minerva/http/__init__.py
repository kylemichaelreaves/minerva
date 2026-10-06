"""HTTP layer for `minerva serve`.

`server_core` holds the shared types (`ServerDeps`, `_HTTPError`,
`_RateLimiter`) consumed by both the request loop and the handlers.
`handlers/` is the per-endpoint package — its `__init__` re-exports
every `_handle_*` function, which is what `router.py` and `serve.py`
import.
"""
