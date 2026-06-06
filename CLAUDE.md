# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Gatekeeper** is an AI-powered GitLab Merge Request orchestrator built with FastAPI (backend), React (frontend), and a custom agent framework. It provides automated code reviews, incident management, and auto-remediation workflows using Google Gemini AI.

### Architecture

```
├── main.py                 # FastAPI application entry point
├── api_models.py          # Pydantic models for API validation
├── agents/                # Agent framework (workflow engine, planning, execution)
├── services/              # Business logic services
├── config/                # Observability configuration (Arize/Phoenix)
├── frontend/gatekeeper/   # React frontend (Vite)
└── prompts/               # AI prompt templates
```

### Key Technologies

- **Backend**: FastAPI, Uvicorn, Pydantic, Motor (MongoDB async)
- **AI**: Google GenAI (Gemini), Arize/Phoenix observability
- **Frontend**: React 19, Vite, TanStack Query, Tailwind CSS
- **Agent Framework**: Custom ReAct-style workflow engine with MCP integration
- **Observability**: OpenInference tracing, Phoenix Cloud, LLM-as-a-Judge

## Common Development Commands

### Backend

```bash
# Install dependencies
npm run setup-python  # or: pip install -r requirements.txt

# Development server (with auto-reload)
npm run dev:api       # or: uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production server
npm start             # or: uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
# Install dependencies
cd frontend/gatekeeper && npm install

# Development server
npm run dev           # Vite on port 5173

# Build for production
npm run build

# Lint
npm run lint
```

### Testing

```bash
# Run the main test suite
python test.py

# Test specific agent workflows
python -c "import asyncio; from agents import run_mr_review_workflow; asyncio.run(run_mr_review_workflow())"
```

## Agent Framework Architecture

The `agents/` directory contains a custom agent framework for orchestrating complex workflows:

### Core Components

1. **WorkflowEngine** (`agents/engine.py`): Main orchestrator running the planning-execution-reflection loop
   - Generates initial plans using the Planner
   - Executes steps via Executor with dependency resolution
   - Applies reflection after each step
   - Supports human approval gates and recovery from failures
   - Can resume paused tasks from saved state

2. **Planner** (`agents/planner.py`): Generates execution plans using ReAct-style reasoning
   - Uses Gemini AI to create step-by-step plans from objectives
   - Respects tool registry capabilities
   - Incorporates semantic memory from past executions

3. **Executor** (`agents/executor.py`): Executes individual steps with error handling
   - Runs tools from the registry
   - Captures output in memory store
   - Supports retry logic

4. **MemoryStore** (`agents/memory.py`): Persistent execution tracing
   - Logs all messages and tool calls to MongoDB
   - Supports semantic search for similar incidents/fixes
   - Enables learning from past executions

5. **ToolRegistry** (`agents/registry.py`): Manages available tools (local and MCP)
   - Built-in tools: file operations, GitLab API, HTTP
   - MCP wrappers: GitLabMCPTool, MongoMCPTool, DynatraceMCPTool, GitNexusMCPTool

6. **Layers**:
   - `ReflectionLayer` - Analyzes results and suggests next actions
   - `HumanApprovalLayer` - Gates execution on human approval for destructive operations
   - `FailureRecoveryManager` - Handles errors with retry strategies

### Pre-built Workflows (`agents/workflows.py`)

- `run_mr_review_workflow()` - Automated merge request code review
- `run_incident_workflow()` - Incident analysis and remediation
- `run_auto_remediation_workflow()` - Automated fix application

### Using the Agent Framework

```python
from agents import WorkflowEngine, build_default_registry, ContextBuilder

# Build tool registry with MCP tools
registry = await build_default_registry()

# Create context
context = ContextBuilder() \
    .with_objective("Analyze MR #123") \
    .with_task_id("task-123") \
    .build()

# Run workflow
engine = WorkflowEngine(registry)
result = await engine.run_task(context)
```

## Services Architecture

The `services/` directory contains business logic modules:

