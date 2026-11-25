# Architecture: an AI ops agent that runs Azure infrastructure

Part 1 of the series. Everything here maps to an Azure service that exists today (checked against Microsoft Learn, November 2026).

```mermaid
flowchart LR
  subgraph Desired["Desired state (what should exist)"]
    Git["Git repo<br/>Bicep + operating contract"] --> Stack["Deployment stack<br/>deny settings"]
    Policy["Azure Policy"]
  end
  subgraph Run["Running platform"]
    App["Container Apps / AKS / VMSS"]
    Reflex["Reflexes: KEDA scale rules,<br/>HPA, autoscale"]
    Reflex --> App
  end
  subgraph Senses["Senses"]
    LA["Log Analytics + App Insights"]
    Alerts["Dynamic-threshold + guardrail alerts"]
    LA --> Alerts
  end
  subgraph Brain["Judgment: the AI employee"]
    SRE["Azure SRE Agent<br/>(or Foundry Agent Service agent)"]
    MCP["Azure MCP Server<br/>(self-hosted, read-only by default)"]
    SRE --> MCP
  end
  subgraph Guard["Guardrails + accountability"]
    Id["Managed identity / Entra Agent ID<br/>least-privilege RBAC"]
    Tools["Run modes, tool access policies, hooks"]
    Audit["Audit: customEvents, Activity Log"]
    Timeline["Timeline page:<br/>what scaled, when, why"]
  end
  App --> LA
  Alerts --> SRE
  SRE -- "PR with Bicep change" --> Git
  SRE -- "bounded runtime change<br/>(within the contract)" --> App
  Stack --> App
  Policy --> App
  Id --- SRE
  Tools --- SRE
  SRE --> Audit --> Timeline
  LA --> Timeline
```

## The layers

| Layer | Job | Azure services | Who acts |
|---|---|---|---|
| Desired state | Define what should exist and protect it | Bicep, deployment stacks (deny settings), Azure Policy | Pipeline, and the agent through pull requests |
| Reflexes | React to load in seconds, deterministically | Container Apps scale rules (KEDA), AKS HPA and cluster autoscaler, Azure Monitor autoscale | The platform. No AI in the hot path |
| Senses | Know what normal looks like and notice when it isn't | Log Analytics, Application Insights, dynamic-threshold alerts, Azure Copilot Observability Agent | Azure Monitor |
| Judgment | Investigate, decide, change the rules the reflexes work within | Azure SRE Agent, or a custom agent on Foundry Agent Service, with Azure MCP Server as the tool belt | The AI agent |
| Guardrails | Limit what the agent can do and prove what it did | Managed identity, Entra Agent ID, RBAC, run modes, tool access policies, hooks, deny settings | Platform team (once), then automatic |
| Accountability | Show every scale event and every agent decision with evidence | App Insights `customEvents`, Activity Log, AzureMetrics, a timeline page | Anyone |

## Design rules

1. **Reflexes stay deterministic.** The agent never sits in the request path and never replaces KEDA or HPA. It changes the bounds and rules they work within.
2. **The contract lives on the resource.** Every managed workload carries `aiops-*` tags (min/max replicas, change mode, owner, SLO, budget). See `infra/types/contract.bicep`.
3. **Code is the source of truth.** Permanent changes go through a pull request against the Bicep. Runtime changes are allowed only inside the contract and get written back to code.
4. **Read-only first.** The agent's identity starts with Reader-level roles and Review mode. Autonomy is earned per task, not granted per agent.
5. **Every action leaves evidence.** If it isn't in the audit trail and on the timeline, it didn't happen.
