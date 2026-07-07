"""
karing-cli 主入口 —— CLI 命令定义模块

使用 Python Click 框架构建命令行界面：
- @click.group() 定义主命令组，全局选项（--secret, --host, --port）
- @cli.command() 注册子命令（status, proxies, switch, best 等）
- @click.pass_context 在命令间传递 KaringClient 实例
- click.secho() 实现彩色终端输出
- --json-output 标志支持 JSON 格式输出（便于脚本调用）
"""

import click
import json
import sys
from urllib.parse import quote

from . import __version__
from .client import KaringClient, KaringAPIError
from .config import save_cli_config, load_cli_config, load_karing_settings, get_secret_source


def _client(ctx) -> KaringClient:
    """从 Click 上下文中获取 KaringClient 实例（在 cli() 主命令中初始化）。"""
    return ctx.obj["client"]


def _handle_error(e):
    """统一错误处理：红色输出错误信息并退出。"""
    if isinstance(e, KaringAPIError):
        click.secho(f"Error: {e}", fg="red", err=True)
    else:
        click.secho(f"Error: {e}", fg="red", err=True)
    sys.exit(1)


def json_output(data, indent=2):
    """输出格式化的 JSON（用于 --json-output 模式，便于脚本解析）。"""
    click.echo(json.dumps(data, indent=indent, ensure_ascii=False))


