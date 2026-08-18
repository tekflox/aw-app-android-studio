#!/usr/bin/env python3
"""SKELETON — design only, per docs/provisioning-bootstrap.md.

NOT wired into the app, NOT tested against any real host, NOT part of this
release. This file exists so the shape of a future
`aw-workspace-cli android-studio bootstrap-new-host <remote_host_id>`
command is written down next to the design doc instead of only in prose —
every function below is a stub raising NotImplementedError.

Do not import this from android_studio_app/ until it has been implemented
and tested for real; nothing currently references it.
"""
from __future__ import annotations

import argparse
import sys


def detect_os(remote_host_id: str) -> str:
    """Should run `uname -s` via remote_host.exec() and map to
    'darwin' / 'linux' — raise a clear error for anything else (Windows is
    explicitly out of scope for a first cut; see the design doc)."""
    raise NotImplementedError("design only — see docs/provisioning-bootstrap.md")


def download_platform_tools(remote_host_id: str, os_name: str) -> str:
    """Should curl the official platform-tools-latest-<os>.zip directly on
    the remote host (never proxied through this workspace) and unzip it
    under ~/Android/platform-tools/. Returns the resolved adb path."""
    raise NotImplementedError("design only — see docs/provisioning-bootstrap.md")


def verify_adb(remote_host_id: str, adb_path: str) -> list[str]:
    """Should run `adb devices -l` and return the list of device serials in
    `device` state. An empty list is not itself a failure — see the design
    doc for why it must be reported distinctly from adb being broken."""
    raise NotImplementedError("design only — see docs/provisioning-bootstrap.md")


def write_app_config(remote_host_id: str, adb_path: str, device_serials: list[str]) -> None:
    """Should POST to /api/apps/android-studio/config with remote_host_id +
    adb_path, and — only if exactly one device came back — default_device_serial.
    More than one device must be reported, not silently guessed."""
    raise NotImplementedError("design only — see docs/provisioning-bootstrap.md")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("remote_host_id")
    parser.parse_args()
    print("bootstrap_new_host.py is a design skeleton, not a working command. "
          "See docs/provisioning-bootstrap.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
