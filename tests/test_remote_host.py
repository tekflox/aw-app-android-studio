"""remote_host.py — config resolution, per-call host override, and the
tilde-expansion / file-transfer gotchas ported from aw-app-crispal's own
test suite for the same pattern.

Deliberately no real network: every test that would call out stubs
urllib.request.urlopen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from android_studio_app.mcp import remote_host  # noqa: E402

_FULL = {
    "remote_backend_url": "https://api.aw.tekflox.com",
    "remote_workspace": "aw",
    "remote_token": "awlk_test",
    "remote_host_id": "824decc7e0610089",
}


@pytest.fixture(autouse=True)
def _reset():
    remote_host.set_config_resolver(lambda: {})
    remote_host._HOME_CACHE.clear()
    yield
    remote_host.set_config_resolver(lambda: {})
    remote_host._HOME_CACHE.clear()


def test_unconfigured_reports_every_missing_setting():
    remote_host.set_config_resolver(lambda: {})
    assert not remote_host.configured()
    missing = remote_host.missing_settings()
    for key in ("remote_backend_url", "remote_workspace", "remote_token", "remote_host_id"):
        assert key in missing


def test_fully_configured_reports_no_missing_settings():
    remote_host.set_config_resolver(lambda: dict(_FULL))
    assert remote_host.configured()
    assert remote_host.missing_settings() == ""


def test_per_call_host_override_satisfies_a_missing_default():
    values = dict(_FULL)
    values["remote_host_id"] = ""
    remote_host.set_config_resolver(lambda: values)
    assert not remote_host.configured()
    assert remote_host.configured(host_override="some-other-host")


def test_url_targets_the_account_host_route():
    remote_host.set_config_resolver(lambda: dict(_FULL))
    url = remote_host._url("/exec")
    assert url == "https://api.aw.tekflox.com/api/workspaces/aw/remote-hosts/824decc7e0610089/exec"


def test_host_override_changes_the_url_target():
    remote_host.set_config_resolver(lambda: dict(_FULL))
    url = remote_host._url("/exec", host_override="other-host")
    assert "/remote-hosts/other-host/exec" in url


def test_tilde_is_resolved_against_the_remote_home(monkeypatch):
    remote_host.set_config_resolver(lambda: dict(_FULL))
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=20, host_override=None: ("/Users/aw", "", 0))
    assert remote_host.expanduser("~/Android/x.png") == "/Users/aw/Android/x.png"


def test_an_absolute_path_is_left_alone():
    assert remote_host.expanduser("/tmp/x.png") == "/tmp/x.png"


def test_an_unresolvable_home_leaves_the_path_untouched(monkeypatch):
    """Better a path that fails loudly than one silently rewritten to '/...'."""
    remote_host.set_config_resolver(lambda: dict(_FULL))
    monkeypatch.setattr(remote_host, "exec", lambda cmd, timeout=20, host_override=None: ("", "no such var", 1))
    assert remote_host.expanduser("~/x.png") == "~/x.png"


def test_home_is_cached_per_host(monkeypatch):
    remote_host.set_config_resolver(lambda: dict(_FULL))
    calls = []

    def fake_exec(cmd, timeout=20, host_override=None):
        calls.append(host_override)
        return (f"/home/{host_override or 'default'}", "", 0)

    monkeypatch.setattr(remote_host, "exec", fake_exec)
    assert remote_host.home() == remote_host.home()
    assert remote_host.home(host_override="other") != remote_host.home()
    assert len(calls) == 2  # one per distinct host, not re-fetched


def test_upload_path_is_passed_as_a_query_param(monkeypatch, tmp_path):
    remote_host.set_config_resolver(lambda: dict(_FULL))
    src = tmp_path / "f.bin"
    src.write_bytes(b"hi")

    captured = {}

    class _Resp:
        def read(self):
            return json.dumps({"sha256": "abc"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(remote_host.urllib.request, "urlopen", fake_urlopen)
    result = remote_host.upload(str(src), "~/dst.bin")
    assert result["sha256"] == "abc"
    assert "path=" in captured["url"]


def test_download_url_is_the_fs_route():
    remote_host.set_config_resolver(lambda: dict(_FULL))
    url = remote_host._url("/fs/download", {"path": "/x.png"})
    assert url.endswith("/fs/download?path=%2Fx.png")


def test_missing_settings_names_only_the_absent_ones():
    remote_host.set_config_resolver(lambda: {"remote_backend_url": "https://x", "remote_workspace": "aw"})
    named = remote_host.missing_settings().split("missing ", 1)[-1].split(".", 1)[0]
    assert "remote_token" in named and "remote_host_id" in named
    assert "remote_backend_url" not in named and "remote_workspace" not in named
