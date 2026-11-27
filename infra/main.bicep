// Job Radar : toute l'infrastructure Azure en un seul fichier.
// Déploiement : voir docs/azure-setup.md (EN) ou docs/installation-azure.md (FR), méthode rapide.
//
// Crée : Log Analytics, stockage + partage de fichiers, environnement Container Apps,
// identité managée, Key Vault + secrets, Azure AI Foundry + modèle, tableau de bord,
// routine du matin, rôles, et un budget mensuel (facultatif).
// Ne crée pas : la connexion Microsoft du tableau de bord ni l'accès GitHub (étapes manuelles).

targetScope = 'resourceGroup'

// ---------- Paramètres ----------

@description('Suffixe unique (initiales ou chiffres) pour les noms qui doivent être uniques dans tout Azure. Minuscules et chiffres, 3 à 8 caractères.')
@minLength(3)
@maxLength(8)
param suffix string

@description('Ton dépôt GitHub, par exemple alice/Job-Radar. Sert au nom de l\'image Docker.')
param ghRepo string

@description('Adresse qui reçoit le résumé du matin.')
param digestTo string

@description('Contenu de token.json (accès Gmail). Rangé dans Key Vault.')
@secure()
param gmailTokenJson string

@description('Téléphone affiché sur le CV (facultatif). Rangé dans Key Vault.')
@secure()
param cvPhone string = ''

@description('Object ID de ton compte (az ad signed-in-user show --query id -o tsv), pour pouvoir modifier les secrets plus tard. Facultatif.')
param adminObjectId string = ''

@description('Adresse qui reçoit les alertes de budget (facultatif : pas de budget si vide).')
param budgetEmail string = ''

@description('Budget mensuel en euros.')
param budgetAmount int = 5

@description('Requête Gmail qui trouve les emails d\'alerte.')
param gmailQuery string = 'from:jobalerts-noreply@linkedin.com newer_than:3d'

@description('Heure de la routine, format cron, en UTC.')
param cron string = '0 6 * * *'

@description('Modèle déployé sur Azure AI Foundry.')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'

@description('Capacité du modèle, en milliers de tokens par minute.')
param modelCapacity int = 10

param location string = resourceGroup().location

@description('Facultatif : nom d\'un environnement Container Apps existant à réutiliser (utile si ton abonnement est limité à un seul environnement). Vide = en créer un.')
param existingEnvironmentName string = ''

@description('Groupe de ressources de l\'environnement existant (même région que location).')
param existingEnvironmentResourceGroup string = resourceGroup().name

@description('Ne pas modifier : premier jour du mois courant, pour le budget.')
param budgetStartDate string = utcNow('yyyy-MM-01')

// ---------- Noms ----------

var image = 'ghcr.io/${toLower(ghRepo)}:latest'
var storageName = 'stjobradar${suffix}'
var shareName = 'jobradar-data'
var keyVaultName = 'kv-jobradar-${suffix}'
var foundryName = 'fdy-jobradar-${suffix}'
var apiName = 'ca-jobradar-api'
var jobName = 'caj-jobradar-daily'
var hasPhone = !empty(cvPhone)
var useExistingEnv = !empty(existingEnvironmentName)
var envName = useExistingEnv ? existingEnvironmentName : 'cae-jobradar'
var envResourceGroup = useExistingEnv ? existingEnvironmentResourceGroup : resourceGroup().name
var envStorageName = 'jobradar${suffix}' // nom propre à cette installation : ne gêne pas une autre installation dans le même environnement

// Rôles intégrés Azure (identifiants fixes)
var roles = {
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  keyVaultSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
}

// ---------- Journaux ----------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (!useExistingEnv) {
  name: 'log-jobradar'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------- Stockage (base SQLite, profil, base du CV) ----------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: { shareQuota: 1 }
}

// ---------- Environnement Container Apps ----------

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = if (!useExistingEnv) {
  name: envName
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

resource existingEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = if (useExistingEnv) {
  name: envName
  scope: resourceGroup(envResourceGroup)
}

var environmentId = useExistingEnv ? existingEnv.id : env.id

module envStorage 'env-storage.bicep' = {
  name: 'env-storage-${suffix}'
  scope: resourceGroup(envResourceGroup)
  params: {
    environmentName: envName
    name: envStorageName
    storageAccountName: storage.name
    storageAccountKey: storage.listKeys().keys[0].value
    shareName: share.name
  }
  dependsOn: [
    env
  ]
}

// ---------- Identité managée commune aux deux apps ----------
// Identité "attribuée par l'utilisateur" : elle existe avant les apps, donc ses rôles
// sont en place quand les apps lisent Key Vault pour la première fois.

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-jobradar'
  location: location
}

