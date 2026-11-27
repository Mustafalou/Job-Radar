// Branche le partage Azure Files sur un environnement Container Apps.
// Module séparé : l'environnement peut se trouver dans un autre groupe de ressources.

param environmentName string
param name string
param storageAccountName string
@secure()
param storageAccountKey string
param shareName string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: environmentName
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: name
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAccountKey
      shareName: shareName
      accessMode: 'ReadWrite'
    }
  }
}

output name string = envStorage.name
