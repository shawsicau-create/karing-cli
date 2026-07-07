"""
karing-cli 配置管理模块

负责：
1. 读取 Karing 自身的配置文件（端口、主机等）
2. 管理 karing-cli 自己的配置（Secret 等）
3. Secret 自动发现：从多个来源按优先级获取 API 密钥

Karing 在 macOS 上将配置存储在 Group Container 中：
  ~/Library/Group Containers/group.com.nebula.karing/
"""

import os
import json
from pathlib import Path

# ============================================================
# 默认值 —— 来自 Karing 源码 setting_manager.dart
# 当配置文件不存在时，使用这些默认值
# ============================================================
DEFAULT_CONTROL_PORT = 3057       # Clash API 端口（sing-box 的控制接口）
DEFAULT_MIXED_PORT = 3067         # 混合代理端口（HTTP + SOCKS5）
DEFAULT_HTML_BOARD_PORT = 3072    # Web 面板（Zashboard）端口
DEFAULT_HOST = "127.0.0.1"        # 绑定地址

# ============================================================
# Karing Group Container 路径（macOS 应用沙箱共享目录）
# Karing 的 Bundle ID 是 com.nebula.karing，Group ID 是 group.com.nebula.karing
# ============================================================
KARING_GROUP_CONTAINER = Path.home() / "Library" / "Group Containers" / \
    "group.com.nebula.karing"
KARING_SETTING_FILE = KARING_GROUP_CONTAINER / \
    "karing_setting.json"       # Karing 用户设置（端口、代理模式等）
KARING_SERVICE_FILE = KARING_GROUP_CONTAINER / \
    "service.json"              # 服务配置（包含 secret）
KARING_SERVICE_CORE_FILE = KARING_GROUP_CONTAINER / \
    "service_core.json"    # sing-box 核心配置（完整 JSON）

# karing-cli 自身的配置文件目录
CONFIG_DIR = Path.home() / ".config" / "karing-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_karing_settings():
    """
    读取 Karing 的用户设置文件，获取端口和主机信息。

    返回包含 host、control_port、mixed_port、html_board_port 的字典。
    如果文件不存在或解析失败，返回默认值。
    """
    try:
        if KARING_SETTING_FILE.exists():
            with open(KARING_SETTING_FILE, "r") as f:
                data = json.load(f)
                proxy = data.get("proxy", {})
                return {
                    "host": proxy.get("host", DEFAULT_HOST),
                    "control_port": proxy.get("control_port", DEFAULT_CONTROL_PORT),
                    "mixed_port": proxy.get("mixed_port", DEFAULT_MIXED_PORT),
                    "html_board_port": data.get("html_board_port", DEFAULT_HTML_BOARD_PORT),
                }
    except Exception:
        pass
    # 配置文件不存在时返回默认值
    return {
        "host": DEFAULT_HOST,
        "control_port": DEFAULT_CONTROL_PORT,
        "mixed_port": DEFAULT_MIXED_PORT,
        "html_board_port": DEFAULT_HTML_BOARD_PORT,
    }


def load_cli_config():
    """
    读取 karing-cli 自身的配置文件（~/.config/karing-cli/config.json）。
    目前主要存储手动设置的 API Secret。
    """
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_cli_config(config):
    """保存 karing-cli 配置到文件。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_secret():
    """
    获取 Clash API 的认证密钥（Secret）。

    Secret 按以下优先级查找：
    1. CLI 的 --secret 参数（在 main.py 中处理，传入 KaringClient）
    2. KARING_SECRET 环境变量
    3. karing-cli 保存的配置文件（~/.config/karing-cli/config.json）
    4. Karing 的 service.json（自动发现）
    5. Karing 的 service_core.json（自动发现，从 experimental.clash_api.secret 读取）
    6. 返回 None（可能 API 未设置密码）

    技巧：service.json 是 Karing 在启动 VPN 时写入的 IPC 配置文件，
    其中 secret 字段就是 sing-box Clash API 的 Bearer Token。
    """
    # 1. 检查环境变量
    env_secret = os.environ.get("KARING_SECRET")
    if env_secret:
        return env_secret

    # 2. 检查 karing-cli 保存的配置
    config = load_cli_config()
    saved_secret = config.get("secret")
    if saved_secret:
        return saved_secret

    # 3. 从 service.json 自动发现（Karing 写入的 IPC 配置）
    try:
        if KARING_SERVICE_FILE.exists():
            with open(KARING_SERVICE_FILE, "r") as f:
                data = json.load(f)
                secret = data.get("secret")
                if secret:
                    return secret
    except Exception:
        pass

    # 4. 从 service_core.json 自动发现（sing-box 完整配置）
    # 路径：experimental.clash_api.secret
    try:
        if KARING_SERVICE_CORE_FILE.exists():
            with open(KARING_SERVICE_CORE_FILE, "r") as f:
                data = json.load(f)
                clash_api = data.get("experimental", {}).get("clash_api", {})
                secret = clash_api.get("secret")
                if secret:
                    return secret
    except Exception:
        pass

    return None


def get_secret_source():
    """
    返回 (secret值, 来源描述) 的元组，用于 config show 命令显示。
    来源描述帮助用户了解 Secret 是从哪里获取的。
    """
    env_secret = os.environ.get("KARING_SECRET")
    if env_secret:
        return env_secret, "env var (KARING_SECRET)"

    config = load_cli_config()
    saved_secret = config.get("secret")
    if saved_secret:
        return saved_secret, "saved config"

    try:
        if KARING_SERVICE_FILE.exists():
            with open(KARING_SERVICE_FILE, "r") as f:
                data = json.load(f)
                secret = data.get("secret")
                if secret:
                    return secret, "auto (service.json)"
    except Exception:
        pass

    try:
        if KARING_SERVICE_CORE_FILE.exists():
            with open(KARING_SERVICE_CORE_FILE, "r") as f:
                data = json.load(f)
                clash_api = data.get("experimental", {}).get("clash_api", {})
                secret = clash_api.get("secret")
                if secret:
                    return secret, "auto (service_core.json)"
    except Exception:
        pass

    return None, "not configured"
