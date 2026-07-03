import hmac
import time
from collections.abc import Collection
from logging import Logger

import config as config_module
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

DEFAULT_PUBLIC_PATHS = frozenset({"/api/health", "/metrics"})


def _config():
    return config_module.config


def register_middleware(
    app: FastAPI,
    *,
    logger: Logger,
    public_paths: Collection[str] = DEFAULT_PUBLIC_PATHS,
) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def internal_token_auth(request: Request, call_next):
        current_config = _config()
        path = request.url.path
        if request.method == "OPTIONS" or path in public_paths or not path.startswith("/api"):
            return await call_next(request)
        if not current_config.INTERNAL_API_TOKEN:
            if current_config.INTERNAL_API_ALLOW_MISSING_TOKEN:
                return await call_next(request)
            return JSONResponse({"detail": "internal authentication is misconfigured"}, status_code=503)

        provided = request.headers.get("X-Internal-Token", "")
        if not hmac.compare_digest(provided, current_config.INTERNAL_API_TOKEN):
            return JSONResponse({"detail": "unauthorized internal request"}, status_code=401)

        return await call_next(request)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)")
        return response
