// Built-in role assignments for one principal on the resource group this module is deployed to.
// Role IDs are the built-in role definition IDs from the Azure built-in roles reference.

@description('Object ID of the principal.')
param principalId string

@description('Built-in role definition IDs (GUIDs) to assign.')
param roleIds string[]

@description('Principal type. ServicePrincipal for managed identities.')
@allowed([
  'ServicePrincipal'
  'User'
  'Group'
])
param principalType string = 'ServicePrincipal'

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in roleIds: {
  name: guid(resourceGroup().id, principalId, roleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    principalId: principalId
    principalType: principalType
  }
}]
