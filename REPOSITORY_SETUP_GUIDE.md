# Developer Setup Guide (Cross-Platform)

Welcome to **The Gatekeeper**! This orchestrator integrates MongoDB, GitLab, and GitNexus to automatically audit GitLab Merge Requests, run pre-review impact analysis, and open automated code remediation (auto-fix) PRs.

Follow these steps to set up the codebase on macOS, Linux, or Windows.

---

## Prerequisites
1. **Python 3.8+** (Python 3.13 is fully tested)
2. **Node.js** and **npm** (v10+ / v20+)
3. **Git** installed on your system

---

## Step 1: Python Environment Setup

1. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   ```
2. **Activate the virtual environment:**
   * **macOS/Linux:**
     ```bash
     source venv/bin/activate
     ```
   * **Windows:**
     ```cmd
     venv\Scripts\activate.bat
     ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Step 2: Node.js (MCP) Packages Setup

The Gatekeeper uses MCP (Model Context Protocol) servers to communicate with GitLab, MongoDB, and GitNexus. These packages are installed locally in the project to support execution without requiring global node root permissions.

1. **Install Node dependencies:**
   * If you encounter permissions errors (`EACCES` or `EPERM`) during global installations or default npm installations, use the local cache flag to bypass global directory write locks:
     ```bash
     npm install --save-dev --cache ./npm-cache
     ```
   * *Note: This installs `mongodb-mcp-server`, `@zereight/mcp-gitlab`, and `gitnexus` directly into your local `node_modules` directory.*

---

## Step 3: Configure Environment Variables

Create or update the `.env` file in the root directory:

```env
PORT=8000
GEMINI_API_KEY=AIzaSy...your_gemini_api_key...
MDB_MCP_CONNECTION_STRING=mongodb+srv://...your_mongodb_uri...

# IMPORTANT: The GitLab Token must be valid, active, and have the `api` scope.
# Expired or unauthorized tokens will cause GitLab API calls to return 404 (Project Not Found).
GITLAB_PERSONAL_ACCESS_TOKEN=glpat-your_personal_access_token_here
```

---

## Step 4: Verify the Setup

1. **Verify Impact Analysis tools & GitNexus:**
   ```bash
   python setup_impact_analysis.py
   ```
   *Expected Output:*
   ```text
   ============================================================
   Setup Summary
   ============================================================
   [✅] Basic setup complete!
   [✅] GitNexus integration available via MCP
   [✅] Impact analysis features are ready to use!
   ```

2. **Verify Repository configurations:**
   Check the status of monitored repositories:
   ```bash
   python setup_repos.py status
   ```

---

## Step 5: Monitoring repositories (Adding and Indexing)

To add a GitLab repository for Gatekeeper to monitor, run:
```bash
# Add and pre-index the repository
python setup_repos.py add <project_id_or_descriptive_name> <gitlab_url> --index
```
*Example:*
```bash
python setup_repos.py add rapid-agents-test https://gitlab.com/Swapnendu003/rapid-agents-test --index
```

---

## Step 6: Start Gatekeeper

Once configured, launch the FastAPI server:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## How to Test Your Integration

To test that webhooks are processed correctly:
1. Open a tunnel to your local server (since GitLab.com needs to send POST requests to a public address):
   * **Pinggy (Fastest, zero install):**
     ```bash
     ssh -R 80:localhost:8000 free.pinggy.io
     ```
   * **Ngrok:**
     ```bash
     ngrok http 8000
     ```
2. Set up the webhook URL in your GitLab Repository under **Settings** ➡️ **Webhooks**:
   * URL: `https://your-public-tunnel-domain.link/webhooks/gitlab`
   * Trigger: Select **Merge request events** (uncheck Push events).
3. Push a branch introducing a test vulnerability (e.g. hardcoded secrets or raw credential logging) and open a **Merge Request**.
4. Check the MR to view Gatekeeper's comments and check your terminal logs to observe the automated remediation branches!
