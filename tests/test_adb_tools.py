"""adb_tools.py + http_handler.py — dispatch, config resolution, and the
screenshot two-hop path that exists specifically to avoid the 1 MiB exec
stdout cap silently truncating a PNG.

No real network: every test that would call out stubs remote_host.exec /
remote_host.download / remote_host.upload / remote_host.expanduser.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from android_studio_app.mcp import adb_tools, http_handler, remote_host  # noqa: E402

_FULL_CFG = {
    "remote_backend_url": "https://api.aw.tekflox.com",
    "remote_workspace": "aw",
    "remote_token": "awlk_test",
    "remote_host_id": "824decc7e0610089",
    "adb_path": "~/Android/platform-tools/adb",
    "default_device_serial": "",
    "screenshot_dir": ".tmp/android-studio/",
}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    adb_tools.set_config_resolver(lambda: dict(_FULL_CFG))
    remote_host.set_config_resolver(lambda: dict(_FULL_CFG))
    monkeypatch.setenv("AW_WORKSPACE_CONTAINER_DIR", "/opt/aw-workspace")
    yield
    adb_tools.set_config_resolver(lambda: {})
    remote_host.set_config_resolver(lambda: {})


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_all_13_monolith_tools_survived_the_port():
    names = {t["name"] for t in adb_tools.TOOLS}
    assert names == {
        "adb_devices", "adb_shell", "adb_tap", "adb_swipe", "adb_text",
        "adb_keyevent", "adb_screenshot", "adb_push", "adb_launch_app",
        "adb_stop_app", "adb_list_packages", "adb_media_scan", "upload_file",
    }
    assert names == set(adb_tools.HANDLERS)


def test_adb_bin_expands_tilde_against_remote_host(monkeypatch):
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=20, host_override=None: ("/Users/aw", "", 0))
    assert adb_tools._adb_bin(None, None) == "/Users/aw/Android/platform-tools/adb"


def test_adb_bin_override_wins_over_config(monkeypatch):
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=20, host_override=None: ("/Users/aw", "", 0))
    assert adb_tools._adb_bin("/custom/adb", None) == "/custom/adb"


def test_device_flag_falls_back_to_configured_default_serial():
    adb_tools.set_config_resolver(lambda: {**_FULL_CFG, "default_device_serial": "emulator-5554"})
    assert adb_tools._device_flag(None) == "-s emulator-5554 "
    assert adb_tools._device_flag("emulator-9999") == "-s emulator-9999 "


def test_device_flag_is_empty_when_nothing_configured():
    assert adb_tools._device_flag(None) == ""


def test_workspace_relative_path_resolves_against_container_dir(monkeypatch):
    monkeypatch.setenv("AW_WORKSPACE_CONTAINER_DIR", "/opt/aw-workspace")
    assert adb_tools._resolve_local_path(".tmp/x.png") == "/opt/aw-workspace/.tmp/x.png"
    assert adb_tools._resolve_local_path("/abs/x.png") == "/abs/x.png"


def test_adb_shell_double_quotes_the_whole_device_command(monkeypatch):
    captured = {}

    def fake_run_adb(args, **kw):
        captured["args"] = args
        return ("ok", "", 0)

    monkeypatch.setattr(adb_tools, "_run_adb", fake_run_adb)
    adb_tools._handle_adb_shell({"command": "echo hello world"})
    # The whole "shell 'echo hello world'" must arrive as ONE argv element
    # to adb, or the words get re-split on the device side.
    assert captured["args"] == "shell 'echo hello world'"


def test_adb_text_double_wraps_for_the_two_shell_hops(monkeypatch):
    captured = {}

    def fake_run_adb(args, **kw):
        captured["args"] = args
        return ("", "", 0)

    monkeypatch.setattr(adb_tools, "_run_adb", fake_run_adb)
    adb_tools._handle_adb_text({"text": "a b c"})
    assert captured["args"] == "shell 'input text '\"'\"'a b c'\"'\"''"


def test_screenshot_stages_on_remote_disk_then_downloads_never_via_exec_stdout(monkeypatch, tmp_path):
    """The whole reason this differs from the monolith: exec's stdout is
    capped at 1 MiB and truncates silently past it."""
    exec_calls = []
    download_calls = []

    def fake_exec(cmd, timeout=30, host_override=None):
        exec_calls.append(cmd)
        return ("", "", 0)

    def fake_download(remote_path, local_path, host_override=None):
        download_calls.append((remote_path, local_path))
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(b"\x89PNG-fake-bytes")
        return len(b"\x89PNG-fake-bytes")

    monkeypatch.setattr(remote_host, "exec", fake_exec)
    monkeypatch.setattr(remote_host, "download", fake_download)
    monkeypatch.setattr(remote_host, "expanduser", lambda p, host_override=None: p.replace("~", "/Users/aw"))

    out_path = str(tmp_path / "shot.png")
    result = adb_tools._handle_adb_screenshot({"local_path": out_path})

    assert "Saved screenshot" in result
    assert os.path.isfile(out_path)
    # screencap is redirected on the REMOTE shell (> file), never piped as
    # base64 back through this exec call's own stdout.
    assert any("screencap -p >" in c for c in exec_calls)
    assert not any("base64" in c for c in exec_calls)
    assert len(download_calls) == 1
    # staged file gets cleaned up
    assert any(cmd.startswith("rm -f") for cmd in exec_calls)


def test_screenshot_raises_loudly_on_zero_bytes(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=30, host_override=None: ("", "", 0))
    monkeypatch.setattr(remote_host, "download", lambda *a, **k: 0)
    monkeypatch.setattr(remote_host, "expanduser", lambda p, host_override=None: p.replace("~", "/Users/aw"))
    with pytest.raises(RuntimeError, match="empty"):
        adb_tools._handle_adb_screenshot({"local_path": str(tmp_path / "shot.png")})


def test_screenshot_raises_on_a_nonzero_screencap_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=30, host_override=None: ("", "device offline", 1))
    monkeypatch.setattr(remote_host, "expanduser", lambda p, host_override=None: p.replace("~", "/Users/aw"))
    with pytest.raises(RuntimeError, match="device offline"):
        adb_tools._handle_adb_screenshot({"local_path": str(tmp_path / "shot.png")})


def test_not_configured_surfaces_as_a_tool_error_not_a_crash():
    adb_tools.set_config_resolver(lambda: {})
    remote_host.set_config_resolver(lambda: {})
    resp = _run(http_handler.handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "adb_devices", "arguments": {}}}))
    assert resp["result"]["isError"] is True
    assert "missing" in resp["result"]["content"][0]["text"]


def test_per_call_remote_host_id_bypasses_a_missing_default(monkeypatch):
    """Even with no configured remote_host_id, a caller-supplied one must
    let the call proceed instead of failing NotConfigured."""
    cfg = dict(_FULL_CFG)
    cfg["remote_host_id"] = ""
    adb_tools.set_config_resolver(lambda: cfg)
    remote_host.set_config_resolver(lambda: cfg)
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=20, host_override=None: ("List of devices", "", 0))
    monkeypatch.setattr(remote_host, "expanduser", lambda p, host_override=None: p.replace("~", "/Users/aw"))
    result = adb_tools._handle_adb_devices({"remote_host_id": "some-other-host"})
    assert "List of devices" in result


def test_unknown_tool_is_an_error_not_a_crash():
    resp = _run(http_handler.handle_request({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "nope", "arguments": {}}}))
    assert resp["result"]["isError"] is True
    assert "Unknown tool" in resp["result"]["content"][0]["text"]


def test_initialize_and_tools_list():
    init = _run(http_handler.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert init["result"]["serverInfo"]["name"] == "aw-android-studio"
    listed = _run(http_handler.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    assert len(listed["result"]["tools"]) == 13


def test_initialized_notification_gets_no_response():
    assert _run(http_handler.handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized"})) is None


def test_unknown_method_is_a_jsonrpc_error():
    resp = _run(http_handler.handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}))
    assert resp["error"]["code"] == -32601


def test_mcp_config_names_the_server_the_monolith_used(tmp_path):
    from android_studio_app import mcp_config
    doc = mcp_config.write_mcp_json(str(tmp_path), 9030)
    entry = doc["mcpServers"]["aw-android-studio"]
    assert entry["type"] == "http"
    assert entry["url"].endswith(":9030/api/apps/android-studio/mcp")


def test_mcp_json_write_is_skipped_when_unchanged(tmp_path):
    from android_studio_app import mcp_config
    mcp_config.write_mcp_json(str(tmp_path), 9030)
    before = (tmp_path / "mcp.json").stat().st_mtime_ns
    mcp_config.write_mcp_json(str(tmp_path), 9030)
    assert (tmp_path / "mcp.json").stat().st_mtime_ns == before
    mcp_config.write_mcp_json(str(tmp_path), 9999)
    assert (tmp_path / "mcp.json").stat().st_mtime_ns != before
