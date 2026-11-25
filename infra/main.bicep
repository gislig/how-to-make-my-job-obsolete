// Part 2 of the series: the foundation the AI ops agent stands on.
// Deploy this as a deployment stack (see scripts/deploy-stack.sh) so the platform owns it as one unit.

targetScope = 'resourceGroup'

import { operatingContract } from 'types/contract.bicep'

@description('Short name prefix, for example aiops-demo.')
@minLength(3)
@maxLength(20)
param prefix string

@description('Azure region. Pick one where Azure SRE Agent is offered if you want the agent in the same region (for example swedencentral).')
param location string = resourceGroup().location

@description('Operating contract for the sample workload.')
param contract operatingContract

@description('Email addresses for alert notifications.')
param alertEmails string[] = []

@description('Log Analytics retention in days.')
param retentionInDays int = 30

@description('Container image for the sample workload.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

var tags = {
  workload: prefix
  'managed-by': 'bicep-deployment-stack'
  series: 'azure-ai-ops-agent'
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    prefix: prefix
    location: location
    retentionInDays: retentionInDays
    alertEmails: alertEmails
    tags: tags
  }
}

module containerEnv 'modules/container-env.bicep' = {
  name: 'container-env'
  params: {
    prefix: prefix
    location: location
    workspaceId: monitoring.outputs.workspaceId
    tags: tags
  }
}

module workload 'modules/workload.bicep' = {
  name: 'workload'
  params: {
    name: 'ca-${prefix}-web'
    location: location
    environmentId: containerEnv.outputs.environmentId
    workspaceId: monitoring.outputs.workspaceId
    image: image
    contract: contract
    tags: tags
  }
}

module alerts 'modules/baseline-alerts.bicep' = {
  name: 'baseline-alerts'
  params: {
    prefix: prefix
    location: location
    containerAppId: workload.outputs.appId
    containerAppName: workload.outputs.appName
    maxReplicas: contract.maxReplicas
    workspaceId: monitoring.outputs.workspaceId
    actionGroupId: monitoring.outputs.actionGroupId
    tags: tags
  }
}

output workspaceId string = monitoring.outputs.workspaceId
output appInsightsId string = monitoring.outputs.appInsightsId
output containerAppId string = workload.outputs.appId
output appUrl string = 'https://${workload.outputs.fqdn}'
output alertRuleIds string[] = concat(alerts.outputs.dynamicAlertIds, alerts.outputs.guardrailAlertIds)
