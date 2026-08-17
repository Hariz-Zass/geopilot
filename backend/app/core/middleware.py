from __future__ import annotations

import logging
import re
import uuid
from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import request_id_context

logger = logging.getLogger("geopilot.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        candidate = request.headers.get("X-Request-ID", "")
        request_id = (
            candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request failure path=%s", request.url.path)
            raise
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            logger.info(
                "request method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            request_id_context.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
