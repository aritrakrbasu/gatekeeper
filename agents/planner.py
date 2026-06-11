import json
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from google.genai import types
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from google.genai import types
from pydantic import BaseModel, Field
from google.genai import types
from opentelemetry import trace
from services.gemini_service import ai_client
from agents.context import AgentContext
from agents.registry import ToolRegistry
from peil.models.enums import CaptureEventType
from services.gemini_service import ai_client

if TYPE_CHECKING:
    from agents.aril_bridge import ArilSession

from peil.models.enums import CaptureEventType
from services.gemini_service import ai_client, call_gemini_with_retry

if TYPE_CHECKING:
    from agents.aril_bridge import ArilSession


class StepSchema(BaseModel):
    step_id: str = Field(description="Unique identifier for the step (e.g. clone_step, schema_step)")
    tool_name: str = Field(description="The exact name of the tool to execute")
    arguments_json: str = Field(description="JSON string representing the arguments key-value dictionary to pass to the tool. E.g. '{\"repo_path\": \"/tmp/repo\"}'. Can use '{{step_id.result}}' in values.")
    dependencies: List[str] = Field(default_factory=list, description="List of step_ids that must complete before this step is executed")
    action: str = Field(description="Human readable description of what action is taken in this step")
    reason: str = Field(description="Explicit reasoning and tool justification for running this step")


class PlanSchema(BaseModel):
    explanation: str = Field(description="Brief explanation of the plan strategy")
    steps: List[StepSchema] = Field(description="The steps of the DAG plan")


