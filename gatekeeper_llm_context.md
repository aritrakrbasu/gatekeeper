# Gatekeeper System Context & Execution Flow

This document outlines the system architecture, file structure, and step-by-step execution flow of **The Gatekeeper** code audit and auto-remediation service. It is designed to serve as system context for another Large Language Model (LLM).

---

## 1. High-Level Architecture & Stack
* **Framework**: FastAPI (Python 3.x)
* **Databases**: MongoDB (logs webhooks via stdio MCP bridge)
* **Integrations**: GitLab (reads diffs, posts review comments, manages PR branches), GitNexus (performs pre-review static analysis)
* **AI Engine**: Gemini Pro API (analyzes security vulnerabilities, generates structured hunk-level auto-fixes)
* **Interprocess Communication**: Model Context Protocol (MCP) stdio servers running locally:
  * MongoDB MCP Server: `mongodb-mcp-server/dist/esm/index.js`
  * GitLab MCP Server: `@zereight/mcp-gitlab/build/index.js`
  * GitNexus MCP Server: `gitnexus` CLI

---

## 2. Directory Layout & Module Responsibilities

```
gatekeeper/
├── main.py                     # FastAPI entry point, defines startup hooks and API endpoints.
├── requirements.txt            # Python dependencies (fastapi, uvicorn, pymongo, google-genai, python-dotenv).
├── package.json                # Local Node dependencies (MongoDB/GitLab MCP clients, GitNexus CLI).
├── setup_repos.py              # CLI tool to register, list, and index GitLab repositories.
├── setup_impact_analysis.py    # Helper script to test and verify local GitNexus installation.
├── repo_manager.py             # Handles local workspace directory setups and git clones.
├── impact_analysis.py          # Performs AST / static analysis of diffs to determine change severity.
├── atomic_patches.py           # Parser to read unified diff format and extract code hunks.
├── services/
│   ├── __init__.py             # Module initializer.
│   ├── mcp_service.py          # Initializes and holds stdio pipes/sessions for MongoDB, GitLab, and GitNexus.
│   ├── gemini_service.py       # Handles communication with Gemini API (loads prompts, requests reviews & fixes).
│   ├── remediation_service.py  # Applies hunk-level diff patches, creates fix branches, commits, and opens MRs.
│   └── review_service.py       # Pipeline orchestrator coordinating the entire analysis flow.
└── test_project/               # Nested repository containing intentionally vulnerable mock endpoints for testing.
```

---

## 3. End-to-End Execution Flow (MR Webhook Event)

When a developer opens or updates a Merge Request in GitLab, the following sequential pipeline executes:

