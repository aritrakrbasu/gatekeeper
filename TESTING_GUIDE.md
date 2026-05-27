# Testing Guide - Arize Phoenix Hackathon

This guide covers how to test all the implemented features for the hackathon submission.

---

## Prerequisites Checklist

Before testing, ensure you have:

- [ ] Installed all dependencies: `pip install -r requirements.txt`
- [ ] Configured `.env` with valid credentials
- [ ] Phoenix Cloud account (free at https://app.phoenix.arize.com)
- [ ] A test GitLab project available

---

## Test 1: OpenInference Tracing

**Purpose:** Verify that all Gemini AI calls are automatically traced.

### Steps

1. **Start the application:**

   ```bash
   python main.py
   ```

2. **Verify startup messages:**

   ```
   [OK] Arize observability initialized - Google GenAI calls will be traced
   [✅] Google GenAI instrumentor registered
   [OK] Phoenix client initialized - Mode: https://app.phoenix.arize.com
   ```

3. **Trigger a code review:**
   - Create a test MR in your GitLab project
   - Or use a webhook testing tool like:

   ```bash
   curl -X POST http://localhost:8000/webhooks/gitlab \
     -H "Content-Type: application/json" \
     -H "X-GitLab-Event: Merge Request Hook" \
     -d '{"object_attributes":{"iid":1,"state":"opened","title":"Test MR"},"project":{"id":123}}'
   ```

4. **Check Phoenix Dashboard:**
   - Go to https://app.phoenix.arize.com
   - Navigate to **Traces**
   - Filter by: `project = "gatekeeper"`
   - You should see traces with span names like `generate_content`

5. **Verify Span Attributes:**
   - Click on a trace
   - Check that attributes include: `mr_id`, `project_id`, `operation`, `file_count`

### Expected Results

| Check           | Expected                                |
| --------------- | --------------------------------------- |
| Startup message | Shows "Arize observability initialized" |
| Traces appear   | Within 30 seconds of review             |
| Span attributes | Include MR metadata                     |
| Token counts    | Show prompt/completion tokens           |

### Troubleshooting

**No traces appearing?**

```bash
# Check .env has correct credentials
grep ARIZE .env

# Verify Phoenix is reachable
curl https://app.phoenix.arize.com/health
```

---

## Test 2: Phoenix MCP Bridge

**Purpose:** Verify self-introspection capabilities.

### Steps

1. **Check health endpoint:**

   ```bash
   curl http://localhost:8000/health
   ```

2. **Verify Phoenix status in response:**

   ```json
   {
     "status": "healthy",
     "phoenix_connected": true,
     "evaluations_enabled": true,
     "self_improvement_enabled": true
   }
   ```

3. **Test Phoenix MCP tools (Python REPL):**

   ```python
   import asyncio
   from config.phoenix_mcp import get_phoenix_bridge

   async def test():
       bridge = await get_phoenix_bridge()
       print(f"Connected: {bridge.is_connected()}")

       # Get recent traces
       traces = await bridge.get_recent_traces(limit=5)
       print(f"Found {len(traces)} traces")

       # Get performance metrics
       metrics = await bridge.get_performance_metrics(hours_ago=1)
       print(f"Avg latency: {metrics['average_latency_ms']}ms")

   asyncio.run(test())
   ```

### Expected Results

| Check                       | Expected                  |
| --------------------------- | ------------------------- |
| Health endpoint             | `phoenix_connected: true` |
| `get_recent_traces()`       | Returns list of traces    |
| `get_performance_metrics()` | Returns latency stats     |

---

## Test 3: LLM-as-a-Judge Evaluations

**Purpose:** Verify automatic evaluation of review quality.

### Steps

1. **Enable evaluations in `.env`:**

   ```bash
   ENABLE_EVALUATIONS=true
   JUDGE_MODEL=gemini-3-flash-preview
   ```

2. **Create a test file with a vulnerable code snippet:**

   Create `test_evaluation.py`:

   ```python
   import asyncio
   from ai_observability import get_evaluator, EvaluationCriteria

   async def test_evaluation():
       evaluator = get_evaluator()

       # Test diff with a security issue
       test_diff = """diff --git a/app.py b/app.py
   index 1234567..abcdefg 100644
   --- a/app.py
   +++ b/app.py
   @@ -1,1 +1,1 @@
   -query = f"SELECT * FROM users WHERE id={user_input}"
   +query = f"SELECT * FROM users WHERE id={user_input}"
   """

       # Mock review that mentions the issue
       test_review = """
   ```

## Security Issues

### Critical: SQL Injection

The code is vulnerable to SQL injection attacks. User input is directly
concatenated into the SQL query.

**Fix:** Use parameterized queries:

```python
query = "SELECT * FROM users WHERE id=?"
cursor.execute(query, (user_input,))
```

"""

       # Run evaluation
       result = await evaluator.evaluate_review(
           diff=test_diff,
           review=test_review,
           criteria=[
               EvaluationCriteria.SECURITY_COVERAGE,
               EvaluationCriteria.CLARITY,
           ]
       )

       print(f"Average Score: {result['average_score']}/5")
       print("\nCriteria Breakdown:")
       for eval_data in result['evaluations']:
           print(f"  {eval_data['criteria']}: {eval_data['score']}/5")

asyncio.run(test_evaluation())

````

3. **Run the test:**
```bash
python test_evaluation.py
````

### Expected Results

| Criteria          | Expected Score | Reason                                           |
| ----------------- | -------------- | ------------------------------------------------ |
| security_coverage | 4-5            | SQL injection was identified                     |
| clarity           | 3-4            | Explanation was clear but could be more detailed |

Output should show:

```
Average Score: 4.2/5

Criteria Breakdown:
  security_coverage: 5/5
  clarity: 4/5
```

---

## Test 4: Self-Improvement Loop

**Purpose:** Verify prompt versioning and improvement capabilities.

### Steps

1. **Enable self-improvement in `.env`:**

   ```bash
   ENABLE_SELF_IMPROVEMENT=true
   ```

2. **Test prompt versioning:**

   Create `test_self_improvement.py`:

   ```python
   import asyncio
   from ai_observability import get_prompt_manager

   async def test():
       manager = get_prompt_manager()

       # Check base prompt exists
       base_prompt = manager.load_base_prompt("senior_pr_reviewer")
       print(f"Base prompt length: {len(base_prompt)} chars")

       # Create a new version
       new_version = manager.create_version(
           base_prompt_name="senior_pr_reviewer",
           modifications="Add extra focus on SQL injection vulnerabilities"
       )
       print(f"Created version: {new_version.version_id}")

       # List all versions
       versions = list(manager.prompt_versions.keys())
       print(f"Total versions: {len(versions)}")
       print(f"Versions: {versions}")

       # Create an A/B experiment
       experiment = manager.create_experiment(
           name="SQL Injection Focus Test",
           versions=["senior_pr_reviewer", new_version.version_id]
       )
       print(f"Created experiment: {experiment.experiment_id}")

       # Simulate some results
       manager.record_evaluation("senior_pr_reviewer", 3.8, experiment.experiment_id)
       manager.record_evaluation(new_version.version_id, 4.2, experiment.experiment_id)

       # Check winner
       winner = experiment.get_winner()
       print(f"Winning version: {winner}")

   asyncio.run(test())
   ```

3. **Run the test:**

   ```bash
   python test_self_improvement.py
   ```

4. **Verify files created:**

   ```bash
   # Check versions directory
   ls prompts/versions/

   # Check experiments file
   cat config/experiments.json
   ```

### Expected Results

| Check               | Expected                                             |
| ------------------- | ---------------------------------------------------- |
| New version created | Version ID like `senior_pr_reviewer_20250126_123045` |
| File created        | `prompts/versions/{version_id}.json`                 |
| Experiment created  | Entry in `config/experiments.json`                   |
| Winner declared     | Version with higher score wins                       |

---

## Test 5: End-to-End Integration

**Purpose:** Test the complete flow from webhook to Phoenix.

### Steps

1. **Prepare test environment:**

   ```bash
   # Ensure Gatekeeper is running
   python main.py

   # In another terminal, export test vars
   export GITLAB_URL="https://gitlab.com"
   export GITLAB_TOKEN="your_test_token"
   ```

2. **Create a test MR with actual code:**

   In your test GitLab project:
   - Create a new branch: `test/security-review`
   - Add a file with intentional vulnerabilities:

   ```python
   # vulnerable.py
   def login(username, password):
       # SQL injection vulnerability
       query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
       return db.execute(query)
   ```

   - Create MR to main

3. **Watch Gatekeeper logs:**

   ```
   [+] Webhook caught MR !1 on Project 123
   [*] Starting Gatekeeper analysis pipeline...
   [✅] Step 2 complete: Raw code diffs retrieved
   [✅] Step 4 complete: Gemini analysis compiled
   ```

4. **Check Phoenix Dashboard:**

   Navigate to https://app.phoenix.arize.com and verify:

   a) **Traces Tab:**
   - Click "Traces"
   - Filter: `project = "gatekeeper"`
   - You should see the review trace
   - Click trace → View span attributes

   b) **Evaluations Tab:**
   - Click "Evaluations"
   - Filter by evaluator name
   - You should see quality scores

   c) **Datasets Tab:**
   - Check if review data is stored

5. **Verify MR comment:**
   - Check the MR in GitLab
   - Gatekeeper should have posted:
     - Security review findings
     - Impact analysis (if enabled)
     - Auto-fix suggestions (if issues found)

### Expected Results

| Component          | Expected Behavior            |
| ------------------ | ---------------------------- |
| Webhook processing | MR is accepted and processed |
| AI review          | Security issues identified   |
| Phoenix traces     | Trace appears within 30s     |
| Evaluation         | Score calculated and stored  |
| MR comment         | Review posted to GitLab      |

---

## Test 6: Performance & Metrics

**Purpose:** Verify performance tracking.

### Steps

1. **Process multiple reviews:**
   - Create 5-10 test MRs
   - Wait for all to be processed

2. **Query performance metrics:**

   ```python
   import asyncio
   from config.phoenix_mcp import get_phoenix_bridge

   async def test_metrics():
       bridge = await get_phoenix_bridge()
       metrics = await bridge.get_performance_metrics(hours_ago=1)

       print(f"Total traces: {metrics['total_traces']}")
       print(f"Avg latency: {metrics['average_latency_ms']}ms")
       print(f"Success rate: {metrics['success_rate']}%")
       print(f"Errors: {metrics['error_count']}")

   asyncio.run(test_metrics())
   ```

3. **Check Phoenix dashboard:**
   - Navigate to "Metrics"
   - View latency histogram
   - Check token usage chart

### Expected Results

| Metric       | Expected Range                      |
| ------------ | ----------------------------------- |
| Avg latency  | 5-30 seconds (depends on diff size) |
| Success rate | > 90%                               |
| Token usage  | Proportional to diff size           |

---

## Quick Verification Script

Save this as `verify_hackathon.py` and run to verify all features:

```python
"""
Quick verification script for Arize Phoenix Hackathon features.
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_all():
    print("=" * 50)
    print("Arize Phoenix Hackathon - Feature Verification")
    print("=" * 50)

    # 1. Check configuration
    print("\n[1/5] Configuration Check")
    arize_space = os.getenv("ARIZE_SPACE_ID")
    phoenix_api_key = os.getenv("PHOENIX_API_KEY")
    evals_enabled = os.getenv("ENABLE_EVALUATIONS", "false").lower() == "true"
    si_enabled = os.getenv("ENABLE_SELF_IMPROVEMENT", "false").lower() == "true"

    print(f"  Arize Space ID: {'✅' if arize_space and arize_space != 'your_space_id_here' else '❌'}")
    print(f"  Phoenix API Key: {'✅' if phoenix_api_key and phoenix_api_key != 'your_phoenix_api_key_here' else '❌'}")
    print(f"  Evaluations Enabled: {'✅' if evals_enabled else '❌'}")
    print(f"  Self-Improvement Enabled: {'✅' if si_enabled else '❌'}")

    # 2. Check Phoenix MCP Bridge
    print("\n[2/5] Phoenix MCP Bridge")
    try:
        from config.phoenix_mcp import get_phoenix_bridge
        bridge = await get_phoenix_bridge()
        print(f"  Connected: {'✅' if bridge.is_connected() else '❌'}")
        if bridge.is_connected():
            traces = await bridge.get_recent_traces(limit=1)
            print(f"  Can query traces: ✅")
    except Exception as e:
        print(f"  Error: ❌ {e}")

    # 3. Check LLM-as-a-Judge
    print("\n[3/5] LLM-as-a-Judge Evaluations")
    try:
        from ai_observability import get_evaluator, EvaluationCriteria
        evaluator = get_evaluator()
        print(f"  Evaluator initialized: ✅")
        print(f"  Available criteria: {len(EvaluationCriteria)}")
    except Exception as e:
        print(f"  Error: ❌ {e}")

    # 4. Check Self-Improvement
    print("\n[4/5] Self-Improvement Loop")
    try:
        from ai_observability import get_prompt_manager
        manager = get_prompt_manager()
        print(f"  Prompt manager initialized: ✅")
        print(f"  Versions tracked: {len(manager.prompt_versions)}")
        print(f"  Experiments: {len(manager.experiments)}")
    except Exception as e:
        print(f"  Error: ❌ {e}")

    # 5. Check OpenInference
    print("\n[5/5] OpenInference Instrumentation")
    try:
        from config.arize_config import is_arize_initialized, is_phoenix_configured
        print(f"  Arize initialized: {'✅' if is_arize_initialized() else '❌ (not required for tracing)'}")
        print(f"  Phoenix configured: {'✅' if is_phoenix_configured() else '❌'}")
    except Exception as e:
        print(f"  Error: ❌ {e}")

    print("\n" + "=" * 50)
    print("Verification Complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Trigger a code review via GitLab webhook")
    print("2. Check Phoenix dashboard: https://app.phoenix.arize.com")
    print("3. Verify traces appear in the Traces tab")
    print("4. Check evaluations in the Evaluations tab")

if __name__ == "__main__":
    asyncio.run(verify_all())
```

Run it:

```bash
python verify_hackathon.py
```

---

## Common Issues & Fixes

### Issue: "Phoenix not configured"

**Fix:**

```bash
# Add to .env
PHOENIX_API_KEY=your_actual_key_from_phoenix_dashboard
PHOENIX_BASE_URL=https://app.phoenix.arize.com
```

### Issue: "No traces appearing"

**Fix:**

1. Check Arize credentials: `grep ARIZE .env`
2. Verify network: `curl https://api.arize.com`
3. Check app logs for errors

### Issue: "Evaluator not working"

**Fix:**

```bash
# Add to .env
ENABLE_EVALUATIONS=true
JUDGE_MODEL=gemini-3-flash-preview
```

### Issue: "Self-improvement disabled"

**Fix:**

```bash
# Add to .env
ENABLE_SELF_IMPROVEMENT=true
```

---

## Demo Checklist for Hackathon

Use this checklist during your hackathon demo:

- [ ] Show `.env` configuration
- [ ] Start Gatekeeper and show startup messages
- [ ] Show health endpoint: `curl localhost:8000/health`
- [ ] Trigger a test MR review
- [ ] Show Phoenix dashboard with traces
- [ ] Click on a trace and show span attributes
- [ ] Show LLM-as-a-Judge evaluation results
- [ ] Demonstrate prompt versioning
- [ ] Show A/B experiment results
- [ ] Explain self-improvement loop

Good luck! 🚀
