#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Self-update module for Tomato Novel Downloader (refactored).'''
from __future__ import annotations

import json
import os
import sys
import time
import shutil
import zipfile
import tarfile
import subprocess
import tempfile
import threading
import platform
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, List

_requests = None
_packaging_version = None

UPDATE_LOG_PATH = Path(tempfile.gettempdir()) / "update.log"
# Helper script names for different environments
HELPER_SCRIPT_BASENAME_PY = "tomato_update_helper.py"
HELPER_SCRIPT_BASENAME_PS1 = "tomato_update_helper.ps1"
HELPERSCRIPT_DEFAULT_NAME = HELPER_SCRIPT_BASENAME_PY


def _ensure_dependencies() -> bool:
    '''Lazy import of third-party dependencies.'''
    global _requests, _packaging_version
    if _requests is not None and _packaging_version is not None:
        return True
    try:
        import requests  # type: ignore
        from packaging import version as pkg_version  # type: ignore
        _requests = requests
        _packaging_version = pkg_version
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[Updater] missing dependency: {exc}")
        print("Please install: pip install requests packaging")
        return False


def _get_requests():
    if not _ensure_dependencies():
        raise ImportError("requests is not available")
    return _requests


def _get_packaging_version():
    if not _ensure_dependencies():
        raise ImportError("packaging is not available")
    return _packaging_version


def _log(message: str, level: str = "INFO", echo: bool = False) -> None:
    '''Append a line to the shared update log.'''
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    try:
        UPDATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with UPDATE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass
    if echo:
        print(line)


class UpdateLock:
    '''Prevent multiple update processes from running simultaneously.'''

    def __init__(self) -> None:
        self.lock_file = Path(tempfile.gettempdir()) / "tomato_novel_updater.lock"
        self._handle = None
        self.locked = False

    def acquire(self, timeout: int = 10) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                handle = self.lock_file.open("w")
                if sys.platform.startswith("win"):
                    import msvcrt  # type: ignore
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        handle.write(str(os.getpid()))
                        handle.flush()
                        self._handle = handle
                        self.locked = True
                        return True
                    except OSError:
                        handle.close()
                        time.sleep(0.2)
                else:
                    import fcntl  # type: ignore
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        handle.write(str(os.getpid()))
                        handle.flush()
                        self._handle = handle
                        self.locked = True
                        return True
                    except (BlockingIOError, OSError):
                        handle.close()
                        time.sleep(0.2)
            except FileNotFoundError:
                self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                time.sleep(0.2)
        return False

    def release(self) -> None:
        if not self.locked:
            return
        try:
            if self._handle is not None:
                try:
                    if sys.platform.startswith("win"):
                        import msvcrt  # type: ignore
                        msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl  # type: ignore
                        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                finally:
                    try:
                        self._handle.close()
                    except Exception:
                        pass
        finally:
            self._handle = None
            self.locked = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()

    def is_locked(self) -> bool:
        if self.locked:
            return True

        if not self.lock_file.exists():
            return False

        try:
            if sys.platform.startswith("win"):
                import msvcrt  # type: ignore
                with self.lock_file.open("r+") as handle:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        return False
                    except OSError:
                        return True
            else:
                import fcntl  # type: ignore
                with self.lock_file.open("a+") as handle:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                        return False
                    except (BlockingIOError, OSError):
                        return True
        except FileNotFoundError:
            return False
        except Exception:
            return False


def is_official_release_build() -> bool:
    '''Return True when running from a PyInstaller bundle.'''
    try:
        return bool(getattr(sys, "frozen", False))
    except Exception:
        return False


@dataclass
class _AssetCandidate:
    name: str
    download_url: str
    size: int = 0
    content_type: str = ""


