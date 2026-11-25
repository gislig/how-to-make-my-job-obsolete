using './main.bicep'

param prefix = 'aiops-demo'
param location = 'swedencentral'
param deployApp = bool(readEnvironmentVariable('DEPLOY_APP', 'false'))
param imageTag = readEnvironmentVariable('IMAGE_TAG', '1.0.0')
// Never commit keys. scripts/deploy-mcp.sh generates them and passes them through the environment.
param apiKeys = readEnvironmentVariable('MCP_API_KEYS', '')
param allowWrites = false
param allowedIpRanges = []
