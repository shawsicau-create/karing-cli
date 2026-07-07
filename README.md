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
