// Container Apps environment that sends its logs through Azure Monitor diagnostic settings
// (resource-specific tables ContainerAppSystemLogs and ContainerAppConsoleLogs), so no workspace key is needed.

@description('Name prefix for all resources.')
param prefix string

@description('Azure region.')
param location string

@description('Log Analytics workspace resource ID.')
param workspaceId string

@description('Tags for every resource.')
param tags object

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' = {
  name: 'cae-${prefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// 2021-05-01-preview is the newest diagnosticSettings version and the first with categoryGroup and logAnalyticsDestinationType.
#disable-next-line use-recent-api-versions
resource environmentDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: environment
  properties: {
    workspaceId: workspaceId
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output environmentId string = environment.id
output environmentName string = environment.name
