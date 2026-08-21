---
repo: architecture
path: docs/architecture/aw-app-android-studio.md
source: generated
edited: false
checksum: sha256:14a1c9deed435f038cc4ba7ac86f7370560f18027547aca040e766b939bb5bcc
---
# Android Studio

- **repo**: aw-app-android-studio
- **layer**: app
- **technologies**: python
- **health** (derived): planned

Automate any Android device or emulator over ADB — tap, swipe, type, screenshot, install/inspect apps, push and pull files — reached through a linked host via aw-remote-hosts. No fixed machine: point it at whichever remote host and adb binary you configure, per-call overrides included.

## Connections
- `http` → **aw-workspace** — routes mounted at /api/apps/android-studio
- `stdio-mcp` → **mcp-gateway** — MCP surface aggregated by the gateway

## MCP tools
- `adb_devices`
- `adb_keyevent`
- `adb_launch_app`
- `adb_list_packages`
- `adb_media_scan`
- `adb_push`
- `adb_screenshot`
- `adb_shell`
- `adb_stop_app`
- `adb_swipe`
- `adb_tap`
- `adb_text`
- `upload_file`

## Requirements
_none documented_