// ---------- Key Vault ----------

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource gmailSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'gmail-token'
  properties: { value: gmailTokenJson }
}

resource phoneSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (hasPhone) {
  parent: kv
  name: 'cv-phone'
  properties: { value: cvPhone }
}

resource kvReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, identity.id, roles.keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(adminObjectId)) {
  scope: kv
  name: guid(kv.id, adminObjectId, roles.keyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsOfficer)
    principalId: adminObjectId
    principalType: 'User'
  }
}

// ---------- Azure AI Foundry + modèle ----------

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: foundryName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: foundryName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true // pas de clé d'API : uniquement Microsoft Entra ID (identité managée, az login)
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

// Les DEUX rôles sont nécessaires, sur le compte Foundry (pas sur un projet)
resource foundryRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for r in [roles.cognitiveServicesUser, roles.cognitiveServicesOpenAIUser]: {
  scope: foundry
  name: guid(foundry.id, identity.id, r)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', r)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

// ---------- Volume commun ----------

var volumes = [
  {
    name: 'data'
    storageType: 'AzureFile'
    storageName: envStorage.outputs.name
    mountOptions: 'nobrl,dir_mode=0777,file_mode=0777' // nobrl : évite "database is locked" avec SQLite
  }
]
var volumeMounts = [
  {
    volumeName: 'data'
    mountPath: '/data'
  }
]

// ---------- Tableau de bord (FastAPI) ----------

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: hasPhone ? [
        {
          name: 'cv-phone'
          keyVaultUrl: '${kv.properties.vaultUri}secrets/cv-phone'
          identity: identity.id
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: concat([
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId } // identité utilisée par DefaultAzureCredential
            { name: 'AZURE_OPENAI_ENDPOINT', value: 'https://${foundryName}.openai.azure.com' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: model.name }
          ], hasPhone ? [
            { name: 'CV_PHONE', secretRef: 'cv-phone' }
          ] : [])
          volumeMounts: volumeMounts
        }
      ]
      scale: {
        minReplicas: 0 // s'éteint quand personne ne visite
        maxReplicas: 1 // jamais 2 écrivains SQLite en même temps
      }
      volumes: volumes
    }
  }
  dependsOn: [
    kvReader
    foundryRoles
    phoneSecret
  ]
}

// ---------- Routine du matin ----------

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: cron
        parallelism: 1
        replicaCompletionCount: 1
      }
      secrets: [
        {
          name: 'gmail-token'
          keyVaultUrl: '${kv.properties.vaultUri}secrets/gmail-token'
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'daily'
          image: image
          command: [ 'python', '-m', 'jobradar.daily' ]
          resources: {
            cpu: json('1') // le modèle d'embeddings a besoin de mémoire
            memory: '2Gi'
          }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'GMAIL_TOKEN_JSON', secretRef: 'gmail-token' }
            { name: 'GMAIL_QUERY', value: gmailQuery }
            { name: 'DIGEST_TO', value: digestTo }
            { name: 'DASHBOARD_URL', value: 'https://${api.properties.configuration.ingress.fqdn}' }
          ]
          volumeMounts: volumeMounts
        }
      ]
      volumes: volumes
    }
  }
  dependsOn: [
    kvReader
    gmailSecret
  ]
}

// ---------- Budget (facultatif) ----------

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (!empty(budgetEmail)) {
  name: 'budget-jobradar'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: [ budgetEmail ]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [ budgetEmail ]
      }
    }
  }
}

// ---------- Sorties (à recopier dans les variables GitHub) ----------

output dashboardUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output AZURE_RESOURCE_GROUP string = resourceGroup().name
output AZURE_API_APP string = api.name
output AZURE_JOB string = job.name
output AZURE_STORAGE_ACCOUNT string = storage.name
output AZURE_FILE_SHARE string = share.name
output keyVaultName string = kv.name
output foundryEndpoint string = 'https://${foundryName}.openai.azure.com'
