#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部更新脚本 - 独立处理所有更新操作
当主程序退出后，由这个脚本接管所有更新流程
"""

import sys
import os
import time
import tempfile
import json
import platform
import subprocess
import shutil
import stat
from pathlib import Path

# 延迟导入 requests，避免模块导入失败
_requests = None
# 目标可执行文件路径（由主程序传入）
CURRENT_EXE_PATH = None

def _get_requests():
    """延迟导入并获取 requests 模块"""
    global _requests
    if _requests is None:
        try:
            import requests as req
            _requests = req
        except ImportError as e:
            print(f"[Updater] 错误: requests 库未安装")
            print("[Updater] 请运行: pip install requests")
            raise ImportError(f"requests 模块未安装: {e}")
    return _requests

# 添加项目路径以导入内部模块
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from updater import AutoUpdater
    from config import __github_repo__, __version__, CONFIG
except ImportError as e:
    print(f"[Updater] 导入失败: {e}")
    sys.exit(1)


def log_message(message, level="INFO"):
    """记录日志消息（同时写入临时 update.log 以便 GUI 检测状态）"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    # 同步写入 GUI 解析的日志文件（与 updater._create_update_log 一致）
    try:
        log_file = os.path.join(tempfile.gettempdir(), 'update.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        # 日志写入失败不影响主流程
        pass


def wait_for_process_exit(pid, timeout=30):
    """等待指定进程退出"""
    log_message(f"等待主程序(PID: {pid})退出...")
    
    for i in range(timeout * 2):  # 每0.5秒检查一次
        try:
            if platform.system() == 'Windows':
                # Windows: 使用OpenProcess检查进程是否存在
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                process = kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
                if process == 0:
                    log_message("主程序已退出")
                    # Windows需要额外延迟以确保文件锁完全释放
                    log_message("等待文件锁释放...")
                    time.sleep(2)
                    return True
                kernel32.CloseHandle(process)
            else:
                # Unix: 发送信号0检查进程
                os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            log_message("主程序已退出")
            # 额外延迟以确保所有资源被释放
            log_message("等待文件锁释放...")
            time.sleep(1)
            return True
        
        time.sleep(0.5)
    
    log_message(f"等待超时，继续执行更新", "WARNING")
    # 即使超时也等待一下，给文件锁释放的机会
    time.sleep(2)
    return False


def get_current_exe_path():
    """获取待更新的目标可执行文件路径（由主程序传入）。"""
    global CURRENT_EXE_PATH
    if CURRENT_EXE_PATH and os.path.exists(CURRENT_EXE_PATH):
        return CURRENT_EXE_PATH
    # 回退：尽力推断，但不可靠
    try:
        if getattr(sys, 'frozen', False):
            return sys.executable
    except Exception:
        pass
    return os.path.abspath(sys.argv[0])


def backup_current_exe():
    """备份当前可执行文件"""
    current_exe = get_current_exe_path()
    backup_path = current_exe + ".backup"

    if os.path.exists(current_exe):
        log_message(f"创建备份: {backup_path}")
        shutil.copy2(current_exe, backup_path)
        return backup_path
    return None


def restore_backup(backup_path):
    """从备份恢复文件"""
    if backup_path and os.path.exists(backup_path):
        current_exe = get_current_exe_path()
        log_message(f"从备份恢复: {backup_path}")
        shutil.copy2(backup_path, current_exe)
        return True
    return False


def cleanup_backup(backup_path):
    """清理备份文件"""
    if backup_path and os.path.exists(backup_path):
        try:
            os.remove(backup_path)
            log_message(f"清理备份文件: {backup_path}")
        except Exception as e:
            log_message(f"清理备份文件失败: {e}", "WARNING")


def is_file_locked(filepath):
    """检测文件是否被锁定（Windows专用）"""
    if platform.system() != 'Windows':
        return False
    
    if not os.path.exists(filepath):
        return False
    
    try:
        # 尝试以独占写入模式打开文件
        with open(filepath, 'a') as f:
            pass
        return False
    except (IOError, OSError):
        return True


def wait_for_file_unlock(filepath, timeout=10):
    """等待文件解锁"""
    if not os.path.exists(filepath):
        return True
    
    log_message(f"检查文件锁状态: {filepath}")
    
    for i in range(timeout * 2):  # 每0.5秒检查一次
        if not is_file_locked(filepath):
            log_message("文件已解锁")
            return True
        
        if i == 0:
            log_message("文件被锁定，等待释放...")
        time.sleep(0.5)
    
    log_message("文件锁等待超时", "WARNING")
    return False


class MultiThreadDownloader:
    """多线程分段下载器（支持 Range）。"""
    def __init__(self, url: str, dest: str, headers: dict | None = None, threads: int = 6):
        self.url = url
        self.dest = dest
        self.headers = headers or {}
        self.threads = max(2, int(threads))
        self._stop = False

    def _supports_range(self, requests):
        try:
            resp = requests.head(self.url, headers=self.headers, allow_redirects=True, timeout=15)
            accept_ranges = resp.headers.get('Accept-Ranges', '')
            cl = int(resp.headers.get('Content-Length', '0') or 0)
            return ('bytes' in accept_ranges.lower()) and cl > 0, cl
        except Exception:
            # HEAD 失败，尝试 GET
            try:
                resp = requests.get(self.url, headers=self.headers, stream=True, timeout=15)
                cl = int(resp.headers.get('Content-Length', '0') or 0)
                accept_ranges = resp.headers.get('Accept-Ranges', '')
                resp.close()
                return ('bytes' in accept_ranges.lower()) and cl > 0, cl
            except Exception:
                return False, 0

    def download(self) -> bool:
        requests = _get_requests()
        support, total = self._supports_range(requests)
        if not support or total <= 0:
            # 回退到单线程
            return self._single_thread_download(requests)

        # 分段范围
        part_size = max(1, total // self.threads)
        ranges = []
        start = 0
        for i in range(self.threads):
            end = (start + part_size - 1) if i < self.threads - 1 else (total - 1)
            ranges.append((start, end))
            start = end + 1

        temp_dir = tempfile.gettempdir()
        part_files = [os.path.join(temp_dir, f"{os.path.basename(self.dest)}.part{i}") for i in range(self.threads)]

        import threading
        errs: list[Exception] = []

        def worker(idx: int, byte_range: tuple[int, int]):
            nonlocal errs
            if self._stop:
                return
            s, e = byte_range
            hdrs = dict(self.headers)
            hdrs['Range'] = f'bytes={s}-{e}'
            try:
                with requests.get(self.url, headers=hdrs, stream=True, timeout=60) as resp:
                    resp.raise_for_status()
                    with open(part_files[idx], 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if self._stop:
                                return
                            if chunk:
                                f.write(chunk)
            except Exception as ex:
                errs.append(ex)
                self._stop = True

        threads = []
        for i, r in enumerate(ranges):
            t = threading.Thread(target=worker, args=(i, r), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        if errs or self._stop:
            for pf in part_files:
                try:
                    if os.path.exists(pf):
                        os.remove(pf)
                except Exception:
                    pass
            return False

        # 合并
        try:
            with open(self.dest, 'wb') as out:
                for pf in part_files:
                    with open(pf, 'rb') as p:
                        shutil.copyfileobj(p, out)
            # 校验大小
            if os.path.getsize(self.dest) != total:
                raise IOError("合并后文件大小与预期不符")
        finally:
            for pf in part_files:
                try:
                    if os.path.exists(pf):
                        os.remove(pf)
                except Exception:
                    pass
        return True

    def _single_thread_download(self, requests) -> bool:
        try:
            with requests.get(self.url, headers=self.headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(self.dest, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception:
            return False


def verify_file_checksum(filepath: str, expected_hash: str) -> bool:
    """验证文件的SHA256校验值"""
    import hashlib
    try:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        actual_hash = sha256.hexdigest().lower()
        expected_hash = expected_hash.lower()
        
        if actual_hash != expected_hash:
            log_message(f"SHA256校验失败:", "ERROR")
            log_message(f"  预期: {expected_hash}", "ERROR")
            log_message(f"  实际: {actual_hash}", "ERROR")
            return False
        
        log_message(f"SHA256校验通过: {os.path.basename(filepath)}")
        return True
    except Exception as e:
        log_message(f"计算文件SHA256失败: {e}", "WARNING")
        return True  # 如果无法计算，跳过校验


def download_update_file(update_info):
    """下载更新文件（优先多线程分段）。"""
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                log_message(f"第 {attempt + 1} 次重试下载...")
                time.sleep(retry_delay)
                
            log_message("开始下载更新文件...")

            # 创建更新器实例，仅用于选择资产
            updater = AutoUpdater(__github_repo__, __version__)

            # 选择合适的下载资源
            asset = updater._get_platform_asset(update_info['assets'])
            if not asset:
                log_message("没有找到适合当前平台的更新文件", "ERROR")
                return None

            log_message(f"选择下载文件: {asset['name']}")

            # 创建临时文件
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, asset['name'])
            
            # 如果文件已存在且大小正确，可能是之前下载的，验证后直接使用
            if os.path.exists(file_path):
                expected_size = asset.get('size', 0)
                if expected_size > 0 and os.path.getsize(file_path) == expected_size:
                    log_message(f"发现已存在的文件，验证中...")
                    # 验证SHA256（如果有）
                    expected_hash = update_info.get('checksums', {}).get(asset['name'])
                    if expected_hash:
                        if verify_file_checksum(file_path, expected_hash):
                            log_message(f"使用已存在的文件: {file_path}")
                            return file_path
                        else:
                            log_message(f"已存在文件校验失败，重新下载")
                            os.remove(file_path)
                    else:
                        log_message(f"使用已存在的文件（无校验值）: {file_path}")
                        return file_path

            # 下载文件（带 Range 支持）
            headers = {
                'User-Agent': 'Tomato-Novel-Downloader',
                'Accept': 'application/octet-stream'
            }
            token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
            if token:
                headers['Authorization'] = f'Bearer {token}'

            # 首次尝试多线程下载
            if attempt == 0:
                dl = MultiThreadDownloader(asset['download_url'], file_path, headers=headers, 
                                         threads=min(8, max(4, (os.cpu_count() or 4))))
                ok = dl.download()
                if not ok:
                    log_message("多线程下载失败，回退单线程...", "WARNING")
                    # 回退单线程
                    requests = _get_requests()
                    with requests.get(asset['download_url'], headers=headers, stream=True, timeout=60) as resp:
                        resp.raise_for_status()
                        total_size = int(resp.headers.get('content-length', 0))
                        downloaded = 0
                        
                        with open(file_path, 'wb') as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    # 显示进度
                                    if total_size > 0:
                                        percent = (downloaded / total_size) * 100
                                        if int(percent) % 10 == 0:
                                            log_message(f"下载进度: {percent:.1f}%")
            else:
                # 重试时直接使用单线程下载
                requests = _get_requests()
                with requests.get(asset['download_url'], headers=headers, stream=True, timeout=90) as resp:
                    resp.raise_for_status()
                    with open(file_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
            
            # 验证文件大小
            expected_size = asset.get('size', 0)
            actual_size = os.path.getsize(file_path)
            if expected_size > 0 and actual_size != expected_size:
                log_message(f"文件大小不匹配: 预期 {expected_size}, 实际 {actual_size}", "ERROR")
                os.remove(file_path)
                if attempt < max_retries - 1:
                    continue
                return None
            
            # SHA256校验（如果有校验值）
            expected_hash = update_info.get('checksums', {}).get(asset['name'])
            if expected_hash:
                log_message("正在验证文件完整性...")
                if not verify_file_checksum(file_path, expected_hash):
                    os.remove(file_path)
                    if attempt < max_retries - 1:
                        log_message("文件校验失败，准备重试...")
                        continue
                    return None
                log_message("文件完整性验证通过")
            
            log_message(f"下载完成: {file_path}")
            return file_path

        except Exception as e:
            log_message(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {e}", "ERROR")
            # 清理可能损坏的文件
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            
            if attempt >= max_retries - 1:
                log_message("下载失败次数过多，放弃下载", "ERROR")
                return None
    
    return None


def install_update_windows(update_file):
    """Windows 平台安装更新"""
    backup_path = None
    try:
        current_exe = get_current_exe_path()
        log_message("开始安装更新 (Windows)...")

        # 备份当前文件
        backup_path = backup_current_exe()
        if not backup_path:
            log_message("创建备份失败", "ERROR")
            return False

        # 等待文件解锁
        if not wait_for_file_unlock(current_exe, timeout=15):
            log_message("文件锁等待超时，尝试强制替换", "WARNING")

        # 尝试去除只读属性
        try:
            os.chmod(current_exe, stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass

        # 替换文件（多种策略，带指数退避重试）
        log_message(f"替换文件: {current_exe}")
        max_retries = 30
        success = False
        
        for i in range(max_retries):
            try:
                # 策略1: 直接复制覆盖
                shutil.copy2(update_file, current_exe)
                success = True
                break
            except PermissionError as e:
                if i == 0:
                    log_message(f"文件被锁定，等待释放后重试: {e}")
                # 指数退避，但最大不超过2秒
                wait_time = min(0.5 * (1.5 ** (i // 5)), 2.0)
                time.sleep(wait_time)
            except Exception as e:
                if i == 0:
                    log_message(f"文件操作失败，重试中: {e}")
                time.sleep(0.5)
        
        if not success:
            # 策略2: 删除后复制
            log_message("尝试删除-复制策略...")
            try:
                # 尝试移除只读属性
                try:
                    os.chmod(current_exe, stat.S_IWRITE)
                except Exception:
                    pass
                
                # 删除原文件
                for attempt in range(5):
                    try:
                        os.remove(current_exe)
                        break
                    except Exception as e:
                        if attempt == 4:
                            raise
                        time.sleep(0.5)
                
                # 等待一下确保删除完成
                time.sleep(0.5)
                
                # 复制新文件
                shutil.copy2(update_file, current_exe)
                success = True
            except Exception as e2:
                log_message(f"删除-复制策略失败: {e2}", "ERROR")
        
        if success:
            log_message("更新安装成功")
            # 清理备份
            cleanup_backup(backup_path)
            return True
        else:
            log_message("所有替换策略均失败", "ERROR")
            # 恢复备份
            restore_backup(backup_path)
            return False

    except Exception as e:
        log_message(f"安装失败: {e}", "ERROR")
        # 尝试恢复备份
        if backup_path:
            restore_backup(backup_path)
        return False


def detect_platform_details():
    """检测详细的平台信息"""
    system = platform.system()
    machine = platform.machine().lower()
    
    details = {
        'system': system,
        'machine': machine,
        'is_mac': system == 'Darwin',
        'is_linux': system == 'Linux',
        'is_arm': 'arm' in machine or 'aarch' in machine,
        'is_x86': 'x86' in machine or 'i686' in machine or 'amd64' in machine
    }
    
    # 检测是否在容器中运行
    if system == 'Linux':
        details['is_container'] = (
            os.path.exists('/.dockerenv') or 
            os.path.exists('/run/.containerenv') or
            os.environ.get('KUBERNETES_SERVICE_HOST') is not None
        )
    
    return details


def install_update_unix(update_file):
    """Unix 平台安装更新"""
    backup_path = None
    temp_extract_dir = None
    
    try:
        current_exe = get_current_exe_path()
        current_dir = os.path.dirname(current_exe)
        
        # 获取平台详情
        platform_info = detect_platform_details()
        log_message(f"开始安装更新 ({platform_info['system']}/{platform_info['machine']})...")
        
        # 检查写权限
        if not os.access(current_dir, os.W_OK):
            log_message(f"警告：当前目录没有写权限: {current_dir}", "WARNING")
            # 尝试获取权限或提示用户
            if platform_info['is_mac']:
                log_message("macOS: 请确保应用有正确的权限", "WARNING")
            elif platform_info['is_linux']:
                log_message("Linux: 可能需要使用sudo权限运行", "WARNING")

        # 如果是压缩包，解压到临时目录
        if update_file.endswith('.zip'):
            import zipfile
            temp_extract_dir = os.path.join(tempfile.gettempdir(), 'update_extract')
            # 清理旧的解压目录
            if os.path.exists(temp_extract_dir):
                try:
                    shutil.rmtree(temp_extract_dir)
                except:
                    pass
            os.makedirs(temp_extract_dir, exist_ok=True)

            log_message("解压更新文件...")
            try:
                with zipfile.ZipFile(update_file, 'r') as zip_ref:
                    # 获取所有文件列表
                    file_list = zip_ref.namelist()
                    log_message(f"压缩包包含 {len(file_list)} 个文件")
                    zip_ref.extractall(temp_extract_dir)
            except Exception as e:
                log_message(f"解压失败: {e}", "ERROR")
                return False
                
        elif update_file.endswith('.tar.gz') or update_file.endswith('.tgz'):
            import tarfile
            temp_extract_dir = os.path.join(tempfile.gettempdir(), 'update_extract')
            # 清理旧的解压目录
            if os.path.exists(temp_extract_dir):
                try:
                    shutil.rmtree(temp_extract_dir)
                except:
                    pass
            os.makedirs(temp_extract_dir, exist_ok=True)
            
            log_message("解压tarball更新文件...")
            try:
                with tarfile.open(update_file, 'r:gz') as tar:
                    # 安全解压（避免路径遍历攻击）
                    members = tar.getmembers()
                    safe_members = []
                    for member in members:
                        if member.name.startswith('/') or '..' in member.name:
                            log_message(f"跳过不安全的路径: {member.name}", "WARNING")
                            continue
                        safe_members.append(member)
                    log_message(f"压缩包包含 {len(safe_members)} 个文件")
                    tar.extractall(temp_extract_dir, members=safe_members)
            except Exception as e:
                log_message(f"解压失败: {e}", "ERROR")
                return False
                
        elif update_file.lower().endswith('.appimage'):
            # AppImage 单文件直接覆盖
            temp_extract_dir = None
            log_message("检测到AppImage文件")
        elif update_file.lower().endswith('.dmg'):
            # macOS DMG文件需要特殊处理
            log_message("DMG文件需要手动安装", "ERROR")
            return False
        else:
            # 可能是直接的可执行文件
            temp_extract_dir = None
            log_message(f"直接使用文件: {update_file}")

        update_exe = update_file
        if temp_extract_dir:
            # 查找主要可执行文件
            exe_name = os.path.basename(current_exe)
            candidates = []
            
            # 优先查找相同名称的文件
            for root, dirs, files in os.walk(temp_extract_dir):
                # 跳过隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    # 完全匹配
                    if file == exe_name:
                        candidates.insert(0, file_path)
                    # 部分匹配或可执行文件
                    elif (exe_name.lower() in file.lower() or 
                          file.lower().endswith(('.appimage', '.app')) or
                          (os.access(file_path, os.X_OK) and not file.startswith('.'))):
                        candidates.append(file_path)
            
            if not candidates:
                log_message("未找到匹配的可执行文件", "ERROR")
                # 列出找到的文件以供调试
                log_message(f"解压目录内容:", "DEBUG")
                for root, dirs, files in os.walk(temp_extract_dir):
                    for file in files[:10]:  # 只列出前10个文件
                        log_message(f"  - {os.path.join(root, file)}", "DEBUG")
                return False
                
            # 选择最可能的候选文件
            update_exe = candidates[0]
            log_message(f"选择更新文件: {update_exe}")

        # 备份当前文件
        backup_path = backup_current_exe()
        if not backup_path:
            log_message("创建备份失败", "ERROR")
            return False

        # 替换文件（带重试机制）
        log_message(f"替换文件: {current_exe}")
        success = False
        max_attempts = 10
        
        for attempt in range(max_attempts):
            try:
                # 确保源文件存在且可读
                if not os.path.exists(update_exe):
                    raise FileNotFoundError(f"源文件不存在: {update_exe}")
                if not os.access(update_exe, os.R_OK):
                    raise PermissionError(f"无法读取源文件: {update_exe}")
                
                # 尝试复制文件
                shutil.copy2(update_exe, current_exe)
                
                # 验证复制是否成功
                if os.path.exists(current_exe):
                    success = True
                    break
            except PermissionError as e:
                if attempt == 0:
                    log_message(f"权限错误，尝试修改权限: {e}")
                    try:
                        # 尝试修改目标文件权限
                        if os.path.exists(current_exe):
                            os.chmod(current_exe, 0o755)
                    except:
                        pass
                time.sleep(0.5 * (1.5 ** (attempt // 3)))  # 指数退避
            except Exception as e:
                if attempt == 0:
                    log_message(f"文件替换失败，重试中: {e}")
                time.sleep(0.5)
        
        if not success:
            log_message(f"文件替换失败（尝试 {max_attempts} 次）", "ERROR")
            restore_backup(backup_path)
            return False

        # 设置可执行权限
        try:
            os.chmod(current_exe, 0o755)
            log_message("已设置可执行权限")
        except Exception as e:
            log_message(f"设置可执行权限失败: {e}", "WARNING")

        log_message("更新安装成功")
        # 清理备份和临时文件
        cleanup_backup(backup_path)
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception:
                pass
        return True

    except Exception as e:
        log_message(f"安装失败: {e}", "ERROR")
        # 尝试恢复备份
        if backup_path:
            restore_backup(backup_path)
        # 清理临时目录
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception:
                pass
        return False


def restart_application():
    """重启应用程序"""
    try:
        current_exe = get_current_exe_path()
        log_message("重启应用程序...")

        if platform.system() == 'Windows':
            subprocess.Popen([current_exe], creationflags=subprocess.DETACHED_PROCESS)
        else:
            subprocess.Popen([current_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        log_message("应用程序已重启")
        return True

    except Exception as e:
        log_message(f"重启失败: {e}", "ERROR")
        return False


def pause_on_windows(message="按任意键继续..."):
    """Windows平台暂停等待用户输入"""
    if platform.system() == 'Windows':
        print("\n" + "="*50)
        print(message)
        print("="*50)
        try:
            input()
        except:
            time.sleep(5)


def check_permissions():
    """检查是否有足够的权限进行更新"""
    current_exe = get_current_exe_path()
    current_dir = os.path.dirname(current_exe)
    
    # 检查目录写权限
    if not os.access(current_dir, os.W_OK):
        log_message(f"警告：没有写权限: {current_dir}", "WARNING")
        return False
    
    # 检查文件替换权限
    if os.path.exists(current_exe):
        # 尝试以追加模式打开文件（不会修改内容）
        try:
            with open(current_exe, 'a'):
                pass
            return True
        except (IOError, PermissionError):
            log_message(f"警告：无法修改文件: {current_exe}", "WARNING")
            return False
    
    return True


def request_elevation():
    """请求管理员权限（Windows）或sudo权限（Unix）"""
    system = platform.system()
    
    if system == 'Windows':
        import ctypes
        # 检查是否已经有管理员权限
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            is_admin = False
            
        if not is_admin:
            log_message("需要管理员权限，尝试提权...")
            # 以管理员权限重新启动
            try:
                # 获取Python解释器路径
                python_exe = sys.executable
                # 构建命令行参数
                params = ' '.join(['"{}"'.format(arg) for arg in sys.argv])
                
                # 使用ShellExecute请求提权
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, 
                    "runas",  # 请求管理员权限
                    python_exe,
                    params,
                    None,
                    1  # SW_SHOWNORMAL
                )
                
                if ret > 32:  # 成功
                    log_message("已请求管理员权限，新进程启动")
                    sys.exit(0)  # 退出当前进程
                else:
                    log_message("用户拒绝了管理员权限请求", "ERROR")
                    return False
            except Exception as e:
                log_message(f"请求管理员权限失败: {e}", "ERROR")
                return False
        else:
            log_message("已有管理员权限")
            return True
            
    elif system in ['Linux', 'Darwin']:
        # 检查是否是root用户
        if os.geteuid() != 0:
            log_message("需要root权限，尝试使用sudo...")
            # 尝试使用sudo重新运行
            try:
                # 构建sudo命令
                args = ['sudo', sys.executable] + sys.argv
                log_message(f"执行: {' '.join(args)}")
                
                # 执行sudo命令
                result = subprocess.run(args)
                
                if result.returncode == 0:
                    sys.exit(0)  # 成功执行，退出当前进程
                else:
                    log_message("sudo执行失败", "ERROR")
                    return False
            except Exception as e:
                log_message(f"使用sudo失败: {e}", "ERROR")
                # 提供手动指导
                log_message("请手动使用sudo运行此脚本：")
                log_message(f"  sudo {' '.join(sys.argv)}")
                return False
        else:
            log_message("已有root权限")
            return True
    
    return True


def main():
    """主函数"""
    log_message("=== 外部更新脚本启动 ===")

    # 检查命令行参数
    if len(sys.argv) < 2:
        log_message("错误：缺少更新信息参数", "ERROR")
        pause_on_windows("错误：缺少更新信息参数\n按任意键退出...")
        sys.exit(1)

    try:
        # 解析更新信息
        update_info_json = sys.argv[1]
        update_info = json.loads(update_info_json)

        # 可选：第二个参数为目标可执行文件路径
        global CURRENT_EXE_PATH
        if len(sys.argv) >= 3:
            CURRENT_EXE_PATH = os.path.abspath(sys.argv[2])
        
        # 可选：第三个参数为主程序PID
        main_pid = None
        if len(sys.argv) >= 4:
            try:
                main_pid = int(sys.argv[3])
                log_message(f"接收到主程序PID: {main_pid}")
            except ValueError:
                log_message("无效的PID参数", "WARNING")
        
        log_message(f"准备更新到版本: {update_info.get('version', 'unknown')}")
        
        # 检查权限
        if not check_permissions():
            log_message("权限不足，尝试提权...")
            if not request_elevation():
                log_message("无法获得必要的权限", "ERROR")
                pause_on_windows("更新需要管理员权限\n请以管理员身份运行\n按任意键退出...")
                sys.exit(1)
        
        # 等待主程序退出（如果提供了PID）
        if main_pid:
            wait_for_process_exit(main_pid)
        else:
            # 没有PID，简单等待
            log_message("等待主程序退出...")
            time.sleep(3)
        
        # 标记开始安装（供 GUI 通过 update.log 解析 last_update_time）
        log_message(f"开始安装更新: {update_info.get('version', 'unknown')}")
        
        # 步骤1: 下载更新文件
        update_file = download_update_file(update_info)
        if not update_file:
            log_message("下载失败，保留旧版本", "ERROR")
            pause_on_windows("更新下载失败，程序保持原版本\n按任意键退出...")
            sys.exit(1)

        # 步骤2: 安装更新
        if platform.system() == 'Windows':
            success = install_update_windows(update_file)
        else:
            success = install_update_unix(update_file)

        if not success:
            log_message("安装失败，已恢复旧版本", "ERROR")
            pause_on_windows("更新安装失败，已恢复旧版本\n按任意键退出...")
            sys.exit(1)

        # 步骤3: 清理临时文件
        try:
            os.remove(update_file)
            log_message("清理临时文件完成")
        except Exception as e:
            log_message(f"清理临时文件失败: {e}", "WARNING")

        # 清理备份文件
        backup_path = get_current_exe_path() + ".backup"
        cleanup_backup(backup_path)

        # 写入成功标记，供 GUI 判断更新成功
        log_message("更新成功完成")

        # 步骤4: 重启应用程序
        log_message("更新完成，准备重启应用程序...")
        time.sleep(1)

        if not restart_application():
            log_message("重启失败，请手动重启应用程序", "WARNING")
            pause_on_windows("更新完成，但自动重启失败\n请手动启动程序\n按任意键退出...")
        else:
            log_message("=== 更新脚本执行完成 ===")
            pause_on_windows("更新完成！程序已自动重启\n按任意键关闭此窗口...")

    except json.JSONDecodeError as e:
        log_message(f"解析更新信息失败: {e}", "ERROR")
        pause_on_windows(f"错误：解析更新信息失败\n{e}\n按任意键退出...")
        sys.exit(1)
    except Exception as e:
        log_message(f"更新过程中发生错误: {e}", "ERROR")
        import traceback
        error_detail = traceback.format_exc()
        log_message(f"详细错误:\n{error_detail}", "ERROR")
        pause_on_windows(f"更新失败：{e}\n详细信息已记录到日志\n按任意键退出...")
        sys.exit(1)


if __name__ == "__main__":
    main()
