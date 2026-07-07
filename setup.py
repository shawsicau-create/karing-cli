"""
karing-cli 打包配置

使用 setuptools 将 karing-cli 封装为可安装的 Python CLI 工具。
安装后 karing-cli 命令会自动加入 PATH（通过 console_scripts 入口点）。
"""

from setuptools import setup, find_packages

setup(
    name="karing-cli",
    version="0.1.0",
    description="通过 Clash API 管理 Karing VPN 的命令行工具",
    author="Mr Shaw",
    url="https://cnb.cool/xiaosicau/karing-cli",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",       # CLI 框架：命令解析、参数处理、彩色输出
        "requests>=2.28",   # HTTP 客户端：调用 Clash API
    ],
    entry_points={
        "console_scripts": [
            # 注册 karing-cli 命令 → 调用 karing_cli.main 模块的 main() 函数
            "karing-cli=karing_cli.main:main",
        ],
    },
    python_requires=">=3.8",
)
"""Setup for karing-cli."""

from setuptools import setup, find_packages

setup(
    name="karing-cli",
    version="0.1.0",
    description="CLI for managing Karing VPN via Clash API",
    author="karing-cli",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "requests>=2.28",
    ],
    entry_points={
        "console_scripts": [
            "karing-cli=karing_cli.main:main",
        ],
    },
    python_requires=">=3.8",
)
