import json
import logging

import httpx
from fastapi.responses import StreamingResponse, JSONResponse

from transfermodel import config
from transfermodel.usage_tracker import get_tracker

logger = logging.getLogger("transfermodel.proxy")
HOP_BY_HOP = {
    "transfer-encoding",
    "content-length",
    "content-encoding",
    "connection",
    "keep-alive",
    "host",
}


def rewrite_headers(
    incoming: dict[str, str],
    provider_base_url: str,
    provider_api_key: str,
    api_type: str,
) -> dict[str, str]:
    headers = {}
    for k, v in incoming.items():
        if k.lower() in HOP_BY_HOP:
            continue
        if k.lower() in ("x-api-key", "authorization"):
            continue
        headers[k] = v

    headers["host"] = _extract_host(provider_base_url)
    if api_type == "anthropic":
        headers["x-api-key"] = provider_api_key
        if "anthropic-version" not in {k.lower() for k in headers}:
            headers["anthropic-version"] = config.ANTHROPIC_VERSION
    else:
        headers["authorization"] = f"Bearer {provider_api_key}"
    return headers


def _extract_host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def _body_wants_stream(body: bytes | None) -> bool:
    if not body:
        return False
    try:
        data = json.loads(body)
        return data.get("stream", False) is True
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


async def forward_to_upstream(
    base_url: str,
    path: str,
    api_key: str,
    api_type: str,
    method: str,
    request_headers: dict[str, str],
    body: bytes | None = None,
    timeout_seconds: int = 120,
) -> StreamingResponse | JSONResponse:
    upstream_url = f"{base_url.rstrip('/')}{path}"
    outgoing_headers = rewrite_headers(request_headers, base_url, api_key, api_type)
    wants_stream = _body_wants_stream(body)

    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
            if wants_stream:
                upstream_resp = await _stream_request(
                    client, method, upstream_url, outgoing_headers, body
                )
            else:
                upstream_resp = await client.request(
                    method=method,
                    url=upstream_url,
                    headers=outgoing_headers,
                    content=body,
                )
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": {"message": "Upstream request timed out"}}, status_code=504
        )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": {"message": f"Upstream connection failed: {str(e)}"}},
            status_code=502,
        )

    content_type = upstream_resp.headers.get("content-type", "")
    is_sse = content_type.startswith("text/event-stream")

    if is_sse:
        resp_headers = _filter_headers(upstream_resp.headers)
        tracker = get_tracker()

        async def tracked_stream():
            buffer = b""
            async for chunk in upstream_resp.aiter_bytes():
                yield chunk
                buffer += chunk
                # Parse SSE events from completed frames
                while b"\n\n" in buffer:
                    frame, buffer = buffer.split(b"\n\n", 1)
                    _parse_sse_frame(frame, api_type, tracker)
            # Flush remaining
            if buffer and b"\n\n" not in buffer:
                _parse_sse_frame(buffer, api_type, tracker)
            tracker.end_request()

        return StreamingResponse(
            tracked_stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=content_type,
        )

    # Non-streaming response
    resp_headers = _filter_headers(upstream_resp.headers)
    try:
        resp_json = upstream_resp.json()
    except json.JSONDecodeError:
        resp_json = {"error": {"message": upstream_resp.text[:1000]}}

    # Extract usage from non-stream response
    _extract_nonstream_usage(resp_json, api_type)
    get_tracker().end_request()

    return JSONResponse(
        content=resp_json,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
    )


async def _stream_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
):
    req = client.build_request(method, url, headers=headers, content=body)
    return await client.send(req, stream=True)


