# Talk to the environment from a chat assistant (part 4)

After `scripts/deploy-mcp.sh` you have:

- **URL:** `https://ca-<prefix>-mcp.<environment default domain>/mcp` (Streamable HTTP)
- **Two API keys:** one for Grok Bot, one for SRE Agent. Each is at least 32 characters.
- **Header:** `Authorization: Bearer <key>` (or `X-API-Key: <key>`)

## Grok Bot

Ask Grok Bot to add a custom MCP connector with the URL above and the header
`Authorization: Bearer <grokbot key>`. Grok Bot adds remote MCP servers by URL with auth headers.
Then ask it things like:

- "What's the status of ca-aiops-demo-web?"
- "Why did it scale out this morning?" (`get_scaling_timeline`)
- "What does a normal Monday 09:00 look like?" (`get_baseline`)
- "What changed in the resource group today?" (`get_recent_changes`)
- "Pre-warm to 4 replicas for the 09:00 peak." (`set_scale_range`, dry run first)

## Azure SRE Agent

Add an MCP connector in the agent portal (see "Connect an MCP server directly" in
[MCP connectors](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)): transport **Streamable-HTTP**, the URL
above, and a Bearer token (the sre-agent key). After it connects, the **Select tools** step lets you pick which tools
the agent sees. Name the connection `infra-agent`; tools are registered with the connection name as a prefix,
which is what the tool access policy in `agent/guardrails.md` expects. Check the exact names in the tool list.

## Any MCP client (testing)

```bash
npx @modelcontextprotocol/inspector --cli https://<fqdn>/mcp --transport http \
  --method tools/list --header "Authorization: Bearer <key>"
```

## Why an API key and not Entra ID OAuth

- Grok Bot and SRE Agent both support a static header on a remote MCP server.
- Entra ID doesn't publish an RFC 7591 registration endpoint, so an Entra-protected MCP server can't use dynamic
  client registration. The other options are a pre-registered client ID (not possible for a third-party chat app)
  or a Client ID Metadata Document, which Entra supports in preview only.
- So: a long random key per client, stored as a Container Apps secret, compared in constant time, rotated per
  client, and every call audited with the client name. Optionally restrict the ingress to known IP ranges
  (`allowedIpRanges`).
