#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API管理模块 - 使用新的API接口
"""

import requests
import json
from typing import Dict, List, Optional
from config import CONFIG, print_lock, get_headers

class APIManager:
    """新API管理器 - 直接使用 api-return.cflin.ddns-ip.net"""
    
    def __init__(self):
        self.base_url = CONFIG["api_base_url"]
        self.api_endpoint = CONFIG["api_endpoint"]
        self.full_url = f"{self.base_url}{self.api_endpoint}"
    
    def search_books(self, keyword: str) -> Optional[Dict]:
        """搜索书籍
        参数:
            keyword: 搜索关键词
        返回:
            搜索结果字典或None
        """
        try:
            params = {"q": keyword}
            response = requests.get(self.full_url, params=params, headers=get_headers(), timeout=CONFIG["request_timeout"])
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理实际的API响应格式
                if "data" in data and isinstance(data["data"], list):
                    # 将返回的数组格式转换为我们期望的格式
                    books = []
                    for item in data["data"]:
                        books.append({
                            "book_id": item.get("book_id", ""),
                            "book_name": item.get("title", ""),
                            "author": item.get("author", ""),
                            "cover": item.get("thumb_url", ""),
                            "intro": item.get("abstract", ""),
                            "category": item.get("category", ""),
                            "status": item.get("creation_status", ""),
                            "word_count": item.get("word_number", ""),
                            "update_time": item.get("update_time", ""),
                            "latest_chapter": item.get("latest_chapter", "")
                        })
                    
                    return {
                        "books": books,
                        "total": len(books),
                        "page": 1,
                        "page_size": len(books)
                    }
                    
                # 处理文档中描述的标准格式（以防API更新）
                elif data.get("code") == 0:
                    return data["data"]
                else:
                    with print_lock:
                        print(f"搜索失败: {data.get('message', '未知响应格式')}")
            else:
                with print_lock:
                    print(f"搜索请求失败，状态码: {response.status_code}")
            return None
        except Exception as e:
            with print_lock:
                print(f"搜索异常: {str(e)}")
            return None
    
    def get_book_details(self, book_id: str) -> Optional[Dict]:
        """获取书籍详情
        参数:
            book_id: 书籍ID
        返回:
            书籍详情字典或None
        """
        try:
            params = {"xq": book_id}
            response = requests.get(self.full_url, params=params, headers=get_headers(), timeout=CONFIG["request_timeout"])
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理新API的响应格式
                # 示例返回: {"api_source":"POWER BY return API","data":{"thumb_url":"xxx","book_name":"xxx","book_abstract_v2":"xxx","original_book_name":"xxx"}}
                if "data" in data and isinstance(data["data"], dict):
                    raw_data = data["data"]
                    
                    # 统一字段名称，兼容原有代码调用
                    formatted_data = {
                        "book_name": raw_data.get("book_name", f"未知小说_{book_id}"),
                        "original_book_name": raw_data.get("original_book_name", raw_data.get("book_name", "")),
                        "author": raw_data.get("author", "未知作者"),  # 新API可能不包含作者，保留字段
                        "intro": raw_data.get("book_abstract_v2", raw_data.get("intro", "无简介")),  # 使用book_abstract_v2作为简介
                        "cover": raw_data.get("thumb_url", raw_data.get("cover", "")),  # 使用thumb_url作为封面
                        "category": raw_data.get("category", ""),
                        "status": raw_data.get("status", ""),
                        "word_count": raw_data.get("word_count", ""),
                        "update_time": raw_data.get("update_time", ""),
                        "latest_chapter": raw_data.get("latest_chapter", "")
                    }
                    
                    if CONFIG.get("verbose_logging", False):
                        with print_lock:
                            print(f"成功获取书籍详情: 《{formatted_data['book_name']}》")
                            if formatted_data.get('original_book_name') and formatted_data['original_book_name'] != formatted_data['book_name']:
                                print(f"  别名: {formatted_data['original_book_name']}")
                            if formatted_data.get('cover'):
                                print(f"  封面: 已获取")
                            if formatted_data.get('intro') and formatted_data['intro'] != "无简介":
                                intro_preview = formatted_data['intro'][:50] + "..." if len(formatted_data['intro']) > 50 else formatted_data['intro']
                                print(f"  简介: {intro_preview}")
                    
                    return formatted_data
                else:
                    with print_lock:
                        print(f"获取书籍详情失败: 响应格式不符或数据为空")
                        print(f"  响应内容: {json.dumps(data, ensure_ascii=False)[:200]}")
            else:
                with print_lock:
                    print(f"获取书籍详情请求失败，状态码: {response.status_code}")
            return None
        except Exception as e:
            with print_lock:
                print(f"获取书籍详情异常: {str(e)}")
            return None
    
    def get_chapter_list(self, book_id: str) -> Optional[List[Dict]]:
        """获取章节列表
        参数:
            book_id: 书籍ID
        返回:
            章节列表或None
        """
        try:
            params = {"mulu": book_id}
            response = requests.get(self.full_url, params=params, headers=get_headers(), timeout=CONFIG["request_timeout"])
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理实际的API响应格式
                # 示例: {"api_source": "POWER BY return API", "data": [{"item_id": "xxx", "title": "xxx", "volume_name": "xxx"}]}
                if "data" in data:
                    # 如果data是字典并包含chapters
                    if isinstance(data["data"], dict) and "chapters" in data["data"]:
                        chapters = data["data"]["chapters"]
                        # 统一格式：将字段名标准化
                        formatted_chapters = []
                        for ch in chapters:
                            formatted_chapters.append({
                                "chapter_id": ch.get("item_id", ch.get("chapter_id", "")),
                                "chapter_name": ch.get("title", ch.get("chapter_name", "")),
                                "volume_name": ch.get("volume_name", "")
                            })
                        return formatted_chapters
                    # 如果data直接是章节列表（新API格式）
                    elif isinstance(data["data"], list):
                        # 统一格式：将item_id和title转换为chapter_id和chapter_name
                        formatted_chapters = []
                        for ch in data["data"]:
                            formatted_chapters.append({
                                "chapter_id": ch.get("item_id", ch.get("chapter_id", "")),
                                "chapter_name": ch.get("title", ch.get("chapter_name", "")),
                                "volume_name": ch.get("volume_name", "")
                            })
                        
                        if CONFIG.get("verbose_logging", False):
                            with print_lock:
                                print(f"成功获取章节列表，共 {len(formatted_chapters)} 章")
                        
                        return formatted_chapters
                    else:
                        with print_lock:
                            print(f"章节列表响应格式不符: {type(data['data'])}")
                        return None
                        
                # 处理文档中描述的标准格式
                elif data.get("code") == 0 and "data" in data:
                    chapters = data["data"].get("chapters", [])
                    # 统一格式
                    formatted_chapters = []
                    for ch in chapters:
                        formatted_chapters.append({
                            "chapter_id": ch.get("item_id", ch.get("chapter_id", "")),
                            "chapter_name": ch.get("title", ch.get("chapter_name", "")),
                            "volume_name": ch.get("volume_name", "")
                        })
                    return formatted_chapters
                else:
                    with print_lock:
                        print(f"获取章节列表失败: {data.get('message', '未知响应格式')}")
            else:
                with print_lock:
                    print(f"获取章节列表请求失败，状态码: {response.status_code}")
            return None
        except Exception as e:
            with print_lock:
                print(f"获取章节列表异常: {str(e)}")
            return None
    
    def get_chapter_content(self, chapter_id: str) -> Optional[Dict]:
        """获取章节内容
        参数:
            chapter_id: 章节ID (格式: 书籍ID_章节序号)
        返回:
            章节内容字典或None
        """
        try:
            params = {"content": chapter_id}
            response = requests.get(self.full_url, params=params, headers=get_headers(), timeout=CONFIG["request_timeout"])
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理实际的API响应格式
                if "data" in data:
                    # 如果data是字典，直接返回
                    if isinstance(data["data"], dict):
                        return data["data"]
                    # 如果data是其他格式
                    else:
                        with print_lock:
                            print(f"章节内容响应格式不符: {type(data['data'])}")
                        return None
                        
                # 处理文档中描述的标准格式
                elif data.get("code") == 0 and "data" in data:
                    return data["data"]
                else:
                    with print_lock:
                        print(f"获取章节内容失败: {data.get('message', '未知响应格式')}")
            else:
                with print_lock:
                    print(f"获取章节内容请求失败，状态码: {response.status_code}")
            return None
        except Exception as e:
            with print_lock:
                print(f"获取章节内容异常: {str(e)}")
            return None
    
    def test_connection(self) -> bool:
        """测试API连接
        返回:
            True如果连接成功，False否则
        """
        try:
            # 测试健康检查接口
            health_url = f"{self.base_url}/health"
            response = requests.get(health_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    # 静默成功，减少输出
                    return True
            
            # 如果健康检查失败，尝试获取服务信息
            info_url = self.base_url + "/"
            response = requests.get(info_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "running":
                    return True
                    
            return False
        except Exception:
            # 静默失败，避免刷屏
            return False

# 全局API管理器实例
api_manager = APIManager()