def _filter_headers(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


def _parse_sse_frame(frame: bytes, api_type: str, tracker):
    """Parse a raw SSE frame (bytes between \n\n separators) and update tracker."""
    try:
        text = frame.decode("utf-8", errors="replace")
    except Exception:
        return

    # SSE frame format: "event: xxx\ndata: {...}"
    data_str = None
    for line in text.split("\n"):
        if line.startswith("data: "):
            data_str = line[6:]
        elif line.startswith("data:"):
            data_str = line[5:]

    if not data_str:
        return

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return

    if api_type == "anthropic":
        _parse_anthropic_event(data, tracker)
    else:
        _parse_openai_event(data, tracker)


def _parse_anthropic_event(data: dict, tracker):
    event_type = data.get("type", "")

    if event_type == "message_start":
        msg = data.get("message", {})
        usage = msg.get("usage", {})
        tracker.set_input_tokens(
            n=usage.get("input_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0),
            cache_write=usage.get("cache_creation_input_tokens", 0),
        )

    elif event_type == "content_block_delta":
        delta = data.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text:
                tracker.append_text(text)

    elif event_type == "message_delta":
        usage = data.get("usage", {})
        tracker.set_output_tokens(usage.get("output_tokens", 0))


def _parse_openai_event(data: dict, tracker):
    choices = data.get("choices", [])
    if not choices:
        return

    choice = choices[0]
    delta = choice.get("delta", {})
    content = delta.get("content", "")
    if content:
        tracker.append_text(content)

    # OpenAI usage comes in the final chunk
    usage = data.get("usage")
    if usage:
        tracker.set_input_tokens(usage.get("prompt_tokens", 0))
        tracker.set_output_tokens(usage.get("completion_tokens", 0))

    # Also check for reasoning/reasoning_content
    reasoning = delta.get("reasoning_content", "")
    if reasoning:
        tracker.append_text(reasoning)


def _extract_nonstream_usage(resp_json: dict, api_type: str):
    tracker = get_tracker()
    if api_type == "anthropic":
        usage = resp_json.get("usage", {})
        tracker.set_input_tokens(
            n=usage.get("input_tokens", 0),
            cache_read=usage.get("cache_read_input_tokens", 0),
            cache_write=usage.get("cache_creation_input_tokens", 0),
        )
        tracker.set_output_tokens(usage.get("output_tokens", 0))
        # Extract text from content blocks
        for block in resp_json.get("content", []):
            if block.get("type") == "text":
                tracker.append_text(block.get("text", ""))
    else:
        usage = resp_json.get("usage", {})
        tracker.set_input_tokens(usage.get("prompt_tokens", 0))
        tracker.set_output_tokens(usage.get("completion_tokens", 0))
        for choice in resp_json.get("choices", []):
            msg = choice.get("message", {})
            tracker.append_text(msg.get("content", ""))
    tracker.end_request()


# ---------------------------------------------------------------------------
# Responses API adapter (Codex CLI)
# ---------------------------------------------------------------------------

import uuid as _uuid  # noqa: E402

from transfermodel.responses_adapter import (  # noqa: E402
    responses_to_chat_request,
    chat_sse_to_responses_sse,
    chat_response_to_responses,
    responses_to_anthropic_request,
    anthropic_sse_to_responses_sse,
    anthropic_response_to_responses,
)


async def forward_responses(
    base_url: str,
    api_key: str,
    request_headers: dict[str, str],
    body_bytes: bytes,
    timeout_seconds: int = 120,
) -> StreamingResponse | JSONResponse:
    """Forward a Responses-API request via Chat-Completions upstream."""

    body = json.loads(body_bytes)
    resp_id = body.get("id") or f"resp_{_uuid.uuid4().hex[:16]}"
    model = body.get("model", "unknown")
    is_stream = body.get("stream", False)

    chat_body = responses_to_chat_request(body)
    chat_body_bytes = json.dumps(chat_body).encode()
    logger.info("codex→chat request: %s", chat_body_bytes.decode()[:1500])

    chat_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    outgoing_headers = rewrite_headers(
        request_headers, base_url, api_key, "openai"
    )

    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
            if is_stream:
                upstream_resp = await client.send(
                    client.build_request(
                        "POST", chat_url, headers=outgoing_headers,
                        content=chat_body_bytes,
                    ),
                    stream=True,
                )
            else:
                upstream_resp = await client.post(
                    chat_url, headers=outgoing_headers,
                    content=chat_body_bytes,
                )
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": {"message": "Upstream request timed out"}}, status_code=504
        )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": {"message": f"Upstream connection failed: {str(e)}"}},
            status_code=502,
        )

    if is_stream:
        resp_headers = _filter_headers(upstream_resp.headers)

        async def translated_stream():
            tracker = get_tracker()
            buffer = b""
            first_event_sent = False
            async for chunk in upstream_resp.aiter_bytes():
                buffer += chunk
                while b"\n\n" in buffer:
                    raw, buffer = buffer.split(b"\n\n", 1)
                    try:
                        line = raw.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    if line.startswith("data: ") and line[6:].strip() != "[DONE]":
                        try:
                            chat_data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        choices = chat_data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                tracker.append_text(text)
                            usage = chat_data.get("usage")
                            if usage:
                                tracker.set_input_tokens(
                                    usage.get("prompt_tokens", 0))
                                tracker.set_output_tokens(
                                    usage.get("completion_tokens", 0))
                        translated = chat_sse_to_responses_sse(
                            line, resp_id, model)
                        if translated:
                            if not first_event_sent:
                                created = _make_response_created_sse(
                                    resp_id, model)
                                yield (created + "\n").encode()
                                first_event_sent = True
                            yield (translated + "\n").encode()

            yield _make_completed_sse(resp_id, model).encode()
            tracker.end_request()

        return StreamingResponse(
            translated_stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    # Non-streaming
    try:
        chat_data = upstream_resp.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": upstream_resp.text[:1000]}},
            status_code=upstream_resp.status_code,
        )

    resp_data = chat_response_to_responses(chat_data, resp_id, model)
    return JSONResponse(content=resp_data, status_code=upstream_resp.status_code)


