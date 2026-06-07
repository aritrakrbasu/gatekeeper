# Sentry Bug Fixing Pipeline - Complete Fix Summary

## Date: 2025-06-07

## Issues Identified and Fixed

### Issue 1: Missing `generate_fix` Tool
**Problem**: The planner expected a `generate_fix_step` but the tool didn't exist.

**Fix**: Added `generate_fix` tool that uses Gemini AI to generate fix code based on Sentry issue analysis.

**Files Modified**:
- `agents/tools.py` - Added generate_fix_schema and generate_fix() function
- `agents/workflows.py` - Registered tool in build_sentry_registry()
- `agents/planner.py` - Added to essential_tool_names set

### Issue 2: Invalid Template Syntax with Arithmetic
**Problem**: Planner generated templates like `{{step_id.result.field+10}}` which broke JSON validation.

**Fix**: Updated planner instruction with strict template syntax rules:
- NO arithmetic in templates
- NO complex array indexing
- Use only simple field references

**Files Modified**:
- `agents/planner.py` - Added template syntax rules

### Issue 3: Single File Path Limitation
**Problem**: When `gitnexus_grep` returned 49 files, the workflow couldn't handle multiple file paths.

**Fix**: Implemented multi-file fetching system:
- Executor auto-extracts all file paths from grep results
- gitnexus_file tool accepts both single and multiple file paths
- Fetches all files and merges their contents

**Files Modified**:
- `agents/executor.py` - Auto-extraction of file paths from grep results
- `agents/tools.py` - Multi-file schema and gitnexus_file implementation
- `agents/base_tool.py` - oneOf validation support
- `agents/planner.py` - Updated instructions to reflect multi-file capability

## How the Pipeline Works Now

```
1. Webhook Received → Sentry issue data extracted
2. Clone Repository → Code cloned to workspace
3. GitNexus Analyze → Repository indexed
4. GitNexus Grep → Search for error patterns (finds N files)
5. GitNexus File → Fetch ALL N files and merge content
6. Impact Analysis → Understand dependencies
7. Generate Fix → Use merged content to generate fix
8. Create Branch → Dedicated fix branch
9. Commit Fix → Apply fix to branch
10. Create MR → Draft merge request
```

## Key Features

### Multi-File Context
When searching for error patterns, the system now:
- Fetches ALL matching files (not just the first one)
- Merges content from all files
- Provides comprehensive context for fix generation

Example:
```python
# Grep finds 49 files with "toString"
# All 49 files are fetched and merged:
{
    'files_count': 49,
    'merged_content': '''
FILE: src/utils/timeDifference.js
...

FILE: src/utils/performanceMonitor.js
...
''',
    'individual_files': [...]
}
```

### Smart Template Resolution
The executor automatically handles:
- Simple field references: `{{step_id.result.field}}`
- Array extraction: Automatically extracts all file paths from grep results
- Type validation: Validates against oneOf schemas

### AI-Powered Fix Generation
The `generate_fix` tool:
- Analyzes merged file contents
- Considers stack trace and error context
- Generates minimal, targeted fixes
- Returns structured JSON with file_path, fixed_code, description

## Testing

Run the test script:
```bash
# Test planner only
python test_sentry_workflow.py 1

# Test full workflow
python test_sentry_workflow.py 2
```

## Expected Output

```
[INFO] Sentry workflow started
[INFO] Clone repo completed
[INFO] GitNexus analysis completed
[INFO] GitNexus grep found 49 matches
[INFO] GitNexus file fetching 49 files...
[OK] GitNexus file fetched all 49 files
[INFO] Generating fix with Gemini AI...
[OK] Fix generated for src/problematic/file.js
[INFO] Creating branch fix/sentry-...
[INFO] Committing fix...
[INFO] Creating MR...
[OK] Workflow completed successfully
```

## Environment Variables Required

```bash
# GitLab
GITLAB_BASE_URL=https://gitlab.com
GITLAB_PERSONAL_ACCESS_TOKEN=your_token

# Gemini AI
GOOGLE_GENAI_API_KEY=your_api_key

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=gatekeeper

# GitNexus
GITNEXUS_SERVER_URL=http://localhost:3000
```

## Related Documentation

- `docs/SENTRY_FIX_PIPELINE_CHANGES.md` - Initial fix implementation
- `docs/TEMPLATE_SYNTAX_FIX.md` - Template syntax fixes
- `docs/GITNEXUS_MULTI_FILE_FIX.md` - Multi-file handling
- `docs/SENTRY_WEBHOOK_DATA_FLOW.md` - Complete pipeline diagram
