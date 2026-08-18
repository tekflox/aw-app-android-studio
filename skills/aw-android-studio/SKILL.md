---
name: aw-android-studio
description: Automate an Android device or emulator over ADB — via a machine linked to this workspace through aw-remote-hosts, not a fixed box. Covers finding the device, tapping/swiping by coordinate, screenshotting and pulling the image into the workspace, installing/launching apps, and the gotchas that bite (ASCII-only typing, quoting across two shells, tilde paths, screenshot size). Use whenever asked to pilot an Android app, tap/type/swipe on Android, install/inspect an APK, or take a screenshot of "the Android emulator/device".
---

# aw-android-studio — ADB automation over aw-remote-hosts

## What this is

13 `adb_*` / `upload_file` tools that drive a real Android device or
emulator attached to a **linked remote host** — reached through
**aw-remote-hosts**, not a fixed machine baked into the code. Ported from
agentic-workspace's `src/mcp/aw_android_studio.py`, which hard-coded a
single Mac (`macbook-fred`) and a dead monolith-only transport
(`REMOTE_AGENT_URL` / `/api/clients/{profile}/exec`). Here every setting —
which host, where `adb` lives on it, which device serial, where screenshots
land — is `config_schema`, and every tool also accepts a per-call override of
the same knobs. Nothing about "which Mac" or "which device" is hard-coded.

This workspace is pre-configured for **Frederico's Mac.Home**
(`remote_host_id = 824decc7e0610089`, `adb_path = ~/Android/platform-tools/adb`)
— open the app's Settings if a different host/device is the target.

## The real flow, not just the tool list

1. **`adb_devices`** first, always. It lists attached serials and confirms
   the remote host is actually reachable before you try anything else — a
   cold-booting emulator can take 1-2+ minutes to show `device` state, so a
   tap sent too early lands on nothing.
2. **Screenshot before you act blind.** `adb_screenshot` saves a PNG onto
   THIS workspace's own filesystem (under the app's configured
   `screenshot_dir`, default `.tmp/android-studio/`) — read it back to see
   what's actually on screen before tapping coordinates you're guessing at.
3. **Tap/swipe by coordinate**, read from that screenshot. `adb_tap x y`,
   `adb_swipe x1 y1 x2 y2 [duration_ms]`. There is no accessibility-tree
   tool here (that's the crispal/Arvin app's `uiautomator dump` approach,
   not this one) — coordinates from a screenshot are the whole interaction
   model.
4. **Typing**: `adb_text`. **ASCII only** — see Gotchas.
5. **Getting a file onto the device** (an APK, an image): `upload_file`
   (this workspace → the remote host's disk) then `adb_push` (remote
   host → device storage). Two separate tools because the device and the
   remote host are two different filesystems and neither app nor adb can
   skip the middle hop. For anything that should show up in the Photos
   picker without a reboot, follow with `adb_media_scan`.
6. **Installing/launching an app**: push the APK, then either
   `adb_shell 'pm install <path>'` or `adb_launch_app` by package name
   (optionally with a specific `activity`).

## Gotchas

- **`adb shell input text` is ASCII-only.** It maps characters to
  US-keyboard `KeyEvent`s, so accented/non-Latin characters (á, ã, é, ç, ú,
  ñ, emoji, CJK…) throw a `NullPointerException` on the device and abort the
  **whole** string, not just the bad character. For Portuguese or other
  accented text, strip diacritics first (e.g. Python's
  `unicodedata.normalize('NFKD', s).encode('ascii', 'ignore')`) before
  calling `adb_text`.
- **`adb shell <cmd>` crosses TWO shells.** The remote host's own shell
  (parsing the full command string handed to the exec channel) and then
  adb's own `shell` subcommand, which re-joins its remaining argv with
  spaces and hands THAT to the device's `sh -c`. Quoting only survives the
  first hop unless the WHOLE device-side command is wrapped in one more
  `shlex.quote()` — `adb_shell` and `adb_text` already do this double-wrap;
  do the same in any new handler that builds a device command from
  caller-supplied text, or multi-word args silently truncate to their first
  word.
- **A leading `~` in a path is expanded against the REMOTE host's home**,
  not this workspace's — every path handed to adb goes through
  `shlex.quote`, and a shell does not expand `~` inside quotes. `adb_path`
  and `remote_host_path`/`remote_path` are all resolved through
  `remote_host.expanduser()` for this reason; a raw `os.path.expanduser`
  would resolve against the wrong machine entirely.
- **`adb_screenshot` never reads the PNG back through the exec channel as
  base64** — aw-remote-hosts caps a job's stdout at 1 MiB and returns
  `exit_code -1` past it, which for a real device screenshot (routinely
  well over 1 MB) comes back as a silently truncated, corrupt PNG with no
  loud error. It stages on the remote host's own disk (`exec-out
  screencap -p > file`) and pulls it through the uncapped `fs/download`
  route instead. If you're extending this app, follow the same two-hop
  pattern for anything that reads bytes off the device — never through
  exec's stdout.
- **Cold boot** of a fresh emulator AVD takes 1-2+ minutes — don't assume
  `adb_devices` will show `device` state (rather than `offline` or nothing)
  immediately after the emulator process starts.
- **Not configured ≠ a crash.** If `remote_backend_url` / `remote_workspace`
  / `remote_token` aren't all set (and no per-call override supplies what's
  missing), every tool fails with a message naming exactly which key is
  absent — it never falls back to a guessed host. If you see that error,
  open the app's Settings.

## Config reference

| Setting | Default | Per-call override |
|---|---|---|
| `remote_backend_url` | *(none — must be set)* | — (account-level only) |
| `remote_workspace` | *(none — must be set)* | — (account-level only) |
| `remote_token` | *(none — must be set, secret store)* | — (account-level only) |
| `remote_host_id` | `824decc7e0610089` (Frederico's Mac.Home) | `remote_host_id` arg |
| `adb_path` | `~/Android/platform-tools/adb` | `adb_path` arg |
| `default_device_serial` | *(unset — only one device assumed)* | `device` arg |
| `screenshot_dir` | `.tmp/android-studio/` | `local_path` arg on `adb_screenshot` |

## Provisioning a new host (design only — not implemented)

Today, pointing this app at a *new* machine means someone manually installs
`platform-tools` there, finds the right `adb` path, and pastes it into
Settings. The intended fix — a `bootstrap-new-host` command that installs
platform-tools on a linked host, confirms `adb devices` sees something, and
writes this app's config itself — is designed but **not built or tested**
against any real host yet. See `docs/provisioning-bootstrap.md` in this
repo for the full design and the untested command skeleton
(`scripts/bootstrap_new_host.py`). Don't tell a user this exists as a
working feature.
