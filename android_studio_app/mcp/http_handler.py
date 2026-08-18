"""The ``aw-android-studio`` MCP server, over Streamable HTTP (``POST /mcp``).

The monolith served these same 13 tools over **stdio**, as a subprocess its
gateway respawned. That shape does not port: aw-mcp-gateway spawns stdio
children inside its own container, which has neither this app's code nor its
config/secret store. Serving MCP from this app's own already-authenticated
route sidesteps both — the gateway just makes an HTTP call. Same mechanism as
aw-app-google-maps and aw-app-notion's ``aw-kanban`` server.

Unlike google-maps there is no single "configured or not" gate here: a tool
call can supply enough via per-call overrides (remote_host_id, adb_path) to
work even when the app's own default config is incomplete, and NotConfigured
only fires once the actual attempt is made — see adb_tools.py / remote_host.py.
So every NotConfigured raised by a handler is simply caught below and
reported as a tool error, naming exactly what's missing.
"""
from __future__ import annotations

import logging

from fastapi.concurrency import run_in_threadpool

from . import adb_tools, remote_host

log = logging.getLogger("aw_apps.android-studio")

SERVER_NAME = "aw-android-studio"
SERVER_VERSION = "1.0.0"

TOOLS_SCHEMA = adb_tools.TOOLS


def _result(req_id, text: str, is_error: bool) -> dict:
    return {"jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": text}],
                       "isError": is_error}}


async def handle_request(request: dict) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    params = request.get("params") or {}
    name = params.get("name", "")
    args = params.get("arguments") or {}

    handler = adb_tools.HANDLERS.get(name)
    if not handler:
        return _result(req_id, f"Unknown tool: {name}", True)

    try:
        # Handlers use blocking urllib against aw-backend, so they must not
        # run on the event loop — a slow remote-host round trip would stall
        # every other app route in this process.
        text = await run_in_threadpool(handler, args)
    except remote_host.NotConfigured as exc:
        return _result(req_id, str(exc), True)
    except Exception as exc:  # noqa: BLE001 — last resort, must not 500 the route
        log.exception("android-studio MCP tool %s failed", name)
        return _result(req_id, f"{name} failed: {exc}", True)

    return _result(req_id, text, False)
