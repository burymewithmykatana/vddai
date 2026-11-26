from time import perf_counter_ns
from uuid import uuid4

from fastapi.routing import APIRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import (
    LogError,
    LogEvent,
    elapsed_ms,
    log_event,
    request_id_context,
)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = request_id_context.set(uuid4().hex)
        started_ns = perf_counter_ns()
        http_status = None
        finished = False

        async def track_response(message: Message) -> None:
            nonlocal http_status
            if message["type"] == "http.response.start":
                http_status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, track_response)
            finished = True
        finally:
            route = scope.get("route")
            outcome = "error"
            if finished and http_status is not None and http_status < 500:
                outcome = "rejected" if http_status >= 400 else "ok"
            try:
                log_event(
                    LogEvent.HTTP_REQUEST,
                    service="api",
                    status=outcome,
                    latency_ms=elapsed_ms(started_ns),
                    error_code=LogError.REQUEST_FAILED if outcome == "error" else None,
                    method=scope["method"],
                    route=route.path if isinstance(route, APIRoute) else None,
                    http_status=http_status,
                )
            finally:
                request_id_context.reset(token)
