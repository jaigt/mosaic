"""
Structured logging + request-ID propagation for the FastAPI backend.

Stdlib-only. Provides:
  * ``install_request_id_middleware(app)`` — generates/propagates an
    ``X-Request-ID`` header and binds it to a contextvar for the lifetime of
    the request so any code (handlers, log helpers) can read the current id.
  * ``get_request_id()`` — the id bound to the current context, or ``"-"``.
  * ``log_event(level, event, **fields)`` — emit a single JSON log line that
    always includes the active request id.

Kept deliberately small: no extra pip dependencies, Python 3.9 compatible.
"""
import json
import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"

# Bound per-request; default "-" so logging outside a request never crashes.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("backend.api")


def get_request_id() -> str:
    """Return the request id bound to the current context (or ``"-"``)."""
    return _request_id.get()


def set_request_id(value: str) -> object:
    """Bind a request id; returns the token for later reset."""
    return _request_id.set(value)


def reset_request_id(token: object) -> None:
    _request_id.reset(token)


def new_request_id() -> str:
    return str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate or propagate an X-Request-ID and expose it via contextvar."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        rid = incoming if incoming else new_request_id()
        token = _request_id.set(rid)
        # Also stash on request.state for handlers that prefer that idiom.
        try:
            request.state.request_id = rid
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response


def install_request_id_middleware(app) -> None:
    """Attach the request-id middleware to a FastAPI/Starlette app."""
    app.add_middleware(RequestIDMiddleware)


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def log_event(level: str, event: str, request_id: Optional[str] = None, **fields) -> None:
    """Emit a single structured JSON log line.

    Always includes ``event`` and ``request_id``. Extra keyword fields are
    merged in; values that aren't JSON-serializable are coerced to ``str``.
    """
    payload = {"event": event, "request_id": request_id or get_request_id()}
    payload.update(fields)
    try:
        line = json.dumps(payload, default=str)
    except (TypeError, ValueError):  # pragma: no cover - default=str covers most
        line = json.dumps({k: str(v) for k, v in payload.items()})
    logger.log(_LEVELS.get(level.upper(), logging.INFO), line)
