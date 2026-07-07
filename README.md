# karing-cli

通过 Clash 兼容 API 管理 [Karing VPN](https://karing.app/) 的命令行工具。

**作者**：xiaoshishun  
**源码**：[CNB 仓库](https://cnb.cool/xiaosicau/karing-cli) · [PyPI](https://pypi.org/project/karing-cli/)  
**环境**：macOS · Python >= 3.8 · Karing VPN 本地运行中

## 安装

```bash
pip install karing-cli
# 或使用 uv（推荐）
uv tool install karing-cli
```

## 功能一览

| 命令 | 功能 |
|------|------|
| `karing-cli status` | 查看 VPN 状态、版本、当前代理组、连接数 |
| `karing-cli best` | 一键测速并切换到最快节点 |
| `karing-cli proxies [GROUP]` | 列出所有代理组和节点 |
| `karing-cli switch GROUP NODE` | 切换节点（兼容 URLTest/Fallback/Selector） |
| `karing-cli test --group GROUP` | 测试组内所有节点延迟 |
| `karing-cli connections` | 查看活动连接（支持 `--close` 关闭） |
| `karing-cli dns DOMAIN` | DNS 查询（代理/直连模式） |
| `karing-cli outbound DOMAIN` | 查看域名的出站路由规则 |
| `karing-cli rules` | 列出所有路由规则 |
| `karing-cli reset` | 重置所有连接 |
| `karing-cli config show` | 显示 CLI 配置及 Secret 来源 |
| `karing-cli guide` | 交互式配置向导 |

## 快速开始

```bash
# 检查 VPN 状态（首次运行自动发现 Secret，无需手动配置）
karing-cli status

# 一键测速 + 切换到最快节点
karing-cli best

# 查看当前代理组
karing-cli proxies

# DNS 查询验证分流
karing-cli dns google.com     # 国外域名 → 走代理
karing-cli dns baidu.com      # 国内域名 → 走直连
```
