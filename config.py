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

# 禁用SSL证书验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()

# 全局配置
CONFIG = {
    "max_workers": 12,
    "max_retries": 3,
    "request_timeout": 30,
    "status_file": "chapter.json",
    "request_rate_limit": 0.1,
    "api_base_url": "https://api-return.cflin.ddns-ip.net",  # 新API基础URL
    "api_endpoint": "/api/xiaoshuo/fanqie",  # 新API端点
    "download_enabled": True,  # 启用章节下载功能
    "verbose_logging": False  # 是否启用详细日志输出（GUI环境建议关闭）
}

# 全局锁
print_lock = threading.Lock()

_UA_SINGLETON = None
_UA_LOCK = threading.Lock()
_DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

def _get_ua() -> UserAgent:
    global _UA_SINGLETON
    if _UA_SINGLETON is None:
        with _UA_LOCK:
            if _UA_SINGLETON is None:
                try:
                    # 开启缓存，避免频繁网络拉取；提供可靠回退
                    _UA_SINGLETON = UserAgent(cache=True, fallback=random.choice(_DEFAULT_USER_AGENTS))
                except Exception:
                    _UA_SINGLETON = None
    return _UA_SINGLETON

def get_headers() -> Dict[str, str]:
    """生成请求头（UA 单例缓存 + 本地回退）"""
    user_agent = None
    try:
        ua = _get_ua()
        if ua is not None:
            # 在 chrome/edge 中择一，避免每次新建 UA
            if random.choice(['chrome', 'edge']) == 'chrome':
                user_agent = ua.chrome
            else:
                user_agent = ua.edge
    except Exception:
        user_agent = None

    if not user_agent:
        user_agent = random.choice(_DEFAULT_USER_AGENTS)

    return {
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://fanqienovel.com/",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json"
    }

# 导出配置和函数
__all__ = ['CONFIG', 'print_lock', 'make_request', 'get_headers']