"""
Test script for Sentry Bug Fixing Workflow.

This script tests the enhanced Sentry workflow that:
1. Analyzes if the issue is MongoDB schema or code-based
2. Plans appropriate tools based on problem type
3. Executes the workflow with proper tool chaining
"""

import asyncio
import json
from agents.workflows import run_sentry_bug_workflow

# Demo Sentry issue payload
SENTRY_PAYLOAD = {
    "_id": {
        "$oid": "6a23d627946080d66106c736"
    },
    "action": "unresolved",
    "installation": {
        "uuid": "6614aec7-c8f0-48d6-84b8-698e63b635a6"
    },
    "data": {
        "issue": {
            "id": "125567929",
            "shareId": None,
            "shortId": "GITNEXUS-DEMO-4",
            "title": "TypeError: Cannot read properties of null (reading 'theme')",
            "culprit": "/",
            "permalink": "https://gatekeeper-nj.sentry.io/issues/125567929/",
            "logger": None,
            "level": "error",
            "status": "unresolved",
            "statusDetails": {},
            "substatus": "regressed",
            "isPublic": False,
            "platform": "javascript",
            "environment": "production",  # ADDED: Mark as production for breaking bug detection
            "project": {
                "id": "4511515682209872",
                "name": "gitnexus-demo",
                "slug": "gitnexus-demo",
                "platform": "javascript-react"
            },
            "type": "error",
            "metadata": {
                "value": "Cannot read properties of null (reading 'theme')",
                "type": "TypeError",
                "filename": "..\\..\\src\\BugShowcase.tsx",
                "function": "<object>.{children#2}.onClick",
                "in_app_frame_mix": "mixed",
                "sdk": {
                    "name": "sentry.javascript.react",
                    "name_normalized": "sentry.javascript.react"
                },
                "initial_priority": 75,
                "title": None
            },
            "numComments": 0,
            "assignedTo": None,
            "isBookmarked": False,
            "isSubscribed": False,
            "subscriptionDetails": None,
            "hasSeen": False,
            "annotations": [],
            "issueType": "error",
            "issueCategory": "error",
            "priority": "high",
            "priorityLockedAt": None,
            "seerFixabilityScore": 0.6953399777412415,
            "seerAutofixLastTriggered": None,
            "seerExplorerAutofixLastTriggered": None,
            "isUnhandled": False,
            "count": "2",
            "userCount": 0,
            "firstSeen": "2026-06-06T06:54:40.190000Z",
            "lastSeen": "2026-06-06T08:11:03.965000Z"
        }
    },
    "actor": {
        "type": "application",
        "id": "sentry",
        "name": "Sentry"
    },
    "received_at": "2026-06-06T08:11:19.332419"
}


