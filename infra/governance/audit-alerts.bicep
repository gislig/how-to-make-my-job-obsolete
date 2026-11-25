// Part 3: two alerts that watch the watcher.
//  1. Every successful-or-started write to a container app in this resource group, with the caller as a dimension.
//     A change you did not expect is the first thing to look at.
//  2. The MCP server rejected a scale change (someone or something tried to leave the contract).

@description('Short name prefix, same as part 1.')
param prefix string

@description('Region of the workspace (log search alerts are regional).')
param location string = resourceGroup().location

@description('Log Analytics workspace resource ID from part 1.')
param workspaceId string

@description('Action group resource ID from part 1.')
param actionGroupId string

param tags object = {
  workload: prefix
  series: 'how-to-make-my-job-obsolete'
}

var rules = [
  {
    name: 'containerapp-writes'
    displayName: 'Container app changed (who did it?)'
    description: 'A write operation on a container app in ${resourceGroup().name}. Caller is a dimension, so each writer gets its own alert.'
    severity: 3
    query: 'AzureActivity | where OperationNameValue =~ "Microsoft.App/containerApps/write" | where ResourceGroup =~ "${resourceGroup().name}" | project TimeGenerated, Caller, _ResourceId'
    dimension: 'Caller'
  }
  {
    name: 'mcp-scale-rejected'
    displayName: 'MCP server rejected a scale change outside the contract'
    description: 'set_scale_range was called with values outside the operating contract.'
    severity: 2
    query: 'AppEvents | where Name == "McpScaleDecision" | extend decision = tostring(Properties.decision), client = tostring(Properties.client) | where decision == "rejected" | project TimeGenerated, client'
    dimension: 'client'
  }
]

resource alerts 'Microsoft.Insights/scheduledQueryRules@2026-03-01' = [for rule in rules: {
  name: 'sqr-${prefix}-${rule.name}'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: rule.displayName
    description: rule.description
    severity: rule.severity
    enabled: true
    scopes: [
      workspaceId
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    // The tables only exist once the first rows arrive (Activity Log export, first MCP decision).
    skipQueryValidation: true
    autoMitigate: false
    criteria: {
      allOf: [
        {
          query: rule.query
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          dimensions: [
            {
              name: rule.dimension
              operator: 'Include'
              values: [
                '*'
              ]
            }
          ]
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroupId
      ]
    }
  }
}]

output alertIds string[] = [for (rule, i) in rules: alerts[i].id]