class UpdateChecker:
    '''Query GitHub releases and compare versions.'''

    def __init__(self, github_repo: str, current_version: str, cache_ttl: int = 900) -> None:
        self.github_repo = github_repo
        self.current_version = (current_version or "0.0.0").strip()
        self.cache_ttl = cache_ttl
        self.timeout = 20
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time = 0.0

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "TomatoNovelDownloader"
        }
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _normalize_version(tag: Optional[str]) -> str:
        if not tag:
            return "0.0.0"
        tag = tag.strip()
        if tag.lower().startswith("v"):
            tag = tag[1:]
        return tag

    @staticmethod
    def _is_timestamp_version(version: str) -> bool:
        parts = version.split("+")
        if len(parts) != 2:
            return False
        date_part, suffix = parts
        try:
            numbers = [int(x) for x in date_part.split('.')]
        except ValueError:
            return False
        if len(numbers) != 4:
            return False
        if len(suffix) not in (7, 8):
            return False
        return all(c in "0123456789abcdef" for c in suffix.lower())

    @staticmethod
    def _compare_timestamp_versions(candidate: str, current: str) -> bool:
        def parse(ver: str):
            try:
                main, suffix = ver.split("+", 1)
                numbers = [int(x) for x in main.split('.')]
                return numbers, suffix
            except Exception:
                return [], ""

        cand_numbers, cand_suffix = parse(candidate)
        curr_numbers, curr_suffix = parse(current)
        if not cand_numbers or not curr_numbers:
            return candidate != current
        if cand_numbers > curr_numbers:
            return True
        if cand_numbers < curr_numbers:
            return False
        return cand_suffix > curr_suffix

    @staticmethod
    def _extract_checksums_from_body(body: str, container: Dict[str, str]) -> None:
        import re
        patterns = [
            re.compile(r"SHA256\s*\(([^)]+)\)\s*=\s*([A-Fa-f0-9]{64})"),
            re.compile(r"([A-Fa-f0-9]{64})\s+\*?([\w\.-]+)"),
            re.compile(r"([\w\.-]+)\s*[:=]\s*([A-Fa-f0-9]{64})")
        ]
        for line in body.splitlines():
            text = line.strip()
            if len(text) < 64:
                continue
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        first, second = groups
                        if len(first) == 64:
                            digest, filename = first, second
                        elif len(second) == 64:
                            filename, digest = first, second
                        else:
                            continue
                        container[filename.strip()] = digest.strip().lower()
                        break

    def _is_newer_version(self, candidate: str) -> bool:
        if self._is_timestamp_version(candidate) or self._is_timestamp_version(self.current_version):
            return self._compare_timestamp_versions(candidate, self.current_version)
        try:
            ver_mod = _get_packaging_version()
            return ver_mod.parse(candidate) > ver_mod.parse(self.current_version)
        except Exception:
            return candidate != self.current_version

    def fetch_latest_release(self, include_prerelease: bool = False) -> Optional[Dict[str, Any]]:
        if not _ensure_dependencies():
            return None
        requests = _get_requests()
        url = f"https://api.github.com/repos/{self.github_repo}/releases"
        try:
            resp = requests.get(url, headers=self._headers(), params={"per_page": 5}, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as exc:
            _log(f"failed to query releases: {exc}", "ERROR")
            return None
        releases = resp.json()
        if not isinstance(releases, list):
            return None
        for release in releases:
            if release.get("draft"):
                continue
            if not include_prerelease and release.get("prerelease"):
                continue
            return release
        return None

    def get_latest_update(self, force: bool = False, include_prerelease: bool = False) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not force and self._cache and (now - self._cache_time) < self.cache_ttl:
            return self._cache
        release = self.fetch_latest_release(include_prerelease=include_prerelease)
        if not release:
            return None
        version = self._normalize_version(release.get("tag_name") or release.get("name"))
        if not self._is_newer_version(version):
            return None
        body = release.get("body") or ""
        checksums: Dict[str, str] = {}
        if body:
            self._extract_checksums_from_body(body, checksums)
        assets = []
        for asset in release.get("assets", []):
            assets.append({
                "name": asset.get("name", ""),
                "download_url": asset.get("browser_download_url"),
                "size": asset.get("size", 0),
                "content_type": asset.get("content_type", "")
            })
        update_info = {
            "version": version,
            "name": release.get("name", version),
            "body": body,
            "published_at": release.get("published_at"),
            "assets": assets,
            "checksums": checksums,
            "html_url": release.get("html_url"),
            "prerelease": release.get("prerelease", False),
            "raw": release
        }
        self._cache = update_info
        self._cache_time = now
        return update_info


class AutoUpdater:
    '''High level update helper that exposes check/download/install.'''

    def __init__(self, github_repo: str, current_version: str, official_build_only: bool = False) -> None:
        self.github_repo = github_repo
        self.current_version = current_version
        self.official_build_only = official_build_only
        self.checker = UpdateChecker(github_repo, current_version)
        self.update_callbacks: List[Callable[[str, Any], None]] = []
        self.is_downloading = False
        self.download_progress = 0
        self.download_total = 0
        self._download_path: Optional[Path] = None

    def register_callback(self, callback: Callable[[str, Any], None]) -> None:
        self.update_callbacks.append(callback)

    def _notify(self, event: str, data: Any = None) -> None:
        for callback in self.update_callbacks:
            try:
                callback(event, data)
            except Exception:
                pass

    def check_for_updates(self, force: bool = False, include_prerelease: bool = False) -> Optional[Dict[str, Any]]:
        self._notify('check_start', None)
        info = self.checker.get_latest_update(force=force, include_prerelease=include_prerelease)
        if info:
            self._notify('update_available', info)
        else:
            self._notify('no_update', None)
        return info

    def _select_asset(self, update_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assets = update_info.get('assets', []) or []
        if not assets:
            return None
        system = platform.system().lower()
        machine = platform.machine().lower()

        def score(asset: Dict[str, Any]) -> int:
            name = (asset.get('name') or '').lower()
            s = 0
            if system.startswith('win'):
                if name.endswith('.exe'):
                    s += 4
                if name.endswith('.zip'):
                    s += 3
                if 'windows' in name or 'win' in name:
                    s += 2
                # Prefer installer packages for Windows release updates
                if 'setup' in name or 'installer' in name:
                    s += 6
            elif system == 'darwin':
                if any(token in name for token in ('mac', 'darwin', 'osx')):
                    s += 4
                if name.endswith('.zip'):
                    s += 3
            else:
                if 'linux' in name:
                    s += 3
                if name.endswith('.tar.gz') or name.endswith('.tgz'):
                    s += 5
                if name.endswith('.appimage'):
                    s += 6
            if any(token in machine for token in ('arm', 'aarch')) and any(token in name for token in ('arm', 'aarch', 'arm64')):
                s += 2
            if any(token in machine for token in ('x86_64', 'amd64')) and any(token in name for token in ('x86_64', 'x64', 'amd64')):
                s += 2
            if 'debug' in name:
                s -= 2
            return s

        best = max(assets, key=score)
        if score(best) <= 0:
            return assets[0]
        return best

    def download_update(self, update_info: Dict[str, Any], progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        if self.official_build_only and not is_official_release_build():
            self._notify('download_error', 'auto update is disabled for source builds')
            return None
        if self.is_downloading:
            return None

        asset = self._select_asset(update_info)
        if not asset or not asset.get('download_url'):
            self._notify('download_error', 'no suitable asset')
            return None

        update_lock = UpdateLock()
        if update_lock.is_locked():
            self._notify('download_error', 'another update is running')
            return None

        if not update_lock.acquire(timeout=5):
            self._notify('download_error', 'could not acquire update lock')
            return None

        self.is_downloading = True
        self._notify('download_start', asset)
        try:
            requests = _get_requests()
            headers = {
                'User-Agent': 'Tomato-Novel-Downloader',
                'Accept': 'application/octet-stream'
            }
            token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
            if token:
                headers['Authorization'] = f'Bearer {token}'
            response = requests.get(asset['download_url'], headers=headers, stream=True, timeout=60)
            response.raise_for_status()

            total = int(response.headers.get('content-length') or 0)
            self.download_total = total
            self.download_progress = 0
            temp_dir = Path(tempfile.gettempdir())
            file_path = temp_dir / asset['name']
            with file_path.open('wb') as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
                        self.download_progress += len(chunk)
                        if progress_callback:
                            progress_callback(self.download_progress, total)
                        percent = (self.download_progress / total * 100) if total else 0
                        self._notify('download_progress', {
                            'current': self.download_progress,
                            'total': total,
                            'percent': percent
                        })

            if total and file_path.stat().st_size != total:
                raise RuntimeError('download size mismatch')

            checksum_map = update_info.get('checksums') or {}
            expected = checksum_map.get(asset['name']) if checksum_map else None
            if expected:
                digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if digest.lower() != expected.lower():
                    file_path.unlink(missing_ok=True)
                    raise RuntimeError('SHA256 verification failed')

            self._download_path = file_path
            self._notify('download_complete', {'path': str(file_path)})
            return str(file_path)
        except Exception as exc:
            self._notify('download_error', str(exc))
            return None
        finally:
            self.is_downloading = False
            update_lock.release()

    def _target_root(self) -> Path:
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).resolve().parent
        return Path(os.path.abspath(sys.argv[0])).resolve().parent

    def _restart_command(self) -> List[str]:
        if getattr(sys, 'frozen', False):
            return [sys.executable]
        argv0 = os.path.abspath(sys.argv[0])
        return [sys.executable, argv0] + sys.argv[1:]

    @staticmethod
    def _detect_payload_root(staging_root: Path) -> Path:
        entries = [p for p in staging_root.iterdir() if not p.name.startswith('__MACOSX')]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        return staging_root

    def _prepare_staging(self, update_path: Path) -> Dict[str, Path]:
        staging_root = Path(tempfile.mkdtemp(prefix='tomato_stage_'))
        payload_root = staging_root
        try:
            if update_path.is_dir():
                shutil.copytree(update_path, staging_root / update_path.name, dirs_exist_ok=True)
                payload_root = self._detect_payload_root(staging_root)
            else:
                name_lower = update_path.name.lower()
                if name_lower.endswith('.zip'):
                    with zipfile.ZipFile(update_path, 'r') as zf:
                        zf.extractall(staging_root)
                    payload_root = self._detect_payload_root(staging_root)
                elif name_lower.endswith('.tar.gz') or name_lower.endswith('.tgz') or name_lower.endswith('.tar.xz'):
                    mode = 'r:gz'
                    if name_lower.endswith('.tar.xz'):
                        mode = 'r:xz'
                    with tarfile.open(update_path, mode) as tf:
                        tf.extractall(staging_root)
                    payload_root = self._detect_payload_root(staging_root)
                else:
                    shutil.copy2(update_path, staging_root / update_path.name)
                    payload_root = staging_root
        except Exception as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise RuntimeError(f'failed to extract update package: {exc}')
        return {
            'staging_root': staging_root,
            'payload_root': payload_root
        }

    def _write_manifest(self, staging_root: Path, payload_root: Path, restart: bool, installer_path: Optional[Path] = None) -> Path:
        manifest = {
            'staging_root': str(staging_root),
            'payload_root': str(payload_root),
            'target_root': str(self._target_root()),
            'wait_pid': os.getpid(),
            'restart': bool(restart),
            'restart_cmd': self._restart_command() if restart else [],
            'log_path': str(UPDATE_LOG_PATH),
            'cleanup': True,
            'created_at': time.time(),
            'installer_path': (str(installer_path) if installer_path else None)
        }
        manifest_path = staging_root / 'update_manifest.json'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return manifest_path

    def _write_helper_script(self) -> Path:
        """Create a platform-appropriate helper in a temp directory.

        - For frozen Windows builds: emit a PowerShell helper script to avoid
          relying on a system Python interpreter (which may not exist).
        - Otherwise: emit the Python helper script and invoke with sys.executable.
        """
        helper_dir = Path(tempfile.mkdtemp(prefix='tomato_helper_'))
        if sys.platform.startswith('win') and getattr(sys, 'frozen', False):
            helper_path = helper_dir / HELPER_SCRIPT_BASENAME_PS1
            helper_path.write_text(UPDATE_HELPER_SCRIPT_PS1, encoding='utf-8')
        else:
            helper_path = helper_dir / HELPERSCRIPT_DEFAULT_NAME
            helper_path.write_text(UPDATE_HELPER_SCRIPT, encoding='utf-8')
        return helper_path

    def _spawn_helper(self, helper_path: Path, manifest_path: Path) -> int:
        """Launch the helper process detached.

        Windows frozen builds spawn PowerShell to run a ps1 helper script.
        Other environments use the current Python executable to run a .py helper.
        """
        creationflags = 0
        if sys.platform.startswith('win'):
            creationflags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)

        if helper_path.suffix.lower() == '.ps1':
            # PowerShell helper on Windows
            cmd = [
                'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(helper_path),
                '-Manifest', str(manifest_path)
            ]
        else:
            # Python helper (source runs or non-Windows)
            cmd = [sys.executable, str(helper_path), '--manifest', str(manifest_path)]

        proc = subprocess.Popen(cmd, creationflags=creationflags, close_fds=True)
        return proc.pid

    def install_update(self, update_file: str, restart: bool = True) -> bool:
        name_lower = os.path.basename(update_file).lower()
        is_installer = (sys.platform.startswith('win') and name_lower.endswith('.exe') and (('setup' in name_lower) or ('installer' in name_lower)))
        update_path = Path(update_file)
        if not update_path.exists():
            self._notify('install_error', f'update file not found: {update_file}')
            return False
        try:
            _log(f'staging update from {update_path}', 'INFO')
            staging_info = self._prepare_staging(update_path)
            staging_root = staging_info['staging_root']
            payload_root = staging_info['payload_root']
            manifest_path = self._write_manifest(staging_root, payload_root, restart, (staging_root / update_path.name) if is_installer else None)
            helper_path = self._write_helper_script()
            self._notify('install_ready', {'manifest': str(manifest_path)})
            helper_pid = self._spawn_helper(helper_path, manifest_path)
            self._notify('helper_started', {'pid': helper_pid, 'manifest': str(manifest_path)})
            _log(f'update helper started, pid={helper_pid}', 'INFO')
            return True
        except Exception as exc:
            _log(f'install failed: {exc}', 'ERROR')
            self._notify('install_error', str(exc))
            return False

    def apply_release(self, update_info: Dict[str, Any], restart: bool = True) -> bool:
        path = self.download_update(update_info)
        if not path:
            return False
        success = self.install_update(path, restart=restart)
        if success:
            self._notify('install_scheduled', {'path': path})
        return success

    def _start_force_update(self, update_info: Dict[str, Any]) -> None:
        self.apply_release(update_info, restart=True)

    @staticmethod
    def check_update_status() -> Dict[str, Any]:
        status = {
            'last_update_time': None,
            'update_success': False,
            'error_message': None,
            'log_exists': UPDATE_LOG_PATH.exists()
        }
        if not status['log_exists']:
            return status
        try:
            lines = UPDATE_LOG_PATH.read_text(encoding='utf-8').splitlines()
        except Exception:
            return status
        for line in reversed(lines[-100:]):
            text = line.strip()
            if 'UPDATE_SUCCESS' in text or 'Update helper finished' in text:
                status['update_success'] = True
            if 'files' in text.lower() and 'updated' in text.lower():
                if ']' in text:
                    status['last_update_time'] = text.split(']')[0].strip('[')
            if 'ERROR' in text:
                status['error_message'] = text.split(']')[-1].strip()
        return status

    @staticmethod
    def clear_update_log() -> None:
        try:
            UPDATE_LOG_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def check_and_notify_update(updater: AutoUpdater, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
    def task():
        info = updater.check_for_updates()
        if info and callback:
            callback(info)
    threading.Thread(target=task, daemon=True).start()


UPDATE_HELPER_SCRIPT = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone helper that swaps in the downloaded update."""

import argparse
import json
import os
import sys
import time
import shutil
import subprocess
import tempfile
import platform
import stat
from pathlib import Path
from typing import Optional


def _parse_args():
    parser = argparse.ArgumentParser(description="Tomato Novel Downloader update helper")
    parser.add_argument('--manifest', required=True, help='path to manifest json')
    parser.add_argument('--timeout', type=int, default=90, help='seconds to wait for the main process')
    return parser.parse_args()


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _log(message: str, level: str = 'INFO', log_path: Optional[Path] = None) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    if log_path is None:
        log_path = Path(tempfile.gettempdir()) / 'update.log'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a', encoding='utf-8') as handle:
            handle.write(line + "
")
    except Exception:
        pass
    print(line)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if platform.system().lower().startswith('win'):
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except OSError:
        return False


def _wait_for_exit(pid: int, timeout: int, log_path: Path) -> None:
    if pid <= 0:
        return
    _log(f'waiting for process {pid} to exit', 'INFO', log_path)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _process_alive(pid):
            _log('main process has exited', 'INFO', log_path)
            time.sleep(1.5)
            return
        time.sleep(0.5)
    if _process_alive(pid):
        _log('timeout waiting for process, trying to terminate', 'WARNING', log_path)
        try:
            if platform.system().lower().startswith('win'):
                subprocess.call(['taskkill', '/PID', str(pid), '/F', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, 9)
        except Exception as exc:
            _log(f'failed to terminate process: {exc}', 'WARNING', log_path)
        time.sleep(1.5)


def _ensure_writable(path: Path) -> None:
    try:
        if path.exists():
            path.chmod(path.stat().st_mode | stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except Exception:
        pass


def _copy_payload(payload_root: Path, target_root: Path, log_path: Path) -> None:
    for src_dir, _, filenames in os.walk(payload_root):
        rel = os.path.relpath(src_dir, payload_root)
        dest_dir = target_root if rel == '.' else target_root / rel
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            src_file = Path(src_dir) / filename
            dest_file = Path(dest_dir) / filename
            tmp_file = dest_file.with_suffix(dest_file.suffix + '.updatetmp')
            if tmp_file.exists():
                tmp_file.unlink()
            shutil.copy2(src_file, tmp_file)
            _ensure_writable(dest_file)
            os.replace(tmp_file, dest_file)
            _log(f'updated {dest_file}', 'DEBUG', log_path)


def main():
    args = _parse_args()
    manifest = _load_manifest(Path(args.manifest))
    log_path = Path(manifest.get('log_path') or (Path(tempfile.gettempdir()) / 'update.log'))
    staging_root = Path(manifest['staging_root'])
    payload_root = Path(manifest['payload_root'])
    target_root = Path(manifest['target_root'])
    installer_path = Path(manifest.get('installer_path') or '') if manifest.get('installer_path') else None

    _log('update helper started', 'INFO', log_path)
    _wait_for_exit(int(manifest.get('wait_pid') or 0), args.timeout, log_path)

    try:
        if installer_path and installer_path.exists():
            if platform.system().lower().startswith('win'):
                # Elevate and run NSIS installer silently with target dir
                safe_target = str(target_root)
                ps_cmd = (
                    f"Start-Process -FilePath \"{installer_path}\" "
                    f"-ArgumentList '/S','/D={safe_target}' -Verb RunAs -Wait"
                )
                subprocess.check_call(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_cmd])
                _log('INSTALLER_SUCCESS executed NSIS installer', 'SUCCESS', log_path)
            else:
                subprocess.check_call([str(installer_path), '/S'])
                _log('INSTALLER_SUCCESS executed installer', 'SUCCESS', log_path)
        else:
            _copy_payload(payload_root, target_root, log_path)
            _log('UPDATE_SUCCESS files applied', 'SUCCESS', log_path)
    except Exception as exc:
        _log(f'update failed: {exc}', 'ERROR', log_path)
        sys.exit(1)
    finally:
        if manifest.get('cleanup', True):
            shutil.rmtree(staging_root, ignore_errors=True)

    if manifest.get('restart') and manifest.get('restart_cmd'):
        cmd = manifest['restart_cmd']
        try:
            creationflags = 0
            if platform.system().lower().startswith('win'):
                creationflags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            subprocess.Popen(cmd, creationflags=creationflags, close_fds=True)
            _log('restart command launched', 'INFO', log_path)
        except Exception as exc:
            _log(f'failed to restart application: {exc}', 'WARNING', log_path)

    _log('Update helper finished', 'INFO', log_path)


if __name__ == '__main__':
    main()
'''

# PowerShell helper used for Windows frozen builds to avoid requiring a system Python.
UPDATE_HELPER_SCRIPT_PS1 = r"""
param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [int]$Timeout = 90
)

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO', [string]$LogPath)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] [$Level] $Message"
    try {
        if (-not [string]::IsNullOrEmpty($LogPath)) {
            $dir = Split-Path -Parent $LogPath
            if ($dir) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            Add-Content -Path $LogPath -Value $line -Encoding UTF8
        }
    } catch {}
    Write-Output $line
}

