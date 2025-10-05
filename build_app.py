#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Python编译脚本
用于GitHub Actions中的可执行文件编译
支持不同变体（release/debug）和平台特定的可执行文件命名
"""

import subprocess
import sys
import os
import shutil
import argparse

# 导入编码工具（如果存在）
try:
    from encoding_utils import safe_print, setup_utf8_encoding
    # 确保UTF-8编码设置
    setup_utf8_encoding()
    # 使用安全的print函数
    print = safe_print
except ImportError:
    # 如果编码工具不存在，使用基本的编码设置
    if sys.platform.startswith('win'):
        import locale
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except locale.Error:
            try:
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except locale.Error:
                pass  # 使用默认编码

def build_executable(variant="release", executable_name=None):
    """编译可执行文件
    
    Args:
        variant: 构建变体 ('release' 或 'debug')
        executable_name: 自定义可执行文件名称（不包含扩展名）
    
    Returns:
        tuple: (success, built_name, target_name)
            - success: 构建是否成功
            - built_name: spec文件中定义的原始名称
            - target_name: 期望的最终名称
    """
    print(f"Starting build process for {variant} variant...")
    
    # 确定目标可执行文件名称
    if executable_name:
        target_name = executable_name
    else:
        target_name = "TomatoNovelDownloader-debug" if variant == "debug" else "TomatoNovelDownloader"
    
    # 检查是否有对应的spec文件
    spec_file = "debug.spec" if variant == "debug" else "build.spec"
    
    if os.path.exists(spec_file):
        print(f"Using {spec_file} configuration file")
        # 使用spec文件时不能使用--name参数，需要使用spec中定义的名称
        cmd = [sys.executable, "-m", "PyInstaller", spec_file, "--clean", "--noconfirm"]
        # spec文件中定义的默认名称
        built_name = "TomatoNovelDownloader-debug" if variant == "debug" else "TomatoNovelDownloader"
    else:
        print(f"{spec_file} not found, using default configuration")
        
        # 构建基础命令
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            f"--name={target_name}",
        ]
        
        # 根据变体选择窗口模式或控制台模式
        if variant == "debug":
            cmd.append("--console")
        else:
            cmd.append("--windowed")
        
        # 添加隐藏导入
        hidden_imports = [
            "bs4",
            "beautifulsoup4",
            "fake_useragent",
            "fake_useragent.data",
            "tqdm",
            "requests",
            "urllib3",
            "ebooklib",
            "PIL",
            "PIL.Image",
            "PIL.ImageTk",
            "PIL.ImageDraw",
            "PIL.ImageFile",
            "PIL.ImageFont",
            "PIL.ImageOps",
            "PIL.JpegImagePlugin",
            "PIL.PngImagePlugin",
            "PIL.GifImagePlugin",
            "PIL.BmpImagePlugin",
            "PIL.WebPImagePlugin",
            "PIL._imaging",
            "pillow_heif"
        ]
        
        for import_name in hidden_imports:
            cmd.extend(["--hidden-import", import_name])
        
        # 添加数据收集
        cmd.extend(["--collect-data", "fake_useragent"])
        cmd.extend(["--collect-submodules", "PIL"])
        
        # 添加入口文件
        cmd.append("gui.py")
        
        # 没有使用spec文件时，built_name和target_name相同
        built_name = target_name
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print("Build successful")
        print(result.stdout)
        # 如果使用spec文件，返回built_name和target_name
        if os.path.exists(spec_file):
            return True, built_name, target_name
        else:
            return True, target_name, target_name
    except subprocess.CalledProcessError as e:
        print("Build failed")
        print(f"Error output: {e.stderr}")
        if os.path.exists(spec_file):
            return False, built_name, target_name
        else:
            return False, target_name, target_name

def check_output(expected_name):
    """检查编译输出
    
    Args:
        expected_name: 期望的可执行文件名称（不包含扩展名）
    """
    print("Checking build output...")
    if os.path.exists("dist"):
        files = os.listdir("dist")
        print(f"dist directory contents: {files}")
        
        # 检查可执行文件
        exe_name = f"{expected_name}.exe" if os.name == "nt" else expected_name
        exe_path = os.path.join("dist", exe_name)
        
        if os.path.exists(exe_path):
            size = os.path.getsize(exe_path)
            print(f"Executable created successfully: {exe_name} ({size} bytes)")
            return True
        else:
            print(f"Executable not found: {exe_path}")
            return False
    else:
        print("dist directory does not exist")
        return False

def rename_executable(current_name, target_name):
    """重命名可执行文件
    
    Args:
        current_name: 当前文件名（不包含扩展名）
        target_name: 目标文件名（不包含扩展名）
    """
    if current_name == target_name:
        return True
        
    ext = ".exe" if os.name == "nt" else ""
    current_path = os.path.join("dist", f"{current_name}{ext}")
    target_path = os.path.join("dist", f"{target_name}{ext}")
    
    if os.path.exists(current_path):
        try:
            os.rename(current_path, target_path)
            print(f"Renamed {current_name}{ext} to {target_name}{ext}")
            return True
        except OSError as e:
            print(f"Failed to rename executable: {e}")
            return False
    else:
        print(f"Source file not found: {current_path}")
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Build Tomato Novel Downloader")
    parser.add_argument("--variant", choices=["release", "debug"], default="release",
                       help="Build variant (release or debug)")
    parser.add_argument("--name", type=str, help="Custom executable name (without extension)")
    
    args = parser.parse_args()
    
    # 构建可执行文件
    success, built_name, target_name = build_executable(args.variant, args.name)
    
    if success:
        # 先检查构建输出
        if check_output(built_name):
            # 如果built_name和target_name不同，需要重命名
            if built_name != target_name:
                if rename_executable(built_name, target_name):
                    print(f"Build completed successfully! Final executable: {target_name}")
                    return True
                else:
                    print("Build successful but renaming failed")
                    return False
            else:
                print(f"Build completed successfully! Executable: {built_name}")
                return True
        else:
            print("Build output check failed")
            return False
    else:
        print("Build failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 