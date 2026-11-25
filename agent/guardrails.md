# Guardrails (part 3)

Every rule below uses only syntax and tool names documented in
[Tool access policies in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/tool-access-policies)
and [MCP connectors](https://learn.microsoft.com/azure/sre-agent/mcp-connectors) (checked 25 Nov 2026).

## Global tool access policy

Set it in the portal (**Build + setup > Extensions > Tools > Advanced permissions**) or with the documented API body:

```json
{
  "permissions": {
    "allow": ["RunAzCliReadCommands"],
    "ask":   ["RunAzCliWriteCommands", "infra-agent_set_scale_range"],
    "deny":  ["bash(az * delete *)", "RunKubectlWriteCommand(kubectl delete *)"]
  }
}
```

- `infra-agent_set_scale_range`: MCP tools are registered as `<connection name>_<tool>`, so this assumes you named
  the connection `infra-agent`. Check the name in your agent's tool list.
- Only the global scope can deny. Custom-agent and thread scopes can only add allow rules.
- Evaluation order: hooks, then tool access policies, then default approval, then run mode.
- A user-defined hook that returns allow overrides a global deny (audit-logged). Only SRE Agent Administrators can
  create hooks, so keep that role to a small group.

## The layers that apply whatever the agent decides

1. **RBAC.** The agent identities hold Reader, Monitoring Reader and Log Analytics Reader on one resource group.
   Optional Container Apps Contributor on one app only (`grantScaleWrite`). See `infra/agent/main.bicep`.
2. **Run mode.** Review. Only SRE Agent Administrators approve.
3. **The bounded tool.** `set_scale_range` in the MCP server refuses anything outside the `aiops-*` contract, caps
   the step size, requires a reason, and only writes when the server has `ALLOW_WRITES=true` and the contract's
   effective mode is autonomous (production is always review).
4. **Azure Policy.** `infra/governance/contract-policy.bicep`: agent-managed apps must carry a valid contract and
   production can't be autonomous.
5. **Deployment stacks.** `denyDelete` on everything each part deploys, including the agent and its identity.
6. **Audit.** SRE Agent events (`AgentToolExecution`, `AgentAzCliExecution`, `ApprovalDecision`) and the MCP
   server's `McpToolCall` / `McpScaleDecision` land in the same workspace (`AppEvents`), next to `AzureActivity`.
