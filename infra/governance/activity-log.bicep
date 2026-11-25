// Part 3: send the subscription Activity Log to the workspace (AzureActivity table), so every control-plane write
// (by a human, a pipeline, the SRE Agent or the MCP server identity) is queryable next to the agent's own audit events.

targetScope = 'subscription'

@description('Log Analytics workspace resource ID from part 1.')
param workspaceId string

// 2021-05-01-preview is the newest diagnosticSettings version.
#disable-next-line use-recent-api-versions
resource activityLog 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'activity-to-log-analytics'
  properties: {
    workspaceId: workspaceId
    logs: [for category in [
      'Administrative'
      'Security'
      'Policy'
      'Alert'
      'Autoscale'
      'ResourceHealth'
    ]: {
      category: category
      enabled: true
    }]
  }
}
