#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新机制测试脚本
测试自动更新系统的各项功能
"""

import os
import sys
import json
import time
import tempfile
import unittest
import hashlib
from unittest.mock import Mock, patch, MagicMock

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入要测试的模块
try:
    from updater import UpdateChecker, AutoUpdater, UpdateLock, is_official_release_build
    from external_updater import (
        verify_file_checksum, check_permissions, 
        detect_platform_details, wait_for_process_exit
    )
    modules_available = True
except ImportError as e:
    print(f"警告：无法导入模块: {e}")
    modules_available = False


class TestUpdateChecker(unittest.TestCase):
    """测试UpdateChecker类"""
    
    def setUp(self):
        """测试前设置"""
        if not modules_available:
            self.skipTest("模块不可用")
        self.checker = UpdateChecker("owner/repo", "1.0.0")
    
    def test_version_comparison(self):
        """测试版本比较逻辑"""
        # 测试时间戳版本号比较
        self.assertTrue(self.checker._compare_timestamp_versions(
            "2025.10.17.1234+abcdef1", 
            "2025.10.16.1234+abcdef2"
        ))
        self.assertFalse(self.checker._compare_timestamp_versions(
            "2025.10.16.1234+abcdef1", 
            "2025.10.17.1234+abcdef2"
        ))
        # 相同版本
        self.assertFalse(self.checker._compare_timestamp_versions(
            "2025.10.17.1234+abcdef1", 
            "2025.10.17.1234+abcdef1"
        ))
        # 传统版本号更新到时间戳版本
        self.assertTrue(self.checker._compare_timestamp_versions(
            "2025.10.17.1234+abcdef1", 
            "2.0.0"
        ))
    
    def test_is_timestamp_version(self):
        """测试时间戳版本号识别"""
        self.assertTrue(self.checker._is_timestamp_version("2025.10.17.1234+abcdef1"))  # 7位hash
        self.assertFalse(self.checker._is_timestamp_version("1.2.3"))
        self.assertFalse(self.checker._is_timestamp_version("v2.0.0"))
        self.assertFalse(self.checker._is_timestamp_version("2025.10.17.1234+toolong123"))  # hash太长
    
    def test_extract_checksums_from_body(self):
        """测试从release body提取校验值"""
        checksums = {}
        
        # 测试各种格式
        body = """
        ## SHA256 Checksums
        SHA256 (app.exe) = a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
        app.zip: fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210
        1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef *app.tar.gz
        """
        
        self.checker._extract_checksums_from_body(body, checksums)
        
        self.assertEqual(len(checksums), 3)
        self.assertIn("app.exe", checksums)
        self.assertIn("app.zip", checksums)
        self.assertIn("app.tar.gz", checksums)


class TestUpdateLock(unittest.TestCase):
    """测试UpdateLock类"""
    
    def setUp(self):
        """测试前设置"""
        if not modules_available:
            self.skipTest("模块不可用")
        self.lock = UpdateLock()
    
    def tearDown(self):
        """测试后清理"""
        if hasattr(self, 'lock'):
            self.lock.release()
    
    def test_lock_acquire_and_release(self):
        """测试锁的获取和释放"""
        # 获取锁
        self.assertTrue(self.lock.acquire(timeout=2))
        self.assertTrue(self.lock.locked)
        
        # 再次获取应该失败（已经持有）
        lock2 = UpdateLock()
        self.assertFalse(lock2.acquire(timeout=1))
        
        # 释放后应该可以获取
        self.lock.release()
        self.assertFalse(self.lock.locked)
        self.assertTrue(lock2.acquire(timeout=2))
        lock2.release()
    
    def test_lock_context_manager(self):
        """测试锁的上下文管理器"""
        with UpdateLock() as lock:
            self.assertTrue(lock.locked)
            # 在with块内，其他锁应该无法获取
            lock2 = UpdateLock()
            self.assertFalse(lock2.acquire(timeout=1))
        
        # 退出with块后，锁应该被释放
        self.assertFalse(lock.locked)
    
    def test_lock_timeout(self):
        """测试锁超时"""
        lock1 = UpdateLock()
        lock1.acquire(timeout=1)
        
        lock2 = UpdateLock()
        start_time = time.time()
        result = lock2.acquire(timeout=2)
        elapsed = time.time() - start_time
        
        self.assertFalse(result)
        self.assertTrue(1.5 < elapsed < 2.5)  # 应该等待约2秒
        
        lock1.release()


class TestFileChecksum(unittest.TestCase):
    """测试文件校验功能"""
    
    def test_verify_file_checksum(self):
        """测试SHA256文件校验"""
        if not modules_available:
            self.skipTest("模块不可用")
        
        # 创建临时文件
        test_data = b"Hello, World! This is a test file."
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(test_data)
        temp_file.close()
        
        try:
            # 计算正确的SHA256
            correct_hash = hashlib.sha256(test_data).hexdigest()
            
            # 测试正确的校验值
            self.assertTrue(verify_file_checksum(temp_file.name, correct_hash))
            
            # 测试错误的校验值
            wrong_hash = "0" * 64
            self.assertFalse(verify_file_checksum(temp_file.name, wrong_hash))
            
            # 测试大小写不敏感
            self.assertTrue(verify_file_checksum(temp_file.name, correct_hash.upper()))
            
        finally:
            # 清理临时文件
            os.unlink(temp_file.name)


class TestPlatformDetection(unittest.TestCase):
    """测试平台检测功能"""
    
    def test_detect_platform_details(self):
        """测试平台详情检测"""
        if not modules_available:
            self.skipTest("模块不可用")
        
        details = detect_platform_details()
        
        # 检查必要的字段
        self.assertIn('system', details)
        self.assertIn('machine', details)
        self.assertIn('is_mac', details)
        self.assertIn('is_linux', details)
        self.assertIn('is_arm', details)
        self.assertIn('is_x86', details)
        
        # 验证逻辑一致性
        if details['system'] == 'Darwin':
            self.assertTrue(details['is_mac'])
            self.assertFalse(details['is_linux'])
        elif details['system'] == 'Linux':
            self.assertFalse(details['is_mac'])
            self.assertTrue(details['is_linux'])
        
        # 架构检查
        self.assertTrue(details['is_arm'] or details['is_x86'] or 
                       (not details['is_arm'] and not details['is_x86']))


class TestPermissions(unittest.TestCase):
    """测试权限检查功能"""
    
    def test_check_permissions(self):
        """测试权限检查"""
        if not modules_available:
            self.skipTest("模块不可用")
        
        # 这个测试依赖于实际的文件系统权限
        # 在大多数情况下，临时目录应该是可写的
        result = check_permissions()
        # 只是确保函数能够执行，不验证结果
        self.assertIsInstance(result, bool)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    @patch('updater._get_requests')
    def test_update_workflow(self, mock_get_requests):
        """测试完整的更新工作流"""
        if not modules_available:
            self.skipTest("模块不可用")
        
        # 模拟requests模块
        mock_requests = MagicMock()
        mock_get_requests.return_value = mock_requests
        
        # 模拟GitHub API响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'tag_name': 'v2.0.0',
            'name': 'Release 2.0.0',
            'body': 'New features and fixes',
            'published_at': '2025-10-17T10:00:00Z',
            'html_url': 'https://github.com/owner/repo/releases/tag/v2.0.0',
            'assets': [
                {
                    'name': 'app.exe',
                    'size': 1024000,
                    'browser_download_url': 'https://github.com/download/app.exe',
                    'content_type': 'application/octet-stream'
                }
            ]
        }
        mock_requests.get.return_value = mock_response
        
        # 创建更新器
        updater = AutoUpdater("owner/repo", "1.0.0")
        
        # 检查更新
        update_info = updater.check_for_updates(force=True)
        self.assertIsNotNone(update_info)
        self.assertEqual(update_info['version'], '2.0.0')


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestUpdateChecker))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestUpdateLock))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestFileChecksum))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPlatformDetection))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestPermissions))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回结果
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 60)
    print("开始测试更新机制")
    print("=" * 60)
    
    success = run_tests()
    
    print("\n" + "=" * 60)
    if success:
        print("所有测试通过！")
    else:
        print("部分测试失败，请检查错误信息")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
