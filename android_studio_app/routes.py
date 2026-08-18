"""This app's backend sub-app, mounted by the runtime at
``/api/apps/android-studio`` behind the workspace's IdentityGuard.

The bearer token goes to ``ctx.secrets`` via ``POST /settings``, never
through the generic config path — that would land a credential capable of
running arbitrary commands on Frederico's Mac in plain, cloud-syncable app
config. The other three settings (backend URL, workspace slug, host id) are
not secrets and go through the normal ``POST /api/apps/android-studio/config``
route core already provides — this file only adds what that route can't:
the token, a status readout, and a real connectivity check.
"""
from __future__ import annotations

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import mcp_config
from .mcp import adb_tools, remote_host

SECRET_KEY = "remote_token"


def build_routes(ctx) -> FastAPI:
    app = FastAPI(title="android-studio")

    @app.get("/status")
    async def status() -> dict:
        token = ctx.secrets.read(SECRET_KEY) or ""
        return {
            # "logged_in" is what windows/main.json's auth_status widget binds to.
            "logged_in": bool(token),
            "configured": remote_host.configured(),
            "missing": remote_host.missing_settings(),
            "remote_host_id": adb_tools.current_config().get("remote_host_id") or "",
            "tools": [t["name"] for t in adb_tools.TOOLS],
            "mcp_server": mcp_config.SERVER_NAME,
        }

    @app.post("/settings")
    async def save_settings(data: dict = Body(...)) -> dict:
        token = (data.get(SECRET_KEY) or "").strip()
        if not token:
            return JSONResponse({"ok": False, "error": f"{SECRET_KEY} is required"},
                                status_code=400)
        ctx.secrets.write(SECRET_KEY, token)
        # No restart, no gateway reload: remote_host.py resolves the token per
        # call, so the very next tool call already uses it.
        return {"ok": True, "logged_in": True}

    @app.post("/logout")
    async def clear_token() -> dict:
        ctx.secrets.delete(SECRET_KEY)
        return {"ok": True, "logged_in": False}

    @app.post("/test")
    async def test_connection(data: dict = Body(default={})) -> dict:
        """Run a real `adb devices` on the configured host so a saved token is
        proved, not assumed — a token can be present and still be wrong
        (revoked, wrong workspace, host offline), all of which look identical
        to "configured" until something actually calls out."""
        host_override = (data.get("remote_host_id") or "").strip() or None
        if not remote_host.configured(host_override):
            return JSONResponse(
                {"ok": False, "error": remote_host.missing_settings(host_override)},
                status_code=400)
        try:
            text = adb_tools._handle_adb_devices({"remote_host_id": host_override})
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller, not a 500
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=502)
        return {"ok": True, "result": text[:1500]}

    @app.get("/mcp.json")
    async def mcp_json() -> dict:
        return {"mcpServers": mcp_config.build_mcp_servers()}

    # ------------------------------------------------------------------
    # MCP — Streamable HTTP, auto-discovered by aw-mcp-gateway's app-scan.
    # ------------------------------------------------------------------

    @app.post("/mcp")
    async def mcp_post(data: dict | list = Body(...)):
        from .mcp.http_handler import handle_request

        messages = data if isinstance(data, list) else [data]
        responses = []
        for m in messages:
            r = await handle_request(m)
            if r is not None:
                responses.append(r)
        if not responses:
            return Response(status_code=202)
        return JSONResponse(responses if isinstance(data, list) else responses[0])

    @app.get("/mcp")
    async def mcp_get():
        return Response(status_code=405)

    return app
