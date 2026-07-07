"""Main CLI entry point for karing-cli."""

import click
import json
import sys
from urllib.parse import quote

from . import __version__
from .client import KaringClient, KaringAPIError
from .config import save_cli_config, load_cli_config, load_karing_settings, get_secret_source


def _client(ctx) -> KaringClient:
    """Get KaringClient from click context."""
    return ctx.obj["client"]


def _handle_error(e):
    """Handle API errors gracefully."""
    if isinstance(e, KaringAPIError):
        click.secho(f"Error: {e}", fg="red", err=True)
    else:
        click.secho(f"Error: {e}", fg="red", err=True)
    sys.exit(1)


def json_output(data, indent=2):
    """Pretty-print JSON."""
    click.echo(json.dumps(data, indent=indent, ensure_ascii=False))


def fmt_bytes(n):
    """Format bytes to human-readable."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_delay_display(delay_ms):
    """Display delay value with color."""
    if delay_ms < 0:
        return click.style("timeout", fg="red")
    elif delay_ms < 300:
        return click.style(f"{delay_ms}ms", fg="green")
    elif delay_ms < 1000:
        return click.style(f"{delay_ms}ms", fg="yellow")
    else:
        return click.style(f"{delay_ms}ms", fg="red")


# # # # # # # # # # # # # # # # # # # # # # # #
# CLI GROUP
# # # # # # # # # # # # # # # # # # # # # # # #

@click.group()
@click.option("--secret", envvar="KARING_SECRET", default=None, help="API secret for Clash API authentication.")
@click.option("--host", default=None, help="API host (default: 127.0.0.1).")
@click.option("--port", default=None, type=int, help="API port (default: 3057).")
@click.option("--json-output", is_flag=True, default=False, help="Output as JSON.")
@click.version_option(__version__, prog_name="karing-cli")
@click.pass_context
def cli(ctx, secret, host, port, json_output):
    """karing-cli — CLI for managing Karing VPN via Clash API.

    Manage proxy nodes, test latency, monitor connections, and
    query DNS through Karing's sing-box Clash-compatible API.

    \b
    Secret setup:
      export KARING_SECRET="your-secret"
      Or: karing-cli config set-secret <secret>
    """
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    try:
        ctx.obj["client"] = KaringClient(host=host, port=port, secret=secret)
    except Exception as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# STATUS
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def status(ctx):
    """Show VPN status: version, current proxy, connections count."""
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        ver = c.get_version()
        proxies = c.get_proxies()
        configs = c.get_configs()

        if is_json:
            json_output({"version": ver, "configs": configs})
            return

        # Version info
        click.secho("Karing VPN Status", bold=True, fg="cyan")
        click.echo(f"  Core Version : {ver.get('version', 'N/A')}")
        click.echo(f"  API Endpoint : {c.base_url}")

        # Current selected proxies per group
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

        # Connection count
        try:
            conns = c.get_connections()
            count = len(conns.get("connections", []))
            click.echo(f"\n  Active Connections: {count}")
        except Exception:
            pass

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# PROXIES
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("group", required=False, default=None)
@click.option("--all", "show_all", is_flag=True, help="Show all proxy nodes (including non-group).")
@click.pass_context
def proxies(ctx, group, show_all):
    """List proxy groups and nodes. Optionally filter by GROUP name."""
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
            info = proxy_map.get(group)
            if not info:
                click.secho(f"Group '{group}' not found.", fg="red")
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
                    marker = " ● " if n == now else "   "
                    color = "green" if n == now else None
                    click.echo(f"  {marker}{click.style(n, fg=color)}")
        else:
            # Show all groups
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
                click.echo("  No proxy groups found.")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# SWITCH
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("group")
@click.argument("node")
@click.option("--config-reload", is_flag=True, default=True, help="Reload config after switching (for URLTest/Fallback groups).")
@click.pass_context
def switch(ctx, group, node, config_reload):
    """Switch proxy node in a GROUP.

    \b
    For Selector groups: uses standard Clash API.
    For URLTest/Fallback: modifies sing-box config and reloads.

    \b
    Examples:
      karing-cli switch GLOBAL "🇺🇸 US-Node1"
      karing-cli switch urltest_out "A2 香港6-V2ray-流媒体解锁"
    """
    c = _client(ctx)
    try:
        # First try standard Clash API (works for Selector groups)
        c.switch_proxy(group, node)
        click.secho(f"Switched [{group}] → {node}", fg="green", bold=True)
    except KaringAPIError as e:
        err_msg = str(e)
        if "Must be a Selector" in err_msg or "Resource not found" in err_msg or "not found" in err_msg.lower():
            # Fallback: modify service_core.json and reload
            click.echo(f"  Standard switch not supported for this group type.")
            click.echo(f"  Modifying sing-box config...")
            _switch_via_config(c, group, node, config_reload)
        else:
            _handle_error(e)


def _switch_via_config(c, group_tag, node_name, do_reload=True):
    """Switch by modifying sing-box config file."""
    from .config import KARING_SERVICE_CORE_FILE
    import json as _json

    if not KARING_SERVICE_CORE_FILE.exists():
        click.secho(
            f"Config file not found: {KARING_SERVICE_CORE_FILE}", fg="red")
        return

    try:
        with open(KARING_SERVICE_CORE_FILE, "r") as f:
            config = _json.load(f)
    except Exception as e:
        click.secho(f"Failed to read config: {e}", fg="red")
        return

    outbounds = config.get("outbounds", [])
    found = False
    for ob in outbounds:
        if ob.get("tag") == group_tag and ob.get("type") in ("urltest", "fallback", "selector"):
            ob["default"] = node_name
            found = True
            break

    if not found:
        # Try all outbound groups
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
            f"Node '{node_name}' not found in any outbound group.", fg="red")
        return

    try:
        with open(KARING_SERVICE_CORE_FILE, "w") as f:
            _json.dump(config, f, indent=2, ensure_ascii=False)
        click.echo(f"  Updated [{group_tag}] default → {node_name}")
    except Exception as e:
        click.secho(f"Failed to write config: {e}", fg="red")
        return

    if do_reload:
        try:
            c.reload_configs(str(KARING_SERVICE_CORE_FILE))
            click.secho(
                f"  Config reloaded. Switched to {node_name}.", fg="green", bold=True)
        except Exception as e:
            click.echo(
                f"  Config written but reload may need VPN restart: {e}")
            click.echo(f"  Try: karing-cli reset")
    else:
        click.echo(f"  Config written. Restart VPN to apply.")


# # # # # # # # # # # # # # # # # # # # # # # #
# TEST (LATENCY)
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("name", required=False, default=None)
@click.option("--group", default=None, help="Test all nodes in a specific group.")
@click.option("--url", default="https://www.gstatic.com/generate_204", help="Test URL.")
@click.option("--timeout", default=5000, type=int, help="Timeout in ms.")
@click.pass_context
def test(ctx, name, group, url, timeout):
    """Test latency for proxy nodes.

    \b
    Examples:
      karing-cli test "🇺🇸 US-Node1"
      karing-cli test --group "Proxy"
      karing-cli test --url "https://speed.cloudflare.com/"
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]

    try:
        if name:
            # Test single node
            result = c.get_delay(name, url=url, timeout=timeout)
            if is_json:
                json_output({"name": name, **result})
                return
            delay = result.get("delay", -1)
            display = fmt_delay_display(delay)
            click.echo(f"  {name:<40} {display}")
        elif group:
            # Test all nodes in a group
            data = c.get_proxies()
            info = data.get("proxies", {}).get(group, {})
            all_nodes = info.get("all", [])
            if not all_nodes:
                click.secho(f"No nodes found in group '{group}'", fg="red")
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

            # Summary
            valid = [(n, d) for n, d in results if d > 0]
            if valid:
                best = min(valid, key=lambda x: x[1])
                click.echo(
                    f"\n  Best: {click.style(best[0], fg='green')} ({best[1]}ms)")
        else:
            click.echo(
                "Specify a node name or use --group. See: karing-cli test --help")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# CONNECTIONS
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--close", "close_all", is_flag=True, help="Close all connections.")
@click.option("--close-id", default=None, help="Close a specific connection by ID.")
@click.pass_context
def connections(ctx, close_all, close_id):
    """List or manage active connections.

    \b
    Examples:
      karing-cli connections
      karing-cli connections --close
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        if close_all:
            c.close_connections()
            click.secho("All connections closed.", fg="green")
            return

        if close_id:
            c.close_connection(close_id)
            click.secho(f"Connection {close_id} closed.", fg="green")
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
                chains = " → ".join(conn.get("chains", []))
                host = meta.get("host", meta.get("destinationIP", ""))
                port = meta.get("destinationPort", "")
                net = meta.get("network", "")
                click.echo(
                    f"  {conn['id'][:8]}..  {net:<6} {host}:{port}  via [{chains}]")
            if len(conns) > 20:
                click.echo(f"  ... and {len(conns) - 20} more")

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# TRAFFIC
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--ws-url", is_flag=True, help="Print WebSocket URL only.")
@click.pass_context
def traffic(ctx, ws_url):
    """Show real-time traffic or WebSocket URL.

    \b
    Examples:
      karing-cli traffic           # Print WS URL
      karing-cli traffic --ws-url
    """
    c = _client(ctx)
    url = c.get_traffic_ws_url()
    if ws_url:
        click.echo(url)
        return
    click.echo(f"Traffic WebSocket: {url}")
    click.echo(
        "Connect with any WebSocket client to receive real-time traffic data.")


# # # # # # # # # # # # # # # # # # # # # # # #
# DNS
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("domain")
@click.option("--strategy", default="ipv4_only", type=click.Choice(["ipv4_only", "ipv6_only", "prefer_ipv4", "prefer_ipv6"]))
@click.option("--router", is_flag=True, help="Use default router instead of proxy.")
@click.pass_context
def dns(ctx, domain, strategy, router):
    """DNS query through Karing.

    \b
    Examples:
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
# OUTBOUND
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.argument("domain")
@click.pass_context
def outbound(ctx, domain):
    """Check outbound routing for a domain (Karing custom API).

    \b
    Examples:
      karing-cli outbound google.com
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
# RESET
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def reset(ctx):
    """Reset all connections and outbound connections."""
    c = _client(ctx)
    try:
        c.close_connections()
        click.echo("  Closed all connections.")
        try:
            c.reset_outbound_connections()
            click.echo("  Reset outbound connections.")
        except Exception:
            pass
        click.secho("Network reset complete.", fg="green")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# BEST — auto-test and switch to fastest node
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.option("--group", default="GLOBAL", help="Group to test (default: GLOBAL).")
@click.option("--url", default="https://www.gstatic.com/generate_204", help="Test URL.")
@click.option("--timeout", default=5000, type=int, help="Timeout in ms.")
@click.option("--no-switch", is_flag=True, help="Only test, don't switch.")
@click.pass_context
def best(ctx, group, url, timeout, no_switch):
    """Test all nodes and switch to the fastest one.

    \b
    Examples:
      karing-cli best                    # Test + auto-switch to fastest
      karing-cli best --no-switch        # Test only, show fastest
      karing-cli best --group urltest_out
    """
    c = _client(ctx)
    is_json = ctx.obj["json_output"]
    try:
        # Get all nodes in the group
        data = c.get_proxies()
        info = data.get("proxies", {}).get(group, {})
        all_nodes = info.get("all", [])

        if not all_nodes:
            click.secho(f"No nodes found in group '{group}'", fg="red")
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

            # Show progress
            display = fmt_delay_display(delay)
            click.echo(f"  {node_name:<40} {display}")

        # Find best
        valid = [(n, d) for n, d in results if d > 0]
        if not valid:
            click.secho("\n  No reachable nodes found!", fg="red")
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

        # Switch to the best node
        click.echo()
        try:
            c.switch_proxy(group, best_node)
            click.secho(
                f"Switched [{group}] → {best_node}", fg="green", bold=True)
        except KaringAPIError as e:
            err_msg = str(e)
            if "Must be a Selector" in err_msg or "not found" in err_msg.lower():
                click.echo(
                    f"  Standard switch not supported. Modifying config...")
                _switch_via_config(c, group, best_node, True)
            else:
                _handle_error(e)

    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# RULES
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def rules(ctx):
    """List routing rules."""
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
            click.echo(f"  ... and {len(rule_list) - 30} more rules")
    except KaringAPIError as e:
        _handle_error(e)


# # # # # # # # # # # # # # # # # # # # # # # #
# CONFIG (sub-group)
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.group("config")
def config_group():
    """Manage karing-cli configuration."""
    pass


@config_group.command("set-secret")
@click.argument("secret")
def config_set_secret(secret):
    """Save API secret for future use.

    \b
    How to get the secret:
      1. Open Karing Dashboard (Zashboard) in browser
      2. Copy the 'secret' parameter from the URL
      3. Run: karing-cli config set-secret <the-secret>
    """
    cfg = load_cli_config()
    cfg["secret"] = secret
    save_cli_config(cfg)
    click.secho(f"Secret saved.", fg="green")
    click.echo("Verify with: karing-cli status")


@config_group.command("show")
def config_show():
    """Show current karing-cli configuration."""
    settings = load_karing_settings()
    secret_val, secret_src = get_secret_source()
    click.secho("karing-cli Configuration:", bold=True, fg="cyan")
    if secret_val:
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
    """Remove saved API secret."""
    cfg = load_cli_config()
    cfg.pop("secret", None)
    save_cli_config(cfg)
    click.secho("Secret cleared.", fg="yellow")


# # # # # # # # # # # # # # # # # # # # # # # #
# GUIDE
# # # # # # # # # # # # # # # # # # # # # # # #

@cli.command()
@click.pass_context
def guide(ctx):
    """Interactive guide to set up API secret."""
    settings = load_karing_settings()
    click.secho("=" * 60, fg="cyan")
    click.secho("  Karing CLI Setup Guide", bold=True, fg="cyan")
    click.secho("=" * 60, fg="cyan")
    click.echo()
    click.echo("To use karing-cli, you need the API secret from Karing.")
    click.echo()
    click.secho("Step 1: Open Karing Dashboard", bold=True, fg="yellow")
    click.echo("  Option A: Open Karing app → click the 'Dashboard' button")
    click.echo("  Option B: Run this command:")
    click.echo(
        f"    {click.style('open http://127.0.0.1:' + str(settings['html_board_port']), fg='green')}")
    click.echo()
    click.secho("Step 2: Get the secret from URL", bold=True, fg="yellow")
    click.echo("  The dashboard URL looks like:")
    click.echo(
        f"    http://127.0.0.1:{settings['html_board_port']}/?hostname=127.0.0.1&port={settings['control_port']}&secret={click.style('YOUR_SECRET_HERE', fg='green', bold=True)}")
    click.echo()
    click.echo("  Copy the value after 'secret=' in the URL.")
    click.echo()
    click.secho("Step 3: Save the secret", bold=True, fg="yellow")
    click.echo("  Run one of these commands:")
    click.echo()
    click.echo("  Method 1 (save permanently):")
    click.echo(
        f"    {click.style('karing-cli config set-secret YOUR_SECRET_HERE', fg='green')}")
    click.echo()
    click.echo("  Method 2 (use environment variable):")
    click.echo(f"    {click.style('export KARING_SECRET=\"YOUR_SECRET_HERE\"', fg='green')}")
    click.echo()
    click.secho("Step 4: Verify", bold=True, fg="yellow")
    click.echo(f"  {click.style('karing-cli status', fg='green')}")
    click.echo()
    click.secho("=" * 60, fg="cyan")


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
