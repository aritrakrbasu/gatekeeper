# Gatekeeper Deployment Runbook

This repository is now prepared for deployment, but nothing in this change set performs a live deployment.

## What Was Added

- Backend containerization with a root `Dockerfile`
- Backend image context control with `.dockerignore`
- Azure infrastructure definition in `infra/main.bicep`
- Example infrastructure parameters in `infra/main.parameters.json`
- Backend release helper in `scripts/release-backend.ps1`
- Backend env template in `.env.azure.example`
- Vercel SPA routing config in `frontend/gatekeeper/vercel.json`
- Frontend production env template in `frontend/gatekeeper/.env.production.example`

## Deployment Shape

- Backend runs as one Azure Container App
- Backend images are built inside Azure Container Registry
- Backend release tags use `yyyyMMdd-HHmmss`
- Frontend is deployed separately from `frontend/gatekeeper` to Vercel
- The backend is the public webhook receiver for connected GitLab repositories

## Backend Preparation

1. Copy `.env.azure.example` to `.env.azure`.
2. Fill in the real values for:
   - `FRONTEND_URL`
   - `GATEKEEPER_WEBHOOK_URL`
   - `GITLAB_REDIRECT_URI`
   - `SECRET_KEY`
   - `GITLAB_CLIENT_ID`
   - `GITLAB_CLIENT_SECRET`
   - `MDB_MCP_CONNECTION_STRING`
3. Leave `FIVETRAN_MCP_ENABLED=false` unless you are explicitly packaging and enabling that integration.
4. Keep Arize and Phoenix values blank if you want the app to start without those integrations.

## Azure Infra Bootstrap

Edit `infra/main.parameters.json` before first deployment:

- `location`
- `resourcePrefix`
- `frontendUrl`

When you are ready to create infra later, the intended command flow is:

```powershell
az login
az account set --subscription <subscription-id>
az group create --name <resource-group> --location <location>
az deployment group create `
  --resource-group <resource-group> `
  --template-file infra/main.bicep `
  --parameters "@infra/main.parameters.json"
```

The Bicep template provisions:

- ACR
- Log Analytics
- Container Apps environment
- Public backend Container App
- `AcrPull` access from the Container App identity to ACR

## Backend Release Flow

Later, when you are ready to release the backend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release-backend.ps1 `
  -ResourceGroupName <resource-group> `
  -Location <location> `
  -ResourcePrefix <resource-prefix> `
  -EnvFilePath .env.azure
```

What the script does:

1. Generates a timestamp tag.
2. Builds the backend image in ACR.
3. Loads secrets and plain env vars from `.env.azure`.
4. Stores secrets in Container Apps secrets.
5. Updates the Container App image and env vars.
6. Prints the backend URL.

Use `-BootstrapInfra` if you want the script to create the resource group and deploy the Bicep template first.

## Frontend Release Flow

1. In Vercel, point the project root to `frontend/gatekeeper`.
2. Set `VITE_API_URL` from `frontend/gatekeeper/.env.production.example`.
3. Deploy the frontend.
4. Confirm that `/login`, `/auth/callback`, `/dashboard`, and `/repositories` work with direct navigation.

`frontend/gatekeeper/vercel.json` ensures SPA routes rewrite to `index.html`.

## Post-Deployment Configuration

After the backend and frontend are live:

1. Set `FRONTEND_URL` in the backend to the real Vercel domain.
2. Set `GATEKEEPER_WEBHOOK_URL` to `https://<backend-domain>/webhooks/gitlab`.
3. Set the GitLab OAuth callback URL to `https://<frontend-domain>/auth/callback`.
4. Reconnect or onboard GitLab repositories so their webhooks point to the hosted backend.

## Important Operational Notes

- The backend container includes both Python and Node because runtime MCP processes depend on both.
- `services/mcp_service.py` now prefers the locally installed GitNexus CLI for MCP startup when available, which is safer for containerized environments than relying on `npx ... @latest`.
- Fivetran remains intentionally disabled by default for the hosted deployment until its MCP/runtime packaging is finalized.
- This runbook assumes manual releases first. CI/CD can be added after the first successful hosted deployment.