- **review_service.py** - Orchestrates MR review pipeline using Gemini AI
- **gemini_service.py** - Google GenAI client wrapper with observability
- **mcp_service.py** - MCP server and bridge initialization
- **auth_service.py** - GitLab OAuth authentication and JWT handling
- **repository_service.py** - Repository sync and webhook management
- **billing_service.py** - Usage tracking and invoice generation
- **incident_service.py** - Incident creation and management
- **impact_measurement_service.py** - Change impact analysis
- **remediation_service.py** - Automated fix generation
- **mongo_client.py** - MongoDB connection singleton

## Observability (Arize/Phoenix)

The application includes comprehensive AI observability:

- **OpenInference Tracing**: All Gemini calls are automatically traced via `arize-otel`
- **Phoenix Cloud**: Centralized observability dashboard at https://app.phoenix.arize.com
- **Phoenix MCP Bridge**: Self-introspection via `config/phoenix_mcp.py`
- **LLM-as-a-Judge**: Automatic evaluation of review quality
- **Self-Improvement**: Prompt versioning and A/B testing

### Configuration (.env)

```bash
# Arize AI Observability
ARIZE_SPACE_ID=your_space_id
ARIZE_API_KEY=your_api_key

# Phoenix Cloud
PHOENIX_MODE=cloud
PHOENIX_API_KEY=your_phoenix_key
PHOENIX_BASE_URL=https://app.phoenix.arize.com

# Feature Flags
ENABLE_EVALUATIONS=true
ENABLE_SELF_IMPROVEMENT=true
JUDGE_MODEL=gemini-3-flash-preview
```

### Initialization Code

Located in `config/arize_config.py` and `config/arize_client.py`. The observability is initialized at application startup in `main.py`.

## Environment Variables

Key variables in `.env`:

```bash
# Server
PORT=8000
FRONTEND_URL=http://localhost:3000

# GitLab
GITLAB_URL=https://gitlab.com
GITLAB_APP_ID=your_app_id
GITLAB_SECRET=your_secret

# Google AI
GOOGLE_GENAI_USE_GDC=true
GCP_PROJECT_ID=your_project
GCP_LOCATION=us-central1

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=gatekeeper

# Arize/Phoenix (see Observability section above)
```

## Frontend Architecture

React application with:
- **React Router** for navigation
- **TanStack Query** for API state management
- **Framer Motion** for animations
- **Lucide React** for icons
- **Tailwind CSS** for styling
- **React Markdown** for rendering AI-generated content

### API Integration

Frontend communicates with backend via REST endpoints defined in `main.py`. All endpoints are prefixed with `/api/`.

### Key Frontend Directories

- `src/pages/` - Route components
- `src/components/` - Reusable UI components
- `src/contexts/` - React context providers
- `src/hooks/` - Custom hooks
- `src/services/` - API client functions
- `src/utils/` - Utility functions

## Webhook Handling

GitLab webhooks are received at `/webhooks/gitlab`. The webhook handler:
1. Validates the webhook signature
2. Extracts MR metadata
3. Triggers the review pipeline via `review_service.py`
4. Posts results back to GitLab as comments

## MCP Integration

The application uses MCP (Model Context Protocol) for tool integration:

- **GitLab MCP** - `@zereight/mcp-gitlab` npm package
- **MongoDB MCP** - `mongodb-mcp-server` npm package
- **GitNexus MCP** - Custom integration via `agents/mcp_wrappers.py`

MCP servers are initialized in `services/mcp_service.py`.

## Development Notes

### Windows Console Fix

The application includes a Windows console encoding fix in `main.py` to handle emoji characters correctly.

### Event Loop Policy

On Windows, the event loop policy is set to `WindowsSelectorEventLoopPolicy` to fix subprocess issues with asyncio.

### MongoDB Collections

- `agent_execution_traces` - Agent workflow execution logs
- `users` - User profiles
- `repositories` - Synced repositories
- `incidents` - Incident records
- `billing_usage` - Usage tracking for billing

### Prompt Templates

Base prompts are stored in `prompts/` directory. The prompt manager in `ai_observability/` handles versioning and A/B testing.

## Related Documentation

- `TESTING_GUIDE.md` - Comprehensive testing guide for Arize/Phoenix features
- `ARIZE_SETUP.md` - Detailed observability setup instructions
- `.env.example` - Environment variable template
