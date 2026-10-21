// Proof of Play: everything in one resource group.
// Deploy:  az deployment group create -g <rg> -f infra/main.bicep -p prefix=pop
targetScope = 'resourceGroup'

@description('Short lowercase prefix for resource names')
param prefix string = 'pop'
param location string = resourceGroup().location
@description('Foundry model to deploy for the Explainer')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelCapacity int = 50
@description('Container image for the API + web app (set after the first ACR build)')
param image string = 'mcr.microsoft.com/k8se/quickstart:latest'
@secure()
param adminKey string
@secure()
param experimentSeed string

var suffix = uniqueString(resourceGroup().id)
var name = '${prefix}${suffix}'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${name}acr'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// Microsoft Foundry resource (AI Services) with a project and a model deployment.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${name}-foundry'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: '${name}-foundry'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'proof-of-play'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: { displayName: 'Proof of Play', description: 'Explainable, verified match intelligence' }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: modelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: { model: { format: 'OpenAI', name: modelName, version: modelVersion } }
}

resource eh 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: '${name}-eh'
  location: location
  sku: { name: 'Standard', tier: 'Standard', capacity: 1 }
  properties: { disableLocalAuth: true }
}

resource hub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: eh
  name: 'match-events'
  properties: { partitionCount: 2, messageRetentionInDays: 1 }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${name}-cosmos'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [ { locationName: location, failoverPriority: 0 } ]
    capabilities: [ { name: 'EnableServerless' } ]
    disableLocalAuth: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'pop'
  properties: { resource: { id: 'pop' } }
}

resource sessions 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: db
  name: 'engagement'
  properties: {
    resource: {
      id: 'engagement'
      partitionKey: { paths: [ '/session_id' ], kind: 'Hash' }
      defaultTtl: 2592000 // 30 days: the watch-along log deletes itself after judging
    }
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-app'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      secrets: [
        { name: 'admin-key', value: adminKey }
        { name: 'experiment-seed', value: experimentSeed }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'POP_LLM', value: 'foundry' }
            { name: 'AZURE_AI_PROJECT_ENDPOINT', value: foundry.properties.endpoint }
            { name: 'AZURE_AI_MODEL_DEPLOYMENT', value: model.name }
            { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
            { name: 'EVENTHUB_NAMESPACE', value: '${eh.name}.servicebus.windows.net' }
            { name: 'POP_ADMIN_KEY', secretRef: 'admin-key' }
            { name: 'POP_EXPERIMENT_SEED', secretRef: 'experiment-seed' }
          ]
        }
      ]
      // One replica on purpose: the live broadcast and the engagement log live in one process
      // until the Cosmos and Event Hubs adapters are switched on.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

// Managed-identity access, no keys anywhere.
var cogUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'   // Cognitive Services User
var ehSender = '2b629674-e913-4c01-ae53-ef4638d8f975'  // Azure Event Hubs Data Sender
var ehReceiver = 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde' // Azure Event Hubs Data Receiver

resource rCog 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, app.id, cogUser)
  scope: foundry
  properties: { principalId: app.identity.principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cogUser) }
}
resource rEhS 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eh.id, app.id, ehSender)
  scope: eh
  properties: { principalId: app.identity.principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', ehSender) }
}
resource rEhR 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eh.id, app.id, ehReceiver)
  scope: eh
  properties: { principalId: app.identity.principalId, principalType: 'ServicePrincipal', roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', ehReceiver) }
}
// Cosmos DB Built-in Data Contributor (data plane role)
resource rCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, app.id, 'data-contributor')
  properties: {
    principalId: app.identity.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}

output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
output foundryEndpoint string = foundry.properties.endpoint
output acrLoginServer string = acr.properties.loginServer
