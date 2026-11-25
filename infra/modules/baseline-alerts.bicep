// The monitoring baseline. Two kinds of rules:
//  - Dynamic thresholds: Azure Monitor learns what "normal" looks like (hourly, daily, weekly patterns)
//    and fires on deviations. This is the baseline the agent investigates against.
//  - Static guardrails: hard facts that need no learning, such as "we are at the replica ceiling"
//    or "5xx errors are happening".

@description('Name prefix for all resources.')
param prefix string

@description('Container app resource ID to watch.')
param containerAppId string

@description('The maxReplicas value from the operating contract.')
param maxReplicas int

@description('Action group resource ID.')
param actionGroupId string

@description('Static threshold: 5xx responses per 5 minutes before alerting.')
@minValue(1)
param http5xxThreshold int = 10

@description('Static threshold: container restarts per 15 minutes before alerting.')
@minValue(0)
param restartThreshold int = 0

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

// Guardrail 3: containers restarting. A crash loop is never "normal", so no learning needed either.
resource restartAlert 'Microsoft.Insights/metricAlerts@2026-01-01' = {
  name: 'ma-${prefix}-restarts'
  location: 'global'
  tags: tags
  properties: {
    description: 'Container restarts in the last 15 minutes. Scaling out will not fix a crash loop.'
    severity: 2
    enabled: true
    scopes: [
      containerAppId
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    targetResourceType: appNamespace
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'restarts'
          metricNamespace: appNamespace
          metricName: 'RestartCount'
          timeAggregation: 'Total'
          operator: 'GreaterThan'
          threshold: restartThreshold
        }
      ]
    }
    actions: actions
  }
}

output dynamicAlertIds string[] = [for (rule, i) in dynamicRules: dynamicAlerts[i].id]
output guardrailAlertIds string[] = [
  replicaCeilingAlert.id
  http5xxAlert.id
  restartAlert.id
]