class PlannerAgent:
    """
    Constructs and refines step-by-step DAG execution plans using Gemini.
    Enforces maximum 15 steps and maximum 5 mutating (write) actions.
    """

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name

    def _get_workflow_type(self, context: AgentContext) -> str:
        """Determine the workflow type from context metadata or objective."""
        # Check metadata first
        trigger_type = context.metadata.get("trigger_type", "")
        if trigger_type == "sentry_issue":
            return "sentry"
        elif trigger_type == "dynatrace_incident":
            return "dynatrace"
        elif "merge_request" in context.objective.lower() or "mr review" in context.objective.lower():
            return "mr_review"
        # Fallback to objective analysis
        objective_lower = context.objective.lower()
        if "sentry issue" in objective_lower or "fix bug" in objective_lower:
            return "sentry"
        elif "incident" in objective_lower and "dynatrace" in objective_lower:
            return "dynatrace"
        else:
            return "mr_review"  # Default

    def _build_sentry_system_instruction(self) -> str:
        """System instruction for Sentry bug fixing workflows."""
        return (
            "You are the elite Gatekeeper AI Planner for Sentry bug fixing workflows.\n\n"
            "Your job is to construct a DAG execution plan to automatically fix Sentry bugs.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You MUST generate a maximum of 10 steps.\n"
            "2. You MUST have at most 3 write/mutating actions (e.g. committing, pushing MRs).\n"
            "3. You must justify each step inside the 'reason' field and describe the action in the 'action' field.\n\n"
            "COMPLETE PLAN REQUIREMENT:\n"
            "EVERY step in your plan must be included in the steps array. If a step depends on another step, "
            "that dependent step MUST also be included in the steps array.\n\n"
            "Rules for arguments:\n"
            "1. Arguments must be a valid JSON string inside 'arguments_json'. E.g. '{\"repo_path\": \"/tmp/repo\"}'.\n"
            "2. Use exact tool parameter names from function declarations.\n"
            "3. TEMPLATE SYNTAX RULES (CRITICAL - VALIDATION FAILS IF VIOLATED):\n"
            "   a. Use ONLY simple field references: '{{step_id.result.field}}'\n"
            "   b. NEVER use arithmetic: NO '{{step_id.result.field+10}}' or '{{step_id.result.field-5}}'\n"
            "   c. NEVER use array indexing: NO '{{step_id.result.results[0].field}}'\n"
            "   d. NEVER use complex expressions: NO '{{step_id.result.field || \"default\"}}'\n"
            "   e. If a step returns an array, pass the entire result: '{{step_id.result}}'\n"
            "   f. The executor will handle array extraction automatically\n"
            "   g. CRITICAL: ALWAYS use the format '{{step_id.result.field}}' EXACTLY - with double curly braces and NO SPACES inside\n"
            "   h. NEVER split template references across multiple lines or add extra braces\n"
            "4. CRITICAL: Any step that generates a fix MUST depend on and use results from analysis steps.\n\n"
            "SENTRY BUG FIXING WORKFLOW - PROBLEM TYPE ANALYSIS:\n"
            "FIRST, you MUST analyze the Sentry issue (stack trace, culprit, title) to determine the problem type:\n\n"
            "   MONGODB/SCHEMA PROBLEM INDICATORS:\n"
            "   - Stack trace shows MongoDB errors (duplicate key, validation failed, schema mismatch)\n"
            "   - Error mentions 'MongoError', 'DuplicateKey', 'ValidationError', 'CastError'\n"
            "   - Issue involves database queries, indexes, or data operations\n"
            "   - Culprit points to database operations (insert, update, find with schema issues)\n"
            "   - Error mentions field names, types, or schema constraints\n\n"
            "   CODE PROBLEM INDICATORS:\n"
            "   - Stack trace shows TypeError, ReferenceError, ValueError, IndexError\n"
            "   - Error mentions undefined variables, null references, method calls\n"
            "   - Issue involves application logic, API calls, or business rules\n"
            "   - Culprit points to application code files (routes, controllers, services)\n"
            "   - Error mentions line numbers and code logic issues\n\n"
            "SENTRY BUG FIXING WORKFLOW - TEMPLATE SYNTAX CRITICAL RULES:\n"
            "When using template references in arguments_json, ALWAYS use this EXACT format: {{step_id.result.field}}\n"
            "Examples: {{create_mr_step.result.iid}} or {{generate_fix_step.result.file_path}}\n"
            "NEVER add extra braces, NEVER split across lines, NEVER add formatting\n"
            "WRONG: '{\n      {\n        create_mr_step.result.iid\n      }\n    }' (nested braces with newlines)\n"
            "CORRECT: '{{create_mr_step.result.iid}}' (single line, double braces, NO extra formatting)\n"
            "The executor will replace these with actual values from previous steps.\n\n"
            "SENTRY BUG FIXING WORKFLOW - CRITICAL CORRECT ORDER:\n"
            "   Step 1: Clone the repository via 'clone_repo' -> 'clone_repo_step' (MUST BE FIRST)\n"
            "   Step 2: Based on problem type analysis, choose appropriate analysis path:\n\n"
            "           IF MONGODB/SCHEMA PROBLEM:\n"
            "           - Step 2a: Use 'run_schema_inspection' -> 'schema_inspection_step'\n"
            "                      Purpose: Inspect MongoDB schema, collections, indexes to identify schema drift or validation issues\n"
            "                      Arguments: '{\"repo_path\": \"{{clone_repo_step.result}}\"}'\n"
            "           - Step 3a: Use 'gitnexus_grep' -> 'mongo_models_grep_step' (MUST follow schema_inspection_step)\n"
            "                      Purpose: Search for MongoDB model definitions and query patterns in codebase\n"
            "                      This step MUST depend on schema_inspection_step to use findings from schema inspection\n"
            "                      CRITICAL: gitnexus_grep does SUBSTRING SEARCH, not regex!\n"
            "                      - Use PLAIN TEXT patterns only: 'mongoose', 'Schema', 'model', 'db', 'collection'\n"
            "                      - NEVER use regex escapes: NO '\\.', NO '\\s+', NO '\\d+', NO '(', NO '['\n"
            "                      - NEVER use alternation: NO '|' (pipe character)\n"
            "                      - For multiple patterns, run gitnexus_grep multiple times with simple patterns\n"
            "                      Arguments: '{\"pattern\": \"<plain_text_pattern>\", \"limit\": 100}'\n"
            "           - Step 4a: Use 'gitnexus_file' -> 'mongo_model_file_step' (MUST follow mongo_models_grep_step)\n"
            "                      Purpose: Read the full content of MongoDB model files found by grep to understand schema definitions\n"
            "                      This step MUST depend on mongo_models_grep_step to get file paths from search results\n"
            "                      CRITICAL: Use ONLY simple template syntax for arguments:\n"
            "                      Arguments: '{\"file_path\": \"{{mongo_models_grep_step.result}}\"}'\n"
            "                      NOTE: The executor extracts ALL file paths from grep results.\n"
            "                      The gitnexus_file tool will fetch every MongoDB model file and merge their contents.\n\n"
            "           IF CODE PROBLEM:\n"
            "           - Step 2b: Use 'gitnexus_analyze' -> 'gitnexus_analysis_step'\n"
            "                      Purpose: INDEX the repository so GitNexus tools can search and read files\n"
            "                      Arguments: '{\"repo_path\": \"{{clone_repo_step.result}}\"}'\n"
            "                      CRITICAL: gitnexus_analyze ONLY accepts 'repo_path' - NO query/pattern/search/stack_trace params!\n"
            "           - Step 3b: Use 'gitnexus_grep' -> 'gitnexus_grep_step' (MUST follow gitnexus_analysis_step)\n"
            "                      Purpose: Search for specific error patterns or function names across indexed files\n"
            "                      This step MUST depend on gitnexus_analysis_step to ensure indexing is complete\n"
            "                      CRITICAL: gitnexus_grep does SUBSTRING SEARCH, not regex!\n"
            "                      - Use PLAIN TEXT patterns only: 'toString', 'undefined', 'null', 'Cannot read'\n"
            "                      - NEVER use regex escapes: NO '\\.', NO '\\s+', NO '\\d+', NO '(', NO '['\n"
            "                      - Extract key identifiers from error message for searching\n"
            "                      Examples: 'toString', 'undefined', 'Cannot read properties', 'map', 'forEach'\n"
            "                      Arguments: '{\"pattern\": \"<plain_text_pattern>\", \"limit\": 50}'\n"
            "           - Step 4b: Use 'gitnexus_file' -> 'gitnexus_file_step' (MUST follow gitnexus_grep_step)\n"
            "                      Purpose: Read the full content of specific files found by grep to understand context\n"
            "                      This step MUST depend on gitnexus_grep_step to get file paths from search results\n"
            "                      CRITICAL TEMPLATE SYNTAX RULES:\n"
            "                      - Use ONLY simple field references like '{{step_id.result.field}}'\n"
            "                      - NEVER use arithmetic in templates: NO '{{step_id.result.field+10}}'\n"
            "                      - NEVER use complex array indexing: AVOID '{{step_id.result.results[0].filePath}}'\n"
            "                      - INSTEAD: Use a simpler approach or omit optional parameters\n"
            "                      - For gitnexus_file, use the simple template - it will fetch ALL matching files:\n"
            "                      Arguments: '{\"file_path\": \"{{gitnexus_grep_step.result}}\"}'\n"
            "                      NOTE: The executor auto-extracts ALL file paths from grep results.\n"
            "                      The gitnexus_file tool will fetch every file and merge their contents together.\n"
            "                      This provides complete context from all relevant files for fix generation.\n\n"
            "   Step 5: Create branch via 'create_gitlab_branch' -> 'create_branch_step'\n"
            "           Arguments: '{\"user_id\": \"USER_ID_FROM_PROMPT\", \"project_id\": \"REPOSITORY_ID_FROM_PROMPT\", "
            "           \"branch_name\": \"fix/sentry-{{SENTRY_ISSUE_ID}}-{{TIMESTAMP}}\", \"ref\": \"main\"}'\n"
            "           This step MUST depend on clone_repo_step\n\n"
            "   Step 6: Generate fix using analysis results -> 'generate_fix_step'\n"
            "           DO NOT use gitnexus_analyze for fix generation - it is only for indexing\n"
            "           This step MUST depend on gitnexus_file_step (or schema_inspection_step for MongoDB issues)\n"
            "           Purpose: Convert analysis findings into executable fix code\n"
            "           CRITICAL TEMPLATE SYNTAX: Use these EXACT argument patterns:\n"
            "           - sentry_issue_id: Use from context (e.g., \"12345\")\n"
            "           - sentry_title: Use from context (e.g., \"TypeError: Cannot read properties\")\n"
            "           - stack_trace: Use from context Sentry issue data\n"
            "           - culprit: Use from context Sentry issue data\n"
            "           - problem_type: Use \"code\" OR \"mongodb\" (string, not a template)\n"
            "           - analysis_findings: Use '{{gitnexus_file_step.result.merged_content}}' for merged file contents.\n"
            "              The merged content includes ALL files found by grep for comprehensive analysis.\n"
            "           - file_path: Use literal string path OR extract from previous results\n"
            "           Output: Returns structured JSON with file_path, fixed_code, description\n\n"
            "   Step 7: Commit fix to branch via 'commit_file_to_branch' -> 'commit_fix_step'\n"
            "           This step MUST depend on BOTH create_branch_step AND generate_fix_step\n"
            "           CRITICAL: Use the SAME branch name from create_branch_step\n"
            "           Arguments: '{\"user_id\": \"USER_ID_FROM_PROMPT\", \"project_id\": \"REPOSITORY_ID_FROM_PROMPT\", "
            "           \"file_path\": \"{{generate_fix_step.result.file_path}}\", "
            "           \"content\": \"{{generate_fix_step.result.fixed_code}}\", "
            "           \"commit_message\": \"Fix Sentry issue {{SENTRY_ISSUE_ID}}: {{SENTRY_TITLE}}\", "
            "           \"branch_name\": \"fix/sentry-{{SENTRY_ISSUE_ID}}-{{TIMESTAMP}}\"}'\n"
            "           NOTE: Use the EXACT SAME branch name pattern as in create_branch_step\n"
            "           DO NOT use placeholder comments - commit the ACTUAL fixed code\n\n"
            "   Step 8: Create draft MR via 'create_gitlab_merge_request' -> 'create_mr_step'\n"
            "           Arguments: '{\"user_id\": \"USER_ID_FROM_PROMPT\", \"project_id\": \"REPOSITORY_ID_FROM_PROMPT\", "
            "           \"source_branch\": \"{{create_branch_step.result.branch_name}}\", "
            "           \"title\": \"Fix Sentry issue {{SENTRY_ISSUE_ID}}: {{SENTRY_TITLE}}\", "
            "           \"description\": \"{{generate_fix_step.result.description}}\"}'\n"
            "           This step MUST depend on commit_fix_step\n\n"

            "   Step 9: Attach PR to Sentry issue via 'attach_pr_to_sentry_issue' -> 'attach_pr_step'\n"
            "           Purpose: Update the Sentry alert in MongoDB with the PR details for UI display\n"
            "           Arguments: '{\"user_id\": \"USER_ID_FROM_PROMPT\", \"sentry_issue_id\": \"{{SENTRY_ISSUE_ID}}\", "
            "           \"pr_id\": \"{{create_mr_step.result.iid}}\", "
            "           \"pr_title\": \"{{create_mr_step.result.title}}\", "
            "           \"pr_web_url\": \"{{create_mr_step.result.web_url}}\"}'\n"
            "           CRITICAL TEMPLATE FORMAT: Use EXACT format '{{create_mr_step.result.iid}}' and '{{SENTRY_ISSUE_ID}}' - double braces, NO extra formatting\n"
            "           This step MUST depend on create_mr_step\n"
            "           Use the EXACT USER ID value from the USER ID field in the prompt above\n"
            "           This will allow the UI to show the attached autofix PR for the Sentry issue\n\n"

            "CRITICAL REMINDER:\n"
            "- The commit_fix_step arguments_json MUST include 'file_path', 'content', and 'commit_message'\n"
            "- The 'content' field MUST contain the ACTUAL fixed code, NOT placeholders\n"
            "- Use '{{generate_fix_step.result.fixed_code}}' to get the fix from the fix generation step\n"
            "- If analysis doesn't return structured fix data, the analysis step failed - add retry logic\n"
            "- For MongoDB issues: ensure schema changes are reflected in Mongoose/model files\n"
            "- For code issues: ensure imports, dependencies, and logic are corrected\n\n"
            "NOTE: Sentry issue details (issue_id, title, level, stack_trace) are already in the prompt.\n"
            "IMPORTANT: Call submit_execution_plan ONCE with your COMPLETE plan including ALL steps."
        )

    def _build_mr_review_system_instruction(self) -> str:
        """System instruction for MR review workflows."""
        return (
            "You are the elite Gatekeeper AI Planner for Merge Request code review workflows.\n\n"
            "Your job is to construct a DAG execution plan to review GitLab Merge Requests.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You MUST generate a maximum of 15 steps.\n"
            "2. You MUST have at most 5 write/mutating actions (e.g. posting comments).\n"
            "3. You must justify each step inside the 'reason' field and describe the action in the 'action' field.\n\n"
            "COMPLETE PLAN REQUIREMENT:\n"
            "EVERY step in your plan must be included in the steps array. If a step depends on another step, "
            "that dependent step MUST also be included in the steps array.\n\n"
            "Rules for arguments:\n"
            "1. Arguments must be a valid JSON string inside 'arguments_json'. E.g. '{\"repo_path\": \"/tmp/repo\"}'.\n"
            "2. Use exact tool parameter names from function declarations.\n"
            "3. For dependencies, use the template token '{{step_id.result}}' in values.\n"
            "4. CRITICAL: For placeholder values like USER_ID_FROM_PROMPT, project_id, mr_iid, etc., "
            "use the EXACT values provided in the prompt's OBJECTIVE and MERGE REQUEST DETAILS sections.\n\n"
            "PRE-EXECUTED STEPS (Already completed before planning):\n"
            "The following prerequisite steps have ALREADY been executed and are NOT available as tools:\n"
            "  0) validate_mr_webhook - MR validation passed (workflow would have terminated otherwise)\n"
            "     Valid actions: 'open', 'reopen', 'update' (not merge, close)\n"
            "  1) clone_repo - Repository is already cloned (path available in context)\n"
            "  2) gitnexus_analyze - Repository is already indexed for code search\n"
            "  3) get_gitlab_mr_diffs - MR diff content is already available in prompt\n\n"
            "IMPORTANT: Do NOT include validate_mr_webhook, clone_repo, gitnexus_analyze, or get_gitlab_mr_diffs in your plan.\n\n"
            "PRE-STEP RESULTS AVAILABLE IN CONTEXT:\n"
            "  - prestep_repo_path: Path to the cloned repository (use this for analysis tools)\n"
            "  - prestep_gitnexus_completed: GitNexus indexing is complete (gitnexus_grep/gitnexus_file are ready)\n"
            "  - mr_diff_content: Full MR diff is included in the prompt below\n\n"
            "MR DIFF CONTENT AVAILABILITY:\n"
            "The user message includes the full MR diff content in the 'MERGE REQUEST DIFF CONTENT' section. "
            "USE THIS DIFF to make intelligent decisions about what analysis is actually needed:\n\n"
            "ANALYSIS STRATEGY - BE SELECTIVE:\n"
            "1. First, analyze the diff content to understand what changed\n"
            "2. Then, decide which analysis tools are actually NEEDED (don't run everything blindly):\n"
            "   - gitnexus_grep + gitnexus_file: Use these for DEEP understanding of specific issues\n"
            "   - run_impact_analysis: ONLY if the diff shows significant structural changes affecting dependencies\n"
            "   - run_schema_inspection: ONLY if the diff contains MongoDB schema/model files\n\n"
            "3. For deep understanding, PREFER gitnexus_grep and gitnexus_file:\n"
            "   - Use grep to find all references to changed functions/variables\n"
            "   - Use file to read complete context of affected files\n"
            "   - This gives you actual code context for better analysis\n\n"
            "4. SKIP analysis steps that are not relevant:\n"
            "   - No schema files changed? Skip run_schema_inspection\n"
            "   - Small/simple change? Skip run_impact_analysis\n\n"
            "REVIEW REPORT FORMAT - CRITICAL FOR UPDATE_REVIEW_COMMENT:\n"
            "When generating the audit_report for update_review_comment, use THIS EXACT FORMAT:\n\n"
            "```markdown\n"
            "### 🛡️ Security & Code Review Report\n\n"
            "---\n\n"
            "#### 📋 Overview\n"
            "Brief 2-3 sentence summary of what this MR changes and the overall risk level.\n\n"
            "---\n\n"
            "#### 📁 Files Changed\n\n"
            "| File | Changes | Risk |\n"
            "|------|----------|------|\n"
            "| `path/to/file.ts` | Brief description | Low/Medium/High |\n\n"
            "---\n\n"
            "#### 🔍 Detailed Analysis\n\n"
            "<details>\n"
            "<summary><b>🔎 Analysis Category Name (e.g., Type Safety, API Breaking Changes)</b></summary>\n\n"
            "**What Changed:**\n"
            "Clear explanation of the specific change.\n\n"
            "**Impact:**\n"
            "- ✅ Safe if... (explain why)\n"
            "- ⚠️  Risk if... (explain potential issues)\n"
            "\n"
            "**Affected Locations:**\n"
            "- `src/App.tsx:42` - background property check\n"
            "- `src/App.tsx:51` - onClick handler\n"
            "- `src/App.tsx:56` - color property check\n"
            "\n"
            "CRITICAL: When processing grep results, extract filePath/line/text into the format above.\n"
            "DO NOT include raw JSON like {'results': [...]}. Process into readable bullet points.\n"
            "\n"
            "**Recommendation:**\n"
            "Specific action needed or confirmation it's safe.\n"
            "\n"
            "</details>\n\n"
            "<details>\n"
            "<summary><b>🔎 Another Analysis Category</b></summary>\n\n"
            "... same format ...\n"
            "\n"
            "</details>\n\n"
            "---\n\n"
            "#### ✅ Recommendations\n\n"
            "1. **[Action Required]** Specific actionable item\n"
            "2. **[Consider]** Optional improvement\n"
            "3. **[Verified]** Item that looks good\n\n"
            "---\n\n"
            "#### 📊 Summary\n\n"
            "| Metric | Value |\n"
            "|--------|-------|\n"
            "| Files Analyzed | X |\n"
            "| Risk Level | Low/Medium/High |\n"
            "| Issues Found | X |\n"
            "\n"
            "---\n\n"
            "*This review was generated by The Gatekeeper AI.*\n"
            "```\n\n"
            "CRITICAL REPORT FORMAT RULES:\n"
            "1. Use HTML <details> tags for expandable sections\n"
            "2. Reference files with `path:line` format for easy navigation\n"
            "3. Use emojis for visual clarity (🛡️ 🔍 📁 ✅ ⚠️)\n"
            "4. Keep analysis concise but actionable\n"
            "5. NEVER include raw JSON outputs like {'results': [...]} in the report\n"
            "6. ALWAYS process grep results into readable bullet points\n"
            "7. ALWAYS resolve template references like {{step_id.result}} before putting in report\n"
            "8. Use markdown tables with proper formatting (| header | header | | row | row |)\n"
            "9. Include blank lines between sections for readability\n"
            "10. When showing grep results, extract filePath and line into clean format:\n"
            "    WRONG: {'results': [{'filePath': 'src/App.tsx', 'line': 42, ...}]}\n"
            "    RIGHT: - src/App.tsx:42 - function call\n"
            "           - src/App.tsx:51 - another reference\n\n"
            "MINIMAL WORKFLOW EXAMPLE (for simple changes):\n"
            "   Step 1: post_loading_indicator\n"
            "   Step 2: gitnexus_grep (to find usages of changed symbols)\n"
            "   Step 3: gitnexus_file (to read full context)\n"
            "   Step 4: update_review_comment (with your analysis using the format above)\n"
            "   Step 5: update_commit_status\n\n"
            "COMPREHENSIVE WORKFLOW EXAMPLE (for complex changes):\n"
            "   Step 1: post_loading_indicator\n"
            "   Step 2: gitnexus_grep (find affected symbols)\n"
            "   Step 3: gitnexus_file (read full context)\n"
            "   Step 4: run_schema_inspection (ONLY if schema files changed)\n"
            "   Step 5: run_impact_analysis (ONLY if structural changes)\n"
            "   Step 6: update_review_comment (with comprehensive analysis using the format above)\n"
            "   Step 7: update_commit_status\n\n"
            "CRITICAL REMINDERS:\n"
            "- The planner should GENERATE THE PLAN based on what the diff shows\n"
            "- NOT every MR needs impact analysis or schema inspection\n"
            "- USE gitnexus_grep and gitnexus_file for depth understanding\n"
            "- Focus on WHAT ACTUALLY CHANGED rather than running every tool\n"
            "- Repo is already cloned and indexed - use prestep_repo_path for analysis\n"
            "- ALWAYS use the report format template above for audit_report\n\n"
            "MR REVIEW WORKFLOW - CORE STRUCTURE:\n"
            "   Step 1: Post loading indicator via 'post_loading_indicator' -> 'loading_step'\n"
            "           Purpose: Post loading comment to show analysis is in progress\n"
            "           Returns: comment_id for later update\n"
            "           Arguments: '{\"project_id\": \"<project_id>\", \"mr_iid\": <mr_iid>, \"user_id\": \"USER_ID_FROM_PROMPT\"}'\n\n"
            "   Step 2: SELECTIVE ANALYSIS (CHOOSE based on diff):\n"
            "           Option A: gitnexus_grep + gitnexus_file (for deep code understanding)\n"
            "                      Use gitnexus_grep to find all references to changed functions/variables\n"
            "                      Use gitnexus_file to read complete context of affected files\n"
            "           Option B: run_impact_analysis (ONLY for structural changes)\n"
            "                      Arguments: '{\"repo_path\": \"PRESTEP_REPO_PATH\", \"repo_name\": \"REPO_NAME\", \"source_branch\": \"SOURCE_BRANCH\"}'\n"
            "                      Note: Use the prestep_repo_path from context for repo_path\n"
            "           Option C: run_schema_inspection (ONLY for schema files)\n"
            "                      Arguments: '{\"diff_text\": \"DIFF_CONTENT\", \"project_id\": \"PROJECT_ID\", \"target_branch\": \"TARGET_BRANCH\"}'\n"
            "           Include ONLY the analysis steps that are RELEVANT to the diff\n\n"
            "   Step 3: Run Gemini AI review via 'run_gemini_mr_review' -> 'gemini_review_step'\n"
            "           Purpose: Produce the full Gatekeeper security/quality audit (same as standard mode)\n"
            "           Arguments: '{\"project_id\": \"<project_id>\", \"mr_iid\": <mr_iid>, \"diff_text\": \"<MR_DIFF_FROM_PROMPT>\", \"repo_path\": \"PRESTEP_REPO_PATH\", \"repo_name\": \"REPO_NAME\", \"source_branch\": \"SOURCE_BRANCH\", \"target_branch\": \"TARGET_BRANCH\", \"impact_context\": \"{{impact_analysis_step.result.gemini_prompt_formatted}}\", \"schema_context\": \"{{schema_inspection_step.result.markdown_report}}\"}'\n"
            "           Depends on: loading_step and any analysis steps you included\n"
            "           CRITICAL: Use gemini_review_step.result.audit_report as the final comment body — do NOT concatenate raw tool markdown instead of running this step\n\n"
            "   Step 4: Update review comment via 'update_review_comment' -> 'update_comment_step'\n"
            "           Purpose: Update the loading comment with the Gemini audit report\n"
            "           Arguments: '{\"project_id\": \"<project_id>\", \"mr_iid\": <mr_iid>, \"comment_id\": \"{{loading_step.result.comment_id}}\", \"audit_report\": \"{{gemini_review_step.result.audit_report}}\", \"user_id\": \"USER_ID_FROM_PROMPT\"}'\n"
            "           Depends on: loading_step, gemini_review_step\n\n"
            "   Step 5: Update commit status via 'update_commit_status' -> 'commit_status_step'\n"
            "           Purpose: Update commit badge to show successful review\n"
            "           Arguments: '{\"project_id\": \"<project_id>\", \"commit_sha\": \"BASE_COMMIT_SHA_FROM_PROMPT\", \"status\": \"success\", \"description\": \"Security audit completed\", \"user_id\": \"USER_ID_FROM_PROMPT\"}'\n"
            "           NOTE: Use the BASE COMMIT SHA value from the MERGE REQUEST DETAILS section in the prompt\n\n"
            "SUCCESS CRITERIA:\n"
            "1. Loading indicator posted and updated with findings\n"
            "2. Analysis performed (only relevant steps based on diff)\n"
            "3. Comment posted with audit report in the PROPER FORMAT (expandable sections, file references)\n"
            "4. Commit status updated to 'success' or 'failed'\n\n"
            "ERROR HANDLING:\n"
            "1. If any step fails, update commit status to 'failed' and post error comment\n"
            "2. Always update the loading comment with findings or error status\n\n"
            "IMPORTANT NOTES:\n"
            "- You are generating a CUSTOM plan based on the diff content\n"
            "- NOT every MR needs the same analysis steps\n"
            "- USE gitnexus_grep and gitnexus_file for depth understanding\n"
            "- Include ONLY the analysis steps that are RELEVANT to what actually changed\n"
            "- Pre-steps (validation, clone, indexing, diff fetch) are already complete\n"
            "- ALWAYS use the report format template for audit_report\n"
            "- Call submit_execution_plan ONCE with your COMPLETE plan.\n"
        )

    def _build_dynatrace_system_instruction(self) -> str:
        """System instruction for Dynatrace incident self-healing workflows."""
        return (
            "You are the elite Gatekeeper AI Planner for Dynatrace incident self-healing workflows.\n\n"
            "Your job is to construct a DAG execution plan to heal production incidents.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You MUST generate a maximum of 10 steps.\n"
            "2. You MUST have at most 3 write/mutating actions (e.g. committing, pushing MRs).\n"
            "3. You must justify each step inside the 'reason' field and describe the action in the 'action' field.\n\n"
            "COMPLETE PLAN REQUIREMENT:\n"
            "EVERY step in your plan must be included in the steps array. If a step depends on another step, "
            "that dependent step MUST also be included in the steps array.\n\n"
            "Rules for arguments:\n"
            "1. Arguments must be a valid JSON string inside 'arguments_json'.\n"
            "2. Use exact tool parameter names from function declarations.\n"
            "3. For dependencies, use the template token '{{step_id.result}}' in values.\n\n"
            "DYNATRANCE SELF-HEALING WORKFLOW - STANDARD SEQUENCE:\n"
            "   a. Fetch incident details via 'get_dynatrace_incident_details' -> 'fetch_incident_step'\n"
            "   b. Clone repository via 'clone_repo' -> 'clone_repo_step'\n"
            "   c. Diagnose and write diff patch -> 'diagnose_step'\n"
            "   d. Apply patch via 'apply_hotfix_patch' -> 'apply_patch_step'\n"
            "   e. Commit and open MR via 'create_hotfix_branch_and_mr' -> 'create_mr_step'\n\n"
            "ALL these steps must be included in your plan.\n"
            "IMPORTANT: Call submit_execution_plan ONCE with your COMPLETE plan including ALL steps."
        )

    def _is_mutate_action(self, tool_name: str) -> bool:
        """Determines if a tool performs modifying/mutating actions."""
        mutate_keywords = {"create", "update", "delete", "post", "write", "apply", "hotfix", "push", "patch"}
        name_lower = tool_name.lower()
        return any(keyword in name_lower for keyword in mutate_keywords)

    def _serialize_tools(self, registry: ToolRegistry) -> str:
        """Serialize tools as text for fallback/reference."""
        serialized = []
        for name, tool in registry._tools.items():
            schema = tool.get_schema()
            desc = tool.get_description() or schema.get("description", "No description available.")
            params = schema.get("parameters", {})
            serialized.append(
                f"Tool Name: {name}\n"
                f"Description: {desc}\n"
                f"Parameters: {json.dumps(params, indent=2)}\n"
                f"---"
            )
        return "\n".join(serialized)

    def _build_tool_function_declarations(self, registry: ToolRegistry) -> List[types.FunctionDeclaration]:
        """
        Build Gemini function declarations from tool registry.
        These represent the actual tools that can be executed in the plan.
        """
        declarations = []
        for name, tool in registry._tools.items():
            schema = tool.get_schema()
            desc = tool.get_description() or schema.get("description", "No description available.")
            params = schema.get("parameters", {})

            # Build parameters using types.Schema
            parameters = None
            if params:
                properties = {}
                for prop_name, prop_def in params.get("properties", {}).items():
                    prop_type = prop_def.get("type", "string").upper()
                    # Map JSON schema types to Gemini types
                    if prop_type in ["NUMBER", "FLOAT", "DOUBLE"]:
                        gemini_type = "NUMBER"
                    elif prop_type in ["INTEGER", "INT"]:
                        gemini_type = "INTEGER"
                    elif prop_type == "BOOLEAN":
                        gemini_type = "BOOLEAN"
                    elif prop_type == "ARRAY":
                        gemini_type = "ARRAY"
                    elif prop_type == "OBJECT":
                        gemini_type = "OBJECT"
                    else:
                        gemini_type = "STRING"

                    properties[prop_name] = types.Schema(
                        type=gemini_type,
                        description=prop_def.get("description")
                    )

                required = params.get("required", [])
                parameters = types.Schema(
                    type="OBJECT",
                    properties=properties if properties else None,
                    required=required if required else None
                )

            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=desc,
                    parameters=parameters
                )
            )

        return declarations

    def _build_plan_submission_declaration(self) -> types.FunctionDeclaration:
        """
        Create a function declaration for submitting the final execution plan.
        The model will call this function with the generated plan.
        """
        return types.FunctionDeclaration(
            name="submit_execution_plan",
            description=(
                "Submit the final execution plan for the given objective. "
                "Call this function ONCE when you have constructed the complete plan with all steps."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "explanation": types.Schema(
                        type="STRING",
                        description="Brief explanation of the plan strategy"
                    ),
                    "steps": types.Schema(
                        type="ARRAY",
                        description="The steps of the DAG plan",
                        items=types.Schema(
                            type="OBJECT",
                            properties={
                                "step_id": types.Schema(
                                    type="STRING",
                                    description="Unique identifier for the step (e.g. clone_step, schema_step)"
                                ),
                                "tool_name": types.Schema(
                                    type="STRING",
                                    description="The exact name of the tool to execute"
                                ),
                                "arguments_json": types.Schema(
                                    type="STRING",
                                    description="JSON string representing the arguments key-value dictionary. E.g. '{\"repo_path\": \"/tmp/repo\"}'. Use '{{step_id.result}}' for dependencies."
                                ),
                                "dependencies": types.Schema(
                                    type="ARRAY",
                                    description="List of step_ids that must complete before this step",
                                    items=types.Schema(type="STRING")
                                ),
                                "action": types.Schema(
                                    type="STRING",
                                    description="Human readable description of what action is taken"
                                ),
                                "reason": types.Schema(
                                    type="STRING",
                                    description="Explicit reasoning and tool justification for running this step"
                                )
                            },
                            required=["step_id", "tool_name", "arguments_json", "action", "reason"]
                        )
                    )
                },
                required=["explanation", "steps"]
            )
        )


    def _emit_plan_events(
        self,
        aril: Optional["ArilSession"],
        *,
        explanation: str,
        steps: List[StepSchema],
        plan_revision: int,
        history_steps: Optional[List[Dict[str, Any]]],
        prompt_hash: str,
        response_hash: str,
        token_count: Optional[int],
        knowledge_manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        if aril is None:
            return
        try:
            step_snapshots = [
                {
                    "step_id": s.step_id,
                    "tool_name": s.tool_name,
                    "action": s.action,
                    "reason": s.reason,
                    "arguments_json": s.arguments_json,
                    "dependencies": s.dependencies,
                }
                for s in steps
            ]
            aril.emit(
                CaptureEventType.MODEL_TURN,
                {
                    "source": "planner",
                    "prompt_hash": prompt_hash,
                    "response_hash": response_hash,
                    "token_count": token_count,
                },
            )
            manifest_payload = knowledge_manifest or {}
            if history_steps:
                aril.emit(
                    CaptureEventType.PLAN_REVISED,
                    {
                        "explanation": explanation,
                        "steps": step_snapshots,
                        "plan_revision": plan_revision,
                        "history_steps": history_steps,
                        "supersedes_plan_revision": max(0, plan_revision - 1),
                        "knowledge_manifest": manifest_payload,
                    },
                )
            else:
                aril.emit(
                    CaptureEventType.PLAN_EMITTED,
                    {
                        "explanation": explanation,
                        "steps": step_snapshots,
                        "plan_revision": plan_revision,
                        "knowledge_manifest": manifest_payload,
                    },
                )
            aril.plan_revision = plan_revision
        except Exception as exc:
            print(f"[WARN] [Planner] ARIL plan emit failed: {exc}")

    async def _persist_knowledge_manifest(
        self,
        aril: Optional["ArilSession"],
        knowledge_manifest: Dict[str, Any],
    ) -> None:
        if aril is None or not knowledge_manifest:
            return
        try:
            await aril.execution_repo.update_fields(
                aril.execution_id,
                {"knowledge_manifest": knowledge_manifest},
            )
        except Exception as exc:
            print(f"[WARN] [Planner] knowledge_manifest persist failed: {exc}")

    async def generate_plan(
        self,
        context: AgentContext,
        registry: ToolRegistry,
        history_steps: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        aril: Optional["ArilSession"] = None,
        plan_revision: int = 0,
    ) -> List[StepSchema]:
        """
        Queries Gemini to construct a dependency-based PlanStep DAG using function calling.
        Enforces strict limits of <= 10 steps and <= 3 write actions.
        """
        print(f"[INFO] [Planner] generate_plan called with objective: {context.objective[:50]}...")

        # Determine workflow type early (needed for tool filtering)
        workflow_type = self._get_workflow_type(context)
        print(f"[INFO] [Planner] Detected workflow type: {workflow_type}")

        knowledge_context = None
        knowledge_manifest: Dict[str, Any] = {}
        try:
            from knowledge.resolver.resolver import KnowledgeResolver

            resolver_db = None
            if aril is not None:
                resolver_db = getattr(aril.execution_repo, "_db", None)
            resolver = KnowledgeResolver(resolver_db)
            knowledge_context = await resolver.resolve_for_context(context)
            knowledge_manifest = knowledge_context.to_manifest_dict()
        except Exception as exc:
            print(f"[WARN] [Planner] KnowledgeResolver failed: {exc}")

        # Filter to only essential planning tools to avoid overwhelming the model
        # The planner doesn't need all 70+ GitLab tools - just the core workflow tools
        # For MR review, exclude prerequisite tools (already executed before planning)
        essential_tool_names = {
            # Core repository operations (exclude for MR review - already executed)
            # 'clone_repo', 'get_gitlab_mr_diffs',  # Prerequisites - excluded for MR review
            # Analysis tools
            'run_impact_analysis', 'run_schema_inspection', 'run_gemini_mr_review',  # 'gitnexus_analyze' is a prerequisite
            # Code search and debugging tools (GitNexus HTTP API tools)
            'gitnexus_grep', 'gitnexus_file',
            # AI Fix Generation
            'generate_fix',
            # Output/MR operations
            'post_gitlab_mr_comment',
            # Incident/healing tools
            'get_dynatrace_incident_details', 'apply_hotfix_patch',
            'create_hotfix_branch_and_mr',
            # GitLab operations
            'create_gitlab_branch', 'create_gitlab_merge_request',
            'commit_file_to_branch', 'merge_merge_request',
            # MR Review Enhancement Tools (exclude validate_mr_webhook - already executed)
            'post_loading_indicator', 'update_review_comment',
            'update_commit_status', 'track_progress',
            # Sentry PR attachment
            'attach_pr_to_sentry_issue'
        }

        # Add prerequisite tools for non-MR workflows only
        if workflow_type != "mr_review":
            essential_tool_names.update(['clone_repo', 'get_gitlab_mr_diffs', 'gitnexus_analyze', 'validate_mr_webhook'])

        # Build function declarations for essential tools only
        tool_declarations = []
        for name in essential_tool_names:
            if name in registry._tools:
                tool = registry._tools[name]
                schema = tool.get_schema()
                desc = tool.get_description() or schema.get("description", "No description available.")
                params = schema.get("parameters", {})

                # Build parameters using types.Schema
                parameters = None
                if params:
                    properties = {}
                    for prop_name, prop_def in params.get("properties", {}).items():
                        prop_type = prop_def.get("type", "string").upper()
                        if prop_type in ["NUMBER", "FLOAT", "DOUBLE"]:
                            gemini_type = "NUMBER"
                        elif prop_type in ["INTEGER", "INT"]:
                            gemini_type = "INTEGER"
                        elif prop_type == "BOOLEAN":
                            gemini_type = "BOOLEAN"
                        elif prop_type == "ARRAY":
                            gemini_type = "ARRAY"
                        elif prop_type == "OBJECT":
                            gemini_type = "OBJECT"
                        else:
                            gemini_type = "STRING"

                        # Build the schema property
                        schema_kwargs = {"type": gemini_type}
                        if "description" in prop_def:
                            schema_kwargs["description"] = prop_def["description"]

                        # Handle array items - Gemini requires items field for arrays
                        if gemini_type == "ARRAY" and "items" in prop_def:
                            items_def = prop_def["items"]
                            items_type = items_def.get("type", "string").upper()
                            if items_type in ["NUMBER", "FLOAT", "DOUBLE"]:
                                items_gemini_type = "NUMBER"
                            elif items_type in ["INTEGER", "INT"]:
                                items_gemini_type = "INTEGER"
                            elif items_type == "BOOLEAN":
                                items_gemini_type = "BOOLEAN"
                            elif items_type == "ARRAY":
                                items_gemini_type = "ARRAY"
                            elif items_type == "OBJECT":
                                items_gemini_type = "OBJECT"
                            else:
                                items_gemini_type = "STRING"

                            schema_kwargs["items"] = types.Schema(type=items_gemini_type)

                        properties[prop_name] = types.Schema(**schema_kwargs)

                    required = params.get("required", [])
                    parameters = types.Schema(
                        type="OBJECT",
                        properties=properties if properties else None,
                        required=required if required else None
                    )

                tool_declarations.append(
                    types.FunctionDeclaration(
                        name=name,
                        description=desc,
                        parameters=parameters
                    )
                )
            else:
                print(f"[WARN] [Planner] Essential tool '{name}' not found in registry")

        plan_submission_decl = self._build_plan_submission_declaration()

        # Combine all declarations: essential tools + plan submission function
        all_declarations = tool_declarations + [plan_submission_decl]

        print(f"[INFO] [Planner] Using {len(tool_declarations)} essential tools (filtered from {len(registry._tools)} total)")

        # Determine workflow type and use appropriate system instruction
        workflow_type = self._get_workflow_type(context)
        print(f"[INFO] [Planner] Detected workflow type: {workflow_type}")

        if workflow_type == "sentry":
            system_instruction = self._build_sentry_system_instruction()
        elif workflow_type == "dynatrace":
            system_instruction = self._build_dynatrace_system_instruction()
        else:  # mr_review (default)
            system_instruction = self._build_mr_review_system_instruction()

        prompt = (
            f"OBJECTIVE: {context.objective}\n"
            f"REPOSITORY ID: {context.repository.id}\n"
            f"REPOSITORY NAME: {context.repository.name}\n"
            f"GIT URL: {context.repository.git_url}\n"
            f"SOURCE BRANCH: {context.branch.source_branch}\n"
            f"TARGET BRANCH: {context.branch.target_branch}\n"
            f"USER ID: {context.user.user_id}\n\n"
        )

        # Add pre-step results if available (from MR review workflow pre-steps)
        if context.metadata.get("prestep_validation_passed"):
            prompt += "PRE-STEP RESULTS (already executed):\n"
            prompt += f"VALIDATION: Passed\n"
            if context.metadata.get("prestep_repo_path"):
                prompt += f"REPO_PATH: {context.metadata['prestep_repo_path']}\n"
            if context.metadata.get("prestep_gitnexus_completed"):
                prompt += f"GITNEXUS_INDEXING: Completed (gitnexus_grep/gitnexus_file are ready)\n"
            prompt += f"DIFF_FETCHED: Yes ({len(context.metadata.get('mr_diff_content', ''))} chars)\n"
            prompt += "\n"

        # Add MR details if available (from webhook payload)
        if context.branch.base_commit_sha or context.branch.head_commit_sha:
            prompt += "MERGE REQUEST DETAILS (from webhook payload):\n"
            if context.branch.base_commit_sha:
                prompt += f"BASE COMMIT SHA: {context.branch.base_commit_sha}\n"
            if context.branch.head_commit_sha:
                prompt += f"HEAD COMMIT SHA: {context.branch.head_commit_sha}\n"
            prompt += "\n"

        # Add MR diff content if available (fetched before planning)
        mr_diff_content = context.metadata.get("mr_diff_content", "")
        if mr_diff_content:
            # Truncate diff if too large to fit in context window
            max_diff_length = 50000  # Keep under 50k chars for the planner
            diff_to_show = mr_diff_content[:max_diff_length]
            if len(mr_diff_content) > max_diff_length:
                diff_to_show += f"\n... (diff truncated, showing {max_diff_length} of {len(mr_diff_content)} characters)"

            prompt += "MERGE REQUEST DIFF CONTENT:\n"
            prompt += "The following is the raw unified diff of the code changes:\n"
            prompt += "```\n"
            prompt += diff_to_show + "\n"
            prompt += "```\n"
            prompt += "Use this diff to inform your planning - analyze what files are changed, what types of modifications are made, and plan your review steps accordingly.\n\n"
            print(f"[INFO] [Planner] Added MR diff to prompt ({len(diff_to_show)} chars shown)")

        # Add Sentry issue details if available (from webhook payload)
        if context.sentry_issue:
            prompt += (
                f"SENTRY ISSUE DETAILS (from webhook payload):\n"
                f"ISSUE ID: {context.sentry_issue.issue_id}\n"
                f"TITLE: {context.sentry_issue.title}\n"
                f"LEVEL: {context.sentry_issue.level}\n"
                f"ENVIRONMENT: {context.sentry_issue.environment}\n"
                f"CULPRIT: {context.sentry_issue.culprit or 'N/A'}\n"
            )
            if context.sentry_issue.stack_trace:
                prompt += f"STACK TRACE:\n{context.sentry_issue.stack_trace}\n"
            if context.sentry_issue.git_commit_sha:
                prompt += f"GIT COMMIT SHA: {context.sentry_issue.git_commit_sha}\n"
            prompt += "\n"

        if memories:
            prompt += (
                f"HISTORICAL SIMILAR MEMORIES RETRIEVED:\n"
                f"{json.dumps(memories, indent=2)}\n"
                f"Use this context to inform your plan strategy (e.g. reuse successful patch designs or root causes).\n\n"
            )

        if knowledge_context is not None:
            knowledge_section = knowledge_context.to_prompt_section()
            if knowledge_section:
                prompt += f"{knowledge_section}\n\n"

        if history_steps:
            prompt += (
                f"PREVIOUS EXECUTION STEPS HISTORY (some steps may have failed):\n"
                f"{json.dumps(history_steps, indent=2)}\n\n"
                f"Please adjust the plan to recover from any failures. If a recovery is not possible, design a step to report/post the failure comment and exit cleanly.\n\n"
            )

        print(f"[INFO] [Planner] Asking Gemini to build/adjust plan with function calling...")

        # Get current span to add context attributes for observability
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            print(f"[INFO] [Planner] Planning within span context: {current_span.name}")

        from agents.aril_bridge import hash_text

        prompt_hash = hash_text(system_instruction + prompt)
        start = time.time()

        # Build tools config with function declarations
        print(f"[DEBUG] [Planner] Building tools config with {len(all_declarations)} declarations...")
        try:
            tools_config = [
                types.Tool(function_declarations=all_declarations)
            ]
            print(f"[DEBUG] [Planner] Tools config built successfully")
        except Exception as e:
            print(f"[ERROR] [Planner] Failed to build tools config: {e}")
            import traceback
            traceback.print_exc()
            raise

        print(f"[DEBUG] [Planner] Calling Gemini API with function calling...")
        try:
            response = ai_client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    tools=tools_config,
                ),
            )
            print(f"[DEBUG] [Planner] Got response from Gemini")
        except Exception as e:
            print(f"[ERROR] [Planner] Gemini API call failed: {e}")
            import traceback
            traceback.print_exc()
            raise

        # Extract function call from response
        func_call = None
        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    func_call = part.function_call
                    break
        except (IndexError, AttributeError) as e:
            print(f"[ERROR] [Planner] Failed to extract function call: {e}")
            raise ValueError("Planner response did not contain a function call. Expected submit_execution_plan to be called.")

        if not func_call or func_call.name != "submit_execution_plan":
            print(f"[ERROR] [Planner] Expected submit_execution_plan function call, got: {func_call.name if func_call else 'None'}")
            raise ValueError(f"Expected submit_execution_plan function call, got: {func_call.name if func_call else 'None'}")

        # Parse plan from function call arguments
        try:
            plan_args = dict(func_call.args)
            explanation = plan_args.get("explanation", "")
            steps_data = plan_args.get("steps", [])

            # Convert steps to StepSchema objects
            steps = []
            for step_data in steps_data:
                steps.append(StepSchema(
                    step_id=step_data.get("step_id"),
                    tool_name=step_data.get("tool_name"),
                    arguments_json=step_data.get("arguments_json"),
                    dependencies=step_data.get("dependencies", []),
                    action=step_data.get("action"),
                    reason=step_data.get("reason")
                ))

            # Validate constraints
            if len(steps) > 15:
                raise ValueError(f"Plan validation failed: plan has {len(steps)} steps, which exceeds the max limit of 15.")

            write_count = sum(1 for s in steps if self._is_mutate_action(s.tool_name))
            if write_count > 5:
                raise ValueError(f"Plan validation failed: plan has {write_count} write/mutating actions, which exceeds the max limit of 5.")

        except Exception as e:
            print(f"[ERROR] [Planner] Failed to parse plan from function call: {e}")
            raise

        # Calculate response hash and token count
        response_text = json.dumps({"explanation": explanation, "steps": [s.model_dump() for s in steps]})
        response_hash = hash_text(response_text)
        token_count = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            token_count = getattr(usage, "total_token_count", None)

        effective_revision = plan_revision if not history_steps else plan_revision + 1
        self._emit_plan_events(
            aril,
            explanation=explanation,
            steps=steps,
            plan_revision=effective_revision,
            history_steps=history_steps,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
            token_count=token_count,
            knowledge_manifest=knowledge_manifest,
        )
        await self._persist_knowledge_manifest(aril, knowledge_manifest)
        if aril is not None:
            await aril.flush()

        print(f"[OK] [Planner] Plan successfully generated via function calling. Explanation: '{explanation}'")
        for i, step in enumerate(steps):
            print(f"     Step {i+1}: {step.step_id} -> {step.tool_name} (depends on: {step.dependencies})")
        return steps


Planner = PlannerAgent
