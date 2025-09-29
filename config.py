# -*- coding: utf-8 -*-
"""
配置管理模块 - 基于参考代码的简化版本
"""

import time
import requests
import bs4
import re
import os
import random
import json
import urllib3
import threading
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from collections import OrderedDict
from fake_useragent import UserAgent
from typing import Optional, Dict
from ebooklib import epub
import base64
import gzip
from urllib.parse import urlencode

# 禁用SSL证书验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()

# 全局配置
CONFIG = {
    "max_workers": 4,
    "max_retries": 3,
    "request_timeout": 15,
    "status_file": "chapter.json",
    "request_rate_limit": 0.4,
    "auth_token": "wcnmd91jb",
    "server_url": "https://dlbkltos.s7123.xyz:5080",
    "api_endpoints": [],
    "download_enabled": True,  # 禁用章节下载功能
    "batch_config": {
        "name": "qyuing",
        "base_url": None,
        "batch_endpoint": None,
        "token": None,
        "max_batch_size": 290,
        "timeout": 10,
        "enabled": True
    }
}

# 全局锁
print_lock = threading.Lock()

def make_request(url, headers=None, params=None, data=None, method='GET', verify=False, timeout=None):
    """通用的请求函数"""
    if headers is None:
        headers = get_headers()

    try:
        request_params = {
            'headers': headers,
            'params': params,
            'verify': verify,
            'timeout': timeout if timeout is not None else CONFIG["request_timeout"]
        }

        if data:
            request_params['json'] = data

        session = requests.Session()
        if method.upper() == 'GET':
            response = session.get(url, **request_params)
        elif method.upper() == 'POST':
            response = session.post(url, **request_params)
        else:
            raise ValueError(f"不支持的HTTP方法: {method}")

        return response
    except Exception as e:
        with print_lock:
            print(f"请求失败: {str(e)}")
        raise

def get_headers() -> Dict[str, str]:
    """生成随机请求头"""
    # 默认用户代理列表作为兜底
    DEFAULT_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
    ]
    
    try:
        # 尝试使用 fake_useragent
        browsers = ['chrome', 'edge']
        browser = random.choice(browsers)

        ua = UserAgent(cache=False, fallback=random.choice(DEFAULT_USER_AGENTS))
        if browser == 'chrome':
            user_agent = ua.chrome
        else:
            user_agent = ua.edge
    except Exception:
        # 如果 fake_useragent 失败，使用默认用户代理
        user_agent = random.choice(DEFAULT_USER_AGENTS)

    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://fanqienovel.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json"
    }

# 导出配置
__all__ = ['CONFIG', 'print_lock', 'make_request', 'get_headers']
