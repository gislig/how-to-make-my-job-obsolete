# Azure MCP Server on my own machine (part 2)

The agent in Azure (SRE Agent) has built-in Azure tools for Application Insights, Log Analytics, Azure Monitor and
Resource Graph. Azure MCP Server is the same kind of tool belt for the chat assistant or IDE on *my* machine.

Pinned to the stable release and read-only, with only the namespaces this series needs:

```json
{
  "mcpServers": {
    "azure-mcp-readonly": {
      "command": "npx",
      "args": ["-y", "@azure/mcp@3.0.0", "server", "start", "--read-only",
               "--namespace", "monitor", "--namespace", "resourcehealth",
               "--namespace", "containerapps", "--namespace", "advisor"]
    }
  }
}
```

Checked on 25 Nov 2026:

- `npm view @azure/mcp dist-tags` shows `latest: 4.0.0-beta.10`, so `@latest` is a beta. 3.0.0 is the newest stable.
- `@azure/mcp@3.0.0` needs Node.js 22 or later (`engines.node >=22.0.0`).
- The flags above are in `azmcp server start --help` for 3.0.0.
- Listing tools with MCP Inspector against this exact command returns one tool per namespace (`monitor`,
  `resourcehealth`, `containerapps`, `advisor`) plus `group_list`, `group_resource_list` and `subscription_list`,
  the last three marked `readOnlyHint: true`.

Why not run it inside SRE Agent as a stdio connector? Stdio connectors there run on Node.js 20, and 3.0.0 needs 22.
The agent already has the Azure tools built in, so I don't need it there.
