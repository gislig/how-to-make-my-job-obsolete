# Azure AI Ops Agent

Code for my blog series **"Obsolete by Design: Building an AI Agent That Runs Your Azure Infrastructure"** on
[gisli78.substack.com](https://gisli78.substack.com). The series builds, one part at a time, an AI agent that does the
day-to-day work of an Azure infrastructure specialist: it provisions with Bicep, watches a monitoring baseline,
scales services within agreed limits, proposes changes as pull requests, and leaves an audit trail for every decision.

Author: **Gísli Guðmundsson**, Microsoft MVP, Iceland.

> Status: parts 1 and 2. Validated with `bicep build`, `bicep lint` and `bicep build-params` (Bicep 0.48.1).
> Not yet deployed by me in a live subscription from this repo. Run `what-if` first.

## What's here

| Path | Part | What it is |
|---|---|---|
| `docs/architecture.md` | 1 | The layers (desired state, reflexes, senses, judgment, guardrails, accountability) and design rules |
| `agent/job-description.md` | 1 | The agent's instructions, written as a job description |
| `agent/guardrails.md` | 1 | Guardrail intent: tool access policy patterns, RBAC, run modes |
| `infra/types/contract.bicep` | 1 | The **operating contract** as an exported Bicep type, plus a function that turns it into `aiops-*` tags |
| `infra/main.bicep` | 2 | Foundation: Log Analytics, Application Insights, Container Apps environment, sample workload, baseline alerts |
| `infra/modules/baseline-alerts.bicep` | 2 | Dynamic-threshold alerts (requests, CPU, memory, scaling churn) and static guardrails (replica ceiling, 5xx) |
| `queries/*.kql` | 2 | Hour-of-week baseline, anomaly decomposition, replica timeline, KEDA events, agent audit |
| `scripts/deploy-stack.sh` | 2 | Deploys the foundation as a deployment stack with `denyDelete` |
| `scripts/what-if.sh`, `scripts/validate.sh`, `scripts/load.sh` | 2 | Preview, validate, generate load |
| `scripts/kql-check/` | 2 | Parses the KQL files with Kusto.Language |

## Quick start (part 2)

```bash
az group create -n rg-aiops-demo -l swedencentral
./scripts/validate.sh
./scripts/what-if.sh rg-aiops-demo
./scripts/deploy-stack.sh rg-aiops-demo <platform-team-group-object-id>
./scripts/load.sh "$(az stack group show -n aiops-foundation -g rg-aiops-demo --query outputs.appUrl.value -o tsv)" 300 200
```

Requirements: Azure CLI 2.61.0 or later (deployment stacks), Bicep CLI, and Owner or
Contributor + Azure Deployment Stack Owner on the resource group (to create deny settings).

## The operating contract

Every workload the agent manages carries its boundaries as tags:

| Tag | Meaning |
|---|---|
| `aiops-managed` | `true` when the agent may operate the resource |
| `aiops-owner` | Who the agent escalates to |
| `aiops-min-replicas` / `aiops-max-replicas` | The only range the agent may move replicas in |
| `aiops-change-mode` | `review` (propose, human approves) or `autonomous` (act, then report) |
| `aiops-tier` | `prod` or `nonprod` |
| `aiops-slo-p95-ms` | Latency objective to protect (0 = none) |
| `aiops-budget-eur` | Monthly cost ceiling (0 = none) |

## Series

1. Hiring an AI infrastructure engineer: the vision and architecture
2. The foundation: Bicep, deployment stacks and a monitoring baseline the agent can trust
3. Onboarding the employee: Azure SRE Agent with Bicep, identity and Review mode
4. A tool belt with guardrails: a self-hosted Azure MCP Server for the agent
5. Scale by evidence: letting the agent tune autoscale from the baseline
6. Changes through code: the agent opens pull requests, what-if and deployment stacks apply them
7. Securing the AI management agent: identity, least privilege, hooks, policy and audit
8. The timeline page: what scaled, when, why, with links to the evidence

## License

MIT
