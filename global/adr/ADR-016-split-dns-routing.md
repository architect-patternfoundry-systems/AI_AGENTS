# ADR-016: Sovereign Split-DNS Routing Architecture

## Status
Accepted

## Context
The infrastructure requires seamless resolution of both global open internet domain names (e.g., `google.com`) and internal sovereign domain names routed via Tailscale MagicDNS (e.g., `registry-bridge.tailc2cafc.ts.net`).

Initially, Tailscale's global `accept-dns=true` configuration intercepted all host DNS requests, forcing them through `100.100.100.100`. This created a recursive "death loop" with the internal cluster K3s DNS, ultimately breaking global internet connectivity. Disabling `accept-dns` resolved the global internet routing but severed the host's ability to resolve `.ts.net` addresses, completely breaking the local Docker builder's ability to push images to the `registry-bridge`.

## Decision
We will implement a true **Split-DNS routing architecture** natively within the host's `systemd-resolved` system, bypassing Tailscale's global DNS hijacking while retaining its MagicDNS endpoint.

1. Tailscale is configured with `--accept-dns=false` to prevent it from aggressively overtaking the global DNS routing table.
2. A `systemd-resolved` drop-in configuration (`/etc/systemd/resolved.conf.d/10-tailscale-magicdns.conf`) explicitly maps the `.ts.net` routing domain to the Tailscale MagicDNS resolver.
3. The host's `/etc/gai.conf` is modified to prefer IPv4 (`precedence ::ffff:0:0/96 100`) to prevent dual-stack unroutable IPv6 blackholes from triggering `[Errno 101] Network is unreachable` in applications like Python/urllib.

### Implementation Config
`/etc/systemd/resolved.conf.d/10-tailscale-magicdns.conf`
```ini
[Resolve]
DNS=100.100.100.100
Domains=~tailc2cafc.ts.net ~ts.net
```

## Consequences
- **Positive:** Docker and local builds can cleanly push to `registry-bridge.tailc2cafc.ts.net` via 127.0.0.53 without requiring any custom Docker daemon DNS overrides.
- **Positive:** The system can freely communicate with the open internet via standard resilient resolvers (e.g., `8.8.8.8`) without touching Tailscale.
- **Positive:** Unroutable IPv6 connections gracefully fall back to functional IPv4 instead of raising hard Kernel-level `Errno 101` exceptions.
- **Negative:** If the Tailscale MagicDNS IP (`100.100.100.100`) ever changes globally across the Tailnet protocol, this hardcoded drop-in will need to be updated. (Highly unlikely as it is a reserved Tailscale subnet IP).
