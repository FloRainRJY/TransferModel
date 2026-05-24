import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from transfermodel.routers_proxy import router as proxy_router

logger = logging.getLogger("transfermodel.access")


def create_app() -> FastAPI:
    app = FastAPI(title="TransferModel", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "%s %s → HTTP %s (%.0fms)",
            request.method, request.url.path, response.status_code, elapsed,
        )
        return response

    app.include_router(proxy_router)
    return app
