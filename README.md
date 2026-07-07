# karing-cli

通过 Clash 兼容 API 管理 [Karing VPN](https://karing.app/) 的命令行工具。

## 功能特性

- 查看 VPN 状态、版本、当前代理组
- 列出所有代理节点及延迟
- 一键测速并切换到最快节点（`karing-cli best`）
- 切换代理节点（兼容 URLTest / Fallback / Selector 三种类型）
- 监控活动连接和流量
- DNS 查询与出站路由检查
- 查看路由规则

## 安装

```bash
pip install -e .
# 或
uv tool install -e .
```

## 快速开始

```bash
# 查看配置向导
karing-cli guide

# Secret 自动发现（macOS）
# 自动从 ~/Library/Group Containers/group.com.nebula.karing/service.json 读取

# 查看 VPN 状态
karing-cli status

# 列出所有代理节点
karing-cli proxies

# 测速并自动切换到最快节点
karing-cli best

# 只测速不切换
karing-cli best --no-switch

# 手动切换节点
karing-cli switch urltest_out "节点名称"

# 测试延迟
karing-cli test --group GLOBAL

# 查看活动连接
karing-cli connections

# DNS 查询
karing-cli dns google.com

# 查看出站路由
karing-cli outbound google.com

# 查看路由规则
karing-cli rules

# 重置所有连接
karing-cli reset

# 查看 CLI 配置
karing-cli config show

# 手动设置 Secret
karing-cli config set-secret YOUR_SECRET
```

## 编程原理与技术技巧

### 架构总览

```
用户终端 ──→ karing-cli (Python Click) ──→ Clash API (HTTP) ──→ sing-box 核心 ──→ VPN 网络
                                                  ↑
                                          Karing 本地服务
                                         (127.0.0.1:3057)
```

本项目本质上是一个 **HTTP API 客户端**，通过调用 Karing VPN 内置的 RESTful API 来控制 VPN。

### 核心发现：Karing 的 Clash 兼容 API

Karing 底层使用 **sing-box** 网络引擎，它在本地 `127.0.0.1:3057` 暴露了一套 Clash 兼容的 RESTful API。
这是 Karing 内置 Web 面板（Zashboard）控制 VPN 的接口，本工具"借用"了它。

**标准 Clash 端点：**

| 端点 | 方法 | 作用 |
|------|------|------|
| `/version` | GET | 获取 sing-box 内核版本 |
| `/proxies` | GET | 列出所有代理组和节点 |
| `/proxies/{group}` | PUT | 切换 Selector 类型组的节点 |
| `/proxies/{name}/delay` | GET | 测试节点延迟 |
| `/connections` | GET/DELETE | 查看/关闭活动连接 |
| `/rules` | GET | 查看路由规则 |
| `/configs` | GET/PUT | 查看/重载配置 |

**Karing 自定义端点：**

| 端点 | 作用 |
|------|------|
| `/karing/dnsQuery` | 通过代理进行 DNS 查询 |
| `/karing/outboundQuery` | 查询域名的出站路由规则 |
| `/karing/resetOutboundConnections` | 重置出站连接 |
| `/karing/remoteRuleSetStates` | 远程规则集状态 |

### Secret 自动发现机制

API 使用 Bearer Token 认证。Secret 按以下优先级获取：

```
CLI --secret 参数
  → KARING_SECRET 环境变量
    → ~/.config/karing-cli/config.json（手动保存）
      → service.json（自动发现）
        → service_core.json（自动发现）
```

**关键发现：** Karing 将 sing-box 配置保存在 macOS Group Container 的 JSON 文件中：
- `service.json` 的 `secret` 字段直接存储了 API 密钥
- `service_core.json` 的 `experimental.clash_api.secret` 也保存了同样的密钥

CLI 直接读取这些文件，实现**零配置开箱即用**。

### URLTest 降级切换策略

这是本项目最有技巧的部分。Karing 使用 **URLTest**（自动选最快）类型的代理组，
而标准 Clash API 的 `PUT /proxies/{group}` 只支持 **Selector** 类型。

**降级策略：**

```
1. 先尝试标准 API：PUT /proxies/{group} {"name": "node"}
2. 如果报 "Must be a Selector" 错误：
   → 读取 service_core.json（sing-box 配置文件）
   → 修改对应 outbound 的 "default" 字段为目标节点
   → 写回文件
   → 调用 PUT /configs 让 sing-box 热重载配置
```

### 自动测速与切换（best 命令）

```
1. GET /proxies → 获取目标组的所有节点列表
2. 遍历每个节点 → GET /proxies/{name}/delay?url=...&timeout=5000
3. 找到 delay 最小的节点
4. 调用 switch 逻辑切换（自动处理 URLTest 降级）
```

### 技术栈

| 组件 | 用途 |
|------|------|
| **Python Click** | CLI 框架，命令解析、参数处理、彩色输出 |
| **requests** | HTTP 客户端，调用 Clash API |
| **setuptools** | 打包为可安装的 CLI 工具 |
| **uv** | 现代 Python 包管理器，绕过 macOS externally-managed-environment 限制 |

### 项目结构

```
karing-cli/
├── karing_cli/
│   ├── __init__.py      # 版本号
│   ├── config.py        # 配置管理：Karing 设置读取、Secret 自动发现
│   ├── client.py        # Clash API HTTP 客户端封装
│   └── main.py          # CLI 入口：所有命令定义（Click 框架）
├── setup.py             # Python 包安装配置
├── README.md
├── LICENSE
└── .gitignore
```

### 逆向工程过程

本项目的 API 端点通过以下方式逆向还原（`clash_api.dart` 未在开源仓库中公开）：

1. **源码分析**：克隆 KaringX/karing 仓库，分析 `setting_manager.dart` 获取端口配置
2. **调用模式分析**：grep `server_manager.dart` 中所有 `ClashApi.*` 调用
3. **二进制逆向**：对 `App.framework/App` 使用 `strings` 提取 API 端点路径
4. **配置文件发现**：在 `~/Library/Group Containers/` 找到 `service.json` 和 `service_core.json`

## 配置说明

CLI 自动从 Karing 配置文件中发现设置：

- `~/Library/Group Containers/group.com.nebula.karing/service.json` — API Secret
- `~/Library/Group Containers/group.com.nebula.karing/karing_setting.json` — 端口/主机
- `~/Library/Group Containers/group.com.nebula.karing/service_core.json` — sing-box 完整配置

也可以手动配置：

```bash
# 保存 Secret
karing-cli config set-secret YOUR_SECRET

# 或使用环境变量
export KARING_SECRET=your_secret
```

## 环境要求

- Python >= 3.8
- Karing VPN 本地运行中
- click >= 8.0
- requests >= 2.28

## License

MIT
# karing-cli

A command-line tool for managing [Karing VPN](https://karing.app/) via its Clash-compatible API.

## Features

- View VPN status, version, and active proxy groups
- List all proxy nodes with latency
- Auto-test and switch to the fastest node (`karing-cli best`)
- Switch proxy nodes (supports URLTest/Fallback/Selector groups)
- Monitor active connections and traffic
- DNS query and outbound routing inspection
- View routing rules

## Installation

```bash
pip install -e .
# or
uv tool install -e .
```

## Quick Start

```bash
# View setup guide
karing-cli guide

# Auto-discover secret from Karing config (macOS)
# Secret is automatically read from ~/Library/Group Containers/group.com.nebula.karing/service.json

# Check VPN status
karing-cli status

# List all proxy nodes
karing-cli proxies

# Test all nodes and switch to fastest
karing-cli best

# Test only (no switch)
karing-cli best --no-switch

# Manual switch
karing-cli switch urltest_out "Your Node Name"

# Test latency
karing-cli test --group GLOBAL

# View active connections
karing-cli connections

# DNS query
karing-cli dns google.com

# View outbound routing for a domain
karing-cli outbound google.com

# View routing rules
karing-cli rules

# Reset all connections
karing-cli reset

# Show CLI config
karing-cli config show

# Manually set secret (if auto-discovery fails)
karing-cli config set-secret YOUR_SECRET
```

## Configuration

The CLI auto-discovers settings from Karing's config files:

- `~/Library/Group Containers/group.com.nebula.karing/service.json` — API secret
- `~/Library/Group Containers/group.com.nebula.karing/karing_setting.json` — port/host config

You can also configure manually:

```bash
# Set secret
karing-cli config set-secret YOUR_SECRET

# Or use environment variable
export KARING_SECRET=your_secret
```

## API Endpoints Used

- Standard Clash API on `127.0.0.1:3057`
- Custom Karing endpoints: `/karing/dnsQuery`, `/karing/outboundQuery`, etc.

## Requirements

- Python ≥ 3.8
- Karing VPN running locally
- click ≥ 8.0
- requests ≥ 2.28

## License

MIT
