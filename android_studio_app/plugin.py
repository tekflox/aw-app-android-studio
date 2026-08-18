"""Entrypoint referenced by aw-app.json's ``runtime.entrypoint``
("android_studio_app.plugin:AndroidStudioAppPlugin").

No subprocess, no venv, no port: every tool is a plain HTTPS call to
aw-backend's remote-hosts routes, served in-process — same shape as
aw-app-google-maps.

Config/secrets are resolved through a callable rather than read once, so
saving a setting takes effect on the next tool call with no restart. See
``mcp/remote_host.py`` and ``mcp/adb_tools.py``.
"""
from __future__ import annotations

import logging
import os

from . import mcp_config, routes as routes_mod
from .mcp import adb_tools, remote_host

log = logging.getLogger("aw_apps.android-studio")


class AndroidStudioAppPlugin:
    async def activate(self, ctx) -> None:
        self.ctx = ctx

        def _resolve_config() -> dict:
            return {
                "remote_backend_url": ctx.config.get("remote_backend_url") or "",
                "remote_workspace": ctx.config.get("remote_workspace") or "",
                "remote_token": ctx.secrets.read(routes_mod.SECRET_KEY) or "",
                "remote_host_id": ctx.config.get("remote_host_id") or "",
                "adb_path": ctx.config.get("adb_path") or "",
                "default_device_serial": ctx.config.get("default_device_serial") or "",
                "screenshot_dir": ctx.config.get("screenshot_dir") or "",
            }

        remote_host.set_config_resolver(_resolve_config)
        adb_tools.set_config_resolver(_resolve_config)

        ctx.routes.register(routes_mod.build_routes(ctx))

        port = int(os.environ.get("AW_PORT") or 9030)
        # Rebuilt every boot rather than persisted: the entry embeds this
        # process's hostname and API key, both of which change when the
        # workspace container is recreated.
        doc = mcp_config.write_mcp_json(ctx.package_dir, port)

        log.info(
            "aw-app-android-studio activated: mcp server=%s, tools=%s, remote-hosts=%s",
            sorted(doc["mcpServers"]),
            len(adb_tools.TOOLS),
            "configured" if remote_host.configured() else f"NOT SET ({remote_host.missing_settings()})",
        )

    async def deactivate(self) -> None:
        log.info("aw-app-android-studio deactivated")