```mermaid
sequenceDiagram
    autonumber
    participant GitLab as GitLab Webhook
    participant Main as main.py (FastAPI)
    participant Review as review_service.py
    participant MCP as mcp_service.py
    participant Repo as repo_manager.py
    participant Impact as impact_analysis.py
    participant Schema as schema_inspection_service.py
    participant Gemini as gemini_service.py
    participant Remed as remediation_service.py

    GitLab->>Main: POST /webhooks/gitlab (MR payload)
    Main->>Review: orchestrate_review(payload)
    
    Note over Review,MCP: Step 1: Log Signature
    Review->>MCP: mongo_session.call_tool("insert-many", collection="intercepted_mrs")
    
    Note over Review,Repo: Step 2: Prepare Repository
    Review->>Repo: get_repo_manager().clone_or_update(git_url)
    
    Note over Review,Impact: Step 3: Pre-Review AST Analysis
    Review->>Impact: run_pre_review_analysis(diff)
    Impact-->>Review: return ImpactLevel (Low/Medium/High)

    Note over Review,Schema: Step 3.5: Database Schema & Drift Inspection
    Review->>Schema: run_schema_inspection(diff)
    Schema->>MCP: mongo_session.call_tool("find", last_snapshot)
    Schema->>MCP: mongo_session.call_tool("collection-schema", target_collections)
    Schema->>MCP: mongo_session.call_tool("collection-indexes", target_collections)
    Schema-->>Review: return SchemaInspectionReport (with delta drift)
    Review->>MCP: mongo_session.call_tool("insert-many", log_new_snapshot)

    Note over Review,Gemini: Step 4: Run Gemini Security Audit
    Review->>Gemini: run_gemini_review(diff + schema_markdown)
    Gemini-->>Review: return markdown security report

    Note over Review,Impact: Step 5: Post-Review Integrity Check
    Review->>Impact: run_post_review_validation(audit_report)

    Note over Review,MCP: Step 6: Post Findings to GitLab
    Review->>MCP: gitlab_session.call_tool("create_merge_request_note", body=audit_report)
    Review->>MCP: gitlab_session.call_tool("post_commit_status", state="failed/success")

    Note over Review,Gemini: Step 7: Generate Auto-Fixes (if unsafe)
    Review->>Gemini: run_gemini_fix_analysis(audit_report, patch_summary, schema_context)
    Gemini-->>Review: return list of structured hunk repairs (JSON)

    Note over Review,Remed: Step 8: Apply Remediation & Push
    Review->>Remed: apply_auto_fixes(fixing_hunks)
    Remed->>Remed: Apply hunk patches to files, add env/gitignore modifications
    Remed->>MCP: gitlab_session.call_tool("create_branch", name="gatekeeper/atomic-fix-...")
    Remed->>MCP: gitlab_session.call_tool("commit_changes")
    Remed->>MCP: gitlab_session.call_tool("create_merge_request", source_branch="gatekeeper/...")
```

---

## 4. Specific Webhook Pipeline Logic Details

### Webhook Event Filters
* The orchestrator filters out any MR events that are not in the `"opened"` state.
* The orchestrator ignores incoming webhook requests originating from source branches prefixed with `"gatekeeper/"` to prevent recursive, infinite loop reviews.

### Database Schema Drift & Inspection Engine (Step 3.5)
* **Backend Change Detection**: Scans unified diff headers for models/migrations folders and matches added lines (`+` statements) in diff bodies for MongoDB operations (e.g., `.insert_one(`, `.find(`, `db[`).
* **Confidence Gating**:
  * `HIGH` (Models/Migrations path match) -> full MCP inspection (falls back to all collections if scoping yields nothing).
  * `MEDIUM` (Soft path match or keyword content match) -> scoped MCP inspection only (no fallback).
  * `LOW` (Config file single-occurrence keyword match) -> skips MCP queries entirely.
* **Decoupled Collection Discovery**: Parses target collections directly from the code diff stream using regular expressions, eliminating the need to execute the broad `list-collections` MCP tool call.
* **Drift Comparison**: Queries `schema_snapshots` collection for the latest logged baseline for the current project, computes differences (added/removed collections, added/removed fields, field type transformations), and injects the delta warnings directly into the Gemini prompt (both for review and auto-fix patch generation phases).

### Hunk-Level Remediation Structure
Gemini is prompted to return suggested auto-fixes formatted in a strict JSON schema conforming to the following structure:
```json
{
  "explanation": "Why this fix is being applied",
  "modifications": [
    {
      "filePath": "path/to/file.py",
      "startLine": 12,
      "endLine": 15,
      "originalCode": "...",
      "newCode": "..."
    }
  ]
}
```
`remediation_service.py` iterates over these modifications, verifies that the `originalCode` block matches the file content, performs safe in-place replacement, writes secrets to `.env`, and updates `.gitignore`.

---

## 5. Development & Execution Commands

### Run FastAPI Audit Server
Starts the orchestrator server locally on port 8000:
```bash
venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Register/Manage GitLab Repositories
Add a GitLab repository configuration to monitor:
```bash
venv/bin/python setup_repos.py add <project_id> <gitlab_repository_url>
```
Force pre-indexing and analyze codebase structures using GitNexus:
```bash
venv/bin/python setup_repos.py index
```
