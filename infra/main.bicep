// Part 1 of the series: the foundation the infrastructure agent stands on.
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
  series: 'how-to-make-my-job-obsolete'
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
    image: image
    contract: contract
    tags: tags
  }
}

module alerts 'modules/baseline-alerts.bicep' = {
  name: 'baseline-alerts'
  params: {
    prefix: prefix
    containerAppId: workload.outputs.appId
    maxReplicas: contract.maxReplicas
    actionGroupId: monitoring.outputs.actionGroupId
    tags: tags
  }
}

output workspaceId string = monitoring.outputs.workspaceId
output appInsightsId string = monitoring.outputs.appInsightsId
output workspaceCustomerId string = monitoring.outputs.workspaceCustomerId
output environmentId string = containerEnv.outputs.environmentId
output containerAppName string = workload.outputs.appName
output containerAppId string = workload.outputs.appId
output appUrl string = 'https://${workload.outputs.fqdn}'
output alertRuleIds string[] = concat(alerts.outputs.dynamicAlertIds, alerts.outputs.guardrailAlertIds)
