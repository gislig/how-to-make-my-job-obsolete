using './main.bicep'

param prefix = 'aiops-demo'
param location = 'swedencentral'

param contract = {
  owner: 'platform-team@contoso.com'
  minReplicas: 1
  maxReplicas: 10
  changeMode: 'review'
  tier: 'nonprod'
  sloP95Ms: 300
  monthlyBudgetEur: 50
}

param alertEmails = []
param retentionInDays = 30