def fmt_bytes(n):
    """
    将字节数格式化为人类可读的字符串。
    例：1048576 → "1.0 MB"
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_delay_display(delay_ms):
    """
    延迟值彩色显示：
    - < 0:    红色 "timeout"（节点不可达）
    - < 300:  绿色（快速）
    - < 1000: 黄色（一般）
    - >= 1000: 红色（慢）
    """
    if delay_ms < 0:
        return click.style("timeout", fg="red")
    elif delay_ms < 300:
        return click.style(f"{delay_ms}ms", fg="green")
    elif delay_ms < 1000:
        return click.style(f"{delay_ms}ms", fg="yellow")
    else:
        return click.style(f"{delay_ms}ms", fg="red")


# # # # # # # # # # # # # # # # # # # # # # # #
# 主命令组 —— 所有子命令的父级
# 全局选项在这里定义，通过 ctx.obj 传递给子命令
# # # # # # # # # # # # # # # # # # # # # # # #

@click.group()
@click.option("--secret", envvar="KARING_SECRET", default=None, help="Clash API 认证密钥。")
@click.option("--host", default=None, help="API 主机地址（默认: 127.0.0.1）。")
@click.option("--port", default=None, type=int, help="API 端口（默认: 3057）。")
@click.option("--json-output", is_flag=True, default=False, help="以 JSON 格式输出。")
@click.version_option(__version__, prog_name="karing-cli")
@click.pass_context
def cli(ctx, secret, host, port, json_output):
    """karing-cli — 通过 Clash API 管理 Karing VPN 的命令行工具。

    \b
    管理代理节点、测试延迟、监控连接、查询 DNS。
    首次使用请运行 karing-cli guide 查看配置向导。
    """
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    try:
        # 初始化 KaringClient，自动从配置文件读取 host/port/secret
        ctx.obj["client"] = KaringClient(host=host, port=port, secret=secret)
    except Exception as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# STATUS —— 显示 VPN 状态
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def status(ctx):
    """显示 VPN 状态：版本、当前代理组、连接数。"""
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        ver = c.get_version()
        proxies = c.get_proxies()
        configs = c.get_configs()

        if is_json:
            json_output({"version": ver, "configs": configs})
            return

        # 版本信息
        click.secho("Karing VPN Status", bold=True, fg="cyan")
        click.echo(f"  Core Version : {ver.get('version', 'N/A')}")
        click.echo(f"  API Endpoint : {c.base_url}")

        # 遍历所有代理组，找出 Selector/URLTest/Fallback 类型显示当前选中节点
        proxy_data = proxies.get("proxies", {})
        groups = []
        for name, info in proxy_data.items():
            if info.get("type") in ("Selector", "URLTest", "Fallback") and "now" in info:
                groups.append(
                    {"group": name, "type": info["type"], "now": info["now"]})

        if groups:
            click.echo()
            click.secho("  Active Proxy Groups:", bold=True)
            for g in groups:
                click.echo(
                    f"    {g['group']:<30} [{g['type']:<8}] → {g['now']}")

        # 活动连接数
        try:
            conns = c.get_connections()
            count = len(conns.get("connections", []))
            click.echo(f"\n  Active Connections: {count}")
        except Exception:
            pass

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# PROXIES —— 列出代理组和节点
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("group", required=False, default=None)
@click.option("--all", "show_all", is_flag=True, help="显示所有节点（包括非代理组）。")
@click.pass_context
def proxies(ctx, group, show_all):
    """列出代理组和节点。可指定 GROUP 名称查看详情。"""
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        data = c.get_proxies()
        proxy_map = data.get("proxies", {})

        if is_json:
            if group:
                json_output(proxy_map.get(group, {}))
            else:
                json_output(data)
            return

        if group:
            # 显示指定代理组的详情
            info = proxy_map.get(group)
            if not info:
                click.secho(f"代理组 '{group}' 未找到。", fg="red")
                return
            click.secho(f"Group: {group}", bold=True, fg="cyan")
            click.echo(f"  Type    : {info.get('type', 'N/A')}")
            now = info.get("now", "")
            all_nodes = info.get("all", [])
            if not all_nodes and info.get("history"):
                all_nodes = [info.get("name", "")]
            click.echo(
                f"  Current : {click.style(now, fg='green', bold=True)}")
            click.echo(f"  Nodes   : {len(all_nodes)}")
            if all_nodes:
                click.echo()
                for n in all_nodes:
                    # 当前选中节点用绿色圆点标记
                    marker = " ● " if n == now else "   "
                    color = "green" if n == now else None
                    click.echo(f"  {marker}{click.style(n, fg=color)}")
        else:
            # 显示所有代理组概览
            click.secho("Proxy Groups:", bold=True, fg="cyan")
            groups_found = 0
            for name, info in sorted(proxy_map.items()):
                ptype = info.get("type", "")
                if ptype in ("Selector", "URLTest", "Fallback", "LoadBalance"):
                    now = info.get("now", "")
                    all_nodes = info.get("all", [])
                    count = len(all_nodes) if all_nodes else len(
                        info.get("history", []))
                    now_display = click.style(
                        now, fg="green") if now else "N/A"
                    click.echo(
                        f"  {name:<35} [{ptype:<11}] now={now_display}  ({count} nodes)")
                    groups_found += 1

            if show_all:
                click.echo()
                click.secho("All Nodes:", bold=True, fg="cyan")
                for name, info in sorted(proxy_map.items()):
                    ptype = info.get("type", "")
                    if ptype not in ("Selector", "URLTest", "Fallback", "LoadBalance"):
                        click.echo(f"  {name:<35} [{ptype}]")

            if groups_found == 0:
                click.echo("  未找到代理组。")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# SWITCH —— 切换代理节点
# 核心技巧：降级策略处理 URLTest/Fallback 类型
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("group")
@click.argument("node")
@click.option("--config-reload", is_flag=True, default=True, help="URLTest/Fallback 组切换后重载配置。")
@click.pass_context
def switch(ctx, group, node, config_reload):
    """切换代理组中的节点。

    \b
    - Selector 类型：直接使用标准 Clash API
    - URLTest/Fallback：修改 sing-box 配置文件并热重载

    \b
    示例:
      karing-cli switch GLOBAL "🇺🇸 US-Node1"
      karing-cli switch urltest_out "A2 香港6-V2ray-流媒体解锁"
    """
    c = _client(ctx)
    try:
        # 第一步：尝试标准 Clash API（仅 Selector 类型支持）
        c.switch_proxy(group, node)
        click.secho(f"Switched [{group}] → {node}", fg="green", bold=True)
    except KaringAPIError as e:
        err_msg = str(e)
        # 第二步：降级处理 —— URLTest/Fallback 不支持标准 API
        # 报错 "Must be a Selector" 时，改用修改配置文件 + 重载
        if "Must be a Selector" in err_msg or "Resource not found" in err_msg or "not found" in err_msg.lower():
            click.echo(f"  标准切换不支持此组类型，改用配置修改方式...")
            _switch_via_config(c, group, node, config_reload)
        else:
            _handle_error(e)


def _switch_via_config(c, group_tag, node_name, do_reload=True):
    """
    URLTest/Fallback 降级切换：直接修改 sing-box 配置文件并热重载。

    原理：
    1. 读取 service_core.json（sing-box 的完整配置）
    2. 找到目标 outbound 组，修改其 "default" 字段为指定节点
    3. 写回文件
    4. 调用 PUT /configs 让 sing-box 热重载

    这是 Karing 不开放 Selector 切换时的 workaround。
    """
    from .config import KARING_SERVICE_CORE_FILE
    import json as _json

    if not KARING_SERVICE_CORE_FILE.exists():
        click.secho(
            f"配置文件不存在: {KARING_SERVICE_CORE_FILE}", fg="red")
        return

    try:
        with open(KARING_SERVICE_CORE_FILE, "r") as f:
            config = _json.load(f)
    except Exception as e:
        click.secho(f"读取配置失败: {e}", fg="red")
        return

    # 在 outbounds 数组中查找目标组
    outbounds = config.get("outbounds", [])
    found = False
    for ob in outbounds:
        # 精确匹配：tag 名和目标组名一致
        if ob.get("tag") == group_tag and ob.get("type") in ("urltest", "fallback", "selector"):
            ob["default"] = node_name  # 修改默认节点
            found = True
            break

    if not found:
        # 宽泛匹配：在所有组中查找包含该节点的组
        for ob in outbounds:
            if ob.get("type") in ("urltest", "fallback", "selector"):
                node_list = ob.get("outbounds", [])
                if node_name in node_list:
                    ob["default"] = node_name
                    group_tag = ob.get("tag", group_tag)
                    found = True
                    break

    if not found:
        click.secho(
            f"节点 '{node_name}' 未在任何代理组中找到。", fg="red")
        return

    # 写回修改后的配置
    try:
        with open(KARING_SERVICE_CORE_FILE, "w") as f:
            _json.dump(config, f, indent=2, ensure_ascii=False)
        click.echo(f"  已更新 [{group_tag}] default → {node_name}")
    except Exception as e:
        click.secho(f"写入配置失败: {e}", fg="red")
        return

    # 热重载 sing-box 配置
    if do_reload:
        try:
            c.reload_configs(str(KARING_SERVICE_CORE_FILE))
            click.secho(
                f"  配置已重载，已切换到 {node_name}。", fg="green", bold=True)
        except Exception as e:
            click.echo(
                f"  配置已写入但重载可能失败: {e}")
            click.echo(f"  请尝试: karing-cli reset")
    else:
        click.echo(f"  配置已写入。重启 VPN 以生效。")


# # # # # # # # # # # # # # # # # # # # # # # #
# TEST —— 延迟测试
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("name", required=False, default=None)
@click.option("--group", default=None, help="测试指定组的所有节点。")
@click.option("--url", default="https://www.gstatic.com/generate_204", help="测试目标 URL。")
@click.option("--timeout", default=5000, type=int, help="超时毫秒数。")
@click.pass_context
def test(ctx, name, group, url, timeout):
    """测试代理节点延迟。

    \b
    示例:
      karing-cli test "🇺🇸 US-Node1"
      karing-cli test --group "GLOBAL"
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]

    try:
        if name:
            # 测试单个节点
            result = c.get_delay(name, url=url, timeout=timeout)
            if is_json:
                json_output({"name": name, **result})
                return
            delay = result.get("delay", -1)
            display = fmt_delay_display(delay)
            click.echo(f"  {name:<40} {display}")
        elif group:
            # 测试组内所有节点
            data = c.get_proxies()
            info = data.get("proxies", {}).get(group, {})
            all_nodes = info.get("all", [])
            if not all_nodes:
                click.secho(f"组 '{group}' 中没有节点", fg="red")
                return

            click.secho(
                f"Testing {len(all_nodes)} nodes in [{group}]...", fg="cyan")
            results = []
            for node_name in all_nodes:
                try:
                    r = c.get_delay(node_name, url=url, timeout=timeout)
                    delay = r.get("delay", -1)
                except Exception:
                    delay = -1
                results.append((node_name, delay))
                display = fmt_delay_display(delay)
                click.echo(f"  {node_name:<40} {display}")

            if is_json:
                json_output([{"name": n, "delay": d} for n, d in results])

            # 汇总：找出最快节点
            valid = [(n, d) for n, d in results if d > 0]
            if valid:
                best = min(valid, key=lambda x: x[1])
                click.echo(
                    f"\n  Best: {click.style(best[0], fg='green')} ({best[1]}ms)")
        else:
            click.echo(
                "请指定节点名或使用 --group 参数。详见: karing-cli test --help")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# CONNECTIONS —— 活动连接管理
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--close", "close_all", is_flag=True, help="关闭所有连接。")
@click.option("--close-id", default=None, help="关闭指定连接（按 ID）。")
@click.pass_context
def connections(ctx, close_all, close_id):
    """查看或管理活动连接。

    \b
    示例:
      karing-cli connections
      karing-cli connections --close
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        if close_all:
            c.close_connections()
            click.secho("所有连接已关闭。", fg="green")
            return

        if close_id:
            c.close_connection(close_id)
            click.secho(f"连接 {close_id} 已关闭。", fg="green")
            return

        data = c.get_connections()
        conns = data.get("connections", [])
        upload = data.get("uploadTotal", 0)
        download = data.get("downloadTotal", 0)

        if is_json:
            json_output(data)
            return

        click.secho(f"Active Connections: {len(conns)}", bold=True, fg="cyan")
        click.echo(f"  Total Upload   : {fmt_bytes(upload)}")
        click.echo(f"  Total Download : {fmt_bytes(download)}")

        if conns:
            click.echo()
            for conn in conns[:20]:
                meta = conn.get("metadata", {})
                # 代理链：如 [urltest_out, A2 香港6...]
                chains = " → ".join(conn.get("chains", []))
                host = meta.get("host", meta.get("destinationIP", ""))
                port = meta.get("destinationPort", "")
                net = meta.get("network", "")
                click.echo(
                    f"  {conn['id'][:8]}..  {net:<6} {host}:{port}  via [{chains}]")
            if len(conns) > 20:
                click.echo(f"  ... 还有 {len(conns) - 20} 个连接")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# TRAFFIC —— 实时流量（WebSocket）
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--ws-url", is_flag=True, help="仅输出 WebSocket URL。")
@click.pass_context
def traffic(ctx, ws_url):
    """显示实时流量的 WebSocket URL。

    \b
    示例:
      karing-cli traffic --ws-url
    """
    c = _client(ctx)
    url = c.get_traffic_ws_url()
    if ws_url:
        click.echo(url)
        return
    click.echo(f"Traffic WebSocket: {url}")
    click.echo("使用任意 WebSocket 客户端连接此 URL 即可接收实时流量数据。")


# # # # # # # # # # # # # # # # # # # # # # # #
# DNS —— 通过 Karing 进行 DNS 查询
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("domain")
@click.option("--strategy", default="ipv4_only", type=click.Choice(["ipv4_only", "ipv6_only", "prefer_ipv4", "prefer_ipv6"]))
@click.option("--router", is_flag=True, help="使用默认路由（直连）而非代理。")
@click.pass_context
def dns(ctx, domain, strategy, router):
    """通过 Karing 进行 DNS 查询。

    \b
    示例:
      karing-cli dns google.com
      karing-cli dns example.com --strategy ipv6_only
      karing-cli dns example.com --router
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        if router:
            result = c.dns_query_default_router(domain, strategy)
        else:
            result = c.dns_query(domain, strategy)

        if is_json:
            json_output(result)
        else:
            click.secho(f"DNS Query: {domain}", bold=True, fg="cyan")
            if isinstance(result, dict):
                for k, v in result.items():
                    click.echo(f"  {k}: {v}")
            else:
                click.echo(f"  Result: {result}")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# OUTBOUND —— 查询域名的出站路由（Karing 特有）
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("domain")
@click.pass_context
def outbound(ctx, domain):
    """查询域名会走哪条路由规则（Karing 自定义 API）。

    \b
    示例:
      karing-cli outbound google.com   # 查看 google.com 走代理还是直连
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        result = c.outbound_query(domain)
        if is_json:
            json_output(result)
        else:
            click.secho(f"Outbound Query: {domain}", bold=True, fg="cyan")
            if isinstance(result, dict):
                for k, v in result.items():
                    click.echo(f"  {k}: {v}")
            else:
                click.echo(f"  Result: {result}")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# RESET —— 重置网络连接
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def reset(ctx):
    """重置所有连接和出站连接。"""
    c = _client(ctx)
    try:
        c.close_connections()
        click.echo("  已关闭所有连接。")
        try:
            c.reset_outbound_connections()
            click.echo("  已重置出站连接。")
        except Exception:
            pass
        click.secho("网络重置完成。", fg="green")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# BEST —— 自动测速并切换到最快节点
# 这是最实用的命令：一键优化 VPN 速度
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--group", default="GLOBAL", help="测试的代理组（默认: GLOBAL）。")
@click.option("--url", default="https://www.gstatic.com/generate_204", help="测试 URL。")
@click.option("--timeout", default=5000, type=int, help="超时毫秒数。")
@click.option("--no-switch", is_flag=True, help="只测速不切换。")
@click.pass_context
def best(ctx, group, url, timeout, no_switch):
    """测试所有节点并自动切换到最快节点。

    \b
    示例:
      karing-cli best                    # 测速 + 自动切换
      karing-cli best --no-switch        # 只测速
      karing-cli best --group urltest_out
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        # 1. 获取目标组的所有节点列表
        data = c.get_proxies()
        info = data.get("proxies", {}).get(group, {})
        all_nodes = info.get("all", [])

        if not all_nodes:
            click.secho(f"组 '{group}' 中没有节点", fg="red")
            return

        click.secho(
            f"Testing {len(all_nodes)} nodes in [{group}]...", fg="cyan")

        # 2. 逐个测试延迟
        results = []
        for node_name in all_nodes:
            try:
                r = c.get_delay(node_name, url=url, timeout=timeout)
                delay = r.get("delay", -1)
            except Exception:
                delay = -1
            results.append((node_name, delay))

            # 实时显示进度
            display = fmt_delay_display(delay)
            click.echo(f"  {node_name:<40} {display}")

        # 3. 找出最快节点
        valid = [(n, d) for n, d in results if d > 0]
        if not valid:
            click.secho("\n  没有可达节点！", fg="red")
            return

        best_node, best_delay = min(valid, key=lambda x: x[1])
        click.echo(
            f"\n  Best: {click.style(best_node, fg='green', bold=True)} ({best_delay}ms)")

        if is_json:
            json_output({
                "best": best_node,
                "delay_ms": best_delay,
                "all_results": [{"name": n, "delay": d} for n, d in results],
            })

        if no_switch:
            return

        # 4. 切换到最快节点（自动处理 URLTest 降级）
        click.echo()
        try:
            c.switch_proxy(group, best_node)
            click.secho(
                f"Switched [{group}] → {best_node}", fg="green", bold=True)
        except KaringAPIError as e:
            err_msg = str(e)
            if "Must be a Selector" in err_msg or "not found" in err_msg.lower():
                click.echo(
                    f"  标准切换不支持，改用配置修改方式...")
                _switch_via_config(c, group, best_node, True)
            else:
                _handle_error(e)

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# RULES —— 路由规则列表
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def rules(ctx):
    """列出路由规则（分流规则）。"""
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        data = c.get_rules()
        if is_json:
            json_output(data)
            return
        rule_list = data.get("rules", [])
        click.secho(f"Routing Rules: {len(rule_list)}", bold=True, fg="cyan")
        for r in rule_list[:30]:
            ptype = r.get("type", "")
            payload = r.get("payload", "")
            proxy = r.get("proxy", "")
            click.echo(f"  [{ptype:<8}] {payload:<50} → {proxy}")
        if len(rule_list) > 30:
            click.echo(f"  ... 还有 {len(rule_list) - 30} 条规则")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# CONFIG 子命令组 —— 管理 karing-cli 自身配置
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.group("config")
def config_group():
    """管理 karing-cli 配置。"""
    pass


