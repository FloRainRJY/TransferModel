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
