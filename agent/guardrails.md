# Guardrail intent for the agent (draft)

Part 1 lists the intent. Parts 3 and 7 turn it into configuration. Patterns below use the glob syntax from
[Tool access policies in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/tool-access-policies).
Verify the runtime tool names in your own agent before applying them.

| Scope | Rule | Pattern (example) | Why |
|---|---|---|---|
| Global | Deny | `bash(az * delete *)` | The agent never deletes anything |
| Global | Deny | `bash(az role *)` | No RBAC changes |
| Global | Deny | `bash(az keyvault *)` | No secrets |
| Global | Ask | `RunAzCliWriteCommands` | Every Azure CLI write needs approval in Review mode |
| Global | Allow | `RunKubectlReadCommand(kubectl get *)` | Reads never need approval |

Other layers that apply regardless of these rules:

- **RBAC.** The identity only holds the roles listed in `infra` (Reader, Monitoring Reader, Log Analytics Reader to start).
- **Run mode.** Review for anything tagged `aiops-tier=prod`.
- **Deployment stack deny settings.** `denyDelete` on everything the stack manages.
- **Hooks.** A PreToolUse hook that reads the `aiops-*` tags and denies any replica change outside the contract (part 7).
- **Audit.** Every tool call is logged as `AgentToolExecution` in Application Insights `customEvents`.