function Wait-ForExit {
    param([int]$Pid, [int]$TimeoutSec, [string]$LogPath)
    if ($Pid -le 0) { return }
    Write-Log "waiting for process $Pid to exit" 'INFO' $LogPath
    try {
        Wait-Process -Id $Pid -Timeout $TimeoutSec -ErrorAction SilentlyContinue
    } catch {}
    Start-Sleep -Seconds 1.5
}

function Copy-Payload {
    param([string]$Src, [string]$Dst, [string]$LogPath)
    # Prefer robocopy for robustness if available
    $robocopy = (Get-Command robocopy -ErrorAction SilentlyContinue)
    if ($robocopy) {
        # /E recurse, /XO skip older, /R:2 retry 2 times, /W:1 wait 1s, /NP no progress
        $rcArgs = @($Src, $Dst, '/E','/XO','/R:2','/W:1','/NFL','/NDL','/NP','/NJH','/NJS')
        $p = Start-Process -FilePath $robocopy.Source -ArgumentList $rcArgs -Wait -NoNewWindow -PassThru
        if ($p.ExitCode -lt 8) { return }
        Write-Log "robocopy exit code $($p.ExitCode), falling back to Copy-Item" 'WARNING' $LogPath
    }
    $srcPrefix = (Resolve-Path $Src).Path.TrimEnd('\\','/')
    Get-ChildItem -Path $Src -Recurse -File | ForEach-Object {
        $full = $_.FullName
        if ($full.StartsWith($srcPrefix)) { $rel = $full.Substring($srcPrefix.Length).TrimStart('\\','/') } else { $rel = $_.Name }
        $destDir = Join-Path $Dst ([System.IO.Path]::GetDirectoryName($rel))
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        $destFile = Join-Path $Dst $rel
        $tmpFile = "$destFile.updatetmp"
        if (Test-Path $tmpFile) { Remove-Item -Path $tmpFile -Force -ErrorAction SilentlyContinue }
        Copy-Item -Path $_.FullName -Destination $tmpFile -Force
        try { Move-Item -Path $tmpFile -Destination $destFile -Force } catch {
            # If Move fails, try Copy as fallback
            Copy-Item -Path $_.FullName -Destination $destFile -Force
            if (Test-Path $tmpFile) { Remove-Item -Path $tmpFile -Force -ErrorAction SilentlyContinue }
        }
        Write-Log "updated $destFile" 'DEBUG' $LogPath
    }
}