def _make_response_created_sse(resp_id: str, model: str) -> str:
    ev = {
        "id": resp_id,
        "object": "response",
        "model": model,
        "output": [],
    }
    return f"event: response.created\ndata: {json.dumps(ev, ensure_ascii=False)}"


def _make_completed_sse(resp_id: str, model: str) -> str:
    ev = {
        "id": resp_id,
        "object": "response",
        "model": model,
        "status": "completed",
    }
    return f"event: response.completed\ndata: {json.dumps(ev, ensure_ascii=False)}"


async def forward_responses_anthropic(
    base_url: str,
    api_key: str,
    request_headers: dict[str, str],
    body_bytes: bytes,
    timeout_seconds: int = 120,
) -> StreamingResponse | JSONResponse:
    """Forward Codex Responses requests to an Anthropic-compatible upstream."""

    body = json.loads(body_bytes)
    resp_id = body.get("id") or f"resp_{_uuid.uuid4().hex[:16]}"
    model = body.get("model", "unknown")
    is_stream = body.get("stream", False)

    anthropic_body = responses_to_anthropic_request(body)
    anthropic_bytes = json.dumps(anthropic_body).encode()
    logger.info("codex→anthropic request: %s", anthropic_bytes.decode()[:1500])

    msgs_url = f"{base_url.rstrip('/')}/v1/messages"
    outgoing_headers = rewrite_headers(
        request_headers, base_url, api_key, "anthropic"
    )

    try:
        async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
            if is_stream:
                upstream_resp = await client.send(
                    client.build_request(
                        "POST", msgs_url, headers=outgoing_headers,
                        content=anthropic_bytes,
                    ),
                    stream=True,
                )
            else:
                upstream_resp = await client.post(
                    msgs_url, headers=outgoing_headers,
                    content=anthropic_bytes,
                )
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": {"message": "Upstream request timed out"}}, status_code=504)
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": {"message": f"Upstream connection failed: {str(e)}"}},
            status_code=502)

    if is_stream:
        resp_headers = _filter_headers(upstream_resp.headers)

        async def translated_anthropic_stream():
            tracker = get_tracker()
            buffer = b""
            async for chunk in upstream_resp.aiter_bytes():
                buffer += chunk
                while b"\n\n" in buffer:
                    raw, buffer = buffer.split(b"\n\n", 1)
                    try:
                        line = raw.decode("utf-8", errors="replace")
                    except Exception:
                        continue

                    event_type = None
                    data_json = None
                    for part in line.split("\n"):
                        if part.startswith("event: "):
                            event_type = part[7:].strip()
                        elif part.startswith("data: "):
                            try:
                                data_json = json.loads(part[6:])
                            except json.JSONDecodeError:
                                pass

                    if event_type and data_json:
                        # Track usage
                        if event_type == "message_start":
                            msg = data_json.get("message", {})
                            usage = msg.get("usage", {})
                            tracker.set_input_tokens(
                                n=usage.get("input_tokens", 0),
                                cache_read=usage.get("cache_read_input_tokens", 0),
                                cache_write=usage.get("cache_creation_input_tokens", 0),
                            )
                        elif event_type == "content_block_delta":
                            delta = data_json.get("delta", {})
                            if delta.get("type") == "text_delta":
                                tracker.append_text(delta.get("text", ""))
                        elif event_type == "message_delta":
                            usage = data_json.get("usage", {})
                            tracker.set_output_tokens(usage.get("output_tokens", 0))

                        results = anthropic_sse_to_responses_sse(
                            event_type, data_json, resp_id, model)
                        for translated in results:
                            yield (translated + "\n").encode()

            tracker.end_request()

        return StreamingResponse(
            translated_anthropic_stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    # Non-streaming
    try:
        anthropic_data = upstream_resp.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"error": {"message": upstream_resp.text[:1000]}},
            status_code=upstream_resp.status_code,
        )

    resp_data = anthropic_response_to_responses(anthropic_data, resp_id, model)
    return JSONResponse(content=resp_data, status_code=upstream_resp.status_code)
