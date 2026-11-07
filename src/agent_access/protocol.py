"""The Model Context Protocol's JSON-RPC messages, for any transport.

``handle(message, server)`` answers one JSON-RPC message (or a batch) and
returns the response, or None for a notification. The HTTP transport
(``src/sync/server.py``) and the stdio transport (``stdio.py``) both use it.

Only what a tool server needs: ``initialize``, ``ping``, ``tools/list`` and
``tools/call``. The server keeps no session: every request carries its
token, so any sync service replica can answer it.
"""

import json
import logging
import traceback

from .tools import ToolError, Tools

logger = logging.getLogger("agent-access")

# Newest first. A client asking for another version gets the newest.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def handle(message, tools: Tools):
    """The response to ``message`` (a dict, or a list for a batch), or None."""
    if isinstance(message, list):
        if not message:
            return _error(None, INVALID_REQUEST, "empty batch")
        answers = [a for a in (handle_one(m, tools) for m in message) if a is not None]
        return answers or None
    return handle_one(message, tools)


def handle_one(message, tools: Tools):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "not a JSON-RPC 2.0 message")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    if not isinstance(method, str):
        # A response from the client (we send no requests), or garbage.
        return None if "result" in message or "error" in message else \
            _error(msg_id, INVALID_REQUEST, "no method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return None if is_notification else _error(msg_id, INVALID_PARAMS, "params must be an object")
    if is_notification:
        return None
    try:
        if method == "initialize":
            return _result(msg_id, initialize(params, tools))
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": tools.definitions()})
        if method == "tools/call":
            return _result(msg_id, call_tool(params, tools))
        if method in ("resources/list", "prompts/list"):
            return _result(msg_id, {method.split("/")[0]: []})
        return _error(msg_id, METHOD_NOT_FOUND, f"unknown method {method!r}")
    except _InvalidParams as e:
        return _error(msg_id, INVALID_PARAMS, str(e))
    except Exception:  # noqa: BLE001 - the client gets an error, the log the rest
        logger.error("MCP %s failed:\n%s", method, traceback.format_exc())
        return _error(msg_id, INTERNAL_ERROR, "internal error")


class _InvalidParams(ValueError):
    pass


def initialize(params: dict, tools: Tools) -> dict:
    asked = params.get("protocolVersion")
    version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": tools.server_name(), "title": tools.server_title(),
                       "version": tools.server_version()},
        "instructions": tools.instructions(),
    }


def call_tool(params: dict, tools: Tools) -> dict:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not tools.has(name):
        raise _InvalidParams(f"unknown tool {name!r}")
    if not isinstance(arguments, dict):
        raise _InvalidParams("arguments must be an object")
    try:
        result = tools.call(name, arguments)
    except ToolError as e:
        # A tool error is the assistant's to read and act on, not a protocol error.
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    # Pictures (plots drawn as PNG) go to the assistant as image content.
    images = result.pop("_images", []) if isinstance(result, dict) else []
    text = json.dumps(result, indent=1, default=str)
    content = [{"type": "text", "text": text}]
    for number, image in enumerate(images, start=1):
        content.append({"type": "text", "text": f"Image {number}: {image['title']}"})
        content.append({"type": "image", "data": image["data"], "mimeType": "image/png"})
    return {"content": content, "structuredContent": result, "isError": False}
