// Assigns the operating-contract policy to one resource group.

param policyDefinitionId string

@allowed([
  'Audit'
  'Deny'
  'Disabled'
])
param effect string

resource assignment 'Microsoft.Authorization/policyAssignments@2025-03-01' = {
  name: 'aiops-operating-contract'
  properties: {
    displayName: 'Agent-managed container apps must carry a valid operating contract'
    policyDefinitionId: policyDefinitionId
    enforcementMode: 'Default'
    parameters: {
      effect: {
        value: effect
      }
    }
  }
}

output assignmentId string = assignment.id
