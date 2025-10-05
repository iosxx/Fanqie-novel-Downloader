<div align="center">

# 🍅 番茄小说下载器

<p>简洁 · 高效 · 开箱即用的番茄小说下载工具</p>

<p>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen?style=flat-square">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-orange?style=flat-square">
</p>

</div>

---

## ✨ 功能特性

- 🔍 **智能搜索** - 快速搜索番茄小说平台书籍
- 📖 **完整下载** - 支持整本小说或指定章节范围下载
- 📝 **多格式导出** - 支持 TXT 和 EPUB 格式
- 🎨 **精美封面** - 自动获取并嵌入小说封面
- 🚀 **多线程加速** - 并发下载，速度快
- 💾 **断点续传** - 意外中断后可继续下载
- 🖥️ **双模式** - 图形界面 + 命令行，满足不同需求

---

## 📦 快速开始

### 环境要求

- Python 3.10 或更高版本
- Windows / macOS / Linux

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/POf-L/Fanqie-novel-Downloader.git
cd Fanqie-novel-Downloader
```

2. **创建虚拟环境（推荐）**
```bash
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

### 启动程序

#### 方式一：图形界面（推荐新手）
```bash
python gui.py
```

#### 方式二：命令行
```bash
python novel_downloader.py
```

---

## 🎯 使用指南

### 图形界面使用

1. 启动 `gui.py`
2. 在搜索框输入小说名称或书籍ID
3. 选择要下载的小说
4. 选择下载格式（TXT 或 EPUB）
5. 可选：设置章节范围（如：第1章到第100章）
6. 点击"开始下载"按钮

### 命令行使用

```bash
# 交互式下载
python novel_downloader.py

# 根据提示输入：
# 1. 小说ID（从番茄小说网页URL中获取）
# 2. 保存路径（留空则保存到当前目录）
# 3. 选择格式（1:TXT, 2:EPUB）
```

### 如何获取小说ID？

访问番茄小说网页，URL格式如下：
```
https://fanqienovel.com/page/7276384138653862966
                              ^^^^^^^^^^^^^^^^^^^
                              这就是小说ID
```

---

## ⚙️ 配置说明

主要配置位于 [`config.py`](config.py)：

```python
CONFIG = {
    "max_workers": 4,           # 并发下载线程数
    "max_retries": 3,           # 失败重试次数
    "request_timeout": 15,      # 请求超时时间(秒)
    "request_rate_limit": 0.4,  # 请求间隔(秒)
    "download_enabled": True    # 是否启用下载功能
}
```

### 重要提示

如果下载功能被禁用，请修改 [`config.py`](config.py:40)：
```python
"download_enabled": True  # 改为 True 启用下载
```

---

## 📂 项目结构

```
Tomato-Novel-Downloader/
├── gui.py                  # 图形界面程序
├── novel_downloader.py     # 命令行下载器
├── api_manager.py          # API接口管理
├── config.py               # 全局配置
├── encoding_utils.py       # 编码处理工具
├── updater.py              # 自动更新模块
├── version.py              # 版本信息
├── requirements.txt        # 依赖列表
└── README.md               # 项目文档
```

---

## 🔌 API接口说明

本项目使用稳定的API接口进行数据获取：

### API基础信息
- **基础URL**: `https://api-return.cflin.ddns-ip.net`
- **端点**: `/api/xiaoshuo/fanqie`
- **方法**: GET
- **格式**: JSON

### 核心功能

#### 1. 搜索书籍
```bash
GET /api/xiaoshuo/fanqie?q=关键词
```

**示例**:
```bash
curl "https://api-return.cflin.ddns-ip.net/api/xiaoshuo/fanqie?q=我不是戏神"
```

#### 2. 获取书籍详情
```bash
GET /api/xiaoshuo/fanqie?xq=书籍ID
```

**示例**:
```bash
curl "https://api-return.cflin.ddns-ip.net/api/xiaoshuo/fanqie?xq=7276384138653862966"
```

#### 3. 获取章节列表
```bash
GET /api/xiaoshuo/fanqie?mulu=书籍ID
```

**返回格式示例**:
```json
{
  "api_source": "POWER BY return API",
  "data": [
    {
      "item_id": "7276663560427471412",
      "title": "第1章 戏鬼回家",
      "volume_name": "第一卷：戏中人"
    }
  ]
}
```

#### 4. 获取章节内容
```bash
GET /api/xiaoshuo/fanqie?content=章节ID
```

**返回格式示例**:
```json
{
  "api_source": "POWER BY return API",
  "data": {
    "content": "章节正文内容..."
  }
}
```

### Python调用示例

```python
import requests

BASE_URL = "https://api-return.cflin.ddns-ip.net/api/xiaoshuo/fanqie"

# 搜索书籍
response = requests.get(BASE_URL, params={"q": "我不是戏神"})
books = response.json()

# 获取章节列表
response = requests.get(BASE_URL, params={"mulu": "7276384138653862966"})
chapters = response.json()

# 获取章节内容
response = requests.get(BASE_URL, params={"content": "7276663560427471412"})
content = response.json()
```

---

## 🛠️ 常见问题

### Q: 下载失败怎么办？
A: 
1. 检查网络连接是否正常
2. 确认 `download_enabled` 配置为 `True`
3. 删除 `chapter.json` 文件后重试
4. 适当增加 `request_timeout` 值

