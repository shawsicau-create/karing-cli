# karing-cli

通过 Clash 兼容 API 管理 [Karing VPN](https://karing.app/) 的命令行工具。

> **一行命令，一键加速** —— `karing-cli best` 自动测速 30+ 节点并切换到最快的一个。

## 项目亮点

### 零配置开箱即用

安装即可使用，无需手动配置。CLI 自动从 Karing 的 macOS 配置文件中发现 API Secret：

```
~/Library/Group Containers/group.com.nebula.karing/service.json → 自动读取 secret
```

### 逆向还原私有 API

Karing 的核心 API 封装文件（`clash_api.dart`）未开源。本项目通过以下方式逆向还原了完整的 API 接口：

- 源码分析 `setting_manager.dart` 提取端口配置
- `strings` 逆向 `App.framework/App` 二进制提取端点路径
- 在 Group Container 中发现 `service.json` 和 `service_core.json` 配置文件

### URLTest 智能降级切换

Karing 默认使用 URLTest（自动选最快）代理组，不支持标准 Clash API 的节点切换。本项目实现了独创的降级策略：

```
标准 API 切换失败 → 直接修改 sing-box 配置文件 → PUT /configs 热重载 → 切换生效
```

### 一键测速优化

`karing-cli best` 命令自动完成：遍历所有节点 → 逐个测速 → 找出最快 → 智能切换。

## 功能特性

| 命令 | 功能 |
|------|------|
| `status` | 查看 VPN 状态、版本、当前代理组、连接数 |
| `proxies [GROUP]` | 列出所有代理组和节点 |
| `best` | 一键测速并切换到最快节点 |
| `best --no-switch` | 只测速不切换 |
| `switch GROUP NODE` | 切换节点（兼容 URLTest/Fallback/Selector） |
| `test --group GROUP` | 测试组内所有节点延迟 |
| `connections` | 查看活动连接（支持 `--close` 关闭） |
| `dns DOMAIN` | DNS 查询（支持代理/直连模式） |
| `outbound DOMAIN` | 查看域名的出站路由规则 |
| `rules` | 列出所有路由规则 |
| `reset` | 重置所有连接 |
| `config show` | 显示 CLI 配置及 Secret 来源 |
| `guide` | 交互式配置向导 |

## 安装

### 从 wheel 安装（推荐）

```bash
pip install karing_cli-0.1.0-py3-none-any.whl
```

### 从源码安装

```bash
git clone https://cnb.cool/xiaosicau/karing-cli.git
cd karing-cli
pip install .
# 或使用 uv（推荐，绕过 macOS 限制）
uv tool install .
```

## 快速开始

```bash
# 1. 检查 VPN 状态（首次运行会自动发现 Secret）
karing-cli status

# 2. 一键测速 + 切换到最快节点
karing-cli best

# 3. 查看当前代理组
karing-cli proxies

# 4. 查看活动连接
karing-cli connections

# 5. DNS 查询（验证分流是否正确）
karing-cli dns google.com     # 国外域名 → 应走代理
karing-cli dns baidu.com      # 国内域名 → 应走直连

# 6. 查看域名的出站路由
karing-cli outbound google.com
karing-cli outbound baidu.com
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

### Clash 兼容 API

Karing 底层使用 **sing-box** 网络引擎，在本地 `127.0.0.1:3057` 暴露 Clash 兼容 RESTful API。

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

### Secret 自动发现

API 使用 Bearer Token 认证，Secret 按以下优先级获取：

```
CLI --secret 参数
  → KARING_SECRET 环境变量
    → ~/.config/karing-cli/config.json（手动保存）
      → service.json（自动发现 secret 字段）
        → service_core.json（自动发现 experimental.clash_api.secret）
```

### URLTest 降级策略详解

```
karing-cli switch urltest_out "A2 香港6"
         │
         ├─ PUT /proxies/urltest_out {"name": "A2 香港6"}
         │   → 400 "Must be a Selector"
         │
         ├─ 读取 service_core.json
         ├─ 找到 outbounds 中 tag="urltest_out" 的组
         ├─ 修改 "default": "A2 香港6"
         ├─ 写回 service_core.json
         └─ PUT /configs {"path": "...service_core.json"}
             → sing-box 热重载，切换生效
```

### 技术栈

| 组件 | 用途 |
|------|------|
| **Python Click** | CLI 框架，命令解析、参数处理、彩色终端输出 |
| **requests** | HTTP 客户端，调用 Clash API |
| **setuptools** | 打包为 wheel，注册 console_scripts 入口点 |
| **uv** | 现代 Python 包管理，绕过 macOS externally-managed-environment |

### 项目结构

```
karing-cli/
├── karing_cli/
│   ├── __init__.py      # 版本号
│   ├── config.py        # 配置管理：Karing 设置读取、Secret 多级自动发现
│   ├── client.py        # Clash API HTTP 客户端（标准 + Karing 自定义端点）
│   └── main.py          # CLI 入口：12 个命令定义（Click 框架）
├── setup.py             # 打包配置（console_scripts 注册 karing-cli 命令）
├── dist/                # 构建产物（.whl + .tar.gz）
├── README.md
├── LICENSE
└── .gitignore
```

### 逆向工程过程

1. **源码分析**：克隆 KaringX/karing，分析 `setting_manager.dart` 获取默认端口（3057/3067/3072）
2. **调用模式**：grep `server_manager.dart` 提取所有 `ClashApi.getDelay()`、`ClashApi.dnsQuery()` 等调用
3. **二进制逆向**：`strings App.framework/App | grep "^/karing/"` 发现 6 个自定义端点
4. **配置发现**：在 `~/Library/Group Containers/` 找到 `service.json`（含 secret）和 `service_core.json`（完整 sing-box 配置）

## 配置说明

CLI 自动从 Karing 配置文件中读取设置，通常无需手动配置：

| 文件 | 内容 |
|------|------|
| `service.json` | API Secret |
| `karing_setting.json` | 端口、主机地址 |
| `service_core.json` | sing-box 完整配置（路由规则、代理节点等） |

路径：`~/Library/Group Containers/group.com.nebula.karing/`

如需手动设置：

```bash
karing-cli config set-secret YOUR_SECRET
# 或
export KARING_SECRET=your_secret
```

## 环境要求

- Python >= 3.8
- Karing VPN 本地运行中（macOS）
- click >= 8.0
- requests >= 2.28

## License

MIT
