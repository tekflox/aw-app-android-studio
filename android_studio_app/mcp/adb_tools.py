"""The 13 adb_* / upload_file tools, ported from agentic-workspace's
``src/mcp/aw_android_studio.py`` onto :mod:`remote_host` (aw-remote-hosts)
instead of the monolith's dead remote-agent.

Tool logic and shell-quoting are otherwise untouched from the monolith —
including the double ``shlex.quote`` wrap in ``adb_shell``/``adb_text``,
needed because the command string crosses TWO shells (the remote host's own
shell, then adb's own ``shell`` subcommand re-joining its argv) — see the
comment on ``_run_adb_shell`` below and the monolith's own for the full
explanation.

One deliberate change beyond the transport swap: ``adb_screenshot`` no
longer reads the PNG back over the exec channel as base64. aw-remote-hosts
caps a job's stdout at 1 MiB and reports exit_code -1 past it — a screenshot
above that size (routine for a real device) would silently come back
truncated with no loud error, exactly the "PNG that isn't actually a PNG"
failure mode aw-app-crispal hit and documented in its own remote_host.py.
Screenshots now stage on the remote host's own disk via `exec-out ... >
file`, then pull through the dedicated (uncapped) fs/download route — the
same two-hop pattern crispal's Arvin automation uses for pulling files off
the device.
"""
from __future__ import annotations

import os
import shlex
import uuid
from typing import Callable

from . import remote_host

DEFAULT_ADB_PATH = "~/Android/platform-tools/adb"
DEFAULT_SCREENSHOT_DIR = ".tmp/android-studio/"

_config_resolver: Callable[[], dict] = lambda: {}


def set_config_resolver(resolver: Callable[[], dict]) -> None:
    """Installed once from ``plugin.activate`` — same resolver instance the
    plugin hands to :mod:`remote_host`, so adb_path/default_device_serial/
    screenshot_dir also pick up a Settings change on the very next call."""
    global _config_resolver
    _config_resolver = resolver


def _cfg() -> dict:
    try:
        return _config_resolver() or {}
    except Exception:
        return {}


def current_config() -> dict:
    """The resolved config (including this app's own schema-default
    fallbacks — see plugin.py's ``_SCHEMA_DEFAULTS``), for display purposes.
    routes.py's ``/status`` uses this instead of reading ``ctx.config``
    directly so the Settings UI shows what a tool call will actually use."""
    return _cfg()


def _workspace_root() -> str:
    return os.environ.get("AW_WORKSPACE_CONTAINER_DIR", "/opt/aw-workspace")


def _resolve_local_path(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_workspace_root(), path)


def _adb_bin(adb_path_override: str | None, host_override: str | None) -> str:
    path = adb_path_override or _cfg().get("adb_path") or DEFAULT_ADB_PATH
    return remote_host.expanduser(path, host_override=host_override)


def _device_flag(device: str | None) -> str:
    device = device or _cfg().get("default_device_serial") or None
    return f"-s {shlex.quote(device)} " if device else ""


def _run_adb(adb_args: str, timeout: int = 30, *, remote_host_id: str | None = None,
             adb_path: str | None = None) -> tuple[str, str, int]:
    adb_bin = _adb_bin(adb_path, remote_host_id)
    command = f"{adb_bin} {adb_args}"
    return remote_host.exec(command, timeout=timeout, host_override=remote_host_id)


def _format_result(out: str, err: str, code: int) -> str:
    parts = []
    if out:
        parts.append(out.rstrip())
    if err:
        parts.append(f"[stderr]\n{err.rstrip()}")
    if code:
        parts.append(f"[exit {code}]")
    return "\n".join(parts) if parts else "(no output)"


# ── Tool schema ────────────────────────────────────────────────────────────

_REMOTE_HOST_PARAM = {
    "type": "string",
    "description": (
        "Id of the linked host running adb (from 'aw-workspace-cli "
        "remote-hosts hosts'). Defaults to this app's configured "
        "remote_host_id (Frederico's Mac.Home unless changed in Settings). "
        "The operation runs ON THAT HOST, not locally."
    ),
}

_DEVICE_PARAM = {
    "type": "string",
    "description": (
        "Optional device/emulator serial (as shown by adb_devices) to target "
        "with `adb -s <serial>`. Defaults to this app's configured "
        "default_device_serial, or the only attached device if that's unset "
        "and unambiguous."
    ),
}

_ADB_PATH_PARAM = {
    "type": "string",
    "description": (
        "Optional override for the adb binary's path on the remote host. "
        "Defaults to this app's configured adb_path."
    ),
}

TOOLS = [
    {
        "name": "adb_devices",
        "description": (
            "Run `adb devices -l` on the remote host to list attached "
            "Android devices/emulators (serial, state, product/model info). "
            "Use this first to discover which device serial to target with "
            "other tools' optional `device` parameter."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "adb_path": _ADB_PATH_PARAM,
            },
            "required": [],
        },
    },
    {
        "name": "adb_shell",
        "description": (
            "Run an arbitrary `adb shell <command>` on the remote host's "
            "attached Android device. Use for anything not covered by a more "
            "specific tool (dumpsys, getprop, cat, ls, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "command": {
                    "type": "string",
                    "description": "Shell command to run inside `adb shell`, e.g. 'dumpsys battery'.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "adb_tap",
        "description": "Tap the screen at (x, y) via `adb shell input tap X Y`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "x": {"type": "integer", "description": "X coordinate in screen pixels."},
                "y": {"type": "integer", "description": "Y coordinate in screen pixels."},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "adb_swipe",
        "description": (
            "Swipe from (x1, y1) to (x2, y2) via `adb shell input swipe`, "
            "optionally over duration_ms milliseconds."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "x1": {"type": "integer", "description": "Start X coordinate."},
                "y1": {"type": "integer", "description": "Start Y coordinate."},
                "x2": {"type": "integer", "description": "End X coordinate."},
                "y2": {"type": "integer", "description": "End Y coordinate."},
                "duration_ms": {
                    "type": "integer",
                    "description": "Swipe duration in milliseconds (optional; adb default if omitted).",
                },
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "adb_text",
        "description": (
            "Type text into the currently focused input field via "
            "`adb shell input text`. The text is shell-quoted safely on the "
            "server side (both spaces and shell metacharacters survive), so "
            "multi-word strings are safe to pass. LIMITATION: Android's "
            "`input text` only supports ASCII -- it maps characters to "
            "US-keyboard key events, so accented/non-Latin characters (á, ã, "
            "é, ç, ú, ñ, emoji, CJK, ...) throw a NullPointerException on the "
            "device and abort the whole string. For accented text (e.g. "
            "Portuguese), strip diacritics first (e.g. Python's "
            "`unicodedata.normalize('NFKD', s).encode('ascii','ignore')`) "
            "before calling this tool."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "adb_keyevent",
        "description": (
            "Send a key event via `adb shell input keyevent <code>`. Accepts "
            "either a symbolic name (e.g. 'KEYCODE_BACK', 'KEYCODE_HOME') or "
            "a numeric keycode."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "keycode": {
                    "type": "string",
                    "description": "Keycode name (e.g. KEYCODE_BACK) or numeric code (e.g. '4').",
                },
            },
            "required": ["keycode"],
        },
    },
    {
        "name": "adb_launch_app",
        "description": (
            "Launch an Android app by package name. If `activity` is given, "
            "launches that exact component via `adb shell am start -n "
            "package/activity`; otherwise launches by package's launcher "
            "intent via `adb shell monkey -p <package> -c "
            "android.intent.category.LAUNCHER 1`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "package": {"type": "string", "description": "App package name, e.g. com.example.app."},
                "activity": {
                    "type": "string",
                    "description": (
                        "Optional fully-qualified activity name (e.g. "
                        ".MainActivity or com.example.app.MainActivity). "
                        "If omitted, launches via the launcher intent instead."
                    ),
                },
            },
            "required": ["package"],
        },
    },
    {
        "name": "adb_stop_app",
        "description": "Force-stop an app via `adb shell am force-stop <package>`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "package": {"type": "string", "description": "App package name to force-stop."},
            },
            "required": ["package"],
        },
    },
    {
        "name": "adb_list_packages",
        "description": (
            "List installed packages via `adb shell pm list packages`. If "
            "`filter` is given, only packages whose name contains that "
            "substring are returned."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "filter": {
                    "type": "string",
                    "description": "Optional substring to filter package names by.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "adb_screenshot",
        "description": (
            "Capture a screenshot of the device screen and save it as a PNG "
            "on THIS workspace's own filesystem, NOT on the remote host. "
            "Staged on the remote host's disk first, then pulled over the "
            "uncapped file-transfer route (never through exec's stdout, "
            "which truncates silently above 1 MiB). Defaults to a path under "
            "this app's configured screenshot_dir if `local_path` is "
            "omitted — repeated calls will OVERWRITE that file unless you "
            "pass a distinct local_path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "local_path": {
                    "type": "string",
                    "description": (
                        "Absolute or workspace-relative path to save the PNG "
                        "to. Defaults to <screenshot_dir>/screenshot.png "
                        "(overwritten on repeat calls) if omitted."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "upload_file",
        "description": (
            "Upload a file from THIS workspace's own filesystem to a path on "
            "the remote host via aw-remote-hosts. Use this to get an APK or "
            "any other file onto the remote host before pushing/installing "
            "it on the device (e.g. with adb_push, or an `adb shell pm "
            "install <remote_path>` command run via adb_shell)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "local_path": {
                    "type": "string",
                    "description": (
                        "Absolute or workspace-relative path to the file to "
                        "read and upload."
                    ),
                },
                "remote_path": {
                    "type": "string",
                    "description": (
                        "Absolute path on the REMOTE HOST's filesystem to "
                        "write the file to, e.g. ~/Android/uploads/app.apk."
                    ),
                },
            },
            "required": ["local_path", "remote_path"],
        },
    },
    {
        "name": "adb_push",
        "description": (
            "Run `adb push <remote_host_path> <device_path>` to copy a file "
            "that already exists on the REMOTE HOST's filesystem into the "
            "attached Android device/emulator's storage. This is the second "
            "half of getting a file from THIS workspace onto the device: "
            "first call `upload_file` to land it on the remote host, then "
            "call `adb_push` to get it from there onto the device (e.g. "
            "/sdcard/Pictures/foo.jpg). For images meant to show up in the "
            "device's Photos gallery/picker, follow this with an `adb_shell` "
            "MEDIA_SCANNER broadcast (see adb_media_scan) so the picker sees "
            "it without a reboot."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "remote_host_path": {
                    "type": "string",
                    "description": (
                        "Absolute path on the REMOTE HOST's filesystem "
                        "(written there earlier by upload_file) to push "
                        "onto the device."
                    ),
                },
                "device_path": {
                    "type": "string",
                    "description": (
                        "Absolute path on the DEVICE's filesystem to write to, e.g. "
                        "/sdcard/Pictures/foo.jpg or /sdcard/Download/app.apk."
                    ),
                },
            },
            "required": ["remote_host_path", "device_path"],
        },
    },
    {
        "name": "adb_media_scan",
        "description": (
            "Trigger the media scanner on a file already pushed onto the "
            "device (via adb_push) so it immediately shows up in the Photos "
            "gallery / image picker, without needing a device reboot. Runs "
            "`adb shell am broadcast -a "
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "
            "file://<device_path>`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "remote_host_id": _REMOTE_HOST_PARAM,
                "device": _DEVICE_PARAM,
                "adb_path": _ADB_PATH_PARAM,
                "device_path": {
                    "type": "string",
                    "description": "Absolute path on the DEVICE's filesystem to scan, e.g. /sdcard/Pictures/foo.jpg.",
                },
            },
            "required": ["device_path"],
        },
    },
]


# ── Tool handlers ─────────────────────────────────────────────────────────

def _handle_adb_devices(args: dict) -> str:
    out, err, code = _run_adb("devices -l", remote_host_id=args.get("remote_host_id"),
                              adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_shell(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    command = args["command"]
    # This command string crosses TWO shells: the remote host's own shell
    # (which parses the full "adb -s dev shell <command>" line handed to
    # remote_host.exec) and then adb's `shell` subcommand re-joins its
    # remaining argv with spaces and hands THAT to the device's own `sh -c`.
    # Any quotes inside `command` only survive the first hop -- by the time
    # adb rebuilds the string for the device, they're gone and multi-word
    # args get re-split on whitespace (confirmed on the monolith: `input
    # text 'a b c'` arrived on device as `input text a b c`, typing only
    # "a"). Wrapping the whole command in one more shlex.quote makes it
    # arrive at adb as a SINGLE argv element, which adb then hands to the
    # device shell untouched, preserving any quoting the caller put inside
    # `command`.
    out, err, code = _run_adb(f"{device_flag}shell {shlex.quote(command)}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_tap(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    x, y = args["x"], args["y"]
    out, err, code = _run_adb(f"{device_flag}shell input tap {x} {y}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_swipe(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    x1, y1, x2, y2 = args["x1"], args["y1"], args["x2"], args["y2"]
    duration = args.get("duration_ms")
    dur_part = f" {duration}" if duration is not None else ""
    out, err, code = _run_adb(f"{device_flag}shell input swipe {x1} {y1} {x2} {y2}{dur_part}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_text(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    # Two shlex.quote layers: the inner one protects `text` inside the
    # device-side "input text <text>" command; the outer one protects that
    # WHOLE command from the remote host's own shell, so it arrives at adb
    # as one argv element and adb hands it to the device shell with the
    # inner quoting still intact (see _handle_adb_shell's comment -- without
    # the outer layer, multi-word text silently truncates to its first
    # word).
    device_command = "input text " + shlex.quote(args["text"])
    out, err, code = _run_adb(f"{device_flag}shell {shlex.quote(device_command)}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_keyevent(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    keycode = shlex.quote(args["keycode"])
    out, err, code = _run_adb(f"{device_flag}shell input keyevent {keycode}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_launch_app(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    package = args["package"]
    activity = args.get("activity")
    if activity:
        component = activity if "/" in activity else f"{package}/{activity}"
        out, err, code = _run_adb(f"{device_flag}shell am start -n {shlex.quote(component)}",
                                  remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    else:
        out, err, code = _run_adb(
            f"{device_flag}shell monkey -p {shlex.quote(package)} -c android.intent.category.LAUNCHER 1",
            remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_stop_app(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    package = shlex.quote(args["package"])
    out, err, code = _run_adb(f"{device_flag}shell am force-stop {package}",
                              remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_list_packages(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    filter_str = args.get("filter")
    if filter_str:
        cmd = f"{device_flag}shell pm list packages | grep {shlex.quote(filter_str)}"
    else:
        cmd = f"{device_flag}shell pm list packages"
    out, err, code = _run_adb(cmd, timeout=30, remote_host_id=args.get("remote_host_id"),
                              adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_screenshot(args: dict) -> str:
    remote_host_id = args.get("remote_host_id")
    device_flag = _device_flag(args.get("device"))
    local_path = _resolve_local_path(
        args.get("local_path") or os.path.join(_cfg().get("screenshot_dir") or DEFAULT_SCREENSHOT_DIR,
                                                "screenshot.png"))

    staged = remote_host.expanduser(f"~/Android/uploads/screenshot_{uuid.uuid4().hex}.png",
                                     host_override=remote_host_id)
    adb_bin = _adb_bin(args.get("adb_path"), remote_host_id)
    # Redirected on the REMOTE HOST's own shell, never through exec's
    # stdout — see module docstring for why (silent 1 MiB truncation).
    command = f"mkdir -p {shlex.quote(os.path.dirname(staged))} && " \
              f"{adb_bin} {device_flag}exec-out screencap -p > {shlex.quote(staged)}"
    out, err, code = remote_host.exec(command, timeout=45, host_override=remote_host_id)
    if code:
        raise RuntimeError(f"adb screencap failed (exit {code}): {err or out}")

    try:
        size = remote_host.download(staged, local_path, host_override=remote_host_id)
    finally:
        remote_host.exec(f"rm -f {shlex.quote(staged)}", timeout=10, host_override=remote_host_id)

    if size == 0:
        raise RuntimeError("Screenshot came back empty (0 bytes) — the device may be locked or off.")

    return f"Saved screenshot to {local_path} ({size} bytes)"


def _handle_upload_file(args: dict) -> str:
    remote_host_id = args.get("remote_host_id")
    local_path = _resolve_local_path(args["local_path"])
    remote_path = args["remote_path"]

    if not os.path.isfile(local_path):
        raise RuntimeError(f"Local file not found: {local_path}")
    size = os.path.getsize(local_path)
    remote_path_resolved = remote_host.expanduser(remote_path, host_override=remote_host_id)
    remote_host.exec(f"mkdir -p {shlex.quote(os.path.dirname(remote_path_resolved))}",
                     timeout=20, host_override=remote_host_id)
    result = remote_host.upload(local_path, remote_path_resolved, host_override=remote_host_id)
    if result.get("error"):
        raise RuntimeError(result["error"])
    sha256 = result.get("sha256", "?")
    return f"Uploaded {size} bytes (sha256={sha256}): {local_path} -> {remote_path_resolved}"


def _handle_adb_push(args: dict) -> str:
    remote_host_id = args.get("remote_host_id")
    device_flag = _device_flag(args.get("device"))
    remote_host_path = shlex.quote(
        remote_host.expanduser(args["remote_host_path"], host_override=remote_host_id))
    device_path = shlex.quote(args["device_path"])
    out, err, code = _run_adb(f"{device_flag}push {remote_host_path} {device_path}", timeout=60,
                              remote_host_id=remote_host_id, adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


def _handle_adb_media_scan(args: dict) -> str:
    device_flag = _device_flag(args.get("device"))
    device_path = args["device_path"]
    uri = shlex.quote(f"file://{device_path}")
    out, err, code = _run_adb(
        f"{device_flag}shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d {uri}",
        remote_host_id=args.get("remote_host_id"), adb_path=args.get("adb_path"))
    return _format_result(out, err, code)


HANDLERS = {
    "adb_devices": _handle_adb_devices,
    "adb_shell": _handle_adb_shell,
    "adb_tap": _handle_adb_tap,
    "adb_swipe": _handle_adb_swipe,
    "adb_text": _handle_adb_text,
    "adb_keyevent": _handle_adb_keyevent,
    "adb_launch_app": _handle_adb_launch_app,
    "adb_stop_app": _handle_adb_stop_app,
    "adb_list_packages": _handle_adb_list_packages,
    "adb_screenshot": _handle_adb_screenshot,
    "upload_file": _handle_upload_file,
    "adb_push": _handle_adb_push,
    "adb_media_scan": _handle_adb_media_scan,
}
