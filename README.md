# 🛡️ The Gatekeeper: Gemini Webhook Reviewer & Auto-Remediator

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![AI Engine](https://img.shields.io/badge/AI-Gemini%203.5%20Flash-red.svg)](https://deepmind.google/technologies/gemini/)

**The Gatekeeper** is an automated Model Context Protocol (MCP) powered code reviewer and security auditor. It sits in your GitLab CI/CD pipeline, intercepts Merge Requests (MRs) via webhooks, performs deep AST-based impact analysis, audits the code using Gemini Pro, and autonomously creates hunk-level remediation PRs to fix security vulnerabilities (like hardcoded keys or unhashed credentials) before merge.

---

## 🚀 Key Features

* **🧠 Gemini Pro Audit Engine**: Leverages the official Google Gen AI Client (`gemini-3.5-flash`) to review MR changes for performance, code quality, and security vulnerabilities.
* **🔌 Stdio MCP Bridge Core**: Automatically coordinates concurrent pipes with:
  - **GitLab MCP**: To fetch project structures, pull MR diff files, write review comments, and toggle green/red commit check marks.
  - **MongoDB MCP**: To log audit trails, metadata signatures, and patch history.
  - **GitNexus MCP**: To index repositories and analyze blast radius.
* **🎯 Pre & Post-Review Impact Analysis**:
  - Calculates the **blast radius** of changes to locate code dependencies and call-chains outside the modified diff.
  - Detects breaking API changes and configuration alterations.
  - Falls back to built-in AST Python code analysis if GitNexus is not available.
* **🔧 Atomic Auto-Fix (Hunk-Level Remediations)**:
  - Parses code diffs into granular, independently applicable hunks (`atomic_patches.py`).
  - Utilizes Gemini's JSON schema-enforced output to design drop-in replacements.
  - Automatically extracts hardcoded secrets into a `.env` file, updates `.gitignore`, commits changes, and opens a separate **Remediation Merge Request** against the developer's branch.

---

## 🛠️ System Architecture

```
                       ┌─────────────────────────────────────────────────────────────┐
                       │                     GitLab Repository                       │
                       │   Merge Request Opened ──► Webhook Triggered                │
                       └─────────────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
                       ┌─────────────────────────────────────────────────────────────┐
                       │                Gatekeeper Server (FastAPI)                  │
                       │                                                             │
                       │  1. Receive Webhook & Log Metadata (MongoDB MCP)            │
                       │  2. Fetch MR Diff & Repository (GitLab MCP)                │
                       │  3. Analyze blast radius & API changes (GitNexus MCP/AST)   │
                       │  4. Run Security Audit & code review (Gemini API)           │
                       │  5. Generate Hunk-Level patches & open Auto-Fix MRs         │
                       │  6. Post final Review Report and Commit Status check        │
                       └─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ Quick Start

### 1. Installation
Check out the detailed [Developer Setup Guide](file:///Volumes/Biryani/gatekeeper/REPOSITORY_SETUP_GUIDE.md) for full installation instructions.
```bash
# Clone the repository and setup venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install local MCP node dependencies
npm install --save-dev --cache ./npm-cache
```

### 2. Configure Environment
Set up your `.env` file:
```env
PORT=8000
GEMINI_API_KEY=your_gemini_api_key_here
MDB_MCP_CONNECTION_STRING=mongodb+srv://...your_mongodb_connection...
GITLAB_PERSONAL_ACCESS_TOKEN=glpat-your_access_token_here
```

### 3. Add and Pre-Index Your Repositories
```bash
python setup_repos.py add my-project https://gitlab.com/username/my-project --index
```

### 4. Run the Server
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 👥 Contributors

This project is built and maintained with ❤️ by:

* **Aritra Basu**
* **Swapnendu Banerjee**
* **Sagnik Datta**

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
