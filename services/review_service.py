import os
import time
import json
import asyncio
from pathlib import Path

# Gatekeeper Modules
from atomic_patches import (
    AtomicPatchParser,
    create_patch_summary
)
from impact_analysis import (
    ImpactLevel,
    run_pre_review_analysis,
    run_post_review_validation
)
from repo_manager import get_repo_manager

# Service Imports
from services import mcp_service, repository_service, user_service
from services.gemini_service import run_gemini_review, run_gemini_fix_analysis
from services.remediation_service import apply_auto_fixes


async def get_user_config_from_repo(project_id: str) -> dict:
    """
    Get user's Gemini configuration from the repository owner.

    Args:
        project_id: GitLab project/repository ID

    Returns:
        User's Gemini config dict or empty dict if not found
    """
    try:
        # Look up repository to get user_id
        repo = await repository_service.get_repository(str(project_id))
        if repo and repo.get("user_id"):
            user_id = repo["user_id"]
            print(f"[INFO] Found repository owner: {user_id}")
            # Get user's Gemini config
            return await user_service.get_user_gemini_config(user_id)
        else:
            print(f"[WARN] Repository {project_id} not found or has no owner")
            return {}
    except Exception as e:
        print(f"[WARN] Failed to get user config from repository: {e}")
        return {}


async def should_process_webhook(repo_id: str, target_branch: str) -> bool:
    """
    Check if webhook should be processed based on repository's target branches.

    Args:
        repo_id: Repository ID
        target_branch: Target branch of the MR

    Returns:
        True if webhook should be processed, False otherwise
    """
    try:
        repo = await repository_service.get_repository(str(repo_id))
        target_branches = repo.get("target_branches", ["main", "master", "develop"])

        # If no target branches specified, process all
        if not target_branches:
            return True

        # Check if target branch is in the monitored list
        should_process = target_branch in target_branches

        if not should_process:
            print(f"[ℹ️] Skipping MR for branch '{target_branch}' - not in monitored branches: {target_branches}")

        return should_process
    except Exception as e:
        print(f"[⚠️] Failed to check target branches, processing anyway: {e}")
        return True  # Default to processing on error


