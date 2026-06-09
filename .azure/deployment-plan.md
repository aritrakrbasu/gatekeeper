# Gatekeeper Hosted Deployment Plan

## Status
- Prepared for later deployment
- Deployment not executed in this change set

## Target Architecture
- Backend: Azure Container Apps
- Registry: Azure Container Registry with timestamped tags
- Frontend: Vercel static hosting for `frontend/gatekeeper`
- Environment model: single shared demo environment
- Release model: manual-first

## Implemented Artifacts
- Root `Dockerfile` for the FastAPI backend and local MCP dependencies
- Root `.dockerignore` to keep backend image context small
- `infra/main.bicep` to provision Azure backend infrastructure
- `infra/main.parameters.json` with editable deployment parameters
- `scripts/release-backend.ps1` for later ACR build and Container App release
- Root `.env.azure.example` for backend runtime configuration
- `frontend/gatekeeper/vercel.json` for SPA rewrites
- `frontend/gatekeeper/.env.production.example` for frontend production config
- `docs/deployment/azure-container-apps-vercel.md` as the deployment runbook

## Azure Resource Model
- Resource group contains:
  - Azure Container Registry
  - Log Analytics workspace
  - Container Apps environment
  - Public Container App for the backend
- The Container App uses a system-assigned managed identity
- The infra grants `AcrPull` to the Container App identity for the registry

## Backend Runtime Decisions
- Backend image includes both Python and Node because `services/mcp_service.py` starts Node-based MCP processes
- GitNexus startup now prefers the locally installed CLI when present, avoiding production reliance on `npx ... @latest` for that integration
- Fivetran MCP remains opt-in through `FIVETRAN_MCP_ENABLED=false` by default
- Secrets are intended to be loaded into Container Apps secrets during the later release step

## Frontend Runtime Decisions
- Vercel remains the deployment target for the Vite SPA
- Production API traffic uses `VITE_API_URL`
- SPA routes are rewritten to `index.html`

## Required Inputs Before Deployment
- Azure subscription and resource group
- Chosen resource prefix, location, backend domain, and frontend domain
- Backend env file derived from `.env.azure.example`
- Vercel project linked to `frontend/gatekeeper`
- GitLab OAuth app configured with the Vercel callback URL

## Validation To Perform Later
- Deploy infra with Bicep
- Build backend image in ACR using the release script
- Set Container App secrets and env vars from a real `.env.azure`
- Verify `GET /health`
- Verify GitLab OAuth callback end-to-end
- Verify webhook delivery to `/webhooks/gitlab`
