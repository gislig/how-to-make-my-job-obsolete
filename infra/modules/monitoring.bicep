// The agent's senses: one Log Analytics workspace, workspace-based Application Insights
// and an action group for the humans who still want an email.

@description('Name prefix for all resources.')
param prefix string

@description('Azure region.')
param location string

@description('Log Analytics retention in days. The dynamic-threshold models look at 10 days to 3 weeks of history, keep more than that.')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

@description('Email addresses that get alert notifications. Leave empty to rely on the agent and the portal only.')
param alertEmails string[] = []

@description('Tags for every resource.')
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: 'log-${prefix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    features: {
      // Access to logs follows resource RBAC, so the agent's identity only sees what it is allowed to see.
      enableLogAccessUsingOnlyResourcePermissions: true
      // Entra ID only, no workspace keys.
      disableLocalAuth: true
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: take('aiops${uniqueString(prefix)}', 12)
    enabled: true
    emailReceivers: [for (email, i) in alertEmails: {
      name: 'email-${i}'
      emailAddress: email
      useCommonAlertSchema: true
    }]
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output workspaceCustomerId string = workspace.properties.customerId
output appInsightsName string = appInsights.name
output appInsightsId string = appInsights.id
output actionGroupId string = actionGroup.id
