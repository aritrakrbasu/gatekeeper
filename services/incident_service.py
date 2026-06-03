import os
import time
import json
import re
import asyncio
from pydantic import BaseModel
from google.genai import types
from services import mcp_service, mongo_client
from services.gemini_service import ai_client


def apply_unified_patch(original_code: str, diff_patch: str) -> str:
    """
    Applies a unified diff patch string to original_code and returns the patched code.
    Fails gracefully by returning the original_code or doing a best-effort line replacement.
    """
    if not original_code:
        original_code = ""
    if not diff_patch:
        return original_code

    original_lines = original_code.splitlines()
    patch_lines = diff_patch.splitlines()

    hunks = []
    current_hunk = None
    hunk_header_re = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@')

    for line in patch_lines:
        match = hunk_header_re.match(line)
        if match:
            if current_hunk:
                hunks.append(current_hunk)
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) else 1
            current_hunk = {
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "lines": []
            }
        elif current_hunk is not None:
            current_hunk["lines"].append(line)

    if current_hunk:
        hunks.append(current_hunk)

    if not hunks:
        return original_code

    # Apply hunks from bottom to top to preserve line indices
    hunks.sort(key=lambda h: h["old_start"], reverse=True)
    result_lines = list(original_lines)

    for hunk in hunks:
        old_start = hunk["old_start"]
        old_count = hunk["old_count"]
        hunk_lines = hunk["lines"]

        expected_old_lines = []
        new_lines = []

        for hl in hunk_lines:
            if hl.startswith('-'):
                expected_old_lines.append(hl[1:])
            elif hl.startswith('+'):
                new_lines.append(hl[1:])
            elif hl.startswith(' '):
                expected_old_lines.append(hl[1:])
                new_lines.append(hl[1:])
            else:
                expected_old_lines.append(hl)
                new_lines.append(hl)

        start_idx = old_start - 1
        match_found = False

        # Match with sliding window offsets to handle minor line position deviations
        for offset in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
            idx = start_idx + offset
            if idx >= 0 and idx + len(expected_old_lines) <= len(result_lines):
                window = result_lines[idx : idx + len(expected_old_lines)]
                if all(w.strip() == e.strip() for w, e in zip(window, expected_old_lines)):
                    start_idx = idx
                    match_found = True
                    break

        if match_found:
            result_lines[start_idx : start_idx + len(expected_old_lines)] = new_lines
        else:
            print(f"[WARN] apply_unified_patch: Hunk old lines mismatch. Applying at exact start index fallback.")
            if 0 <= start_idx < len(result_lines):
                result_lines[start_idx : start_idx + old_count] = new_lines

    return '\n'.join(result_lines) + '\n'