async def orchestrate_review(payload: dict) -> dict:
    """
    Orchestrates the entire webhook auditing pipeline.

    1. Logs signature to MongoDB
    2. Clones/indexes repository
    3. Triggers pre-review impact analysis
    4. Submits code diff to Gemini Pro Core
    5. Performs post-review validation
    6. Posts final review report & commit status
    7. Runs hunk-level auto-fix generation & MR creation
    """
    # Grab sessions dynamically from connection manager module
    mongo_session = mcp_service.mongo_session
    gitlab_session = mcp_service.gitlab_session
    nexus_session = mcp_service.nexus_session

    object_attrs = payload.get("object_attributes", {})

    # Helper function to add progress logs
    async def add_log(step: str, message: str, status: str = "running"):
        """Add a progress log entry to the MR document"""
        try:
            await repository_service.add_mr_progress_log(
                repo_id=str(project_id),
                mr_iid=int(mr_iid),
                step=step,
                message=message,
                status=status
            )
        except Exception as log_err:
            print(f"[⚠️] Failed to add progress log: {log_err}")
    state = object_attrs.get("state")

    if state != "opened":
        print(f"[ℹ] MR state is '{state}' - skipping audit")
        return {"status": "skipped_state", "state": state}

    mr_title = object_attrs.get("title")
    source_branch = object_attrs.get("source_branch")
    target_branch = object_attrs.get("target_branch", "main")
    project_id = payload.get("project", {}).get("id")
    mr_iid = object_attrs.get("iid")
    mr_internal_id = object_attrs.get("id")
    author = payload.get("user", {}).get("username", "unknown")
    web_url = object_attrs.get("url", "")
    created_at = object_attrs.get("created_at", "")
    updated_at = object_attrs.get("updated_at", "")
    description = object_attrs.get("description", "")

    # Check if we should process this webhook based on target branches
    if not await should_process_webhook(str(project_id), target_branch):
        return {"status": "skipped_branch_not_monitored", "target_branch": target_branch}

    # Extract changes statistics from webhook payload
    # GitLab MR hook provides this in object_attributes.stats
    stats = object_attrs.get("stats", {})
    additions = stats.get("additions", 0)
    deletions = stats.get("deletions", 0)
    files_changed = stats.get("total", 0)  # 'total' is the key for total files changed in GitLab

    # Debug: Log the stats extraction
    print(f"[DEBUG] object_attrs keys: {list(object_attrs.keys())}")
    print(f"[DEBUG] Stats from webhook: {stats}")
    print(f"[DEBUG] Extracted - additions: {additions}, deletions: {deletions}, files_changed: {files_changed}")

    # If stats are missing or all zeros, fetch from GitLab API
    if not stats or (additions == 0 and deletions == 0 and files_changed == 0):
        print("[INFO] Stats missing from webhook payload, fetching from GitLab API...")
        try:
            mr_details = await gitlab_session.call_tool(
                name="get_merge_request",
                arguments={
                    "project_id": str(project_id),
                    "merge_request_iid": int(mr_iid)
                }
            )
            if hasattr(mr_details, 'content') and mr_details.content:
                try:
                    mr_data = json.loads(mr_details.content[0].text)
                    print(f"[DEBUG] GitLab API response keys: {list(mr_data.keys())}")
                    print(f"[DEBUG] Full MR data snippet: {str(mr_data)[:500]}...")

                    # Try different possible locations for stats
                    # GitLab API may provide stats in different fields
                    if "diff_stats" in mr_data:
                        diff_stats = mr_data.get("diff_stats", {})
                        print(f"[DEBUG] diff_stats: {diff_stats}")
                        additions = diff_stats.get("additions", 0)
                        deletions = diff_stats.get("deletions", 0)
                    else:
                        print("[WARN] No diff_stats in API response")

                    files_changed = mr_data.get("changed_files_count", 0)
                    if files_changed == 0:
                        # Try alternative field names
                        files_changed = mr_data.get("changes_count", 0)

                    print(f"[INFO] Fetched stats from GitLab API: +{additions} -{deletions} ({files_changed} files)")
                except json.JSONDecodeError:
                    print("[WARN] Could not parse MR details JSON")
        except Exception as e:
            print(f"[WARN] Failed to fetch stats from GitLab API: {e}")
            print(f"[WARN] Using default values (all zeros) for changes statistics")

    print(f"[INFO] MR changes: +{additions} -{deletions} ({files_changed} files)")

    # Ensure consistent types for database queries
    mr_iid_int = int(mr_iid) if mr_iid else 0
    project_id_str = str(project_id)

    # Store MR in MongoDB for frontend retrieval
    analysis_start_time = time.time()  # Track when we received the MR
    try:
        mr_data = {
            "gitlab_mr_id": mr_iid_int,
            "gitlab_mr_internal_id": mr_internal_id,
            "repository_id": project_id_str,
            "repository_name": payload.get("project", {}).get("path_with_namespace", ""),
            "title": mr_title,
            "description": description,
            "author": author,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "status": "open",
            "web_url": web_url,
            "created_at": created_at,
            "updated_at": updated_at,
            "changes": {
                "additions": additions,
                "deletions": deletions,
                "files_changed": files_changed
            },
            "analysis_status": "pending",
            "is_auto_fix": False,
            "auto_fix_for": None,
            "auto_fix_mrs": [],
            "progress_logs": [],  # Initialize empty progress logs
            "analysis_started_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(analysis_start_time))
        }

        print(f"[DEBUG] Storing MR: gitlab_mr_id={mr_iid_int} (type: {type(mr_iid_int).__name__}), repository_id={project_id_str} (type: {type(project_id_str).__name__})")

        action = object_attrs.get("action")
        if action == "open":
            print(f"[INFO] New MR opened: {mr_title}")

        await repository_service.store_mr_in_mongodb(mr_data)

        # Add initial log
        await add_log("received", "Merge request received and queued for analysis", "completed")
        print(f"[✅] MR {mr_iid} stored in MongoDB with changes data")

    except Exception as e:
        print(f"[⚠️] Failed to store MR in MongoDB: {e}")
        # Continue with review even if storage fails

    # Get commit SHA for status updates
    commit_sha = (
        object_attrs.get("last_commit", {}).get("id") or
        object_attrs.get("sha") or
        object_attrs.get("merge_request_sha") or
        None
    )

    print(f"[+] Webhook caught MR !{mr_iid} on Project {project_id}")
    print(f"[+] Commit SHA: {commit_sha}")
    print(f"[+] Starting Gatekeeper analysis pipeline...")

    if not commit_sha:
        print("[⚠️] Warning: No commit SHA found in webhook!")
        print(f"[DEBUG] object_attrs keys: {list(object_attrs.keys())}")
        print(f"[DEBUG] last_commit: {object_attrs.get('last_commit')}")

        # Fallback: Try to get the MR details from GitLab MCP to find the commit SHA
        if gitlab_session:
            try:
                print("[*] Fetching MR details from GitLab to get commit SHA...")
                mr_details = await gitlab_session.call_tool(
                    name="get_merge_request",
                    arguments={
                        "project_id": str(project_id),
                        "merge_request_iid": int(mr_iid)
                    }
                )
                print(f"[DEBUG] MR details response type: {type(mr_details)}")
                if hasattr(mr_details, 'content'):
                    print(f"[DEBUG] MR details content preview: {str(mr_details.content)[:300]}...")
            except Exception as e:
                print(f"[x] Failed to fetch MR details: {e}")

    # 🔒 Skip audit for Gatekeeper auto-generated branches to prevent infinite loops
    if source_branch.startswith("gatekeeper/"):
        print(f"[⏭️] Skipping audit for auto-generated branch: {source_branch}")
        return {"status": "skipped_auto_branch"}

    # 1. Store Request Signature in MongoDB Cluster via MCP
    if mongo_session:
        try:
            await mongo_session.call_tool(
                name="insert-many",
                arguments={
                    "database": "gatekeeper_dev",
                    "collection": "intercepted_mrs",
                    "documents": [{"title": mr_title, "project_id": project_id, "mr_iid": mr_iid, "status": "gemini_auditing"}]
                }
            )
            print("[+] Metadata logged to local MongoDB cluster.")
        except Exception as e:
            print(f"[x] DB Log failed: {e}")
    else:
        print("[⚠️] MongoDB session not available - skipping DB log")

    # 2. Prepare Repository for GitNexus (Option 2 → Option 1)
    print("[*] ===== PREPARING REPOSITORY FOR ANALYSIS =====")
    repo_manager = get_repo_manager()
    repo_local_path = None

    gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
    if gitlab_token:
        print(f"[✅] GitLab token found (length: {len(gitlab_token)})")
    else:
        print("[⚠️] GitLab token NOT found in environment!")

    # Try to get project URL from GitLab
    gitlab_url = None
    try:
        project_result = await gitlab_session.call_tool(
            name="get_project",
            arguments={"project_id": str(project_id)}
        )
        if hasattr(project_result, 'content') and project_result.content:
            project_data = json.loads(project_result.content[0].text)
            gitlab_url = project_data.get("http_url_to_repo")
    except Exception as e:
        print(f"[⚠️] Could not fetch project URL: {e}")

    # Ensure repository is ready (Option 2: Pre-indexed → Option 1: Auto-index)
    if gitlab_url:
        print(f"[*] Ensuring repository {project_id} is ready...")
        print("[ℹ️] Checking for pre-indexed repository (Option 2)...")

        try:
            repo_local_path = await repo_manager.ensure_repository_ready(
                project_id=str(project_id),
                gitlab_url=gitlab_url,
                private_token=gitlab_token,
                gitlab_session=gitlab_session
            )

            if repo_local_path:
                print(f"[✅] Repository ready at: {repo_local_path}")
            else:
                print("[⚠️] Repository preparation failed - using fallback analysis")
        except Exception as repo_err:
            print(f"[⚠️] Repository preparation error: {repo_err}")
            print("[ℹ️] Impact analysis will use built-in AST-based analysis")
    else:
        print("[⚠️] No repository URL available - skipping GitNexus integration")

    # 3. Extract Comprehensive Diffs via GitLab MCP and Process using Gemini
    print("[*] ===== STARTING GATEKEEPER ANALYSIS PIPELINE =====")

    # Update status to "reviewing"
    try:
        await repository_service.update_mr_analysis(
            repo_id=str(project_id),
            mr_iid=mr_iid_int,
            analysis_data={"status": "reviewing", "analysis_status": "in_progress"}
        )
        await add_log("starting", "🚀 Starting Gatekeeper security analysis", "completed")
        print(f"[✅] Updated MR {mr_iid} status to 'reviewing'")
    except Exception as status_err:
        print(f"[⚠️] Failed to update MR status to 'reviewing': {status_err}")

    print("[*] Step 1: Posting loading indicator to MR...")
    await add_log("fetching", "📡 Fetching merge request details and code changes", "running")

    if gitlab_session:
        loading_note_id = None
        try:
            # 🔄 Post a loading comment (will be updated with results)
            print("[*] Posting loading indicator to MR...")
            loading_note = await gitlab_session.call_tool(
                name="create_merge_request_note",
                arguments={
                    "project_id": str(project_id),
                    "merge_request_iid": int(mr_iid),
                    "body": """### 🔄 Gatekeeper Review In Progress

**The Gatekeeper** is analyzing your code changes for security vulnerabilities, code quality issues, and performance improvements.

This may take 30-60 seconds depending on the size of the changes.

---
*⏳ Status: Analyzing...*"""
                }
            )
            
            if hasattr(loading_note, 'content') and loading_note.content:
                text_content = loading_note.content[0].text if hasattr(loading_note.content[0], 'text') else str(loading_note.content[0])
                try:
                    note_data = json.loads(text_content)
                    loading_note_id = note_data.get("id")
                    if loading_note_id:
                        print(f"[+] Loading indicator posted! Note ID: {loading_note_id}")
                    else:
                        print("[+] Loading indicator posted! (No ID in response)")
                except json.JSONDecodeError:
                    print("[+] Loading indicator posted! (Could not parse JSON)")
            else:
                print("[+] Loading indicator posted!")

            print("[*] Step 2: Fetching comprehensive MR diff text via GitLab MCP...")

            # Using list_merge_request_diffs to pull actual raw line changes
            changes = await gitlab_session.call_tool(
                name="list_merge_request_diffs",
                arguments={
                    "project_id": str(project_id),
                    "merge_request_iid": int(mr_iid)
                }
            )

            # Extract actual diff text from MCP response
            raw_diff_content = ""
            if hasattr(changes, 'content') and changes.content:
                for item in changes.content:
                    if hasattr(item, 'text'):
                        try:
                            diff_data = json.loads(item.text)
                            if isinstance(diff_data, list):
                                for diff_obj in diff_data:
                                    if isinstance(diff_obj, dict):
                                        old_path = diff_obj.get('old_path', '')
                                        new_path = diff_obj.get('new_path', '')
                                        diff_text = diff_obj.get('diff', '')

                                        if old_path and new_path:
                                            raw_diff_content += f"diff --git a/{old_path} b/{new_path}\n"
                                            raw_diff_content += diff_text + "\n"
                                print(f"[DEBUG] Parsed {len(diff_data)} diff objects from GitLab MCP")
                            else:
                                raw_diff_content += item.text
                        except json.JSONDecodeError:
                            raw_diff_content += item.text

            if not raw_diff_content:
                raw_diff_content = str(changes.content)

            print(f"[✅] Step 2 complete: Raw code diffs retrieved ({len(raw_diff_content)} chars)")

            if raw_diff_content:
                print(f"[DEBUG] Diff preview: {raw_diff_content[:500]}")
                await add_log("diff_fetched", f"📥 Retrieved {len(raw_diff_content)} characters of code changes", "completed")
            else:
                print("[⚠️] WARNING: Diff content is empty!")
                await add_log("diff_fetched", "⚠️ No code changes found in this merge request", "completed")

            # --- 🎯 PRE-REVIEW IMPACT ANALYSIS ---
            print("[*] Step 3: Running pre-review impact analysis to identify affected code...")
            await add_log("semantic_analysis", "🔍 Analyzing semantic changes and affected code areas", "running")

            impact_report = None
            impact_context = ""

            try:
                def parse_diff():
                    parser = AtomicPatchParser()
                    return parser.parse_unified_diff(raw_diff_content)

                print("[DEBUG] Calling parse_unified_diff (with 10s timeout)...")
                atomic_patches = await asyncio.wait_for(
                    asyncio.to_thread(parse_diff),
                    timeout=10.0
                )
                print(f"[DEBUG] Parser returned {len(atomic_patches)} patches")

                changed_files = list(set(
                    hunk.file_path for patch in atomic_patches for hunk in patch.hunks
                ))

                # Calculate actual additions and deletions from the parsed diff
                calculated_additions = 0
                calculated_deletions = 0
                for patch in atomic_patches:
                    for hunk in patch.hunks:
                        for line in hunk.lines:
                            if line.startswith('+'):
                                calculated_additions += 1
                            elif line.startswith('-'):
                                calculated_deletions += 1

                calculated_files_changed = len(changed_files)

                print(f"[ℹ️] Calculated changes from diff: +{calculated_additions} -{calculated_deletions} ({calculated_files_changed} files)")

                # Update the MR in MongoDB with the calculated stats
                if calculated_additions > 0 or calculated_deletions > 0 or calculated_files_changed > 0:
                    try:
                        await repository_service.update_mr_analysis(
                            repo_id=str(project_id),
                            mr_iid=mr_iid_int,
                            analysis_data={
                                "changes": {
                                    "additions": calculated_additions,
                                    "deletions": calculated_deletions,
                                    "files_changed": calculated_files_changed
                                }
                            }
                        )
                        print(f"[✅] Updated MR {mr_iid} with calculated diff stats")
                    except Exception as stats_err:
                        print(f"[⚠️] Failed to update MR stats: {stats_err}")

                print(f"[ℹ️] Identified {len(changed_files)} changed files for impact analysis")

                impact_report, impact_context = await run_pre_review_analysis(
                    project_id=str(project_id),
                    mr_iid=int(mr_iid),
                    source_branch=source_branch,
                    target_branch="main",
                    changed_files=changed_files,
                    gitlab_session=gitlab_session,
                    nexus_session=nexus_session
                )

                print(f"[✅] Step 3 complete: Impact analysis found {len(impact_report.findings)} findings")

                if impact_report.findings:
                    impact_summary = impact_report.to_markdown()
                    await gitlab_session.call_tool(
                        name="create_merge_request_note",
                        arguments={
                            "project_id": str(project_id),
                            "merge_request_iid": int(mr_iid),
                            "body": f"""### 🎯 Pre-Review Impact Analysis

{impact_summary}

*This analysis helps identify potential ripple effects from the proposed changes.*"""
                        }
                    )
                    print("[+] Impact analysis posted to MR")

            except asyncio.TimeoutError:
                print("[⏱️] Parser timeout after 10s - using fallback file extraction")
                import re
                changed_files = re.findall(r'diff --git a/(.+?) b/', raw_diff_content)
                print(f"[ℹ️] Fallback extracted {len(changed_files)} files: {changed_files}")
                impact_context = ""
            except Exception as impact_err:
                print(f"[⚠️] Impact analysis failed (continuing anyway): {impact_err}")
                impact_context = ""

            # --- 🔍 SCHEMA INSPECTION SERVICE (Step 3.5) ---
            print("[*] Step 3.5: Checking for backend-touching changes and database schema inspection...")
            await add_log("schema_check", "🗄️ Checking for MongoDB schema changes", "running")

            schema_report = None
            schema_markdown = None
            try:
                from services.schema_inspection_service import run_schema_inspection, format_schema_report_to_markdown
                schema_report = await run_schema_inspection(raw_diff_content, mcp_service.mongo_session, project_id=project_id)
                if schema_report:
                    print(f"[+] Schema inspection complete. Found {len(schema_report.collections)} collections. Confidence: {schema_report.confidence}")
                    await add_log("schema_check", f"✅ Schema analysis complete - {len(schema_report.collections)} collections examined", "completed")
                else:
                    await add_log("schema_check", "ℹ️ No database schema changes detected", "completed")
                    
                    # 1. Format and attach schema_report summary to raw_diff_content passed to run_gemini_review
                    schema_markdown = format_schema_report_to_markdown(schema_report)
                    if schema_markdown:
                        raw_diff_content += f"\n\n{schema_markdown}"
                        
                    # 2. Log schema_report to MongoDB collection "schema_snapshots"
                    if mcp_service.mongo_session:
                        delta_list = []
                        if schema_report.delta:
                            for change in schema_report.delta.changes:
                                delta_list.append({
                                    "collection": change.collection,
                                    "change_type": change.change_type,
                                    "field_name": change.field_name,
                                    "old_value": change.old_value,
                                    "new_value": change.new_value
                                })
                        else:
                            delta_list = None
                            
                        schema_dict = {
                            "inspected_at": schema_report.inspected_at.isoformat() if schema_report.inspected_at else None,
                            "triggered_by_files": schema_report.triggered_by_files,
                            "triggered_by_content": schema_report.triggered_by_content,
                            "confidence": schema_report.confidence,
                            "scoped": schema_report.scoped,
                            "skipped_reason": schema_report.skipped_reason,
                            "delta": delta_list,
                            "collections": [
                                {
                                    "name": col.name,
                                    "fields": col.fields,
                                    "indexes": col.indexes,
                                    "sample_document_keys": col.sample_document_keys
                                } for col in schema_report.collections
                            ]
                        }
                        
                        from datetime import datetime, timezone
                        await mcp_service.mongo_session.call_tool(
                            name="insert-many",
                            arguments={
                                "database": "gatekeeper_dev",
                                "collection": "schema_snapshots",
                                "documents": [{
                                    "mr_id": mr_iid,
                                    "project_id": project_id,
                                    "branch_name": source_branch,
                                    "report": schema_dict,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                }]
                            }
                        )
                        print("[+] Schema snapshot logged to MongoDB collection: schema_snapshots")
            except Exception as schema_err:
                print(f"[⚠️] Schema inspection failed (continuing anyway): {schema_err}")
                await add_log("schema_check", "⚠️ Schema check encountered an error, continuing analysis", "completed")

            # --- 🧠 THE GEMINI COGNITIVE CORE ENGINE ---
            print("[*] Step 4: Shipping code diff to Gemini Pro Core for automated security review...")
            await add_log("ai_analysis", "🤖 Running AI-powered security and code quality analysis", "running")

            # Get user's Gemini config from repository owner
            user_config = await get_user_config_from_repo(str(project_id))
            audit_report = await run_gemini_review(raw_diff_content, impact_context, user_config)

            print(f"[✅] Step 4 complete: Gemini analysis compiled ({len(audit_report)} chars)")
            await add_log("ai_analysis", f"✅ AI analysis complete - {len(audit_report)} characters of findings generated", "completed")

            # --- 🔍 POST-REVIEW VALIDATION ---
            print("[*] Running post-review validation to catch issues outside changed code...")
            validation_findings = []

            if validation_findings:
                await add_log("validation", f"🔍 Post-review validation found {len(validation_findings)} additional considerations", "completed")

            if impact_report:
                try:
                    review_findings = [{"description": audit_report}]  # Simplified
                    validation_findings = await run_post_review_validation(
                        pre_review_report=impact_report,
                        ai_review_findings=review_findings,
                        gitlab_session=gitlab_session,
                        nexus_session=nexus_session
                    )

                    if validation_findings:
                        print(f"[!] Post-review validation found {len(validation_findings)} additional concerns")

                        validation_section = "\n\n### 🔍 Post-Review Validation Findings\n\n"
                        validation_section += "The following potential impacts were identified outside the directly changed code:\n\n"

                        for finding in validation_findings[:10]:
                            emoji = {
                                ImpactLevel.CRITICAL: "🔴",
                                ImpactLevel.HIGH: "🟠",
                                ImpactLevel.MEDIUM: "🟡"
                            }.get(finding.level, "ℹ️")

                            validation_section += f"- {emoji} **{finding.file_path}:{finding.line_number}**: {finding.description}\n"

                        audit_report += validation_section

                except Exception as validation_err:
                    print(f"[⚠️] Post-review validation failed: {validation_err}")

            # 3. Update the loading comment with the final report
            print("[*] Updating review with findings...")
            final_report = f"""### 🛡️ The Gatekeeper Security Audit

{audit_report}

---
*✅ Review completed at {time.strftime('%Y-%m-%d %H:%M:%S UTC')}*"""

            # 3.5 Update MongoDB with AI analysis results
            try:
                # Calculate review duration
                review_duration_seconds = int(time.time() - analysis_start_time)

                # Extract issues from audit_report for frontend display
                ai_issues = []
                lines = audit_report.split('\n')
                for line in lines:
                    line = line.strip()
                    # Look for lines with issue indicators
                    if any(marker in line for marker in ['❌', '⚠️', '🔴', '🟠', '**ERROR**', '**WARNING**', '**Issue**']):
                        # Clean up the line for display
                        clean_line = line
                        # Remove markdown formatting
                        for marker in ['❌', '⚠️', '🔴', '🟠', '**', '*', '`']:
                            clean_line = clean_line.replace(marker, '').strip()
                        if clean_line and len(clean_line) > 5:  # Only meaningful lines
                            ai_issues.append(clean_line[:200])  # Limit length

                # Calculate health score based on issues found
                health_score = 100
                error_count = audit_report.count('❌') + audit_report.count('ERROR')
                warning_count = audit_report.count('⚠️') + audit_report.count('WARNING')

                if error_count > 0:
                    health_score -= min(error_count * 20, 60)
                if warning_count > 0:
                    health_score -= min(warning_count * 5, 30)

                health_score = max(health_score, 0)

                # Store the full audit report as the summary
                update_data = {
                    "ai_summary": audit_report,
                    "ai_issues": ai_issues[:10],  # Store first 10 issues
                    "health_score": health_score,
                    "status": "reviewed",  # Final status after review completion
                    "analysis_status": "completed",
                    "reviewed_at": time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "review_duration_seconds": review_duration_seconds
                }

                print(f"[INFO] Review completed in {review_duration_seconds} seconds ({review_duration_seconds / 60:.2f} minutes)")

                await repository_service.update_mr_analysis(
                    repo_id=str(project_id),
                    mr_iid=mr_iid,
                    analysis_data=update_data
                )
                print(f"[✅] Updated MR {mr_iid} in MongoDB with AI analysis")

                # Update repository's running average review time
                await repository_service.update_repository_avg_review_time(
                    repo_id=str(project_id),
                    new_duration_seconds=review_duration_seconds
                )

                await add_log("completed", "🎉 Review completed successfully - Report published to merge request", "completed")
            except Exception as update_err:
                print(f"[⚠️] Failed to update MongoDB with AI analysis: {update_err}")

            if loading_note_id:
                try:
                    await gitlab_session.call_tool(
                        name="update_merge_request_note",
                        arguments={
                            "project_id": str(project_id),
                            "merge_request_iid": int(mr_iid),
                            "note_id": loading_note_id,
                            "body": final_report
                        }
                    )
                    print("[+] Review report updated in place!")
                except Exception as update_err:
                    print(f"[⚠️] Could not update note (ID: {loading_note_id}): {update_err}")
                    await gitlab_session.call_tool(
                        name="create_merge_request_note",
                        arguments={
                            "project_id": str(project_id),
                            "merge_request_iid": int(mr_iid),
                            "body": final_report
                        }
                    )
                    print("[+] Review report published as new comment!")
            else:
                await gitlab_session.call_tool(
                    name="create_merge_request_note",
                    arguments={
                        "project_id": str(project_id),
                        "merge_request_iid": int(mr_iid),
                        "body": final_report
                    }
                )
                print("[+] Review report published!")

            # 🎉 Set commit status to SUCCESS
            if commit_sha:
                print(f"[*] Setting commit status to SUCCESS...")
                try:
                    await gitlab_session.call_tool(
                        name="create_commit_status",
                        arguments={
                            "project_id": str(project_id),
                            "sha": commit_sha,
                            "state": "success",
                            "name": "gatekeeper/security-review",
                            "description": "✅ Gatekeeper review completed"
                        }
                    )
                    print("[+] Status set to SUCCESS!")
                except Exception as status_err:
                    print(f"[⚠️] Could not set commit status: {status_err}")

            # --- 🤖 AUTO-FIX FEATURE ---
            print("[*] Checking if issues can be auto-fixed via atomic patches...")
            await add_log("auto_fix", "🔧 Analyzing issues for potential auto-fix generation", "running")
            try:
                # Re-parse diff and create patch summary
                patch_parser = AtomicPatchParser(context_lines=3)
                atomic_patches = patch_parser.parse_unified_diff(raw_diff_content)
                patch_summary = create_patch_summary(atomic_patches)

                print("[DEBUG] Requesting fix analysis from Gemini...")
                fix_data = await asyncio.wait_for(
                    run_gemini_fix_analysis(audit_report, patch_summary, schema_context=schema_markdown, user_config=user_config),
                    timeout=60.0
                )

                # Delegate auto-fix branch application to remediation service
                await apply_auto_fixes(
                    project_id=str(project_id),
                    mr_iid=int(mr_iid),
                    mr_title=mr_title,
                    source_branch=source_branch,
                    atomic_patches=atomic_patches,
                    fix_data=fix_data,
                    gitlab_session=gitlab_session
                )
                await add_log("auto_fix", "✅ Auto-fix analysis complete - generating fix branches", "completed")

            except asyncio.TimeoutError:
                print("[⏱️] Fix analysis timed out after 60 seconds - skipping auto-fix")
                await add_log("auto_fix", "⏱️ Auto-fix analysis timed out - skipping", "completed")
            except json.JSONDecodeError as parse_err:
                print(f"[x] Failed to parse fix analysis JSON structure: {parse_err}")
                await add_log("auto_fix", "⚠️ Failed to parse fix analysis - skipping", "completed")
            except Exception as loop_err:
                print(f"[x] Auto-fix execution loop broken: {loop_err}")
                await add_log("auto_fix", "⚠️ Auto-fix encountered an error - skipping", "completed")

        except Exception as e:
            print(f"[x] Intelligent Gemini Audit loop failed: {e}")

            # Update MR status to failed
            try:
                await repository_service.update_mr_analysis(
                    repo_id=str(project_id),
                    mr_iid=mr_iid,
                    analysis_data={"status": "failed", "analysis_status": "error"}
                )
                print(f"[⚠️] Updated MR {mr_iid} status to 'failed'")
            except Exception as status_err:
                print(f"[⚠️] Failed to update MR status to 'failed': {status_err}")

            # ❌ Set commit status to FAILED on error
            if commit_sha and gitlab_session:
                try:
                    await gitlab_session.call_tool(
                        name="create_commit_status",
                        arguments={
                            "project_id": str(project_id),
                            "sha": commit_sha,
                            "state": "failed",
                            "name": "gatekeeper/security-review",
                            "description": f"❌ Gatekeeper review failed: {str(e)[:100]}"
                        }
                    )
                    print("[+] Status set to FAILED")
                except Exception as status_err:
                    print(f"[x] Failed to set error status: {status_err}")

    return {"status": "event_processed"}
