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
