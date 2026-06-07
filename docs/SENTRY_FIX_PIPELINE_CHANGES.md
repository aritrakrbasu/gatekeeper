# Sentry Bug Fixing Pipeline - Fix Summary

## Date: 2025-06-07

## Problem Identified

The Sentry bug fixing pipeline was **incomplete** and could not function properly because:

1. **Missing `generate_fix` Tool**: The planner instruction (`agents/planner.py` lines 137-143) explicitly told Gemini AI to create a `generate_fix_step`, but this tool didn't exist in the codebase.

2. **Broken Workflow Chain**: Without this critical tool, the workflow could not convert analysis results into actual fix code, causing the pipeline to fail after analysis steps.

3. **Registry Mismatch**: The tool wasn't registered in `build_sentry_registry()` and wasn't in the planner's `essential_tool_names` set.

## Solution Implemented

### 1. Added `generate_fix` Tool (`agents/tools.py`)

Created a new tool that:
- Uses Gemini AI to generate fix code based on Sentry issue analysis
- Takes parameters: `sentry_issue_id`, `sentry_title`, `stack_trace`, `culprit`, `problem_type`, `analysis_findings`, `file_path`
- Returns structured JSON: `{file_path, fixed_code, description}`
- Handles both code problems (TypeError, null references) and MongoDB problems (schema validation)

**Location**: `agents/tools.py` lines 619-748

### 2. Registered Tool in Sentry Workflow Registry (`agents/workflows.py`)

Added registration in `build_sentry_registry()`:

```python
# AI Fix Generation tool
registry.register_local_tool("generate_fix", tools.generate_fix_schema, tools.generate_fix)
```

**Location**: `agents/workflows.py` line 301

### 3. Added to Planner Essential Tools (`agents/planner.py`)

Added `'generate_fix'` to the `essential_tool_names` set so Gemini can see and use it.

**Location**: `agents/planner.py` line 469

## How the Pipeline Now Works

When a Sentry webhook fires:

1. ✅ **Webhook Receipt**: `/webhooks/sentry` receives the error event
2. ✅ **Payload Normalization**: Extract issue_id, title, stack_trace, culprit
3. ✅ **Breaking Bug Check**: Validates it's a production error/fatal
4. ✅ **Context Building**: Creates SentryIssueContext with all details
5. ✅ **Tool Registry**: Builds registry with all tools including `generate_fix`
6. ✅ **AI Planning**: Gemini generates execution plan with proper steps
7. ✅ **Execution**:
   - `clone_repo_step`: Clone repository to workspace
   - `gitnexus_analysis_step`: Index repository for searching
   - `gitnexus_grep_step`: Find error-related code
   - `gitnexus_file_step`: Read full file content for context
   - `impact_analysis_step`: Understand dependencies (optional)
   - **`generate_fix_step`**: Generate fix code using AI analysis ← NEW!
   - `create_branch_step`: Create fix branch in GitLab
   - `commit_fix_step`: Commit the fixed code
   - `create_mr_step`: Create merge request with fix
8. ✅ **Result**: Return MR URL to Sentry webhook

## Testing

To test the fixed pipeline:

```bash
# Run the planner test only
python test_sentry_workflow.py 1

# Run the full workflow test
python test_sentry_workflow.py 2
```

## Expected Output

When a Sentry webhook is received, you should see:
```
[INFO] [Planner] Detected workflow type: sentry
[INFO] [Planner] Using 14 essential tools (including generate_fix)
[INFO] [Executor] Executing step 'generate_fix_step' using tool 'generate_fix'...
[INFO] [generate_fix] Calling Gemini AI to generate fix for issue ...
[OK] [generate_fix] Successfully generated fix for src/file.js
[INFO] [Executor] Step 'generate_fix_step' completed successfully
```

## Files Modified

1. `agents/tools.py` - Added `generate_fix_schema` and `generate_fix()` function
2. `agents/workflows.py` - Registered `generate_fix` tool in `build_sentry_registry()`
3. `agents/planner.py` - Added `'generate_fix'` to `essential_tool_names` set

## Next Steps

1. **Test the workflow** with the provided test script
2. **Configure environment variables** for:
   - `GITLAB_PERSONAL_ACCESS_TOKEN` (for GitLab API calls)
   - `GOOGLE_GENAI_API_KEY` (for Gemini AI)
   - `MONGODB_URI` (for execution traces)
3. **Verify MCP sessions** are ready before triggering webhooks
4. **Monitor first webhook** to ensure end-to-end flow works

## Related Documentation

- `docs/SENTRY_WEBHOOK_DATA_FLOW.md` - Complete pipeline diagram
- `test_sentry_workflow.py` - Test scripts for validation
- `docs/SENTRY_WEBHOOK_INTEGRATION.md` - Setup instructions
