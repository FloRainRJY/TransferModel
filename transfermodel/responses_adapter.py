"""Translate between OpenAI Responses API and Chat Completions API.

Codex CLI uses /v1/responses, but many providers (including DeepSeek)
only support /v1/chat/completions.  This module converts in both
directions so Codex can talk to any OpenAI-compatible backend.
"""

import json
import uuid
import time


# ---------------------------------------------------------------------------
# Request: Responses → Chat Completions
# ---------------------------------------------------------------------------

def responses_to_chat_request(body: dict) -> dict:
    """Convert a Responses-API request body to Chat-Completions format."""
    messages = []

    instructions = body.get("instructions", "")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    inp = body.get("input", "")
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
    elif isinstance(inp, list):
        for block in inp:
            msg = _input_block_to_message(block)
            if msg:
                messages.append(msg)

    chat_body = {"messages": messages}

    for src, dst in [
        ("model", "model"),
        ("max_output_tokens", "max_tokens"),
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("stream", "stream"),
        ("stop", "stop"),
    ]:
        if src in body:
            chat_body[dst] = body[src]

    if "tools" in body:
        chat_body["tools"] = _convert_tools(body["tools"])
    if "tool_choice" in body:
        chat_body["tool_choice"] = body["tool_choice"]

    return chat_body


def _input_block_to_message(block: dict) -> dict | None:
    if not isinstance(block, dict):
        return None
    btype = block.get("type", "")
    role = block.get("role", "user")
    content = block.get("content", "")

    if btype == "message":
        text_parts = []
        tool_calls = []
        tool_outputs = []
        for c in (content if isinstance(content, list) else []):
            ct = c.get("type", "")
            if ct in ("input_text", "output_text"):
                text_parts.append(c.get("text", ""))
            elif ct == "tool_use":
                tool_calls.append({
                    "id": c.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": c.get("name", ""),
                        "arguments": json.dumps(c.get("input", {})),
                    },
                })
            elif ct == "tool_output":
                tool_outputs.append({
                    "tool_call_id": c.get("id", ""),
                    "role": "tool",
                    "content": c.get("output", ""),
                })

        msg = {"role": role}
        if tool_calls:
            msg["tool_calls"] = tool_calls
            if text_parts:
                msg["content"] = "\n".join(text_parts)
            else:
                msg["content"] = None
        else:
            msg["content"] = "\n".join(text_parts) if text_parts else str(content)
        return msg

    return None


def _convert_tools(tools: list) -> list:
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {}),
            },
        })
    return out


# ---------------------------------------------------------------------------
# Response: Chat Completions SSE → Responses API SSE
# ---------------------------------------------------------------------------

def chat_sse_to_responses_sse(line: str, resp_id: str, model: str) -> str | None:
    """Convert one Chat-Completions SSE line to a Responses-API SSE event.

    Returns a string (including "event:" and "data:" lines) or None
    when the input line carries no relevant event.
    """
    if not line.startswith("data: "):
        return None

    data_str = line[6:]
    if data_str.strip() == "[DONE]":
        return None

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return None

    choices = data.get("choices", [])
    if not choices:
        return None

    choice = choices[0]
    delta = choice.get("delta", {})
    finish_reason = choice.get("finish_reason")

    events = []

    # Tool calls
    tool_delta = delta.get("tool_calls")
    if tool_delta:
        for tc in tool_delta:
            fn = tc.get("function", {})
            ev = {
                "type": "response.output_item.added",
                "output_index": tc.get("index", 0),
                "item": {
                    "id": tc.get("id", f"tc_{uuid.uuid4().hex[:12]}"),
                    "type": "tool_use",
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", ""),
                },
            }
            events.append(ev)

    # Text delta
    text = delta.get("content", "")
    if text:
        events.append({
            "type": "response.output_text.delta",
            "delta": text,
        })

    # Finish
    if finish_reason:
        events.append({
            "type": "response.completed",
            "response": {
                "id": resp_id,
                "object": "response",
                "model": model,
            },
        })

    if not events:
        return None

    parts = []
    for ev in events:
        etype = ev.pop("type", "")
        parts.append(f"event: {etype}")
        parts.append(f"data: {json.dumps(ev, ensure_ascii=False)}")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Response: Chat Completions (non-stream) → Responses API
# ---------------------------------------------------------------------------

def chat_response_to_responses(chat_resp: dict, resp_id: str, model: str) -> dict:
    """Convert a complete Chat-Completions response to Responses-API format."""
    choices = chat_resp.get("choices", [])
    choice = choices[0] if choices else {}
    message = choice.get("message", {})
    content_text = message.get("content", "")

    output = [
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": content_text,
                }
            ],
        }
    ]

    tool_calls = message.get("tool_calls", [])
    for tc in tool_calls:
        fn = tc.get("function", {})
        output.append({
            "type": "tool_use",
            "id": tc.get("id", f"tc_{uuid.uuid4().hex[:12]}"),
            "name": fn.get("name", ""),
            "input": json.loads(fn.get("arguments", "{}")),
        })

    usage = chat_resp.get("usage", {})
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }
