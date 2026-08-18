# aw-app-android-studio

Pilot a real Android device or emulator over ADB — tap, swipe, type, screenshot,
install/inspect apps, push and pull files — from any agent in this workspace.

Ports agentic-workspace's `aw-android-studio` MCP server
(`src/mcp/aw_android_studio.py`). 13 tools, gateway-prefixed
`aw__aw_android_studio__*`.

**No fixed machine.** The monolith hard-coded a single Mac
(`macbook-fred`, profile id baked into the code) and talked to its own
remote-agent backend, which does not exist in this split deployment. This
app instead reaches whatever host you link through **aw-remote-hosts** —
which host, where `adb` lives on it, which device serial, where screenshots
land are all `config_schema`, and every tool also takes a per-call override
of the same knobs.

Pre-configured for Frederico's Mac.Home (`remote_host_id = 824decc7e0610089`,
`adb_path = ~/Android/platform-tools/adb`) — change it in Settings for a
different host.

## Install

```bash
aw-workspace-cli marketplace install android-studio
```

Then open **Android Studio** in the Apps grid, fill in the backend URL /
workspace slug / bearer token for the aw-backend that fronts your linked
hosts (see `aw-workspace-cli remote-hosts hosts`), and hit **Test the
connection**.

## Why the token is a secret and the rest isn't

`remote_backend_url` / `remote_workspace` / `remote_host_id` / `adb_path` /
`default_device_serial` / `screenshot_dir` are plain config
(`POST /api/apps/android-studio/config`). `remote_token` is a bearer
credential that can run arbitrary commands on the linked host, so it goes
through the zero-knowledge secret store instead
(`POST /api/apps/android-studio/settings`) — never written to plain,
cloud-syncable app config.

## Routes

Under `/api/apps/android-studio`, behind the workspace IdentityGuard.

| Route | Purpose |
|---|---|
| `GET /status` | Configured state, missing settings (if any), tool list. |
| `POST /settings` | Save the bearer token (secret store). Effective on the next call — no restart. |
| `POST /logout` | Forget the token. |
| `POST /test` | Run a real `adb devices -l` against the configured (or overridden) host. |
| `POST /mcp` | The MCP server itself (Streamable HTTP), scanned by MCP Gateway. |
| `GET /mcp.json` | What the gateway will see. |

Plain config (host id, adb path, device serial, screenshot dir) goes through
core's generic `POST /api/apps/android-studio/config`, not a route in this
app.

## The 13 tools

`adb_devices`, `adb_shell`, `adb_tap`, `adb_swipe`, `adb_text`,
`adb_keyevent`, `adb_screenshot`, `adb_push`, `adb_launch_app`,
`adb_stop_app`, `adb_list_packages`, `adb_media_scan`, `upload_file` — same
13 the monolith shipped, none cut. See `skills/aw-android-studio/SKILL.md`
for the real usage flow (not just the tool list) and the gotchas that bite:
ASCII-only typing, quoting across two shells, `~`-path expansion against
the wrong machine, and why screenshots never travel through the exec
channel's stdout.

## Provisioning a new host

Not built yet — see `docs/provisioning-bootstrap.md` for the design and the
untested `scripts/bootstrap_new_host.py` skeleton. Today, pointing this app
at a new host means installing `platform-tools` there by hand and pasting
`remote_host_id` + `adb_path` into Settings.

## Tests

```bash
python3 tests/validate_manifest.py aw-app.json
python3 -m pytest tests -q
```
