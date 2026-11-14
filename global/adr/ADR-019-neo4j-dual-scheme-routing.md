# ADR-019: Neo4j Dual-Scheme Connection Routing

## Status
Accepted

## Context
In our sovereign infrastructure cluster, Neo4j is deployed as a core stateful database service. To balance access across development environments and production GitOps environments:
1. **Production / Cluster-Internal:** Services communicate over Kubernetes Internal DNS (e.g., `bolt://neo4j.infra-data.svc.cluster.local:7687`) inside the Home Lab.
2. **Development / Remote / Tailscale:** Developers work on local workstations and connect via port-forwards or Tailscale tunnel endpoints (e.g., `bolt.tailc2cafc.ts.net:443`).

Because the Tailscale endpoints terminate TLS with self-signed certificates or specific domain certs that are not automatically trusted by default system trust stores, standard Python driver connections with `bolt://` or `neo4j://` protocols fail with verification errors. To resolve this, developers use the `bolt+ssc://` (Bolt with Self-Signed Certificate) protocol scheme for secure remote TLS validation bypass.

Historically, this required developers to manually edit connection strings in configuration files when moving between environments, which violates the **Rule of Environment Parity** (maintaining identical configuration properties across development and production).

## Decision
We establish a **Dual-Scheme Connection Routing Protocol** in `GraphService` to dynamically negotiate and fallback between standard internal DNS (`bolt://`) and remote Tailscale secure routing (`bolt+ssc://`).

1. **Protocol Negotiation:** The driver initialization attempts standard protocol URI parsing from the `NEO4J_URI` configuration.
2. **Fallback Scheme Transformation:** If connection or handshake failure occurs under one protocol scheme, the `GraphService` will automatically toggle/rewrite the scheme (e.g., rewriting `bolt://` to `bolt+ssc://` and vice-versa) and retry the connection handshake before raising a runtime exception.
3. **Environment Parity Preservation:** This ensures the *same* environment variable configuration is portable across internal cluster pods and remote development environments without human intervention.

## Consequences
- **Positive:** Standardizes remote Tailscale access while maintaining secure production service-to-service connections in the cluster.
- **Positive:** Enforces the Sovereign Constitution's Rule of Environment Parity by using identical ConfigMaps and Secrets in development and production.
- **Negative:** Dual connection handshakes can add up to 2 seconds of startup overhead during fallbacks (mitigated by persistent connection pooling in `GraphService`).