@config_group.command("set-secret")
@click.argument("secret")
def config_set_secret(secret):
    """保存 API Secret。

    \b
    获取 Secret 的方法:
      1. 打开 Karing Dashboard（Zashboard）
      2. 从浏览器 URL 中复制 secret= 后面的值
      3. 运行: karing-cli config set-secret <值>

    \b
    注意：通常不需要手动设置，CLI 会自动从 service.json 发现。
    """
    cfg = load_cli_config()
    cfg["secret"] = secret
    save_cli_config(cfg)
    click.secho(f"Secret 已保存。", fg="green")
    click.echo("验证: karing-cli status")


@config_group.command("show")
def config_show():
    """显示当前 karing-cli 配置。"""
    settings = load_karing_settings()
    secret_val, secret_src = get_secret_source()
    click.secho("karing-cli Configuration:", bold=True, fg="cyan")
    if secret_val:
        # Secret 脱敏显示：只显示前4位和后4位
        masked = secret_val[:4] + "****" + \
            secret_val[-4:] if len(secret_val) > 8 else "●●●●●●"
        click.echo(f"  API Secret     : {masked}  [{secret_src}]")
    else:
        click.echo(
            f"  API Secret     : {click.style('NOT SET', fg='red')}  [{secret_src}]")
    click.echo(f"  Karing Host    : {settings['host']}")
    click.echo(f"  Control Port   : {settings['control_port']}")
    click.echo(f"  Mixed Port     : {settings['mixed_port']}")
    click.echo(f"  Dashboard Port : {settings['html_board_port']}")


