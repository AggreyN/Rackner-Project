"""JSON logging to stdout — CloudWatch-ready without any AWS code.

In ECS, awslogs ships container stdout to CloudWatch; locally the same lines
print to the terminal. So the app only ever writes JSON to stdout and the
transport is infra's problem, which is the whole trick.

Every access line carries: request id, method, route TEMPLATE, status, latency,
and the token's `sub` when one is present. Two redaction rules, enforced here
rather than by convention:

  * The route template, not the raw path — /opportunities/{opportunity_id}
    rather than /opportunities/HC1084-26-R-0042, so opportunity ids the user
    searches stay out of the logs.
  * A field-name denylist. Anything a log call passes under a secret-ish key
    (authorization, token, password, ...) is replaced with "[REDACTED]" before
    serialization. Document text never has a field here at all.
"""

from __future__ import annotations

import json
import logging
import sys
import time

_REDACT = {
    "authorization",
    "access_token",
    "token",
    "jwt",
    "password",
    "secret",
    "api_key",
    "cookie",
    "set-cookie",
}

# stdlib LogRecord attributes — everything else on a record is a custom field.
_STDLIB_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STDLIB_ATTRS or key.startswith("_"):
                continue
            entry[key] = "[REDACTED]" if key.lower() in _REDACT else value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup() -> None:
    """Install the JSON formatter on the root logger. Idempotent."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # uvicorn's own access line would duplicate ours (and log raw paths).
    logging.getLogger("uvicorn.access").disabled = True


class AccessLogMiddleware:
    """Pure-ASGI middleware: request id + one JSON access line per request.

    ASGI rather than BaseHTTPMiddleware so it adds no threadpool hop, and the
    response header carries X-Request-Id so a user-reported error can be joined
    to its log line.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import uuid

        request_id = uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or scope.get("path", "")
            logging.getLogger("access").info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", ""),
                    # Route TEMPLATE, so ids stay out of the logs.
                    "route": template,
                    "status": status_holder["status"],
                    "latency_ms": round((time.perf_counter() - start) * 1000, 1),
                    "user_sub": _sub_from_scope(scope),
                },
            )


def _sub_from_scope(scope) -> str | None:
    """The token's `sub` claim, for joining logs to a user.

    Claims-only decode — no signature check, because this is telemetry, not
    authorization; the route dependency does the real validation. The token
    itself is never logged.
    """
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            parts = value.decode("latin-1").split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                try:
                    from jose import jwt

                    return jwt.get_unverified_claims(parts[1]).get("sub")
                except Exception:
                    return None
    return None
