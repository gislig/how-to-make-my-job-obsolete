// The monitoring baseline. Two kinds of rules:
//  - Dynamic thresholds: Azure Monitor learns what "normal" looks like (hourly, daily, weekly patterns)
//    and fires on deviations. This is the baseline the agent investigates against.
//  - Static guardrails: hard facts that need no learning, such as "we are at the replica ceiling"
//    or "5xx errors are happening".

@description('Name prefix for all resources.')
param prefix string

@description('Container app resource ID to watch.')
param containerAppId string

@description('Container app name (used in log queries).')
param containerAppName string

@description('The maxReplicas value from the operating contract.')
param maxReplicas int

@description('Log Analytics workspace resource ID (scope of the log search alert).')
param workspaceId string

@description('Azure region of the workspace (log search alerts are regional).')
param location string

@description('Action group resource ID.')
param actionGroupId string

@description('Static threshold: 5xx responses per 5 minutes before alerting.')
@minValue(1)
param http5xxThreshold int = 10

@description('Optional ISO 8601 date. Dynamic thresholds ignore history before this date, for example after a planned migration.')
param ignoreDataBefore string = ''

@description('Tags for every resource.')
param tags object

var appNamespace = 'Microsoft.App/containerApps'
var actions = [
  {
    actionGroupId: actionGroupId
  }
]

// Shared shape for the dynamic-threshold criteria. 4 evaluations of 5 minutes, 3 must violate.
var failingPeriods = {
  numberOfEvaluationPeriods: 4
  minFailingPeriodsToAlert: 3
}

var dynamicRules = [
  {
    name: 'requests-anomaly'
    description: 'Request volume is outside its learned pattern (up or down). A drop is as interesting as a spike.'
    metricName: 'Requests'
    timeAggregation: 'Total'
    operator: 'GreaterOrLessThan'
    sensitivity: 'Medium'
    severity: 3
  }
  {
    name: 'cpu-anomaly'
    description: 'CPU usage (nanocores) is above its learned pattern.'
    metricName: 'UsageNanoCores'
    timeAggregation: 'Average'
    operator: 'GreaterThan'
    sensitivity: 'Medium'
    severity: 3
  }
  {
    name: 'memory-anomaly'
    description: 'Working set memory is above its learned pattern. Low sensitivity, memory moves slowly.'
    metricName: 'WorkingSetBytes'
    timeAggregation: 'Average'
    operator: 'GreaterThan'
    sensitivity: 'Low'
    severity: 3
  }
]

resource dynamicAlerts 'Microsoft.Insights/metricAlerts@2026-01-01' = [for rule in dynamicRules: {
  name: 'ma-${prefix}-${rule.name}'
  location: 'global'
  tags: tags
  properties: {
    description: rule.description
    severity: rule.severity
    enabled: true
    scopes: [
      containerAppId
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    targetResourceType: appNamespace
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.MultipleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'DynamicThresholdCriterion'
          name: rule.name
          metricNamespace: appNamespace
          metricName: rule.metricName
          timeAggregation: rule.timeAggregation
          operator: rule.operator
          alertSensitivity: rule.sensitivity
          failingPeriods: failingPeriods
          ignoreDataBefore: empty(ignoreDataBefore) ? null : ignoreDataBefore
        }
      ]
    }
    actions: actions
  }
}]

// Guardrail 1: the scaling reflex is out of room. KEDA can't add replicas past maxReplicas,
// so this is the signal that a human or the agent must look at the contract, not just wait.
resource replicaCeilingAlert 'Microsoft.Insights/metricAlerts@2026-01-01' = {
  name: 'ma-${prefix}-replica-ceiling'
  location: 'global'
  tags: tags
  properties: {
    description: 'Replica count reached maxReplicas from the operating contract (${maxReplicas}). Autoscale has no more headroom.'
    severity: 2
    enabled: true
    scopes: [
      containerAppId
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    targetResourceType: appNamespace
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'replicas-at-max'
          metricNamespace: appNamespace
          metricName: 'Replicas'
          timeAggregation: 'Maximum'
          operator: 'GreaterThanOrEqual'
          threshold: maxReplicas
        }
      ]
    }
    actions: actions
  }
}

// Guardrail 2: server errors. No learning needed.
resource http5xxAlert 'Microsoft.Insights/metricAlerts@2026-01-01' = {
  name: 'ma-${prefix}-http-5xx'
  location: 'global'
  tags: tags
  properties: {
    description: 'More than ${http5xxThreshold} HTTP 5xx responses in 5 minutes.'
    severity: 2
    enabled: true
    scopes: [
      containerAppId
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    targetResourceType: appNamespace
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'http-5xx'
          metricNamespace: appNamespace
          metricName: 'Requests'
          timeAggregation: 'Total'
          operator: 'GreaterThan'
          threshold: http5xxThreshold
          dimensions: [
            {
              name: 'statusCodeCategory'
              operator: 'Include'
              values: [
                '5xx'
              ]
            }
          ]
        }
      ]
    }
    actions: actions
  }
}

// Baseline on logs: how often the platform logs scaling (KEDA) events for this app, compared with its own history.
// Lots of scaling churn usually means the scale rule thresholds are wrong, not that load is unusual.
// skipQueryValidation: the ContainerAppSystemLogs table only exists after the first logs arrive.
resource scalingChurnAlert 'Microsoft.Insights/scheduledQueryRules@2026-03-01' = {
  name: 'sqr-${prefix}-scaling-churn'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'Scaling churn on ${containerAppName}'
    description: 'Number of KEDA events for the app is above its learned pattern (dynamic threshold on a log query).'
    severity: 3
    enabled: true
    scopes: [
      workspaceId
    ]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    skipQueryValidation: true
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: 'ContainerAppSystemLogs | where ContainerAppName == "${containerAppName}" | where EventSource has "keda" | project TimeGenerated, ContainerAppName'
          timeAggregation: 'Count'
          criterionType: 'DynamicThresholdCriterion'
          operator: 'GreaterThan'
          alertSensitivity: 'Medium'
          dimensions: [
            {
              name: 'ContainerAppName'
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
}

output dynamicAlertIds string[] = [for (rule, i) in dynamicRules: dynamicAlerts[i].id]
output guardrailAlertIds string[] = [
  replicaCeilingAlert.id
  http5xxAlert.id
  scalingChurnAlert.id
]
