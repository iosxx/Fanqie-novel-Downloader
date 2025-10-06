"""
PyInstaller 构建配置
自动从 requirements.txt 读取依赖并生成 hiddenimports 列表
"""
import re
from pathlib import Path


def parse_requirements(requirements_file='requirements.txt'):
    """
    解析 requirements.txt 文件，提取所有包名
    
    Args:
        requirements_file: requirements.txt 文件路径
        
    Returns:
        list: 包名列表
    """
    packages = []
    req_path = Path(__file__).parent / requirements_file
    
    if not req_path.exists():
        return packages
    
    with open(req_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue
            
            # 提取包名（去除版本约束）
            # 支持格式：package, package==1.0, package>=1.0,<2.0
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                packages.append(match.group(1))
    
    return packages


# 某些包需要显式导入子模块
PACKAGE_SUBMODULES = {
    'requests': [
        'requests.adapters',
        'requests.auth',
        'requests.cookies',
        'requests.exceptions',
        'requests.models',
        'requests.sessions',
        'requests.structures',
        'requests.utils',
    ],
    'urllib3': [
        'urllib3.util',
        'urllib3.util.retry',
        'urllib3.util.ssl_',
        'urllib3.connection',
        'urllib3.connectionpool',
        'urllib3.poolmanager',
        'urllib3.response',
    ],
    'packaging': [
        'packaging.version',
        'packaging.specifiers',
        'packaging.requirements',
    ],
    'PIL': [
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFile',
        'PIL.ImageFont',
        'PIL.ImageOps',
        'PIL.JpegImagePlugin',
        'PIL.PngImagePlugin',
        'PIL.GifImagePlugin',
        'PIL.BmpImagePlugin',
        'PIL.WebPImagePlugin',
        'PIL._imaging',
    ],
    'beautifulsoup4': [
        'bs4',
    ],
    'fake_useragent': [
        'fake_useragent.data',
    ],
    'pillow_heif': [
        'pillow_heif.heif',
        'pillow_heif.misc',
        'pillow_heif.options',
    ],
}

# 标准库模块（需要显式导入的）
STDLIB_MODULES = [
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'tkinter.filedialog',
    'tkinter.font',
    'tkinter.scrolledtext',
    'threading',
    'json',
    'os',
    'sys',
    'time',
    're',
    'base64',
    'gzip',
    'urllib.parse',
    'concurrent.futures',
    'collections',
    'typing',
    'signal',
    'random',
    'io',
    'tempfile',
    'zipfile',
    'shutil',
    'subprocess',
    'datetime',
]

# 包名映射（处理特殊情况）
PACKAGE_NAME_MAPPING = {
    'pillow': 'PIL',
    'fake-useragent': 'fake_useragent',
    'beautifulsoup4': 'bs4',
}

# 隐式依赖（某些包的运行时依赖）
IMPLICIT_DEPENDENCIES = [
    'charset_normalizer',
    'idna',
    'certifi',
]


def get_hidden_imports():
    """
    获取所有需要的 hiddenimports
    
    Returns:
        list: 完整的 hiddenimports 列表
    """
    packages = parse_requirements()
    hidden_imports = []
    
    # 添加基础包
    for pkg in packages:
        pkg_lower = pkg.lower()
        
        # 处理特殊包名映射
        if pkg_lower in PACKAGE_NAME_MAPPING:
            mapped_pkg = PACKAGE_NAME_MAPPING[pkg_lower]
            hidden_imports.append(mapped_pkg)
            pkg = mapped_pkg
        else:
            # 将连字符转换为下划线
            pkg = pkg.replace('-', '_')
            hidden_imports.append(pkg)
        
        # 添加已知的子模块
        if pkg in PACKAGE_SUBMODULES:
            hidden_imports.extend(PACKAGE_SUBMODULES[pkg])
    
    # 添加标准库模块
    hidden_imports.extend(STDLIB_MODULES)
    
    # 添加隐式依赖
    hidden_imports.extend(IMPLICIT_DEPENDENCIES)
    
    # 去重并排序
    hidden_imports = sorted(set(hidden_imports))
    
    return hidden_imports


if __name__ == '__main__':
    # 测试：打印所有 hiddenimports
    imports = get_hidden_imports()
    print("Hidden imports:")
    for imp in imports:
        print(f"  - {imp}")
    print(f"\nTotal: {len(imports)} imports")