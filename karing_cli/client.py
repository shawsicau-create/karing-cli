"""
Clash API HTTP 客户端

封装 Karing VPN 的 Clash 兼容 RESTful API，提供：
- 标准 Clash 端点（代理、连接、规则、延迟测试等）
- Karing 自定义端点（DNS 查询、出站查询、规则集状态等）
- WebSocket URL 生成（流量、连接、日志的实时推送）

所有请求通过 Bearer Token 认证，Token 即 Karing 配置文件中的 secret。
"""

import requests
import json
from typing import Optional, Dict, Any, List

from .config import load_karing_settings, get_secret


class KaringAPIError(Exception):
    """Karing API 错误（HTTP 4xx/5xx 时抛出）。"""
    pass


class KaringClient:
    """
    Karing Clash API 的 HTTP 客户端。

    初始化时自动从 Karing 配置文件读取 host/port/secret，
    也可手动传入覆盖。
    """

    def __init__(self, host: str = None, port: int = None, secret: str = None):
        # 从 Karing 配置文件加载默认值
        settings = load_karing_settings()
        self.host = host or settings["host"]          # 默认 127.0.0.1
        self.port = port or settings["control_port"]  # 默认 3057
        self.base_url = f"http://{self.host}:{self.port}"
        self._secret = secret or get_secret()         # 自动发现或手动指定

    @property
    def headers(self) -> Dict[str, str]:
        """构造 HTTP 请求头，自动添加 Bearer Token 认证。"""
        h = {"Content-Type": "application/json"}
        if self._secret:
            h["Authorization"] = f"Bearer {self._secret}"
        return h

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """
        发送 HTTP 请求的底层方法，所有 API 调用都经过此方法。

        处理：
        - 401 未授权：提示用户设置 Secret
        - 404 未找到：API 端点不存在
        - 其他 4xx/5xx：通用错误
        - 成功：返回 JSON 或纯文本
        """
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, headers=self.headers, timeout=10, **kwargs)
        if resp.status_code == 401:
            raise KaringAPIError(
                "未授权。请设置 API Secret：karing-cli config set-secret <secret>\n"
                "或使用 --secret 参数。Secret 可从 Karing Dashboard URL 中获取。"
            )
        if resp.status_code == 404:
            raise KaringAPIError(f"端点未找到: {path}")
        if resp.status_code >= 400:
            raise KaringAPIError(f"API 错误 {resp.status_code}: {resp.text}")
        if resp.text:
            try:
                return resp.json()
            except json.JSONDecodeError:
                return resp.text
        return None

    # ============================================================
    # 标准 Clash API —— sing-box 内置的 Clash 兼容接口
    # ============================================================

    def get_version(self) -> Dict:
        """GET /version — 获取 sing-box 内核版本号。"""
        return self._request("GET", "/version")

    def get_configs(self) -> Dict:
        """GET /configs — 获取当前运行中的配置信息。"""
        return self._request("GET", "/configs")

    def get_proxies(self) -> Dict:
        """
        GET /proxies — 列出所有代理组和节点。

        返回格式：{"proxies": {"组名": {"type": "URLTest", "now": "当前节点", "all": [...]}}}
        代理组类型：Selector（手选）、URLTest（自动最快）、Fallback（故障转移）、LoadBalance（负载均衡）
        """
        return self._request("GET", "/proxies")

    def get_proxy(self, name: str) -> Dict:
        """GET /proxies/{name} — 获取指定代理组/节点的详细信息。"""
        return self._request("GET", f"/proxies/{name}")

    def switch_proxy(self, group: str, name: str) -> None:
        """
        PUT /proxies/{group} — 切换代理组中的当前节点。

        注意：仅 Selector 类型支持此 API。
        URLTest/Fallback 类型会返回 "Must be a Selector" 错误，
        需要改用修改配置文件 + 重载的方式（见 main.py 的 _switch_via_config）。
        """
        self._request("PUT", f"/proxies/{group}", json={"name": name})

    def get_delay(self, name: str, url: str = "https://www.gstatic.com/generate_204", timeout: int = 15000) -> Dict:
        """
        GET /proxies/{name}/delay — 测试节点延迟。

        参数：
          url: 用于测试的目标 URL（默认 Google 204 检测页）
          timeout: 超时毫秒数
        返回：{"delay": 毫秒数} 或 {"delay": -1} 表示超时
        """
        return self._request("GET", f"/proxies/{name}/delay", params={"url": url, "timeout": timeout})

    def get_connections(self) -> Dict:
        """
        GET /connections — 获取所有活动连接。

        返回包含 connections 列表、uploadTotal、downloadTotal 的字典。
        每个连接包含 id、metadata（host/port/protocol）、chains（经过的代理链）等信息。
        """
        return self._request("GET", "/connections")

    def close_connections(self) -> None:
        """DELETE /connections — 关闭所有活动连接（相当于重置网络）。"""
        self._request("DELETE", "/connections")

    def close_connection(self, conn_id: str) -> None:
        """DELETE /connections/{id} — 关闭指定连接。"""
        self._request("DELETE", f"/connections/{conn_id}")

    def get_rules(self) -> Dict:
        """
        GET /rules — 获取路由规则列表。

        每条规则包含 type（如 DomainSuffix、GeoIP）、payload（匹配条件）、proxy（目标出站）。
        """
        return self._request("GET", "/rules")

    def get_group_delay_history(self) -> Dict:
        """GET /group/delayhistory — 获取代理组的延迟历史记录。"""
        return self._request("GET", "/group/delayhistory")

    def reload_configs(self, path: str = "") -> None:
        """
        PUT /configs — 热重载 sing-box 配置。

        如果指定 path，则从该文件路径加载新配置（用于 URLTest 降级切换）。
        不指定 path 则重新加载当前配置。
        """
        payload = {}
        if path:
            payload["path"] = path
        self._request("PUT", "/configs", json=payload)

    # ============================================================
    # Karing 自定义端点 —— 这些是 Karing 在标准 Clash API 基础上扩展的
    # 通过逆向二进制 App.framework/App 发现
    # ============================================================

    def dns_query(self, domain: str, strategy: str = "ipv4_only") -> Dict:
        """
        POST /karing/dnsQuery — 通过代理进行 DNS 查询。

        strategy 可选值：ipv4_only, ipv6_only, prefer_ipv4, prefer_ipv6
        """
        return self._request("POST", "/karing/dnsQuery", json={
            "domain": domain,
            "strategy": strategy,
        })

    def dns_query_default_router(self, domain: str, strategy: str = "ipv4_only") -> Dict:
        """GET /karing/dnsQueryWithDefaultRouter — 通过默认路由（直连）进行 DNS 查询。"""
        return self._request("GET", "/karing/dnsQueryWithDefaultRouter", params={
            "domain": domain,
            "strategy": strategy,
        })

    def outbound_query(self, domain: str, ip: str = "", port: int = 0) -> Dict:
        """
        GET /karing/outboundQuery — 查询域名的出站路由。

        返回该域名会走哪条规则、哪个出站（direct_out / urltest_out 等）。
        用于调试分流规则是否正确。
        """
        params = {"domain": domain}
        if ip:
            params["ip"] = ip
        if port:
            params["port"] = port
        return self._request("GET", "/karing/outboundQuery", params=params)

    def reset_outbound_connections(self) -> None:
        """POST /karing/resetOutboundConnections — 重置所有出站连接（Karing 特有）。"""
        self._request("POST", "/karing/resetOutboundConnections")

    def get_remote_rulesets_count(self) -> Dict:
        """GET /karing/remoteRuleSetRulesCount — 获取远程规则集的规则条数。"""
        return self._request("GET", "/karing/remoteRuleSetRulesCount")

    def get_remote_rulesets_states(self) -> Dict:
        """GET /karing/remoteRuleSetStates — 获取远程规则集的加载状态。"""
        return self._request("GET", "/karing/remoteRuleSetStates")

    # ============================================================
    # WebSocket URL 生成 —— 用于实时监控
    # Clash API 支持 WebSocket 推送流量、连接、日志数据
    # ============================================================

    def get_traffic_ws_url(self) -> str:
        """生成实时流量 WebSocket URL。客户端连接后可接收上/下行速率数据。"""
        url = f"ws://{self.host}:{self.port}/traffic"
        if self._secret:
            url += f"?token={self._secret}"
        return url

    def get_connections_ws_url(self) -> str:
        """生成实时连接 WebSocket URL。客户端连接后可接收连接变化事件。"""
        url = f"ws://{self.host}:{self.port}/connections"
        if self._secret:
            url += f"?token={self._secret}"
        return url

    def get_logs_ws_url(self, level: str = "info") -> str:
        """生成实时日志 WebSocket URL。level 可选：debug, info, warning, error。"""
        url = f"ws://{self.host}:{self.port}/logs?level={level}"
        if self._secret:
            url += f"&token={self._secret}"
        return url
