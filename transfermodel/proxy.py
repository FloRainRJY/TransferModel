import json
import logging
import time

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
    logger.info("codex→chat request: model=%s stream=%s max_tokens=%s",
                chat_body.get("model"), chat_body.get("stream"), chat_body.get("max_tokens"))

    chat_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    outgoing_headers = rewrite_headers(
        request_headers, base_url, api_key, "openai"
    )

    client = httpx.AsyncClient(timeout=float(timeout_seconds))
    try:
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
        await client.aclose()
        return JSONResponse(
            {"error": {"message": "Upstream request timed out"}}, status_code=504
        )
    except httpx.RequestError as e:
        await client.aclose()
        return JSONResponse(
            {"error": {"message": f"Upstream connection failed: {str(e)}"}},
            status_code=502,
        )

    if is_stream:
        if upstream_resp.status_code >= 400:
            await upstream_resp.aread()
            body_text = upstream_resp.text[:1000]
            logger.error("codex upstream error HTTP %s: %s", upstream_resp.status_code, body_text)
            await client.aclose()
            return JSONResponse(
                {"error": {"message": f"Upstream error: {body_text}"}},
                status_code=upstream_resp.status_code,
            )

        resp_headers = _filter_headers(upstream_resp.headers)

        async def translated_stream():
            tracker = get_tracker()
            msg_item_id = f"msg_{_uuid.uuid4().hex[:16]}"
            reasoning_id = f"rs_{_uuid.uuid4().hex[:12]}"
            item_added = False
            reasoning_added = False
            actual_text = ""
            reasoning_text = ""
            seq = 0
            # Send response.created + response.in_progress immediately
            created = _make_response_created_sse(resp_id, model)
            logger.info("→ codex SSE: response.created")
            yield (created + "\n").encode()
            yield (_make_sse("response.in_progress", {
                "response": {"id": resp_id, "object": "response", "model": model, "status": "in_progress"},
            }) + "\n").encode()
            buffer = b""
            event_count = 0
            try:
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
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            text = delta.get("content") or ""
                            reasoning = delta.get("reasoning_content") or ""

                            # Emit item/part added on first chunk (even empty)
                            if not item_added:
                                item_added = True
                                logger.info("→ codex SSE: output_item.added + content_part.added")
                                yield (_make_sse("response.output_item.added", {
                                    "output_index": 0,
                                    "item": {"id": msg_item_id, "type": "message", "role": "assistant", "status": "in_progress", "content": []},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                                yield (_make_sse("response.content_part.added", {
                                    "output_index": 0,
                                    "content_index": 0,
                                    "part": {"type": "output_text", "text": ""},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1

                            # Reasoning: separate output item + reasoning_text.delta
                            if reasoning:
                                if not reasoning_added:
                                    reasoning_added = True
                                    yield (_make_sse("response.output_item.added", {
                                        "output_index": 1,
                                        "item": {"id": reasoning_id, "type": "reasoning", "status": "in_progress"},
                                        "sequence_number": seq,
                                    }) + "\n").encode(); seq += 1
                                reasoning_text += reasoning
                                tracker.append_text(reasoning)
                                event_count += 1
                                yield (_make_sse("response.reasoning_text.delta", {
                                    "output_index": 1,
                                    "content_index": 0,
                                    "delta": reasoning,
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1

                            # Content: send as response.output_text.delta
                            if text:
                                actual_text += text
                                tracker.append_text(text)
                                event_count += 1
                                yield (_make_sse("response.output_text.delta", {
                                    "item_id": msg_item_id,
                                    "output_index": 0,
                                    "content_index": 0,
                                    "delta": text,
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1

                            usage = chat_data.get("usage")
                            if usage:
                                tracker.set_input_tokens(usage.get("prompt_tokens", 0))
                                tracker.set_output_tokens(usage.get("completion_tokens", 0))
            finally:
                logger.info("→ codex SSE: total %d events, closing stream", event_count)
                if actual_text:
                    yield (_make_sse("response.output_text.done", {
                        "output_index": 0, "content_index": 0, "text": actual_text,
                        "sequence_number": seq,
                    }) + "\n").encode(); seq += 1
                    yield (_make_sse("response.content_part.done", {
                        "output_index": 0, "content_index": 0,
                        "part": {"type": "output_text", "text": actual_text},
                        "sequence_number": seq,
                    }) + "\n").encode(); seq += 1
                yield (_make_sse("response.output_item.done", {
                    "output_index": 0,
                    "item": {"id": msg_item_id, "type": "message", "role": "assistant", "status": "completed",
                             "content": [{"type": "output_text", "text": actual_text}] if actual_text else []},
                    "sequence_number": seq,
                }) + "\n").encode(); seq += 1
                if reasoning_added:
                    yield (_make_sse("response.output_item.done", {
                        "output_index": 1,
                        "item": {"id": reasoning_id, "type": "reasoning", "status": "completed",
                                 "content": [{"type": "output_text", "text": reasoning_text}]},
                        "sequence_number": seq,
                    }) + "\n").encode(); seq += 1
                yield (_make_completed_sse(resp_id, model, msg_item_id, actual_text,
                                            reasoning_id if reasoning_added else "",
                                            reasoning_text if reasoning_added else "") + "\n").encode()
                tracker.end_request()
                await client.aclose()

        # Dump the first 3 events to debug
        import asyncio
        async def debug_stream():
            count = 0
            async for chunk in translated_stream():
                if count < 3:
                    logger.info("DEBUG RAW SSE EVENT: %s", chunk.decode()[:500])
                count += 1
                yield chunk
        return StreamingResponse(
            debug_stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    # Non-streaming
    try:
        chat_data = upstream_resp.json()
    except json.JSONDecodeError:
        await client.aclose()
        return JSONResponse(
            {"error": {"message": upstream_resp.text[:1000]}},
            status_code=upstream_resp.status_code,
        )

    resp_data = chat_response_to_responses(chat_data, resp_id, model)
    logger.info("DEBUG NON-STREAM RESPONSE: %s", json.dumps(resp_data)[:500])
    await client.aclose()
    return JSONResponse(content=resp_data, status_code=upstream_resp.status_code)


def _make_sse(event_type: str, data: dict) -> str:
    ev = {**data, "type": event_type}
    return f"event: {event_type}\ndata: {json.dumps(ev, ensure_ascii=False)}"


def _make_response_created_sse(resp_id: str, model: str) -> str:
    return _make_sse("response.created", {
        "response": {
            "id": resp_id,
            "object": "response",
            "status": "in_progress",
            "model": model,
            "created_at": int(time.time()),
            "output": [],
        },
    })


def _make_completed_sse(resp_id: str, model: str, msg_item_id: str = "", response_text: str = "",
                        reasoning_id: str = "", reasoning_text: str = "") -> str:
    snap = get_tracker().get_snapshot()
    output = []
    if msg_item_id:
        output.append({
            "id": msg_item_id,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": response_text}] if response_text else [],
        })
    if reasoning_id and reasoning_text:
        output.append({
            "id": reasoning_id,
            "type": "reasoning",
            "status": "completed",
            "content": [{"type": "output_text", "text": reasoning_text}],
        })
    return _make_sse("response.completed", {
        "response": {
            "id": resp_id,
            "object": "response",
            "status": "completed",
            "model": model,
            "created_at": int(time.time()),
            "output": output,
            "usage": {
                "input_tokens": snap.input_tokens,
                "output_tokens": snap.output_tokens,
                "total_tokens": snap.input_tokens + snap.output_tokens,
            },
        },
    })


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

    client = httpx.AsyncClient(timeout=float(timeout_seconds))
    try:
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
        await client.aclose()
        return JSONResponse(
            {"error": {"message": "Upstream request timed out"}}, status_code=504)
    except httpx.RequestError as e:
        await client.aclose()
        return JSONResponse(
            {"error": {"message": f"Upstream connection failed: {str(e)}"}},
            status_code=502)

    if is_stream:
        ct = upstream_resp.headers.get("content-type", "")
        if not ct.startswith("text/event-stream"):
            await upstream_resp.aread()
            logger.warning(
                "Expected SSE but got %s, body: %s",
                ct, upstream_resp.text[:500],
            )
            await client.aclose()
            return JSONResponse(
                {"error": {"message": upstream_resp.text[:1000]}},
                status_code=upstream_resp.status_code,
            )

        resp_headers = _filter_headers(upstream_resp.headers)

        async def translated_anthropic_stream():
            tracker = get_tracker()
            msg_item_id = f"msg_{_uuid.uuid4().hex[:16]}"
            reasoning_id = f"rs_{_uuid.uuid4().hex[:12]}"
            seq = 0
            started = False
            item_added = False
            reasoning_added = False
            actual_text = ""
            reasoning_text = ""
            buffer = b""
            try:
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

                        if not event_type or not data_json:
                            continue

                        if event_type == "message_start":
                            msg = data_json.get("message", {})
                            usage = msg.get("usage", {})
                            tracker.set_input_tokens(
                                n=usage.get("input_tokens", 0),
                                cache_read=usage.get("cache_read_input_tokens", 0),
                                cache_write=usage.get("cache_creation_input_tokens", 0),
                            )
                            stream_model = msg.get("model") or model
                            if not started:
                                started = True
                                yield (_make_sse("response.created", {
                                    "response": {
                                        "id": resp_id, "object": "response", "status": "in_progress",
                                        "model": stream_model, "created_at": int(time.time()), "output": [],
                                    },
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                                yield (_make_sse("response.in_progress", {
                                    "response": {"id": resp_id, "object": "response", "model": stream_model, "status": "in_progress"},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                                # Always emit message item (even before text appears)
                                item_added = True
                                yield (_make_sse("response.output_item.added", {
                                    "output_index": 0,
                                    "item": {"id": msg_item_id, "type": "message", "role": "assistant", "status": "in_progress", "content": []},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                                yield (_make_sse("response.content_part.added", {
                                    "output_index": 0, "content_index": 0,
                                    "part": {"type": "output_text", "text": ""},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1

                        elif event_type == "content_block_start":
                            cb = data_json.get("content_block", {})
                            cb_type = cb.get("type", "")
                            if cb_type == "text":
                                pass  # message item already added at stream start
                            elif cb_type == "thinking":
                                if not reasoning_added:
                                    reasoning_added = True
                                    yield (_make_sse("response.output_item.added", {
                                        "output_index": 1,
                                        "item": {"id": reasoning_id, "type": "reasoning", "status": "in_progress"},
                                        "sequence_number": seq,
                                    }) + "\n").encode(); seq += 1

                        elif event_type == "content_block_delta":
                            delta = data_json.get("delta", {})
                            delta_type = delta.get("type", "")
                            if delta_type == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    actual_text += text
                                    tracker.append_text(text)
                                    yield (_make_sse("response.output_text.delta", {
                                        "item_id": msg_item_id, "output_index": 0, "content_index": 0,
                                        "delta": text, "sequence_number": seq,
                                    }) + "\n").encode(); seq += 1
                            elif delta_type == "thinking_delta":
                                thinking = delta.get("thinking", "")
                                if thinking:
                                    reasoning_text += thinking
                                    tracker.append_text(thinking)
                                    yield (_make_sse("response.reasoning_text.delta", {
                                        "output_index": 1, "content_index": 0,
                                        "delta": thinking, "sequence_number": seq,
                                    }) + "\n").encode(); seq += 1

                        elif event_type == "content_block_stop":
                            pass  # handled at message_stop

                        elif event_type == "message_delta":
                            usage = data_json.get("usage", {})
                            tracker.set_output_tokens(usage.get("output_tokens", 0))

                        elif event_type == "message_stop":
                            if actual_text:
                                yield (_make_sse("response.output_text.done", {
                                    "output_index": 0, "content_index": 0, "text": actual_text,
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                                yield (_make_sse("response.content_part.done", {
                                    "output_index": 0, "content_index": 0,
                                    "part": {"type": "output_text", "text": actual_text},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                            yield (_make_sse("response.output_item.done", {
                                "output_index": 0,
                                "item": {"id": msg_item_id, "type": "message", "role": "assistant", "status": "completed",
                                         "content": [{"type": "output_text", "text": actual_text}] if actual_text else []},
                                "sequence_number": seq,
                            }) + "\n").encode(); seq += 1
                            if reasoning_added:
                                yield (_make_sse("response.output_item.done", {
                                    "output_index": 1,
                                    "item": {"id": reasoning_id, "type": "reasoning", "status": "completed",
                                             "content": [{"type": "output_text", "text": reasoning_text}]},
                                    "sequence_number": seq,
                                }) + "\n").encode(); seq += 1
                            yield (_make_completed_sse(resp_id, model, msg_item_id, actual_text,
                                                        reasoning_id if reasoning_added else "",
                                                        reasoning_text if reasoning_added else "") + "\n").encode()
            except Exception:
                logger.warning("Stream read interrupted", exc_info=True)
            finally:
                tracker.end_request()
                await client.aclose()

        async def debug_anthropic_stream():
            count = 0
            async for chunk in translated_anthropic_stream():
                if count < 3:
                    logger.info("DEBUG ANTHROPIC SSE EVENT: %s", chunk.decode()[:500])
                    count += 1
                yield chunk
        return StreamingResponse(
            debug_anthropic_stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    # Non-streaming
    try:
        anthropic_data = upstream_resp.json()
    except json.JSONDecodeError:
        await client.aclose()
        return JSONResponse(
            {"error": {"message": upstream_resp.text[:1000]}},
            status_code=upstream_resp.status_code,
        )

    resp_data = anthropic_response_to_responses(anthropic_data, resp_id, model)
    await client.aclose()
    return JSONResponse(content=resp_data, status_code=upstream_resp.status_code)
