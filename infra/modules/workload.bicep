// A sample HTTP workload with the scaling reflexes (KEDA rules) and its operating contract as tags.

import { operatingContract, contractTags } from '../types/contract.bicep'

@description('Container app name.')
param name string

@description('Azure region.')
param location string

@description('Container Apps environment resource ID.')
param environmentId string

@description('Container image. The default is the public Container Apps quickstart image.')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Port the container listens on.')
param targetPort int = 80

@description('vCPU per replica.')
param cpu string = '0.5'

@description('Memory per replica. Must match the CPU size, for example 0.5 vCPU with 1Gi.')
param memory string = '1Gi'

@description('Concurrent HTTP requests per replica before Container Apps adds a replica.')
@minValue(1)
param concurrentRequests int = 50

@description('Average CPU utilization (percent of the allocated CPU) before a replica is added. Only used when minReplicas is 1 or more.')
@minValue(1)
@maxValue(100)
param cpuUtilizationTarget int = 70

@description('The operating contract the AI ops agent must respect.')
param contract operatingContract

@description('Extra tags.')
param tags object = {}

var httpRule = {
  name: 'http-concurrency'
  http: {
    metadata: {
      concurrentRequests: string(concurrentRequests)
    }
  }
}

// CPU and memory scalers cannot scale to zero, so only add the CPU rule when the contract keeps at least one replica.
var cpuRule = {
  name: 'cpu-utilization'
  custom: {
    type: 'cpu'
    metadata: {
      type: 'Utilization'
      value: string(cpuUtilizationTarget)
    }
  }
}

resource app 'Microsoft.App/containerApps@2026-01-01' = {
  name: name
  location: location
  tags: union(tags, contractTags(contract))
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        allowInsecure: false
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'app'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: targetPort
              }
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: contract.minReplicas
        maxReplicas: contract.maxReplicas
        rules: contract.minReplicas >= 1 ? [httpRule, cpuRule] : [httpRule]
      }
    }
  }
}

output appId string = app.id
output appName string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
