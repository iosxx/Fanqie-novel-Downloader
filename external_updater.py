#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Compatibility helpers for the update subsystem.'''
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


def verify_file_checksum(path: str, expected_sha256: str) -> bool:
    '''Return True when the file digest matches the expected SHA256 value.'''
    target = Path(path)
    if not target.is_file():
        return False
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return digest.lower() == expected_sha256.lower()


def check_permissions(test_path: Optional[str] = None) -> bool:
    '''Simple write-test to make sure we can modify the installation directory.'''
    candidate = Path(test_path) if test_path else Path.cwd()
    candidate.mkdir(parents=True, exist_ok=True)
    try:
        probe = candidate / f"._perm_test_{int(time.time()*1000)}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def detect_platform_details() -> Dict[str, Any]:
    '''Collect a couple of platform hints for logging/debug purposes.'''
    import platform

    system = platform.system()
    machine = platform.machine()
    return {
        'system': system,
        'release': platform.release(),
        'machine': machine,
        'is_windows': system.lower().startswith('win'),
        'is_mac': system == 'Darwin',
        'is_linux': system == 'Linux',
        'is_arm': any(token in machine.lower() for token in ('arm', 'aarch')),
        'is_x86': any(token in machine.lower() for token in ('x86', 'amd64', 'i686', 'i386'))
    }


def wait_for_process_exit(pid: int, timeout: int = 30) -> bool:
    '''Wait until the given PID disappears. Returns True on clean exit.'''
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if os.name == 'nt':
                import ctypes
                SYNCHRONIZE = 0x00100000
                handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    return True
            else:
                os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.5)
    return False


def _auto_install(package: str, repo: str, current_version: str, restart: bool) -> None:
    from updater import AutoUpdater

    updater = AutoUpdater(repo, current_version)
    if updater.install_update(package, restart=restart):
        print("Update helper launched successfully.")
    else:
        print("Failed to schedule update.", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description='Minimal external updater wrapper')
    parser.add_argument('package', nargs='?', help='path to a downloaded update package')
    parser.add_argument('--repo', default=os.environ.get('TOMATO_UPDATE_REPO', ''), help='GitHub repo in owner/name form')
    parser.add_argument('--version', default=os.environ.get('TOMATO_CURRENT_VERSION', '0.0.0'), help='current version string')
    parser.add_argument('--restart', action='store_true', help='restart application after successful install')
    args = parser.parse_args(argv)

    if args.package:
        _auto_install(args.package, args.repo or '', args.version or '0.0.0', args.restart)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