try {
    $m = Get-Content -Path $Manifest -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Log "failed to read manifest: $($_.Exception.Message)" 'ERROR' ''
    exit 1
}

$StagingRoot = $m.staging_root
$PayloadRoot = $m.payload_root
$TargetRoot  = $m.target_root
$WaitPid     = [int]$m.wait_pid
$Restart     = [bool]$m.restart
$RestartCmd  = @($m.restart_cmd)
$LogPath     = if ($m.log_path) { [string]$m.log_path } else { Join-Path $env:TEMP 'update.log' }

Write-Log 'update helper started' 'INFO' $LogPath
Wait-ForExit -Pid $WaitPid -TimeoutSec $Timeout -LogPath $LogPath

try {
    if ($m.installer_path -and (Test-Path -Path $m.installer_path)) {
        $args = @('/S', "/D=$TargetRoot")
        Start-Process -FilePath $m.installer_path -ArgumentList $args -Verb RunAs -Wait
        Write-Log 'INSTALLER_SUCCESS executed NSIS installer' 'SUCCESS' $LogPath
    } else {
        Copy-Payload -Src $PayloadRoot -Dst $TargetRoot -LogPath $LogPath
        Write-Log 'UPDATE_SUCCESS files applied' 'SUCCESS' $LogPath
    }
} catch {
    Write-Log "update failed: $($_.Exception.Message)" 'ERROR' $LogPath
    exit 1
} finally {
    if ($m.cleanup -ne $false) {
        try { Remove-Item -Path $StagingRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}

if ($Restart -and $RestartCmd -and $RestartCmd.Length -gt 0) {
    try {
        $exe = [string]$RestartCmd[0]
        $args = @()
        if ($RestartCmd.Length -gt 1) { $args = $RestartCmd[1..($RestartCmd.Length-1)] }
        Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $TargetRoot -WindowStyle Hidden
        Write-Log 'restart command launched' 'INFO' $LogPath
    } catch {
        Write-Log "failed to restart application: $($_.Exception.Message)" 'WARNING' $LogPath
    }
}

Write-Log 'Update helper finished' 'INFO' $LogPath
"""