### Q: 为什么下载速度慢？
A: 
1. 可以适当增加 `max_workers` 值（建议不超过8）
2. 减少 `request_rate_limit` 值（但可能增加请求失败率）

### Q: Linux 启动 GUI 提示缺少 Tkinter？
A: 
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Fedora
sudo dnf install python3-tkinter
```

### Q: 如何打包成可执行文件？
A:
```bash
pip install pyinstaller

# 打包 Release 版本（无控制台）
python build_app.py --variant=release --name=TomatoNovelDownloader

# 打包 Debug 版本（带控制台）
python build_app.py --variant=debug --name=TomatoNovelDownloader-debug
```

也可以直接从 [Releases](https://github.com/POf-L/Fanqie-novel-Downloader/releases) 页面下载编译好的可执行文件。

### Q: 章节列表显示不正确？
A: 新版本已修复章节列表解析问题，请确保使用最新代码。

---

## 📋 依赖说明

主要依赖库：
- `requests` - HTTP请求
- `beautifulsoup4` - HTML解析
- `ebooklib` - EPUB生成
- `pillow` - 图片处理
- `fake-useragent` - User-Agent生成
- `tqdm` - 进度条显示

完整依赖请查看 [`requirements.txt`](requirements.txt)

---

## 🚀 自动构建与发布

本项目使用 GitHub Actions 自动构建多平台可执行文件。

### 构建平台支持
- 💻 **Windows (x64)** - Release + Debug 版本
- 🐧 **Linux (x64)** - Release + Debug 版本
- 🍎 **macOS (Intel & Apple Silicon)** - Release + Debug 版本

### 版本说明
- **Release 版本**: 适合日常使用，无控制台窗口，界面更简洁
- **Debug 版本**: 包含详细日志输出，遇到问题时使用此版本方便排查

### 下载使用
1. 访问 [Releases](https://github.com/POf-L/Fanqie-novel-Downloader/releases) 页面
2. 下载对应平台的文件：
   - Windows: `TomatoNovelDownloader.exe` 或 `TomatoNovelDownloader-debug.exe`
   - Linux: `TomatoNovelDownloader-linux` 或 `TomatoNovelDownloader-debug-linux`
   - macOS: `TomatoNovelDownloader-macos` 或 `TomatoNovelDownloader-debug-macos`
3. Linux/macOS 用户需要添加执行权限：
   ```bash
   chmod +x TomatoNovelDownloader-linux  # 或其他文件名
   ```
4. macOS 用户首次运行可能需要在"系统偏好设置 > 安全性与隐私"中允许运行

### 版本号格式
格式：`YYYY.MM.DD.HHMM+commit哈希`

示例：`2025.10.05.1703+a1b2c3d`
- `2025.10.05.1703` - 构建时间（UTC时区）
- `a1b2c3d` - Git 提交的短哈希值

### 构建配置说明

#### 构建脚本
- [`build_app.py`](build_app.py) - 主构建脚本
- [`build.spec`](build.spec) - Release 版本 PyInstaller 配置
- [`debug.spec`](debug.spec) - Debug 版本 PyInstaller 配置

#### 工作流配置
- [`.github/workflows/build-release.yml`](build-release.yml) - GitHub Actions 工作流

#### 手动触发构建
1. 进入 [Actions](https://github.com/POf-L/Fanqie-novel-Downloader/actions) 页面
2. 选择 "Build Release and Debug" 工作流
3. 点击 "Run workflow" 按钮
4. 等待构建完成后在 Releases 页面查看

---

## 🔄 更新日志

### v2.2.0 (2025-01-23)
- ✅ 完善 GitHub Actions 自动构建流程
- ✅ 支持 Windows、Linux、macOS 三平台自动构建
- ✅ 添加 Release 和 Debug 双版本支持
- ✅ 优化构建脚本和配置文件
- ✅ 添加 pillow-heif 支持（HEIC 图片格式）

### v2.1.0 (2024-01-15)
- ✅ 修复章节列表解析问题（适配新API格式）
- ✅ 优化章节内容获取逻辑
- ✅ 改进错误处理和日志输出
- ✅ 更新API文档

### v2.0.0 (2024-01-10)
- 🎉 全新API架构
- 🚀 提升下载稳定性
- 📚 完善文档说明

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 参与贡献
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### 报告问题
提交 Issue 时请包含：
- 问题描述
- 复现步骤
- 错误日志
- 运行环境（Python版本、操作系统）

---

## ⚠️ 免责声明

本项目仅供学习交流使用，请勿用于商业用途。

- 下载的内容请在24小时内删除
- 请支持正版，尊重作者权益
- 使用本工具产生的一切后果由使用者自行承担
- 本项目不提供任何形式的技术支持和售后服务

---

## 📜 开源协议

本项目采用 MIT 协议开源。

Copyright (c) 2024 POf-L

---

## 🌟 Star History

如果这个项目对你有帮助，欢迎点个 Star ⭐

<div align="center">
  <img src="https://api.star-history.com/svg?repos=POf-L/Fanqie-novel-Downloader&type=Date" width="600" alt="Star History Chart">
</div>

---

<div align="center">

**[📝 问题反馈](https://github.com/POf-L/Fanqie-novel-Downloader/issues)** · 
**[💬 讨论交流](https://github.com/POf-L/Fanqie-novel-Downloader/discussions)** · 
**[⬆️ 回到顶部](#-番茄小说下载器)**

Made with ❤️ by POf-L

</div>