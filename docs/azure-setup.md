# Run your own Job Radar on Azure

**English** | [Français](installation-azure.md)

This guide starts from scratch: a Google account, a GitHub account and an Azure account.
Expect about 1 h 30 the first time. The target cost is below €1 per month.

All names below (resource group, storage, Key Vault...) are **examples**.
You choose yours once in step 4, and every following command reuses them.

## Contents

1. [What you need](#1-what-you-need)
2. [Fork the repository and adapt it to your profile](#2-fork-the-repository-and-adapt-it-to-your-profile)
3. [Gmail access (once, on your PC)](#3-gmail-access-once-on-your-pc)
   - [Shortcut: create everything with one command (Bicep)](#shortcut-create-everything-with-one-command-bicep)
4. [Choose your names in Azure Cloud Shell](#4-choose-your-names-in-azure-cloud-shell)
5. [Create the storage and the environment](#5-create-the-storage-and-the-environment)
6. [Create the dashboard and the morning routine](#6-create-the-dashboard-and-the-morning-routine)
7. [Store the secrets in Key Vault](#7-store-the-secrets-in-key-vault)
8. [Connect the LLM (Azure AI Foundry)](#8-connect-the-llm-azure-ai-foundry)
9. [Protect the dashboard](#9-protect-the-dashboard)
10. [Automatic deployment from GitHub](#10-automatic-deployment-from-github)
11. [Check that everything works](#11-check-that-everything-works)
12. [Common problems](#12-common-problems)

---

## 1. What you need

- A **GitHub** account.
- A **Google** (Gmail) account that receives your LinkedIn job alerts.
- An **Azure** account. The free trial is enough to start, but remember to switch to
  "pay as you go" before the trial ends, otherwise everything stops.
- **Python 3.13** on your PC, only for step 3.

Azure commands run in **Azure Cloud Shell** (the `>_` icon at the top of the Azure portal,
choose **Bash**). Nothing to install: `az`, `git` and `sed` are already there.

## 2. Fork the repository and adapt it to your profile

1. On GitHub, click **Fork** to copy the repository to your account.
2. In your fork, **Actions** tab, enable the workflows (GitHub disables them on forks).
3. Adapt these files to you:

| File | What you change |
| --- | --- |
| `profile.md` | your profile: target roles, acquired skills, skills in progress, constraints. The LLM reads it to score offers. |
| `cv_base.json` | your experiences, bullet points, skills, education, in FR and EN. The CV generator can **only** use what is written here. |
| `src/jobradar/scoring.py` | `TARGET_ROLES` (target roles), `EXCLUDED` (fields to drop), `SENIOR`, `JUNIOR`, `LANG_NL`. |

> **Warning**: if your fork is public, `profile.md` and `cv_base.json` are public too.
> Only put in them what you would put on LinkedIn. Your phone number does **not** go in
> `cv_base.json`: it is stored in Key Vault (step 7).

4. Commit to `main`. The **Build image** workflow builds the Docker image
   (about 5 minutes). The `deploy` job is skipped for now, that is expected.
5. Make the image public: on GitHub, your profile > **Packages** > `job-radar` >
   **Package settings** > **Change visibility** > **Public**.
   Without this, Azure cannot download the image.

Your image is named `ghcr.io/<your-github-username-in-lowercase>/<repository-name-in-lowercase>`,
for example `ghcr.io/alice/job-radar`.

## 3. Gmail access (once, on your PC)

Job Radar reads your alerts **read-only** and sends a digest to yourself.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project (for example `job-radar`).
2. **APIs & Services > Library**: enable the **Gmail API**.
3. **OAuth consent screen**: type **External**, add your Gmail address as a test user.
4. **Credentials > Create credentials > OAuth client ID > Desktop app**.
   Download the JSON file and rename it `credentials.json` at the root of the project.
5. **Important**: on the consent screen, click **Publish app** (switch to "In production").
   In test mode, Google invalidates the token after 7 days and the routine stops.
   For personal use, you do not need to get the app verified: Google will just show
   an "unverified app" warning when you authorize it, click **Continue**.
6. On your PC:

```powershell
git clone https://github.com/<your-username>/Job-Radar.git
cd Job-Radar
python -m venv .venv
.venv\Scripts\activate          # on Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then put your address in DIGEST_TO
$env:PYTHONPATH="src"
python -m jobradar.ingest
```

A Google page opens: grant access. The `token.json` file is created.
This is what goes into Key Vault. `credentials.json` and `token.json` are secrets:
they are excluded from git, never share them.

## Shortcut: create everything with one command (Bicep)

> Status: the file passes Azure's pre-deployment validation but has not been deployed end to end yet. If you hit an error, please open a GitHub issue; the step-by-step method below is tested.

The file [`infra/main.bicep`](../infra/main.bicep) describes the whole infrastructure (infrastructure as code).
One command replaces steps 4 to 8: storage, environment, managed identity, Key Vault and secrets,
Azure AI Foundry and the model, dashboard, morning routine, roles and budget.
If you take this shortcut, do steps 1 to 3, then this, then steps 9, 10 and 11.

In Cloud Shell (Bash), first upload `token.json` (**Manage files > Upload**), then:

```bash
GH_REPO=alice/Job-Radar          # your fork
RG=rg-jobradar                   # resource group
SUFFIX=ab12                      # 3 to 8 lowercase letters or digits, makes names unique
DIGEST_TO=alice@gmail.com        # receives the morning digest and budget alerts
PHONE="+32 4xx xx xx xx"         # shown on the CV (use "" for none)

git clone https://github.com/$GH_REPO.git jr && cd jr
az group create -n $RG -l francecentral

# Secrets go through a temporary file (never in the shell history)
jq -n --rawfile t ~/token.json --arg p "$PHONE" '{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": { "gmailTokenJson": { "value": $t }, "cvPhone": { "value": $p } }
}' > ~/secrets.json

az deployment group create -g $RG -n jobradar -f infra/main.bicep \
  -p @$HOME/secrets.json \
  -p suffix=$SUFFIX ghRepo=$GH_REPO digestTo=$DIGEST_TO budgetEmail=$DIGEST_TO \
     adminObjectId=$(az ad signed-in-user show --query id -o tsv) \
  --query properties.outputs

rm ~/token.json ~/secrets.json
```

The command takes 5 to 10 minutes and prints the dashboard address and the names to copy into the
GitHub variables (step 10). It is safe to run again: Azure only creates what is missing.

Then upload `profile.md` and `cv_base.json` to the share (the pipeline also does it on every push):

```bash
ST=stjobradar$SUFFIX
KEY=$(az storage account keys list -n $ST -g $RG --query "[0].value" -o tsv)
for f in profile.md cv_base.json; do
  az storage file upload --account-name $ST --account-key "$KEY" --share-name jobradar-data --source $f --path $f
done
```

Differences with the step-by-step method: both apps share a managed identity created up front
(`id-jobradar`), so there is no waiting for role propagation, and the Foundry resource accepts
no API key at all (Microsoft Entra ID only). To run Job Radar locally with the LLM, give your account
the "Cognitive Services User" and "Cognitive Services OpenAI User" roles on `fdy-jobradar-<suffix>`.

If your subscription already has a Container Apps environment and refuses a second one (common on a free trial or just after upgrading), reuse it: add `-p existingEnvironmentName=<name> existingEnvironmentResourceGroup=<group>`, in the same region as that environment. The apps and storage stay in your new group, and the share is mounted under its own name (`jobradar<suffix>`).

If the model is not available in your region, add `-p modelVersion=...` with a version listed by
`az cognitiveservices model list -l francecentral -o table`.

## 4. Choose your names in Azure Cloud Shell

Open Cloud Shell (Bash) and paste this block after editing it.
Storage and Key Vault names must be **unique across all of Azure**:
add your initials or a few digits.

```bash
RG=rg-jobradar                       # resource group
LOC=francecentral                    # region
ST=stjobradarab12                    # storage account: 3-24 characters, lowercase letters and digits only
SHARE=jobradar-data                  # file share (SQLite database, profile, CV)
ENV=cae-jobradar                     # Container Apps environment
API=ca-jobradar-api                  # dashboard
JOB=caj-jobradar-daily               # morning routine
KV=kv-jobradar-ab12                  # Key Vault: 3-24 characters
GH_REPO=alice/Job-Radar              # your fork, exactly as in the GitHub URL
DIGEST_TO=alice@gmail.com            # address that receives the morning digest
IMAGE=ghcr.io/${GH_REPO,,}:latest    # do not edit: image name in lowercase
```

Cloud Shell forgets these variables when the session closes. If you take a break,
just paste this block again before continuing.

## 5. Create the storage and the environment

```bash
az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

az group create -n $RG -l $LOC

# Storage: the file share that holds the SQLite database
az storage account create -n $ST -g $RG -l $LOC --sku Standard_LRS --kind StorageV2
KEY=$(az storage account keys list -n $ST -g $RG --query "[0].value" -o tsv)
az storage share create --name $SHARE --account-name $ST --account-key "$KEY" --quota 1

# Container Apps environment + mount the share
az containerapp env create -n $ENV -g $RG -l $LOC
az containerapp env storage set -n $ENV -g $RG --storage-name jobradardata \
  --azure-file-account-name $ST --azure-file-account-key "$KEY" \
  --azure-file-share-name $SHARE --access-mode ReadWrite
```

Upload your profile and CV base to the share (the pipeline will do it again on every push).
In Cloud Shell, **Manage files > Upload** `profile.md` and `cv_base.json`, then:

```bash
for f in profile.md cv_base.json; do
  az storage file upload --account-name $ST --account-key "$KEY" --share-name $SHARE --source $f --path $f
done
```

## 6. Create the dashboard and the morning routine

The templates are in `deploy/`. Replace the `__UPPERCASE__` values with yours:

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
echo $API_URL     # your dashboard address

# Routine settings (the Gmail query finds the alert emails)
az containerapp job update -n $JOB -g $RG --set-env-vars \
  "DIGEST_TO=$DIGEST_TO" "DASHBOARD_URL=$API_URL" \
  "GMAIL_QUERY=from:jobalerts-noreply@linkedin.com newer_than:3d"
```

At this point the dashboard already opens (empty). The routine cannot read Gmail yet: that is the next step.

## 7. Store the secrets in Key Vault

Secrets are neither in the code nor in the image. They are in Key Vault, and each app
reads them with its **managed identity** (no password to manage).

```bash
az keyvault create -n $KV -g $RG -l $LOC --enable-rbac-authorization true
KV_ID=$(az keyvault show -n $KV --query id -o tsv)

# You: permission to write secrets
az role assignment create --role "Key Vault Secrets Officer" --scope $KV_ID \
  --assignee $(az ad signed-in-user show --query id -o tsv)

# Both apps: permission to read secrets
API_PID=$(az containerapp show -n $API -g $RG --query identity.principalId -o tsv)
JOB_PID=$(az containerapp job show -n $JOB -g $RG --query identity.principalId -o tsv)
for p in $API_PID $JOB_PID; do
  az role assignment create --role "Key Vault Secrets User" --scope $KV_ID \
    --assignee-object-id $p --assignee-principal-type ServicePrincipal
done
```

Wait **2 minutes** (for the permissions to propagate). Then upload `token.json`
to Cloud Shell (**Manage files > Upload**) and run:

```bash
cd ~
az keyvault secret set --vault-name $KV -n gmail-token --file token.json
az keyvault secret set --vault-name $KV -n cv-phone --value "+32 4xx xx xx xx"   # your number, shown on the CV
rm token.json    # do not leave it in Cloud Shell

# The apps read Key Vault: references to the latest version of each secret
az containerapp job secret set -n $JOB -g $RG \
  --secrets "gmail-token=keyvaultref:https://$KV.vault.azure.net/secrets/gmail-token,identityref:system"
az containerapp job update -n $JOB -g $RG --set-env-vars GMAIL_TOKEN_JSON=secretref:gmail-token

az containerapp secret set -n $API -g $RG \
  --secrets "cv-phone=keyvaultref:https://$KV.vault.azure.net/secrets/cv-phone,identityref:system"
az containerapp update -n $API -g $RG --set-env-vars CV_PHONE=secretref:cv-phone
```

## 8. Connect the LLM (Azure AI Foundry)

The LLM powers the **Analyze** and **Generate CV** buttons. Without it, the rest still works.

1. On [ai.azure.com](https://ai.azure.com), create a Foundry resource **in your `$RG` group**.
   Note its name (for example `fdy-jobradar-ab12`).
2. **Models + endpoints > Deploy model**: `gpt-4.1-mini`,
   type **Global Standard**, deployment name `gpt-4.1-mini`.
3. Copy the resource **endpoint** (`https://....azure.com`, the rest of the path is ignored).

Then in Cloud Shell:

```bash
FOUNDRY=fdy-jobradar-ab12                                  # the name noted above
ENDPOINT=https://fdy-jobradar-ab12.services.ai.azure.com   # the endpoint you copied

# Permissions to call the model, on the Foundry ACCOUNT (not the project): both roles
FOUNDRY_ID=$(az cognitiveservices account show -n $FOUNDRY -g $RG --query id -o tsv)
for r in "Cognitive Services User" "Cognitive Services OpenAI User"; do
  az role assignment create --role "$r" --scope $FOUNDRY_ID \
    --assignee-object-id $API_PID --assignee-principal-type ServicePrincipal
done

az containerapp update -n $API -g $RG --set-env-vars \
  "AZURE_OPENAI_ENDPOINT=$ENDPOINT" "AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini"
```

No API key: the app authenticates with its managed identity.

## 9. Protect the dashboard

The dashboard holds your offers and your CV: it must not be open to everyone.

In the Azure portal: your `$API` app > **Authentication** > **Add identity provider** >
**Microsoft**:
- App registration: **Create new**.
- Supported account types: **Current tenant - Single tenant**.
- Unauthenticated requests: **HTTP 302 Found redirect**.

Note: the client secret created here expires after 24 months. Set a reminder to renew it
(Entra ID portal > App registrations > your app > Certificates & secrets).

## 10. Automatic deployment from GitHub

On every push to `main`, GitHub builds the image, updates both apps and uploads
`profile.md` and `cv_base.json` again. GitHub signs in to Azure **without a password** (OIDC).

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

In your fork on GitHub: **Settings > Secrets and variables > Actions**.

| Tab | Name | Value |
| --- | --- | --- |
| Secrets | `AZURE_CLIENT_ID` | printed above |
| Secrets | `AZURE_TENANT_ID` | printed above |
| Secrets | `AZURE_SUBSCRIPTION_ID` | printed above |
| Variables | `AZURE_RESOURCE_GROUP` | your `$RG` |
| Variables | `AZURE_API_APP` | your `$API` |
| Variables | `AZURE_JOB` | your `$JOB` |
| Variables | `AZURE_STORAGE_ACCOUNT` | your `$ST` |
| Variables | `AZURE_FILE_SHARE` | your `$SHARE` |

Then run the workflow again (**Actions > Build image > Run workflow**). The `deploy` job should turn green.

## 11. Check that everything works

```bash
# Run the routine now, without waiting for tomorrow morning
az containerapp job start -n $JOB -g $RG
# Follow the execution (Succeeded expected after 2 to 5 minutes)
az containerapp job execution list -n $JOB -g $RG -o table
```

- You should receive the digest email (if some offers are above the threshold).
- Open `$API_URL` and sign in with your Microsoft account: the offers appear.
- On an offer, click **Analyze** with a pasted description, then **Generate CV**.
- In the portal: **Cost Management > Budgets**, create a €5 monthly budget with an alert.

## 12. Common problems

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| The app does not start, image pull error | private ghcr image | step 2, item 5: make the package public |
| GitHub: `AADSTS700213 No matching federated identity record` | the "subject" does not match | GitHub sometimes uses a format with IDs (`repo:alice@123/Job-Radar@456:...`). Copy the exact subject shown in the error into the federated credential (Entra ID portal > App registrations > `gh-jobradar-deploy` > Certificates & secrets > Federated credentials). |
| Key Vault reference refused | permissions not propagated yet | wait 2 to 5 minutes and run the command again |
| Analyze: 401 error | role set on the Foundry project | the "Cognitive Services User" and "Cognitive Services OpenAI User" roles must be on the Foundry **account** (step 8), then restart the revision |
| Analyze: 404 error | wrong deployment name | `AZURE_OPENAI_DEPLOYMENT` must be the exact deployment name |
| The routine works for a week then fails (`invalid_grant`) | Google app left in test mode | step 3, item 5, then create `token.json` again and update the `gmail-token` secret |
| `database is locked` | two SQLite writers | keep `maxReplicas: 1` and the `nobrl` option (already in the templates) |
| No offers found | Gmail query too strict | check `GMAIL_QUERY` by testing it in the Gmail search bar |
| `MaxNumberOfGlobalEnvironmentsInSubExceeded` or `...Regional...` | the subscription (free trial, or upgraded from one) is limited to one Container Apps environment | reuse the existing environment: `-p existingEnvironmentName=... existingEnvironmentResourceGroup=...` (Bicep), or request a quota increase (Help + support) |
