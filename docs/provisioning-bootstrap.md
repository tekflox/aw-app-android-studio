# Provisioning a new host — design (Phase 2, not implemented)

**Status: design only.** Nothing on this page has been run against a real
host. `scripts/bootstrap_new_host.py` is a skeleton — it is not wired into
the app, not covered by tests, and not part of this release. Do not present
it to a user as a working feature.

## The problem

Getting this app to control a *new* device today means a person:

1. Downloads and unpacks `platform-tools` on the target host by hand.
2. Runs `adb devices` there to confirm it actually sees the attached device.
3. Works out the real path to the `adb` binary (it is deliberately never on
   `PATH` in a non-interactive remote shell — see the skill's gotchas).
4. Opens this app's Settings and pastes `remote_host_id` + `adb_path` in.

Steps 1-3 are mechanical and don't need a human. Step 4 is the only piece
that has to stay manual (choosing *which* linked host is the right one is a
judgment call aw-remote-hosts has no way to make for you).

## The intended shape

A single command, run against an already-linked aw-remote-hosts host:

```bash
aw-workspace-cli android-studio bootstrap-new-host <remote_host_id>
```

What it should do, in order, all via `remote_host.exec()` /
`remote_host.upload()` (the same client this app's tools already use — no
new transport):

1. **Detect the host's OS** (`uname -s` over exec) — platform-tools ships
   separate archives for macOS/Linux/Windows, and the download URL and
   unpack step differ per platform. Windows is explicitly out of scope for
   a first cut (no unzip-equivalent guaranteed on a bare exec shell there);
   fail with a clear message rather than guessing.
2. **Download `platform-tools` for that OS** from Google's official archive
   URL (`https://dl.google.com/android/repository/platform-tools-latest-<os>.zip`)
   directly on the remote host via `curl`, not proxied through this
   workspace — the archive is tens of MB and the exec channel is not the
   right pipe for that either (same 1 MiB-stdout lesson as screenshots,
   though this is a download, not something exec has to echo back).
3. **Unpack it** into a fixed, predictable location under the host's own
   home, e.g. `~/Android/platform-tools/` — matching the existing default so
   a bootstrapped host needs no `adb_path` override at all.
4. **Verify** with `adb devices -l` and require **at least one** entry in
   `device` state before declaring success. Zero devices is not a failure
   of the bootstrap itself (the platform-tools install can be perfectly
   correct with nothing plugged in yet) but must be reported distinctly
   from "adb itself is broken" — these are two different follow-ups for
   whoever runs this.
5. **Write this app's config** — `remote_host_id` (the argument) and
   `adb_path` (the path from step 3) — via the same
   `POST /api/apps/android-studio/config` route the Settings form uses, so
   a successful bootstrap needs no manual paste-in at all. If more than one
   device came back in step 4, still write config but say so explicitly:
   `default_device_serial` is a judgment call this command should not make
   silently.

## What this explicitly does NOT attempt

- **No AVD (emulator) creation.** The monolith's `aw_pixel_gms` AVD was
  built by hand with a specific system image
  (`system-images;android-34;google_apis_playstore;arm64-v8a` — see the
  monolith skill's warning that the plain `google_apis` variant has a dead
  Play Store stub). Reproducing that reliably needs `sdkmanager`/`avdmanager`
  plus a JDK on the target host, which is a much bigger lift than "make adb
  reachable" and is out of scope here. This command targets a host with an
  **already-attached physical device or an already-running emulator** —
  provisioning a fresh emulator from nothing is future work, if ever.
- **No credential setup.** `remote_backend_url` / `remote_workspace` /
  `remote_token` are assumed already correct (this command only runs
  against a host `remote_host.exec()` can already reach) — this is
  ADB-specific bootstrap, not aw-remote-hosts linking.
- **No Windows support** in the first cut (see step 1).

## Why this is Phase 2, not this release

The card that requested this app was explicit: design the bootstrap, don't
implement or test it, and don't spend the one real linked host
(Frederico's Mac.Home, already running a live device this workspace uses
today) as a guinea pig for an unproven install script. `adb_path` and
`remote_host_id` being plain configurable settings (rather than hard-coded,
as the monolith had them) is what makes this command possible to add later
without changing anything about the 13 tools themselves.
