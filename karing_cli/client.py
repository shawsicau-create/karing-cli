"""Clash API HTTP client for Karing."""

import requests
import json
from typing import Optional, Dict, Any, List

from .config import load_karing_settings, get_secret


class KaringAPIError(Exception):
    """Karing API error."""
    pass


class KaringClient:
    """HTTP client for Karing's Clash-compatible API."""

    def __init__(self, host: str = None, port: int = None, secret: str = None):
        settings = load_karing_settings()
        self.host = host or settings["host"]
        self.port = port or settings["control_port"]
        self.base_url = f"http://{self.host}:{self.port}"
        self._secret = secret or get_secret()

    @property
    def headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._secret:
            h["Authorization"] = f"Bearer {self._secret}"
        return h

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, headers=self.headers, timeout=10, **kwargs)
        if resp.status_code == 401:
            raise KaringAPIError(
                "Unauthorized. Set API secret with: karing-cli config set-secret <secret>\n"
                "Or use --secret flag. Get secret from Karing Dashboard URL."
            )
        if resp.status_code == 404:
            raise KaringAPIError(f"Not found: {path}")
        if resp.status_code >= 400:
            raise KaringAPIError(f"API error {resp.status_code}: {resp.text}")
        if resp.text:
            try:
                return resp.json()
            except json.JSONDecodeError:
                return resp.text
        return None

    # === Standard Clash API ===

    def get_version(self) -> Dict:
        """GET /version — sing-box core version."""
        return self._request("GET", "/version")

    def get_configs(self) -> Dict:
        """GET /configs — current running configuration."""
        return self._request("GET", "/configs")

    def get_proxies(self) -> Dict:
        """GET /proxies — list all proxy groups and nodes."""
        return self._request("GET", "/proxies")

    def get_proxy(self, name: str) -> Dict:
        """GET /proxies/{name} — get a specific proxy's info."""
        return self._request("GET", f"/proxies/{name}")

    def switch_proxy(self, group: str, name: str) -> None:
        """PUT /proxies/{group} — switch the selected node in a group."""
        self._request("PUT", f"/proxies/{group}", json={"name": name})

    def get_delay(self, name: str, url: str = "https://www.gstatic.com/generate_204", timeout: int = 15000) -> Dict:
        """GET /proxies/{name}/delay — test latency for a node."""
        return self._request("GET", f"/proxies/{name}/delay", params={"url": url, "timeout": timeout})

    def get_connections(self) -> Dict:
        """GET /connections — list active connections."""
        return self._request("GET", "/connections")

    def close_connections(self) -> None:
        """DELETE /connections — close all connections."""
        self._request("DELETE", "/connections")

    def close_connection(self, conn_id: str) -> None:
        """DELETE /connections/{id} — close a specific connection."""
        self._request("DELETE", f"/connections/{conn_id}")

    def get_rules(self) -> Dict:
        """GET /rules — list routing rules."""
        return self._request("GET", "/rules")

    def get_group_delay_history(self) -> Dict:
        """GET /group/delayhistory — group delay history."""
        return self._request("GET", "/group/delayhistory")

    def reload_configs(self, path: str = "") -> None:
        """PUT /configs — reload sing-box configuration."""
        payload = {}
        if path:
            payload["path"] = path
        self._request("PUT", "/configs", json=payload)

    # === Karing Custom Endpoints ===

    def dns_query(self, domain: str, strategy: str = "ipv4_only") -> Dict:
        """POST /karing/dnsQuery — DNS query through proxy."""
        return self._request("POST", "/karing/dnsQuery", json={
            "domain": domain,
            "strategy": strategy,
        })

    def dns_query_default_router(self, domain: str, strategy: str = "ipv4_only") -> Dict:
        """GET /karing/dnsQueryWithDefaultRouter — DNS query via default router."""
        return self._request("GET", "/karing/dnsQueryWithDefaultRouter", params={
            "domain": domain,
            "strategy": strategy,
        })

    def outbound_query(self, domain: str, ip: str = "", port: int = 0) -> Dict:
        """GET /karing/outboundQuery — check outbound routing for a domain."""
        params = {"domain": domain}
        if ip:
            params["ip"] = ip
        if port:
            params["port"] = port
        return self._request("GET", "/karing/outboundQuery", params=params)

    def reset_outbound_connections(self) -> None:
        """POST /karing/resetOutboundConnections — reset outbound connections."""
        self._request("POST", "/karing/resetOutboundConnections")

    def get_remote_rulesets_count(self) -> Dict:
        """GET /karing/remoteRuleSetRulesCount — remote ruleset count."""
        return self._request("GET", "/karing/remoteRuleSetRulesCount")

    def get_remote_rulesets_states(self) -> Dict:
        """GET /karing/remoteRuleSetStates — remote ruleset states."""
        return self._request("GET", "/karing/remoteRuleSetStates")

    # === WebSocket URLs ===

    def get_traffic_ws_url(self) -> str:
        """Get WebSocket URL for real-time traffic monitoring."""
        url = f"ws://{self.host}:{self.port}/traffic"
        if self._secret:
            url += f"?token={self._secret}"
        return url

    def get_connections_ws_url(self) -> str:
        """Get WebSocket URL for real-time connection monitoring."""
        url = f"ws://{self.host}:{self.port}/connections"
        if self._secret:
            url += f"?token={self._secret}"
        return url

    def get_logs_ws_url(self, level: str = "info") -> str:
        """Get WebSocket URL for real-time logs."""
        url = f"ws://{self.host}:{self.port}/logs?level={level}"
        if self._secret:
            url += f"&token={self._secret}"
        return url