@config_group.command("clear-secret")
def config_clear_secret():
    """删除已保存的 API Secret（恢复自动发现模式）。"""
    cfg = load_cli_config()
    cfg.pop("secret", None)
    save_cli_config(cfg)
    click.secho("Secret 已清除。", fg="yellow")


# # # # # # # # # # # # # # # # # # # # # # # #
# GUIDE —— 交互式配置向导
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def guide(ctx):
    """交互式配置向导，引导设置 API Secret。"""
    settings = load_karing_settings()
    click.secho("=" * 60, fg="cyan")
    click.secho("  Karing CLI 配置向导", bold=True, fg="cyan")
    click.secho("=" * 60, fg="cyan")
    click.echo()
    click.echo("使用 karing-cli 需要 API Secret 来认证 Clash API。")
    click.echo("通常 CLI 会自动从 Karing 配置文件中发现 Secret，无需手动设置。")
    click.echo()
    click.secho("方法一：自动发现（推荐）", bold=True, fg="yellow")
    click.echo("  确保 Karing VPN 正在运行，直接执行:")
    click.echo(f"    {click.style('karing-cli status', fg='green')}")
    click.echo()
    click.secho("方法二：手动设置", bold=True, fg="yellow")
    click.echo("  Step 1: 打开 Karing Dashboard")
    click.echo(
        f"    {click.style('open http://127.0.0.1:' + str(settings['html_board_port']), fg='green')}")
    click.echo()
    click.echo("  Step 2: 从浏览器 URL 中复制 secret= 后面的值")
    click.echo(
        f"    URL 示例: http://127.0.0.1:{settings['html_board_port']}/?hostname=127.0.0.1&port={settings['control_port']}&secret={click.style('YOUR_SECRET', fg='green', bold=True)}")
    click.echo()
    click.echo("  Step 3: 保存 Secret")
    click.echo(
        f"    {click.style('karing-cli config set-secret YOUR_SECRET', fg='green')}")
    click.echo()
    click.echo("  或使用环境变量:")
    click.echo(f"    {click.style('export KARING_SECRET=\"YOUR_SECRET\"', fg='green')}")
    click.echo()
    click.secho("=" * 60, fg="cyan")


def main():
    """CLI 入口函数（setup.py 的 console_scripts 指向此函数）。"""
    cli(obj={})


if __name__ == "__main__":
    main()
