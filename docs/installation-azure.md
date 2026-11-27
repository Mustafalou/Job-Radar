# Installer ta propre version de Job Radar sur Azure

[English](azure-setup.md) | **Français**

Ce guide part de zéro : un compte Google, un compte GitHub et un compte Azure.
Compte environ 1 h 30 la première fois. Le coût visé est de moins de 1 € par mois.

Tous les noms ci-dessous (groupe de ressources, stockage, Key Vault...) sont des **exemples**.
Tu choisis les tiens une seule fois à l'étape 4, et toutes les commandes suivantes les réutilisent.

## Sommaire

1. [Ce qu'il te faut](#1-ce-quil-te-faut)
2. [Copier le dépôt et l'adapter à ton profil](#2-copier-le-dépôt-et-ladapter-à-ton-profil)
3. [Accès Gmail (une seule fois, sur ton PC)](#3-accès-gmail-une-seule-fois-sur-ton-pc)
4. [Choisir tes noms dans Azure Cloud Shell](#4-choisir-tes-noms-dans-azure-cloud-shell)
5. [Créer le stockage et l'environnement](#5-créer-le-stockage-et-lenvironnement)
6. [Créer le tableau de bord et la routine du matin](#6-créer-le-tableau-de-bord-et-la-routine-du-matin)
7. [Ranger les secrets dans Key Vault](#7-ranger-les-secrets-dans-key-vault)
8. [Brancher le LLM (Azure AI Foundry)](#8-brancher-le-llm-azure-ai-foundry)
9. [Protéger le tableau de bord](#9-protéger-le-tableau-de-bord)
10. [Déploiement automatique depuis GitHub](#10-déploiement-automatique-depuis-github)
11. [Vérifier que tout marche](#11-vérifier-que-tout-marche)
12. [Problèmes fréquents](#12-problèmes-fréquents)

---

## 1. Ce qu'il te faut

- Un compte **GitHub**.
- Un compte **Google** (Gmail) qui reçoit tes alertes emploi LinkedIn.
- Un compte **Azure**. L'essai gratuit suffit pour commencer, mais pense à passer en
  "paiement à l'utilisation" avant la fin de l'essai, sinon tout s'arrête.
- **Python 3.13** sur ton PC, uniquement pour l'étape 3.

Les commandes Azure se lancent dans **Azure Cloud Shell** (l'icône `>_` en haut du portail Azure,
choisis **Bash**). Rien à installer : `az`, `git` et `sed` y sont déjà.

## 2. Copier le dépôt et l'adapter à ton profil

1. Sur GitHub, clique sur **Fork** pour copier le dépôt sur ton compte.
2. Dans ton fork, onglet **Actions**, active les workflows (GitHub les désactive sur un fork).
3. Adapte ces fichiers à toi :

| Fichier | Ce que tu changes |
| --- | --- |
| `profile.md` | ton profil : postes visés, compétences acquises, compétences en cours, contraintes. Le LLM le lit pour noter les offres. |
| `cv_base.json` | tes expériences, puces, compétences, formation, en FR et EN. Le générateur de CV ne peut utiliser **que** ce qui est écrit ici. |
| `src/jobradar/scoring.py` | `TARGET_ROLES` (postes visés), `EXCLUDED` (domaines à écarter), `SENIOR`, `JUNIOR`, `LANG_NL`. |

> **Attention** : si ton fork est public, `profile.md` et `cv_base.json` le sont aussi.
> N'y mets que ce que tu mettrais sur LinkedIn. Ton numéro de téléphone **ne va pas** dans
> `cv_base.json` : il est stocké dans Key Vault (étape 7).

4. Fais un commit sur `main`. Le workflow **Build image** construit l'image Docker
   (environ 5 minutes). Le job `deploy` est ignoré pour l'instant, c'est normal.
5. Rends l'image publique : sur GitHub, ton profil > **Packages** > `job-radar` >
   **Package settings** > **Change visibility** > **Public**.
   Sans ça, Azure ne peut pas télécharger l'image.

Ton image s'appelle `ghcr.io/<ton-pseudo-github-en-minuscules>/<nom-du-dépôt-en-minuscules>`,
par exemple `ghcr.io/alice/job-radar`.

## 3. Accès Gmail (une seule fois, sur ton PC)

Job Radar lit tes alertes en **lecture seule** et t'envoie un résumé à toi-même.

1. Va sur [console.cloud.google.com](https://console.cloud.google.com) et crée un projet (par exemple `job-radar`).
2. **API et services > Bibliothèque** : active l'**API Gmail**.
3. **Écran de consentement OAuth** : type **Externe**, ajoute ton adresse Gmail comme utilisateur test.
4. **Identifiants > Créer des identifiants > ID client OAuth > Application de bureau**.
   Télécharge le fichier JSON et renomme-le `credentials.json` à la racine du projet.
5. **Important** : dans l'écran de consentement, clique sur **Publier l'application** (passer "En production").
   En mode test, Google invalide le token au bout de 7 jours et la routine s'arrête.
   Pour un usage personnel, pas besoin de faire vérifier l'application : Google affichera juste
   un avertissement "application non vérifiée" lors de l'autorisation, clique sur **Continuer**.
6. Sur ton PC :

```powershell
git clone https://github.com/<ton-pseudo>/Job-Radar.git
cd Job-Radar
python -m venv .venv
.venv\Scripts\activate          # sous Linux/Mac : source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # puis mets ton adresse dans DIGEST_TO
$env:PYTHONPATH="src"
python -m jobradar.ingest
```

Une page Google s'ouvre : autorise l'accès. Le fichier `token.json` est créé.
C'est lui qu'on mettra dans Key Vault. `credentials.json` et `token.json` sont des secrets :
ils sont exclus de git, ne les envoie jamais.

## 4. Choisir tes noms dans Azure Cloud Shell

Ouvre Cloud Shell (Bash) et colle ce bloc après l'avoir modifié.
Les noms de stockage et de Key Vault doivent être **uniques dans tout Azure** :
ajoute tes initiales ou quelques chiffres.

```bash
RG=rg-jobradar                       # groupe de ressources
LOC=francecentral                    # région
ST=stjobradarab12                    # compte de stockage : 3-24 caractères, minuscules et chiffres seulement
SHARE=jobradar-data                  # partage de fichiers (base SQLite, profil, CV)
ENV=cae-jobradar                     # environnement Container Apps
API=ca-jobradar-api                  # tableau de bord
JOB=caj-jobradar-daily               # routine du matin
KV=kv-jobradar-ab12                  # Key Vault : 3-24 caractères
GH_REPO=alice/Job-Radar              # ton fork, exactement comme dans l'URL GitHub
DIGEST_TO=alice@gmail.com            # adresse qui reçoit le résumé du matin
IMAGE=ghcr.io/${GH_REPO,,}:latest    # ne pas modifier : nom de l'image en minuscules
```

Cloud Shell oublie ces variables quand la session se ferme. Si tu fais une pause,
recolle simplement ce bloc avant de continuer.

## 5. Créer le stockage et l'environnement

```bash
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

az group create -n $RG -l $LOC

# Stockage : le partage de fichiers qui contient la base SQLite
az storage account create -n $ST -g $RG -l $LOC --sku Standard_LRS --kind StorageV2
KEY=$(az storage account keys list -n $ST -g $RG --query "[0].value" -o tsv)
az storage share create --name $SHARE --account-name $ST --account-key "$KEY" --quota 1

# Environnement Container Apps + branchement du partage
az containerapp env create -n $ENV -g $RG -l $LOC
az containerapp env storage set -n $ENV -g $RG --storage-name jobradardata \
  --azure-file-account-name $ST --azure-file-account-key "$KEY" \
  --azure-file-share-name $SHARE --access-mode ReadWrite
```

Envoie ton profil et ta base de CV sur le partage (le pipeline le refera à chaque push ensuite).
Dans Cloud Shell, bouton **Gérer les fichiers > Charger** pour téléverser `profile.md` et `cv_base.json`, puis :

```bash
for f in profile.md cv_base.json; do
  az storage file upload --account-name $ST --account-key "$KEY" --share-name $SHARE --source $f --path $f
done
```

## 6. Créer le tableau de bord et la routine du matin

Les modèles sont dans `deploy/`. On remplace les valeurs `__EN_MAJUSCULES__` par les tiennes :

```bash
git clone https://github.com/$GH_REPO.git jr && cd jr
ENV_ID=$(az containerapp env show -n $ENV -g $RG --query id -o tsv)
for f in api job; do
  sed -e "s|__LOCATION__|$LOC|" -e "s|__ENV_ID__|$ENV_ID|" -e "s|__IMAGE__|$IMAGE|" \
    deploy/containerapp-$f.yaml > /tmp/$f.yaml
done

az containerapp create -n $API -g $RG --yaml /tmp/api.yaml
az containerapp job create -n $JOB -g $RG --yaml /tmp/job.yaml

API_URL=https://$(az containerapp show -n $API -g $RG --query properties.configuration.ingress.fqdn -o tsv)
echo $API_URL     # l'adresse de ton tableau de bord

# Réglages de la routine (la requête Gmail trouve les emails d'alerte)
az containerapp job update -n $JOB -g $RG --set-env-vars \
  "DIGEST_TO=$DIGEST_TO" "DASHBOARD_URL=$API_URL" \
  "GMAIL_QUERY=from:jobalerts-noreply@linkedin.com newer_than:3d"
```

À ce stade, le tableau de bord s'ouvre déjà (vide). La routine ne peut pas encore lire Gmail : c'est l'étape suivante.

## 7. Ranger les secrets dans Key Vault

Les secrets ne sont ni dans le code ni dans l'image. Ils sont dans Key Vault, et chaque app
les lit avec son **identité managée** (aucun mot de passe à gérer).

```bash
az keyvault create -n $KV -g $RG -l $LOC --enable-rbac-authorization true
KV_ID=$(az keyvault show -n $KV --query id -o tsv)

# Toi : droit d'écrire les secrets
az role assignment create --role "Key Vault Secrets Officer" --scope $KV_ID \
  --assignee $(az ad signed-in-user show --query id -o tsv)

# Les deux apps : droit de lire les secrets
API_PID=$(az containerapp show -n $API -g $RG --query identity.principalId -o tsv)
JOB_PID=$(az containerapp job show -n $JOB -g $RG --query identity.principalId -o tsv)
for p in $API_PID $JOB_PID; do
  az role assignment create --role "Key Vault Secrets User" --scope $KV_ID \
    --assignee-object-id $p --assignee-principal-type ServicePrincipal
done
```

Attends **2 minutes** (le temps que les droits se propagent). Téléverse ensuite `token.json`
dans Cloud Shell (**Gérer les fichiers > Charger**), puis :

```bash
cd ~
az keyvault secret set --vault-name $KV -n gmail-token --file token.json
az keyvault secret set --vault-name $KV -n cv-phone --value "+32 4xx xx xx xx"   # ton numéro, affiché sur le CV
rm token.json    # ne le laisse pas traîner dans Cloud Shell

# Les apps lisent Key Vault : références vers la dernière version de chaque secret
az containerapp job secret set -n $JOB -g $RG \
  --secrets "gmail-token=keyvaultref:https://$KV.vault.azure.net/secrets/gmail-token,identityref:system"
az containerapp job update -n $JOB -g $RG --set-env-vars GMAIL_TOKEN_JSON=secretref:gmail-token

az containerapp secret set -n $API -g $RG \
  --secrets "cv-phone=keyvaultref:https://$KV.vault.azure.net/secrets/cv-phone,identityref:system"
az containerapp update -n $API -g $RG --set-env-vars CV_PHONE=secretref:cv-phone
```

## 8. Brancher le LLM (Azure AI Foundry)

Le LLM sert aux boutons **Analyser** et **Générer CV**. Sans lui, le reste fonctionne.

1. Sur [ai.azure.com](https://ai.azure.com), crée une ressource Foundry **dans ton groupe `$RG`**.
   Note son nom (par exemple `fdy-jobradar-ab12`).
2. **Modèles et points de terminaison > Déployer un modèle** : `gpt-4.1-mini`,
   type **Global Standard**, nom du déploiement `gpt-4.1-mini`.
3. Copie le **point de terminaison** de la ressource (`https://....azure.com`, le reste du chemin est ignoré).

Puis dans Cloud Shell :

```bash
FOUNDRY=fdy-jobradar-ab12                                  # le nom noté ci-dessus
ENDPOINT=https://fdy-jobradar-ab12.services.ai.azure.com   # le point de terminaison copié

# Droit d'appeler le modèle, sur le COMPTE Foundry (pas sur le projet)
az role assignment create --role "Cognitive Services User" \
  --scope $(az cognitiveservices account show -n $FOUNDRY -g $RG --query id -o tsv) \
  --assignee-object-id $API_PID --assignee-principal-type ServicePrincipal

az containerapp update -n $API -g $RG --set-env-vars \
  "AZURE_OPENAI_ENDPOINT=$ENDPOINT" "AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini"
```

Pas de clé d'API : l'app s'authentifie avec son identité managée.

## 9. Protéger le tableau de bord

Le tableau de bord contient tes offres et ton CV : il ne doit pas être ouvert à tous.

Dans le portail Azure : ton app `$API` > **Authentification** > **Ajouter un fournisseur d'identité** >
**Microsoft** :
- Inscription d'application : **Créer**.
- Types de comptes : **Locataire actuel uniquement**.
- Requêtes non authentifiées : **HTTP 302, rediriger vers la connexion**.

Note : le secret client créé ici expire après 24 mois. Mets un rappel pour le renouveler
(portail Entra ID > Inscriptions d'applications > ton app > Certificats et secrets).

## 10. Déploiement automatique depuis GitHub

À chaque push sur `main`, GitHub construit l'image, met à jour les deux apps et renvoie
`profile.md` et `cv_base.json`. GitHub se connecte à Azure **sans mot de passe** (OIDC).

```bash
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
APP_ID=$(az ad app create --display-name gh-jobradar-deploy --query appId -o tsv)
az ad sp create --id $APP_ID
az role assignment create --assignee $APP_ID --role Contributor \
  --scope $(az group show -n $RG --query id -o tsv)

az ad app federated-credential create --id $APP_ID --parameters "{
  \"name\": \"github-main\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:$GH_REPO:ref:refs/heads/main\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}"

echo "AZURE_CLIENT_ID=$APP_ID"; echo "AZURE_TENANT_ID=$TENANT_ID"; echo "AZURE_SUBSCRIPTION_ID=$SUB_ID"
echo "AZURE_RESOURCE_GROUP=$RG"; echo "AZURE_API_APP=$API"; echo "AZURE_JOB=$JOB"
echo "AZURE_STORAGE_ACCOUNT=$ST"; echo "AZURE_FILE_SHARE=$SHARE"
```

Dans ton fork sur GitHub : **Settings > Secrets and variables > Actions**.

| Onglet | Nom | Valeur |
| --- | --- | --- |
| Secrets | `AZURE_CLIENT_ID` | affiché ci-dessus |
| Secrets | `AZURE_TENANT_ID` | affiché ci-dessus |
| Secrets | `AZURE_SUBSCRIPTION_ID` | affiché ci-dessus |
| Variables | `AZURE_RESOURCE_GROUP` | ton `$RG` |
| Variables | `AZURE_API_APP` | ton `$API` |
| Variables | `AZURE_JOB` | ton `$JOB` |
| Variables | `AZURE_STORAGE_ACCOUNT` | ton `$ST` |
| Variables | `AZURE_FILE_SHARE` | ton `$SHARE` |

Relance ensuite le workflow (**Actions > Build image > Run workflow**). Le job `deploy` doit passer au vert.

## 11. Vérifier que tout marche

```bash
# Lancer la routine maintenant, sans attendre demain matin
az containerapp job start -n $JOB -g $RG
# Suivre l'exécution (Succeeded attendu au bout de 2 à 5 minutes)
az containerapp job execution list -n $JOB -g $RG -o table
```

- Tu dois recevoir l'email de résumé (s'il y a des offres au-dessus du seuil).
- Ouvre `$API_URL`, connecte-toi avec ton compte Microsoft : les offres apparaissent.
- Sur une offre, **Analyser** avec une description collée, puis **Générer CV**.
- Dans le portail : **Gestion des coûts > Budgets**, crée un budget de 5 € par mois avec alerte.

## 12. Problèmes fréquents

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| L'app ne démarre pas, erreur de téléchargement d'image | image ghcr privée | étape 2, point 5 : rendre le package public |
| GitHub : `AADSTS700213 No matching federated identity record` | le "subject" ne correspond pas | GitHub utilise parfois un format avec identifiants (`repo:alice@123/Job-Radar@456:...`). Copie le subject exact affiché dans l'erreur et mets-le dans l'identité fédérée (portail Entra ID > Inscriptions d'applications > `gh-jobradar-deploy` > Certificats et secrets > Informations d'identification fédérées). |
| Secret Key Vault refusé à la création de la référence | droits pas encore propagés | attends 2 à 5 minutes et relance la commande |
| Analyser : erreur 401 | rôle mis sur le projet Foundry | le rôle "Cognitive Services User" doit être sur le **compte** Foundry (étape 8) |
| Analyser : erreur 404 | mauvais nom de déploiement | `AZURE_OPENAI_DEPLOYMENT` doit être le nom exact du déploiement |
| La routine marche une semaine puis échoue (`invalid_grant`) | application Google restée en mode test | étape 3, point 5, puis refais `token.json` et mets à jour le secret `gmail-token` |
| `database is locked` | deux écrivains SQLite | garder `maxReplicas: 1` et l'option `nobrl` (déjà dans les modèles) |
| Aucune offre trouvée | requête Gmail trop stricte | vérifie `GMAIL_QUERY` en la testant dans la barre de recherche Gmail |
