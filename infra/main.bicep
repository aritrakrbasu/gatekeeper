@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short lowercase prefix for resource names, for example gatekeeperdemo.')
param resourcePrefix string = 'gatekeeperdemo'

@description('Initial container image for the Container App. Use a public placeholder for bootstrap and switch to the ACR image during release.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Public frontend URL allowed by the backend CORS configuration.')
param frontendUrl string = 'https://example.vercel.app'

@description('Backend container port.')
param containerPort int = 8000

@description('Container CPU allocation.')
param containerCpu string = '1.0'

@description('Container memory allocation.')
param containerMemory string = '2Gi'

@description('Minimum replica count.')
param minReplicas int = 1

@description('Maximum replica count.')
param maxReplicas int = 2

var normalizedPrefix = toLower(resourcePrefix)
var registryName = take('${replace(normalizedPrefix, '-', '')}acr', 50)
var logAnalyticsName = '${normalizedPrefix}-logs'
var managedEnvironmentName = '${normalizedPrefix}-cae'
var containerAppName = '${normalizedPrefix}-backend'
var acrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: containerPort
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'gatekeeper-backend'
          image: containerImage
          env: [
            {
              name: 'PORT'
              value: string(containerPort)
            }
            {
              name: 'FRONTEND_URL'
              value: frontendUrl
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, containerApp.id, 'AcrPull')
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleDefinitionId
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output acrName string = registry.name
output acrLoginServer string = registry.properties.loginServer
output containerAppName string = containerApp.name
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output managedEnvironmentName string = managedEnvironment.name
