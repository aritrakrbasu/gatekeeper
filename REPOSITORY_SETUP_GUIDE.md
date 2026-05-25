# Repository Management Quick Start Guide

## Overview

The Gatekeeper now supports **GitNexus integration** with two modes of operation:

1. **Option 2 (Priority)**: Pre-indexed repositories - Fastest, recommended for frequently monitored repos
2. **Option 1 (Fallback)**: Auto-index on webhook - Automatically clones and indexes when first MR arrives

## Quick Start

### Step 1: Install GitNexus

```bash
npm install -g gitnexus
```

### Step 2: Pre-Index Your Repositories (Option 2)

**Interactive Mode:**
```bash
python setup_repos.py
```

**Direct Mode:**
```bash
# Add a repository
python setup_repos.py add my-project https://gitlab.com/your-org/your-project

# Pre-index all configured repositories
python setup_repos.py index

# Check status
python setup_repos.py status
```

### Step 3: Start Gatekeeper

```bash
python main.py
```

Gatekeeper will now:
1. ✅ Check for pre-indexed repositories first (fast)
2. ✅ Fall back to auto-index if not found (automatic)

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    GitLab Remote Repository                 │
│  MR Opened → Webhook → Gatekeeper                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  Gatekeeper (Local)                         │
│                                                             │
│  1. Receive webhook                                        │
│     ↓                                                       │
│  2. Check if repository is pre-indexed                      │
│     ├─ Yes → Use immediately (fast!)                       │
│     └─ No → Auto-clone and index (Option 1 fallback)       │
│     ↓                                                       │
│  3. Run analysis with GitNexus context                     │
│  4. Post review to MR                                      │
│                                                             │
│  Local Storage:                                             │
│  workspace/projects/                                        │
│  ├── project_123/        ← Cloned repository                │
│  │   └── .gitnexus/      ← GitNexus knowledge graph        │
│  └── project_456/                                         │
│      └── .gitnexus/                                        │
└─────────────────────────────────────────────────────────────┘
```

## Repository Management Commands

### Add a Repository

```bash
# Interactive
python setup_repos.py add

# Direct
python setup_repos.py add <repo-id> <gitlab-url> [--branch main] [--token TOKEN]

# Example
python setup_repos.py add backend-api https://gitlab.com/company/backend-api

# With private token
python setup_repos.py add private-repo https://gitlab.com/company/private-repo --token glpat_xxx
```

### List All Repositories

```bash
python setup_repos.py list
```

Output:
```
Repository ID               Project ID   Cloned   Indexed
-----------------------------------------------------------------
backend-api                 12345678     ✅       ✅
frontend-app                87654321     ✅       ❌
```

### Pre-Index All Repositories

```bash
python setup_repos.py index
```

This will:
- Clone any repositories that aren't already cloned
- Run `gitnexus analyze` on each repository
- Take 1-5 minutes per repository (depending on size)

### Check Status

```bash
# All repositories
python setup_repos.py status

# Specific repository
python setup_repos.py status backend-api
```

### Remove a Repository

```bash
python setup_repos.py remove backend-api
```

## Configuration File

Repositories are stored in `config/repositories.json`:

```json
{
  "backend-api": {
    "project_id": "12345678",
    "gitlab_url": "https://gitlab.com/company/backend-api",
    "branch": "main",
    "private_token": null,
    "auto_update": true
  }
}
```

You can edit this file directly or use the CLI commands.

## Workflow Examples

### Example 1: First Time Setup

```bash
# 1. Add your repositories
python setup_repos.py add backend https://gitlab.com/company/backend
python setup_repos.py add frontend https://gitlab.com/company/frontend

# 2. Pre-index them (do this overnight for large repos)
python setup_repos.py index

# 3. Start Gatekeeper
python main.py
```

### Example 2: Add New Repository to Running System

```bash
# Add and index immediately
python setup_repos.py add new-service https://gitlab.com/company/new-service --index

# Gatekeeper will automatically use it on next webhook
```

### Example 3: Update Existing Repositories

Repositories are automatically updated when `auto_update: true` (default).

To manually update:
```bash
cd workspace/projects/project_123
git fetch origin
git reset --hard origin/main
gitnexus analyze --force
```

## Troubleshooting

### Repository Not Found

**Problem**: `Repository {project_id} not found`

**Solution**: Add the repository first:
```bash
python setup_repos.py add <id> <url>
python setup_repos.py index
```

### GitNexus Not Found

**Problem**: `GitNexus not found - skipping indexing`

**Solution**: Install GitNexus:
```bash
npm install -g gitnexus
```

### Clone Failed (Private Repository)

**Problem**: `Authentication failed`

**Solution**: Add a private access token:
```bash
python setup_repos.py add <id> <url> --token glpat_your_token
```

### Index Taking Too Long

**Problem**: Large repository taking 10+ minutes

**Solution**: Use `--skip-embeddings` for faster indexing:
```bash
cd workspace/projects/project_123
gitnexus analyze --skip-embeddings
```

### Out of Disk Space

**Problem**: Repositories taking too much space

**Solution**:
```bash
# Remove specific repository
python setup_repos.py remove <id> --force

# Or clean workspace
rm -rf workspace/projects/*
```

## Best Practices

1. **Pre-Index Frequently Monitored Repositories**
   - Run `python setup_repos.py index` for your main repositories
   - Schedule this to run overnight for large codebases

2. **Use Descriptive Repository IDs**
   - Good: `backend-api`, `frontend-app`, `data-pipeline`
   - Bad: `repo1`, `repo2`, `test`

3. **Keep Repositories Updated**
   - Repositories with `auto_update: true` update automatically
   - Run `gitnexus analyze` after major changes

4. **Monitor Disk Space**
   - Check workspace size: `du -sh workspace/projects/`
   - Remove unused repositories: `python setup_repos.py remove <id> --force`

5. **Use Environment Variables for Tokens**
   ```bash
   export GITLAB_PERSONAL_ACCESS_TOKEN=glpat_your_token
   ```

## Integration with Gatekeeper

When a webhook arrives, Gatekeeper:

1. Checks if repository is pre-indexed in `workspace/projects/`
2. If found → Uses immediately (Option 2)
3. If not found → Automatically clones and indexes (Option 1)
4. Passes repository path to GitNexus for impact analysis
5. Continues with normal review pipeline

The impact analysis will include:
- Blast radius analysis (what depends on changed code)
- Process tracing (execution flows)
- Symbol context (incoming/outgoing references)

## API Usage

For programmatic access:

```python
from repo_manager import get_repo_manager

manager = get_repo_manager()

# Add a repository
manager.add_repository(
    repo_id="my-service",
    gitlab_url="https://gitlab.com/company/my-service"
)

# Ensure repository is ready
local_path = await manager.ensure_repository_ready(
    project_id="12345678",
    gitlab_url="https://gitlab.com/company/my-service"
)

# Check status
status = manager.get_status()
print(status)
```

## Next Steps

1. Install GitNexus: `npm install -g gitnexus`
2. Add your repositories: `python setup_repos.py add`
3. Pre-index: `python setup_repos.py index`
4. Start Gatekeeper: `python main.py`

Your Gatekeeper is now ready for enhanced impact analysis! 🚀
