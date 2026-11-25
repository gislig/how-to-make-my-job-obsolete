// Part 3: Azure Policy makes the operating contract non-optional.
// Any container app that says it is agent-managed (aiops-managed=true) must carry a complete, valid contract,
// and production can never be autonomous. Deploy at subscription scope.

targetScope = 'subscription'

@description('Audit first, then Deny once existing apps are compliant.')
@allowed([
  'Audit'
  'Deny'
  'Disabled'
])
param effect string = 'Audit'

@description('Resource group the assignment applies to (the workload resource group).')
param resourceGroupName string

var required = [
  'aiops-owner'
  'aiops-min-replicas'
  'aiops-max-replicas'
  'aiops-change-mode'
  'aiops-tier'
]

resource definition 'Microsoft.Authorization/policyDefinitions@2025-03-01' = {
  name: 'aiops-operating-contract'
  properties: {
    displayName: 'Agent-managed container apps must carry a valid operating contract'
    description: 'Container apps tagged aiops-managed=true need every aiops-* contract tag, a valid change mode and tier, and production must use review mode.'
    policyType: 'Custom'
    mode: 'Indexed'
    metadata: {
      category: 'Container Apps'
      version: '1.0.0'
    }
    parameters: {
      effect: {
        type: 'String'
        allowedValues: [
          'Audit'
          'Deny'
          'Disabled'
        ]
        defaultValue: 'Audit'
      }
    }
    policyRule: {
      if: {
        allOf: [
          {
            field: 'type'
            equals: 'Microsoft.App/containerApps'
          }
          {
            field: 'tags[\'aiops-managed\']'
            equals: 'true'
          }
          {
            anyOf: concat(map(required, t => {
              field: 'tags[\'${t}\']'
              exists: false
            }), [
              {
                field: 'tags[\'aiops-change-mode\']'
                notIn: [
                  'review'
                  'autonomous'
                ]
              }
              {
                field: 'tags[\'aiops-tier\']'
                notIn: [
                  'prod'
                  'nonprod'
                ]
              }
              {
                allOf: [
                  {
                    field: 'tags[\'aiops-tier\']'
                    equals: 'prod'
                  }
                  {
                    field: 'tags[\'aiops-change-mode\']'
                    equals: 'autonomous'
                  }
                ]
              }
            ])
          }
        ]
      }
      then: {
        effect: '[parameters(\'effect\')]'
      }
    }
  }
}

module assignment 'contract-policy-assignment.bicep' = {
  name: 'aiops-contract-assignment'
  scope: resourceGroup(resourceGroupName)
  params: {
    policyDefinitionId: definition.id
    effect: effect
  }
}

output policyDefinitionId string = definition.id
