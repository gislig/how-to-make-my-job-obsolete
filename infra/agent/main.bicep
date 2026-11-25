// Part 2: hire the agent. Azure SRE Agent with its own identity, least privilege on the workload resource group,
// Review mode, and its audit trail in the same Log Analytics workspace as everything else.
// Deploy into the workload resource group created in part 1.

targetScope = 'resourceGroup'

import { builtInRoles } from '../types/roles.bicep'

@description('Short name prefix, same as part 1.')
@minLength(3)
@maxLength(20)
param prefix string

@description('Region for the agent. Must be a region where Azure SRE Agent is offered. Check the region list in the portal before you deploy.')
param location string = resourceGroup().location

@description('Agent name. Letters, digits and hyphens, starting with a letter.')
@minLength(2)
@maxLength(32)
param agentName string = 'sre-${prefix}'

@description('Log Analytics workspace from part 1 (the agent App Insights writes to it, so AppEvents holds the agent audit trail).')
param workspaceName string = 'log-${prefix}'

@description('Container app the agent looks after (from part 1).')
param containerAppName string = 'ca-${prefix}-web'

@description('Review = the agent proposes, an SRE Agent Administrator approves. Start here. Autonomous = it acts.')
@allowed([
  'Review'
  'Autonomous'
])
param actionMode string = 'Review'

@description('Low = Reader-type permissions. High would add Contributor; this series never uses it.')
@allowed([
  'Low'
])
param accessLevel string = 'Low'

@description('Give the agent identity Container Apps Contributor on the ONE container app, so it can change scale settings (still subject to Review mode). Part 4 replaces this with the bounded MCP tool.')
param grantScaleWrite bool = false

@description('Object ID of the person or group that administers the agent. Defaults to whoever deploys.')
param adminPrincipalId string = deployer().objectId

@allowed([
  'User'
  'Group'
])
param adminPrincipalType string = 'User'

@allowed([
  'Stable'
  'Preview'
])
param upgradeChannel string = 'Stable'

param tags object = {
  workload: prefix
  series: 'how-to-make-my-job-obsolete'
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' existing = {
  name: workspaceName
}

resource app 'Microsoft.App/containerApps@2026-01-01' existing = {
  name: containerAppName
}

// Dedicated Application Insights for the agent's own telemetry, workspace-based, so the agent audit events
// (customEvents) land in the same workspace as AppEvents. Same pattern as the microsoft/sre-agent templates.
resource agentInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}-agent'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-${prefix}-agent'
  location: location
  tags: tags
}

// The job description, in RBAC: read everything in this resource group, query logs and metrics. Nothing else.
var readRoles = [
  builtInRoles.reader
  builtInRoles.monitoringReader
  builtInRoles.logAnalyticsReader
]

module identityRoles '../modules/rg-roles.bicep' = {
  name: 'agent-uami-roles'
  params: {
    principalId: identity.properties.principalId
    roleIds: readRoles
  }
}

resource agent 'Microsoft.App/agents@2026-01-01' = {
  name: agentName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    upgradeChannel: upgradeChannel
    actionConfiguration: {
      accessLevel: accessLevel
      identity: identity.id
      mode: actionMode
    }
    knowledgeGraphConfiguration: {
      identity: identity.id
      managedResources: [
        resourceGroup().id
      ]
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: agentInsights.properties.AppId
        connectionString: agentInsights.properties.ConnectionString
      }
    }
  }
  dependsOn: [
    identityRoles
  ]
}

// The system-assigned identity gets the same read roles (the microsoft/sre-agent templates do the same).
module systemIdentityRoles '../modules/rg-roles.bicep' = {
  name: 'agent-smi-roles'
  params: {
    principalId: agent.identity.principalId
    roleIds: readRoles
  }
}

// Optional and narrow: change ONE container app, nothing else.
resource scaleWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantScaleWrite) {
  name: guid(app.id, identity.id, builtInRoles.containerAppsContributor)
  scope: app
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles.containerAppsContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Who may approve the agent's proposals in Review mode.
resource admin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agent.id, adminPrincipalId, builtInRoles.sreAgentAdministrator)
  scope: agent
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles.sreAgentAdministrator)
    principalId: adminPrincipalId
    principalType: adminPrincipalType
  }
}

output agentId string = agent.id
output agentName string = agent.name
output identityId string = identity.id
output identityPrincipalId string = identity.properties.principalId
output agentInsightsId string = agentInsights.id
