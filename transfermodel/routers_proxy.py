import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from transfermodel import config
from transfermodel.proxy import forward_to_upstream
from transfermodel.storage import load_providers
from transfermodel.usage_tracker import get_tracker

logger = logging.getLogger("transfermodel.proxy")
router = APIRouter()


def _find_provider(model: str, api_type: str) -> tuple:
    providers = load_providers()
    candidates = [
        p
        for p in providers
        if p.enabled and p.api_type == api_type and model in p.models
    ]
    candidates.sort(key=lambda p: (p.priority, p.created_at))

    if not candidates:
        all_models = []
        for p in providers:
            if p.enabled and p.api_type == api_type:
                all_models.extend(p.models)
        return None, JSONResponse(
            {
                "error": {
                    "message": f"No provider configured for model '{model}'.",
                    "available_models": sorted(set(all_models)),
                }
            },
            status_code=400,
        )
    return candidates[0], None


@router.post("/v1/messages")
async def proxy_anthropic(request: Request):
    return await _handle_proxy(request, "anthropic", "/v1/messages")


@router.post("/v1/chat/completions")
async def proxy_openai(request: Request):
    return await _handle_proxy(request, "openai", "/v1/chat/completions")


async def _handle_proxy(request: Request, api_type: str, path: str):
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": "Invalid JSON body"}}, status_code=400
        )

    model = data.get("model", "")
    if not model:
        return JSONResponse(
            {"error": {"message": "Missing 'model' in request body"}}, status_code=400
        )

    stream = data.get("stream", False)
    provider, err = _find_provider(model, api_type)
    if err:
        return err

    tracker = get_tracker()
    tracker.start_request(provider.name, model, api_type)

    client_ip = request.client.host if request.client else "?"
    logger.info(
        "[%s] %s model=%s stream=%s → %s",
        client_ip, api_type, model, provider.name,
    )

    t0 = time.monotonic()
    headers = dict(request.headers)
    try:
        resp = await forward_to_upstream(
            base_url=provider.base_url,
            path=path,
            api_key=provider.api_key,
            api_type=api_type,
            method="POST",
            request_headers=headers,
            body=body,
            timeout_seconds=provider.timeout_seconds,
        )
        elapsed = (time.monotonic() - t0) * 1000

        # Log completion with token usage and response text
        snap = tracker.get_snapshot()
        totals = tracker.get_totals()
        resp_preview = snap.response_text[: config.LOG_RESPONSE_PREVIEW_CHARS].replace("\n", " ")
        logger.info(
            "[%s] %s model=%s → HTTP %s (%.0fms) "
            "tokens: in=%d out=%d cache_r=%d cache_w=%d | total: in=%d out=%d",
            client_ip, api_type, model, resp.status_code, elapsed,
            snap.input_tokens, snap.output_tokens, snap.cache_read, snap.cache_write,
            totals["total_input"], totals["total_output"],
        )
        if resp_preview:
            logger.info("[%s] response: %s", client_ip, resp_preview)

        return resp
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error(
            "[%s] %s model=%s → ERROR %s (%.0fms)",
            client_ip, api_type, model, e, elapsed,
        )
        raise


@router.get("/v1/models")
async def list_models():
    providers = load_providers()
    models = []
    for p in providers:
        if not p.enabled:
            continue
        for m in p.models:
            models.append(
                {
                    "id": m,
                    "object": "model",
                    "created": int(
                        datetime.fromisoformat(p.created_at).timestamp()
                    ),
                    "owned_by": p.name,
                }
            )
    return {"object": "list", "data": models}
