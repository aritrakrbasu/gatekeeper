import asyncio
import os
import sys
import shutil
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- CONFIGURATION ---
TARGET_REPO = "gitnexus-demo" 
REPO_PATH = r"D:\My space\the-gatekeeper\temp_workspace\project_82733194"
# ---------------------

def get_npx_command_and_args():
    """Smart resolver to handle Windows PowerShell and Linux binaries natively."""
    if sys.platform == "win32":
        return "powershell.exe", ["-NoLogo", "-Command", "npx -y gitnexus@latest mcp"]
    else:
        npx_path = shutil.which("npx")
        if not npx_path:
            raise FileNotFoundError("Could not find 'npx' on the Linux/macOS system PATH.")
        return npx_path, ["-y", "gitnexus@latest", "mcp"]


def clean_gitnexus_json(raw_output):
    """GitNexus often appends markdown (--- **Next:**...) to JSON. This strips it."""
    print(raw_output)
    return raw_output.split("\n---")[0].strip()


async def run_pr_audit_pipeline():
    cmd, args = get_npx_command_and_args()
    
    # Silence Node, npm, and GitNexus to prevent non-JSON logs from crashing MCP
    env = os.environ.copy()
    env["npm_config_loglevel"] = "silent"
    env["LOG_LEVEL"] = "error"
    env["GITNEXUS_LOG_LEVEL"] = "error"
    
    server_params = StdioServerParameters(command=cmd, args=args, env=env, cwd=REPO_PATH)
    
    print(f"[*] Spinning up GitNexus MCP Server using: {cmd} {' '.join(args[:3])}...")
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("[*] Connected! Starting automated PR audit pipeline...\n")
                
                # ==========================================
                # STEP 1: DETECT CHANGES
                # ==========================================
                print(f"[1/4] Detecting changed symbols in commit ...")
                changes_response = await session.call_tool(
                    name="detect_changes",
                    arguments={"repo": TARGET_REPO, "scope": "compare", 
                               
                        "scope": "compare",
                        "base_ref":  "feat/optimize-network"  ,  # The branch with changes
                        "head_ref": "code-upgrade"  }
                )
                
                changes_text = "".join(item.text for item in changes_response.content if hasattr(item, 'text'))
                
                try:
                    changes_data = json.loads(clean_gitnexus_json(changes_text))
                    changed_symbols = changes_data.get("changed_symbols", [])
                except json.JSONDecodeError as e:
                    print(f"[!] Failed to parse detect_changes JSON: {e}")
                    return

                if not changed_symbols:
                    print("[!] No symbols were changed. Safe to merge!")
                    return

                # We will just analyze the first changed symbol for this pipeline
                target_symbol = changed_symbols[0]["name"]
                print(f"      -> Found target to analyze: '{target_symbol}'")
                
                # ==========================================
                # STEP 2: CALCULATE BLAST RADIUS (IMPACT)
                # ==========================================
                print(f"\n[2/4] Calculating blast radius for '{target_symbol}'...")
                impact_response = await session.call_tool(
                    name="impact",
                    arguments={"repo": TARGET_REPO, "target": target_symbol, "direction": "upstream"}
                )
                
                impact_text = "".join(item.text for item in impact_response.content if hasattr(item, 'text'))
                
                try:
                    impact_data = json.loads(clean_gitnexus_json(impact_text))
                    # Extract Depth 1 (WILL BREAK) downstream dependencies
                    depth_1_items = impact_data.get("byDepth", {}).get("1", [])
                except json.JSONDecodeError as e:
                    print(f"[!] Failed to parse impact JSON: {e}")
                    return

                if not depth_1_items:
                    print(f"\n[*] No direct downstream dependencies found for '{target_symbol}'. Safe to merge!")
                    return
                
                print(f"      -> Found {len(depth_1_items)} files that WILL BREAK.")

                # ==========================================
                # STEP 3: FETCH DOWNSTREAM SOURCE CODE CONTEXT
                # ==========================================
                print("\n[3/4] Fetching source code context for downstream files...")
                audit_payloads = []
                
                for item in depth_1_items:
                    impacted_id = item.get("id")
                    file_path = item.get("filePath")
                    print(f"      -> Reading graph context for: {file_path}")
                    
                    context_response = await session.call_tool(
                        name="context",
                        arguments={"repo": TARGET_REPO, "uid": impacted_id}
                    )
                    
                    context_text = "".join(c.text for c in context_response.content if hasattr(c, 'text'))
                    
                    audit_payloads.append({
                        "impacted_file": file_path,
                        "dependency_name": item.get("name"),
                        "source_code_context": context_text
                    })

                # ==========================================
                # STEP 4: GENERATE GEMINI LLM PROMPT
                # ==========================================
                print("\n[4/4] Pipeline Complete! Generating LLM Audit Prompt...\n")
                
                # Constructing the exact prompt to send to the Gemini API
                gemini_prompt = f"""You are an expert Principal Software Engineer conducting an automated PR safety audit. 
A developer has submitted a Pull Request, and our graph engine has identified that this change will break downstream dependencies.

=== 1. THE PR CHANGE ===
Target Modified: {target_symbol}

=== 2. THE BLAST RADIUS ===
The following downstream files are directly importing/calling the modified code and are at Depth 1 (WILL BREAK) risk:
"""
                for payload in audit_payloads:
                    gemini_prompt += f"- {payload['impacted_file']}\n"
                
                gemini_prompt += "\n=== 3. DOWNSTREAM SOURCE CODE CONTEXT ===\n"
                for payload in audit_payloads:
                    gemini_prompt += f"\n--- File: {payload['impacted_file']} ---\n"
                    gemini_prompt += f"{payload['source_code_context']}\n"
                
                gemini_prompt += """
=== INSTRUCTIONS ===
Analyze the downstream source code context against the PR change. 
Write a highly specific, actionable comment to post on the developer's GitLab Merge Request. 
Explain exactly *why* their change breaks the downstream files, and provide the exact code snippets required to fix the downstream files so the PR can be safely merged.
"""
                
                print("=======================================================================")
                print(gemini_prompt)
                print("=======================================================================")

    except* Exception as eg:
        print(f"\n[!] Caught TaskGroup Exceptions. Unpacking deep errors:")
        def print_nested_errors(errors, depth=1):
            for exc in errors:
                if hasattr(exc, 'exceptions'):
                    print_nested_errors(exc.exceptions, depth + 1)
                else:
                    print(f"{' -> ' * depth}{type(exc).__name__}: {exc}")
        print_nested_errors(eg.exceptions)

if __name__ == "__main__":
    asyncio.run(run_pr_audit_pipeline())