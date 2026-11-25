// The operating contract: what the AI ops agent is allowed to do with a workload.
// Every workload the agent manages carries this contract as tags, so the agent
// (and Azure Policy, and humans) can read the boundaries straight from the resource.

@export()
@description('Boundaries the AI ops agent must stay inside for one workload.')
type operatingContract = {
  @description('Team or person accountable for the workload. The agent escalates here.')
  owner: string

  @description('Lowest replica count the agent may set. 0 allows scale to zero.')
  @minValue(0)
  @maxValue(1000)
  minReplicas: int

  @description('Highest replica count the agent may set. Hitting this is an alert, not a reason to raise it silently.')
  @minValue(1)
  @maxValue(1000)
  maxReplicas: int

  @description('review = the agent proposes and a human approves. autonomous = the agent acts and reports.')
  changeMode: 'review' | 'autonomous'

  @description('Environment tier. Production defaults to review in every response plan.')
  tier: 'prod' | 'nonprod'

  @description('Optional latency objective (p95, milliseconds) the agent should protect.')
  sloP95Ms: int?

  @description('Optional monthly cost ceiling in EUR the agent must not plan beyond.')
  monthlyBudgetEur: int?
}

@export()
@description('Turns a contract into resource tags. Tag values must be strings.')
func contractTags(contract operatingContract) object => {
  'aiops-managed': 'true'
  'aiops-owner': contract.owner
  'aiops-min-replicas': string(contract.minReplicas)
  'aiops-max-replicas': string(contract.maxReplicas)
  'aiops-change-mode': contract.changeMode
  'aiops-tier': contract.tier
  'aiops-slo-p95-ms': string(contract.?sloP95Ms ?? 0)
  'aiops-budget-eur': string(contract.?monthlyBudgetEur ?? 0)
}