async def process_production_crash(payload: dict) -> dict:
    """
    Asynchronously processes a production crash incident report from Dynatrace.
    Extracts stack trace, runs blast radius change check, diagnoses root cause,
    writes code patch, and submits an emergency Merge Request.
    """
    mongo_session = mcp_service.mongo_session
    gitlab_session = mcp_service.gitlab_session
    gitnexus_session = mcp_service.nexus_session
    dynatrace_session = mcp_service.dynatrace_session

    problem_id = payload.get("problem_id")
    problem_title = payload.get("title")
    impacted_service = payload.get("impacted_entity", "production-backend")

    print(f"[🚨] CRITICAL PRODUCTION CRASH DETECTED: Problem ID {problem_id} - '{problem_title}'")

    # 1. Log incoming high-priority incident signature to MongoDB via MCP
    logged = False
    if mongo_session:
        try:
            await mongo_session.call_tool(
                name="insert-many",
                arguments={
                    "database": "gatekeeper_dev",
                    "collection": "production_incidents",
                    "documents": [{"problem_id": problem_id, "title": problem_title, "service": impacted_service, "status": "triaging"}]
                }
            )
            logged = True
        except Exception as e:
            print(f"[x] DB Log via MCP failed: {e}. Trying direct client...")

    if not logged:
        try:
            await mongo_client.insert_one(
                collection_name="production_incidents",
                document={"problem_id": problem_id, "title": problem_title, "service": impacted_service, "status": "triaging"}
            )
            print("[+] Direct DB Log successful.")
        except Exception as e:
            print(f"[x] Direct DB Log failed: {e}")

    # 2. Extract Deep Root-Cause Intelligence from the Infrastructure Core
    if dynatrace_session and gitlab_session:
        try:
            print(f"[*] Extracting runtime execution stack-traces from Dynatrace Grail for Problem {problem_id}...")
            
            # Fetch detailed telemetry context regarding what broke
            raw_crash_telemetry = ""
            try:
                if str(problem_id) in ["999888", "777888"]:
                    raise ValueError("Simulating test incident")
                dt_details = await dynatrace_session.call_tool(
                    name="dynatrace:get-problem-details",
                    arguments={"problemId": str(problem_id)}
                )
                raw_crash_telemetry = str(dt_details.content)
                if "No problems found" in raw_crash_telemetry:
                    raise ValueError("Problem not found in Dynatrace environment")
            except Exception as e:
                # If we are testing or live lookup fails, fall back to mock details
                if str(problem_id) == "999888":
                    print("[*] Mock TypeError incident detected, loading fallback telemetry...")
                    raw_crash_telemetry = (
                        "Exception: TypeError in app.py\n"
                        "TypeError: create_transaction_schema() missing 1 required positional argument: 'card_number'\n"
                        "Traceback (most recent call last):\n"
                        "  File \"app.py\", line 160, in process_payment\n"
                        "    transaction_doc = create_transaction_schema(request.user_id, request.amount)\n"
                    )
                elif str(problem_id) == "777888":
                    print("[*] Mock NameError incident detected, loading fallback telemetry...")
                    raw_crash_telemetry = (
                        "Exception: NameError in models.py\n"
                        "NameError: name 'hash_pwd' is not defined\n"
                        "Traceback (most recent call last):\n"
                        "  File \"app.py\", line 125, in register_user\n"
                        "    user_doc = create_user_schema(request.username, request.email, request.password)\n"
                        "  File \"models.py\", line 22, in create_user_schema\n"
                        "    \"password\": hash_pwd,\n"
                    )
                else:
                    print(f"[x] Failed to fetch live problem details: {e}. Raising to exit pipeline.")
                    raise e
            print("[+] Stack trace extraction and event sequence loaded.")

            # --- 🔍 BRANCH AND COMMIT DIAGNOSIS LAYER ---
            # Query the project repository configuration to isolate what code is running in prod
            target_project_id = "82576405"  # Fallback target ID
            
            try:
                repos = await mongo_client.find("connected_repositories", {}, limit=1)
                if repos:
                    target_project_id = str(repos[0].get("id"))
                    print(f"[+] Dynamically selected target repository: {target_project_id}")
            except Exception as db_err:
                print(f"[WARN] Dynamic repo lookup failed: {db_err}. Using default: {target_project_id}")
            
            print("[*] Accessing GitLab workspace repository map...")
            # Fetch recent deployment logs or target files to see what was just pushed
            repo_context = await gitlab_session.call_tool(
                name="get_repository_archive", 
                arguments={"project_id": target_project_id}
            )

            # --- 🔍 GITNEXUS CODEBASE BLAST RADIUS MAPPING ---
            impact_radius_context = "No structural codebase call graphs accessible."
            if gitnexus_session:
                try:
                    nexus_analysis = await gitnexus_session.call_tool(
                        name="detect_changes",
                        arguments={}
                    )
                    impact_radius_context = str(nexus_analysis.content)
                except: pass

            # --- 🧠 GEMINI PRODUCTION DIAGNOSIS CORE ---
            print("[*] Presenting incident indicators to Gemini Pro for immediate root-cause extraction...")
            
            diagnosis_instruction = (
                "You are The Gatekeeper, an elite Site Reliability Engineer and automated debugging agent.\n"
                "You have been invoked because a production environment crash has occurred.\n"
                "Analyze the provided stack trace, error context, and current repo files to identify the root cause.\n"
                "Determine exactly which file and lines contain the structural error (e.g., memory leak, unhandled rejection, syntax bug)."
            )

            combined_incident_data = (
                f"LIVE DYNATRACE PRODUCTION EXCEPTION LOGS:\n{raw_crash_telemetry}\n\n"
                f"GITNEXUS CODEBASE DEPENDENCY INTERFACE MAP:\n{impact_radius_context}"
            )

            diagnosis_response = await asyncio.to_thread(
                ai_client.models.generate_content,
                model='gemini-3.1-pro-preview',
                contents=combined_incident_data,
                config=types.GenerateContentConfig(system_instruction=diagnosis_instruction, temperature=0.1)
            )
            diagnosis_report = diagnosis_response.text
            print("[+] Root-cause assessment successfully compiled.")

            # --- 🤖 REMEDIATION AND AUTO-HOTFIX SEQUENCE ---
            print("[*] Dispatching Gemini Flash to write surgical structural repair patch strings...")
            
            class IncidentFixDetail(BaseModel):
                file: str
                issue: str
                unified_diff_patch: str

            class IncidentRemediationSchema(BaseModel):
                fixable: bool
                patches: list[IncidentFixDetail]

            remediation_prompt = (
                f"Review this diagnostic analysis report regarding the ongoing production system crash:\n\n{diagnosis_report}\n\n"
                "Generate a targeted fix. Supply an atomic change block inside the 'unified_diff_patch' field to resolve the exception. "
                "You MUST output ONLY pure code snippets inside the schema parameters with no conversational text blocks."
            )

            fix_analysis = await asyncio.to_thread(
                ai_client.models.generate_content,
                model='gemini-2.5-flash',
                contents=remediation_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are an automated software patch generation engine. Output pure code configurations matching the response schema properties.",
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=IncidentRemediationSchema
                )
            )

            fix_data = json.loads(fix_analysis.text.strip())

            if fix_data.get("fixable") and fix_data.get("patches"):
                print(f"[🔧] Remediation path identified! Instantiating autonomous production hotfix branch...")
                
                timestamp = int(time.time())
                hotfix_branch = f"gatekeeper/hotfix-incident-{problem_id}-{timestamp}"

                # Spawn hotfix branch directly from the root baseline production branch ('main')
                await gitlab_session.call_tool(
                    name="create_branch",
                    arguments={"project_id": target_project_id, "branch": hotfix_branch, "ref": "main"}
                )

                patches_applied = []
                for patch in fix_data["patches"]:
                    file_path = patch.get("file")
                    issue_summary = patch.get("issue")
                    diff_patch = patch.get("unified_diff_patch")

                    if file_path and diff_patch:
                        try:
                            # Fetch live file content text, stitch it, and push it home
                            file_context = await gitlab_session.call_tool(
                                name="get_file_contents",
                                arguments={"project_id": target_project_id, "file_path": file_path, "ref": "main"}
                            )
                            
                            original_code = ""
                            if hasattr(file_context, "content") and file_context.content:
                                text_data = file_context.content[0].text
                                try:
                                    content_json = json.loads(text_data)
                                    content = content_json.get("content", "")
                                    encoding = content_json.get("encoding", "")
                                    if encoding == "base64":
                                        import base64
                                        original_code = base64.b64decode(content).decode("utf-8", errors="replace")
                                    else:
                                        original_code = content
                                except Exception:
                                        original_code = text_data
                            else:
                                original_code = str(file_context)
                            
                            # Use your native apply_unified_patch text stitching utility function 
                            resolved_code = apply_unified_patch(original_code, diff_patch)

                            await gitlab_session.call_tool(
                                name="create_or_update_file",
                                arguments={
                                    "project_id": target_project_id,
                                    "file_path": file_path,
                                    "content": resolved_code,
                                    "branch": hotfix_branch,
                                    "commit_message": f"fix(hotfix): autonomously patching incident {problem_id} - {issue_summary}"
                                }
                            )
                            patches_applied.append(f"- ✅ **{file_path}**: Resolved production crash vulnerability.")
                        except Exception as f_err:
                            print(f"[x] Surgical stitch process broken during incident triage on {file_path}: {f_err}")

                if patches_applied:
                    list_str = "\n".join(patches_applied)
                    # Autonomously open an emergency high-priority Hotfix Merge Request back into main!
                    await gitlab_session.call_tool(
                        name="create_merge_request",
                        arguments={
                            "project_id": target_project_id,
                            "source_branch": hotfix_branch,
                            "target_branch": "main",
                            "title": f"🚨 EMERGENCY HOTFIX: Resolve Incident {problem_id}",
                            "description": f"### 🛡️ The Gatekeeper Self-Healing Incident Report\n\nThis merge request was initialized autonomously in response to a production system downtime alert issued by Dynatrace.\n\n**Incident Diagnostic:** {problem_title}\n\n**Surgical Patches Stitched:**\n{list_str}\n\n---\n*⚠️ Action Required: Review analytics report and merge to restore cluster normalization parameters immediately.*"
                        }
                    )
                    print("[+] Emergency remediation sequence executed successfully. Hotfix PR is live!")

        except Exception as loop_err:
            print(f"[x] Production first-responder tracking cycle encountered exception: {loop_err}")

    return {"status": "incident_processed"}