async def test_sentry_workflow():
    """
    Test the Sentry bug fixing workflow with the demo payload.

    Expected behavior:
    1. Identify this as a CODE problem (TypeError, null reference)
    2. Plan steps: clone_repo → gitnexus_analyze → gitnexus_grep → gitnexus_file → impact_analysis → create_branch → generate_fix → commit → create_mr
    3. Execute the workflow and attempt to fix the bug
    """
    print("=" * 80)
    print("SENTRY BUG FIXING WORKFLOW TEST")
    print("=" * 80)
    print(f"\nIssue Title: {SENTRY_PAYLOAD['data']['issue']['title']}")
    print(f"Error Type: {SENTRY_PAYLOAD['data']['issue']['metadata']['type']}")
    print(f"Error Message: {SENTRY_PAYLOAD['data']['issue']['metadata']['value']}")
    print(f"Filename: {SENTRY_PAYLOAD['data']['issue']['metadata']['filename']}")
    print(f"Function: {SENTRY_PAYLOAD['data']['issue']['metadata']['function']}")
    print(f"\nExpected Problem Type: CODE PROBLEM (TypeError, null reference)")
    print("Expected Workflow Steps:")
    print("  1. clone_repo_step")
    print("  2. gitnexus_analysis_step")
    print("  3. gitnexus_grep_step (search for 'theme' or 'BugShowcase')")
    print("  4. gitnexus_file_step (read BugShowcase.tsx)")
    print("  5. impact_analysis_step")
    print("  6. create_branch_step")
    print("  7. generate_fix_step")
    print("  8. commit_fix_step")
    print("  9. create_mr_step")
    print("\n" + "=" * 80)

    # User credentials for GitLab operations
    # Replace with actual values or use environment variables
    user_id = "sentry-operator"
    username = "sentry-operator"
    target_project_id = "82576405"  # Replace with actual project ID

    print("\n[*] Starting Sentry bug fixing workflow...")
    result = await run_sentry_bug_workflow(
        payload=SENTRY_PAYLOAD,
        user_id=user_id,
        username=username,
        target_project_id=target_project_id
    )

    print("\n" + "=" * 80)
    print("WORKFLOW RESULT")
    print("=" * 80)
    print(json.dumps(result, indent=2))
    print("=" * 80)

    # Check if workflow succeeded
    if result.get("status") == "completed":
        print("\n[OK] Workflow completed successfully!")
        print(f"  Issue ID: {result.get('issue_id')}")
        print(f"  Result: {result.get('result', {})}")
    elif result.get("status") == "ignored":
        print("\n[INFO] Issue ignored (not a breaking bug)")
        print(f"  Reason: {result.get('reason')}")
    elif result.get("status") == "error":
        print("\n[ERROR] Workflow failed with error")
        print(f"  Error: {result.get('message')}")
    else:
        print(f"\n[UNKNOWN] Unknown status: {result.get('status')}")


async def test_planner_only():
    """
    Test only the planner to see what steps it generates.

    This is useful for debugging the planning logic without executing.
    """
    from agents.context import ContextBuilder, normalize_sentry_payload
    from agents.planner import PlannerAgent
    from agents.workflows import build_sentry_registry
    from agents.registry import ToolRegistry

    print("=" * 80)
    print("PLANNER TEST ONLY")
    print("=" * 80)

    # Normalize payload
    normalized = normalize_sentry_payload(SENTRY_PAYLOAD)

    # Build context
    agent_context = await ContextBuilder.build_from_sentry_issue(
        normalized,
        user_id="sentry-operator",
        username="sentry-operator",
        target_project_id="82576405"
    )

    print(f"\n[*] Context built with objective: {agent_context.objective[:100]}...")

    # Build registry
    registry = await build_sentry_registry()

    # Test planner
    planner = PlannerAgent()
    print("\n[*] Generating plan...")

    try:
        steps = await planner.generate_plan(
            context=agent_context,
            registry=registry,
            history_steps=None,
            memories=None,
            aril=None
        )

        print("\n" + "=" * 80)
        print("GENERATED PLAN STEPS")
        print("=" * 80)
        for i, step in enumerate(steps, 1):
            print(f"\nStep {i}: {step.step_id}")
            print(f"  Tool: {step.tool_name}")
            print(f"  Action: {step.action}")
            print(f"  Reason: {step.reason}")
            print(f"  Dependencies: {step.dependencies}")
            print(f"  Arguments: {step.arguments_json[:100]}...")

        print("\n" + "=" * 80)
        print(f"Total Steps: {len(steps)}")
        print("Expected: 9 steps for code problem workflow")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Planner failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys

    # Get mode from command line argument (default to planner test)
    mode = sys.argv[1] if len(sys.argv) > 1 else "1"

    print("\nSENTRY WORKFLOW TEST")
    print("=" * 80)
    print("Choose test mode:")
    print("  1. Planner test only (fast, no execution)")
    print("  2. Full workflow test (slow, executes all steps)")
    print("=" * 80)
    print(f"\n[*] Running in mode: {mode} ({'Planner test' if mode == '1' else 'Full workflow'})")

    if mode == "2":
        print("\n[*] Running full workflow test...")
        asyncio.run(test_sentry_workflow())
    else:
        print("\n[*] Running planner test only...")
        asyncio.run(test_planner_only())
