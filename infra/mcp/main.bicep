// Part 4: the custom MCP server that lets you talk to the environment from a chat assistant.
// Two-step deployment (see scripts/deploy-mcp.sh):
//   1. deployApp=false  -> registry, identity and roles.
//   2. az acr build      -> image in the registry, built in Azure (no local Docker needed).
//   3. deployApp=true   -> the container app with Streamable HTTP at https://<fqdn>/mcp.

targetScope = 'resourceGroup'

import { builtInRoles } from '../types/roles.bicep'

@description('Short name prefix, same as part 1.')
@minLength(3)
@maxLength(20)
param prefix string

param location string = resourceGroup().location

@description('Deploy the container app. False for the first run, before the image exists.')
param deployApp bool = false

@description('Image tag built with az acr build.')
param imageTag string = '1.0.0'

@description('API keys as "client:key" pairs, comma separated, each key at least 32 characters. Example: grokbot:<key>,sre-agent:<key2>')
@secure()
param apiKeys string = ''

@description('Let set_scale_range actually change the app (still only inside the contract and only in autonomous mode). Also grants Container Apps Contributor on the target app.')
param allowWrites bool = false

@description('Largest change in replicas per call to set_scale_range.')
@minValue(1)
param maxStep int = 5

@description('Optional client IP ranges allowed to reach the MCP endpoint (CIDR). Empty = open to the internet, protected by the API key.')
param allowedIpRanges string[] = []

@description('Minimum replicas for the MCP server. 0 saves money; the first call after idle then waits for a cold start.')
@minValue(0)
param minReplicas int = 0

param environmentName string = 'cae-${prefix}'
param workspaceName string = 'log-${prefix}'
param appInsightsName string = 'appi-${prefix}'
param targetAppName string = 'ca-${prefix}-web'

param tags object = {
  workload: prefix
  series: 'how-to-make-my-job-obsolete'
}

resource environment 'Microsoft.App/managedEnvironments@2026-01-01' existing = {
  name: environmentName
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' existing = {
  name: workspaceName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource targetApp 'Microsoft.App/containerApps@2026-01-01' existing = {
  name: targetAppName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: 'acr${uniqueString(resourceGroup().id, prefix)}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-${prefix}-mcp'
  location: location
  tags: tags
}

// Read the resource group: app config, metrics, alerts (Reader + Monitoring Reader), logs (Log Analytics Reader).
module readRoles '../modules/rg-roles.bicep' = {
  name: 'mcp-read-roles'
  params: {
    principalId: identity.properties.principalId
    roleIds: [
      builtInRoles.reader
      builtInRoles.monitoringReader
      builtInRoles.logAnalyticsReader
    ]
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, builtInRoles.acrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles.acrPull)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Audit events go to Application Insights with Entra ID auth (local auth is disabled on it in part 1).
resource telemetryPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, builtInRoles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles.monitoringMetricsPublisher)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// The only write permission, scoped to the one app, and only when writes are switched on.
resource scaleWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (allowWrites) {
  name: guid(targetApp.id, identity.id, builtInRoles.containerAppsContributor)
  scope: targetApp
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', builtInRoles.containerAppsContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

var appName = 'ca-${prefix}-mcp'
// Container app FQDN = <app name>.<environment default domain>. Used for the MCP DNS-rebinding host check.
var fqdn = '${appName}.${environment.properties.defaultDomain}'

resource mcp 'Microsoft.App/containerApps@2026-01-01' = if (deployApp) {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: [
        {
          name: 'mcp-api-keys'
          value: apiKeys
        }
      ]
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        ipSecurityRestrictions: [for (cidr, i) in allowedIpRanges: {
          name: 'allow-${i}'
          action: 'Allow'
          ipAddressRange: cidr
        }]
      }
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: '${registry.properties.loginServer}/infra-agent-mcp:${imageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
            { name: 'AIOPS_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'LOG_ANALYTICS_WORKSPACE_ID', value: workspace.properties.customerId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'MCP_API_KEYS', secretRef: 'mcp-api-keys' }
            { name: 'MCP_ALLOWED_HOSTS', value: fqdn }
            { name: 'ALLOW_WRITES', value: string(allowWrites) }
            { name: 'MAX_STEP', value: string(maxStep) }
            { name: 'PORT', value: '8000' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
              }
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    readRoles
    acrPull
    telemetryPublisher
  ]
}

output registryName string = registry.name
output registryLoginServer string = registry.properties.loginServer
output identityPrincipalId string = identity.properties.principalId
output mcpUrl string = 'https://${fqdn}/mcp'
