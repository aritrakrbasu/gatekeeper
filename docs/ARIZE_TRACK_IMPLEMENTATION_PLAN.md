# Arize Track Implementation Plan: Self-Improving Agent

## Context

**Problem**: The Gatekeeper project has Arize/Phoenix infrastructure in place, but the key features are **not actually integrated**:
- Phoenix MCP bridge exists but isn't called
- Phoenix SDK evaluator exists but never runs
- Self-improvement module exists but isn't used

**Architecture Reality**: The project uses TWO observability channels:
- **Arize Cloud**: Production traces (billing, monitoring) - ALREADY WORKING
- **Phoenix**: Evaluations and self-improvement - NEEDS INTEGRATION

**Strategic Approach**: Implement a **closed-loop learning system** where the agent:
1. Performs reviews → Traced to Arize Cloud ✅
2. Evaluates review quality → Sends to Phoenix ❌ (need to add)
3. Queries past evaluations → Learns patterns ❌ (need to add)
4. Improves prompts → Gets better over time ❌ (need to add)

---

## Stage 1: Quality Evaluation (LLM-as-a-Judge)

**Goal**: Every review gets automatically evaluated for quality

### File: `services/review_service.py`

**Location**: In the `orchestrate_review()` function, after getting the AI review

**Current Code** (around line 850):
```python
# After getting ai_review from Gemini
ai_review = await run_gemini_review(...)
```

**Add After**:
```python
# ========================================================================
# STAGE 1: Evaluate Review Quality using Phoenix SDK Evaluator
# ========================================================================
try:
    from ai_observability import get_phoenix_sdk_evaluator, EvaluationCriteria

    evaluator = get_phoenix_sdk_evaluator()

    # Evaluate the review we just generated
    eval_result = await evaluator.evaluate_review_async(
        diff=raw_diff_content,
        review=ai_review,
        criteria=[
            EvaluationCriteria.SECURITY_COVERAGE,     # Did we catch security issues?
            EvaluationCriteria.CLARITY,                # Is the explanation clear?
            EvaluationCriteria.ACTIONABILITY,          # Can developer act on it?
            EvaluationCriteria.COMPLETENESS             # Did we cover all issues?
        ],
        metadata={
            "mr_id": mr_iid,
            "project_id": project_id,
            "repository_id": repository_id,
            "review_type": "security"
        }
    )

    # Log evaluation results
    print(f"[EVALUATION] Review quality: {eval_result['average_score']}/5")
    for eval_data in eval_result['evaluations']:
        print(f"[EVALUATION]   {eval_data['criteria']}: {eval_data['score']}/5")

    # Store evaluation in MongoDB for learning loop
    await mongo_client.insert_one("review_evaluations", {
        "mr_id": mr_iid,
        "project_id": project_id,
        "repository_id": repository_id,
        "average_score": eval_result["average_score"],
        "evaluations": eval_result["evaluations"],
        "timestamp": datetime.utcnow(),
        "trace_id": getattr(current_span, 'context', {}).get('trace_id', None)
    })

except Exception as e:
    print(f"[WARN] Evaluation failed: {e}")
    print("[INFO] Continuing without evaluation...")
```

### What This Does:
1. **Calls Phoenix SDK evaluator** - LLM-as-a-Judge runs
2. **Scores the review** - 1-5 scale on 4 criteria
3. **Sends to Phoenix** - Evaluation appears in Phoenix dashboard
4. **Stores in MongoDB** - For learning loop (Stage 3)
5. **Links to trace** - Via OpenTelemetry context

### Verification:
```bash
# After triggering a review, check Phoenix dashboard
# Navigate to: https://app.phoenix.arize.com
# Click: Evaluations tab
# Should see: New evaluation with scores
```

---

## Stage 2: Self-Introspection (Query Past Performance)

**Goal**: Before planning, query Phoenix for what worked in similar past reviews

### File 1: `services/mcp_service.py`

**Location**: In the `boot_mcp_bridge()` function (around line 50-100)

**Add to the function**:
```python
# ========================================================================
# Phoenix MCP Bridge Initialization
# ========================================================================
phoenix_bridge = None
phoenix_session = None

try:
    from config.phoenix_mcp import PhoenixMCPBridge

    if os.getenv("PHOENIX_API_KEY"):
        phoenix_bridge = PhoenixMCPBridge()
        if await phoenix_bridge.connect():
            print("[✅] Phoenix MCP bridge connected for self-introspection")

            # Create MCP session wrapper for Phoenix
            from mcp import ClientSession
            from agents.mcp_wrappers import BaseMCPTool

            # Create Phoenix MCP tools
            class PhoenixMCPWrapper(BaseMCPTool):
                def __init__(self, bridge):
                    self.bridge = bridge
                    self.session = None  # Direct HTTP calls instead

                async def call_tool(self, name, arguments):
                    if name == "query_evaluations":
                        return await self.bridge.get_evaluations(
                            limit=arguments.get("limit", 20)
                        )
                    elif name == "query_performance":
                        return await self.bridge.get_performance_metrics(
                            hours_ago=arguments.get("hours_ago", 24)
                        )
                    # Add more tool mappings as needed

            phoenix_session = PhoenixMCPWrapper(phoenix_bridge)

except Exception as e:
    print(f"[WARN] Phoenix MCP bridge initialization failed: {e}")
```

### File 2: `agents/planner.py`

**Location**: In the `generate_plan()` method (around line 50-150)

**Add at the beginning of the method**:
```python
async def generate_plan(self, context, registry, memories=None):
    """
    Generate execution plan using Gemini AI, enhanced with historical performance data.
    """

    # ========================================================================
    # STAGE 2: Self-Introspection - Query Past Performance
    # ========================================================================
    phoenix_context = ""
    try:
        from config.phoenix_mcp import get_phoenix_bridge

        bridge = await get_phoenix_bridge()
        if bridge and bridge.is_connected():
            # Get recent evaluations for similar reviews
            recent_evals = await bridge.get_evaluations(
                limit=20,
                hours_ago=168  # Last week
            )

            if recent_evals:
                # Calculate success patterns
                avg_score = sum(e.get("score", 0) for e in recent_evals) / len(recent_evals)

                # Find top performing reviews
                top_performers = [e for e in recent_evals if e.get("score", 0) >= 4.0]

                # Find common failure patterns
                low_performers = [e for e in recent_evals if e.get("score", 0) < 3.0]

                phoenix_context = f"""

[SELF-REFLECTION FROM PAST {len(recent_evals)} REVIEWS]
Your average review quality score: {avg_score:.1f}/5

{f'Patterns in high-scoring reviews (score ≥4.0): {len(top_performers)} instances' if top_performers else ''}
{f'Areas needing improvement: {len(low_performers)} reviews scored below 3.0' if low_performers else ''}

Use this self-reflection to inform your planning. Focus on:
- Security patterns that received high scores
- Explanation clarity that worked well
- Actionability that developers appreciated
"""
                print(f"[INFO] Queried {len(recent_evals)} past evaluations for context")

    except Exception as e:
        print(f"[WARN] Phoenix self-introspection failed: {e}")
        phoenix_context = "[Unable to retrieve past performance data]"

    # Rest of existing planning code
    # ... (existing code continues)

    # Add phoenix_context to the prompt
    system_instruction = base_prompt + phoenix_context
```

### What This Does:
1. **On startup**: Initializes Phoenix MCP bridge connection
2. **Before planning**: Queries Phoenix for past evaluations
3. **Analyzes patterns**: High scores vs low scores
4. **Injects context**: Adds self-reflection to planning prompt
5. **Improves decisions**: Agent uses past performance to plan better

### Verification:
```bash
# Check logs when triggering a review
# Should see: "[INFO] Queried 20 past evaluations for context"
# Planner uses this context in its prompt
```

---

## Stage 3: Demo Endpoint (Show Self-Reflection)

**Goal**: Make self-introspection visible for hackathon demo

### File: `main.py`

**Location**: Add new endpoint after line 1100 (after `/api/billing/debug`)

**Add**:
```python
@app.get("/api/debug/phoenix/self-reflection")
async def show_agent_self_reflection():
    """
    Demo endpoint showing agent introspecting its own performance.

    This demonstrates the core value of Arize: agents that can
    self-reflect and self-improve using their own observability data.
    """
    try:
        from config.phoenix_mcp import get_phoenix_bridge

        bridge = await get_phoenix_bridge()

        if not bridge or not bridge.is_connected():
            return {
                "error": "Phoenix not connected",
                "message": "Configure PHOENIX_API_KEY to enable self-reflection"
            }

        # Get agent's own recent evaluations
        evals = await bridge.get_evaluations(limit=50, hours_ago=24)

        # Get performance metrics
        metrics = await bridge.get_performance_metrics(hours_ago=24)

        # Calculate trends
        if evals:
            avg_quality = sum(e.get("score", 0) for e in evals) / len(evals)

            # Find weakest area
            criteria_scores = {}
            for eval_data in evals:
                for criterion in eval_data.get("evaluations", []):
                    name = criterion.get("criteria", "unknown")
                    score = criterion.get("score", 0)
                    if name not in criteria_scores:
                        criteria_scores[name] = []
                    criteria_scores[name].append(score)

            weakest_area = None
            lowest_avg = 5.0
            for criterion, scores in criteria_scores.items():
                avg = sum(scores) / len(scores)
                if avg < lowest_avg:
                    lowest_avg = avg
                    weakest_area = criterion

            return {
                "status": "connected",
                "message": "Agent is self-reflecting on its performance",
                "recent_reviews": len(evals),
                "average_quality": round(avg_quality, 2),
                "weakest_area": {
                    "criterion": weakest_area,
                    "average_score": round(lowest_avg, 2)
                },
                "total_evaluations": metrics.get("total_evaluations", 0),
                "improvement_opportunity": f"Focus on improving {weakest_area} scores"
            }
        else:
            return {
                "status": "connected",
                "message": "Phoenix connected but no evaluations yet",
                "recent_reviews": 0,
                "suggestion": "Trigger some reviews to generate evaluation data"
            }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
```

### What This Does:
1. **Queries Phoenix** for agent's own evaluations
2. **Calculates metrics**: Average quality, weakest area
3. **Shows improvement opportunity**: What to focus on
4. **Demonstrates self-reflection**: Agent knows its own performance

### Verification:
```bash
# After running reviews, hit the endpoint
curl http://localhost:8000/api/debug/phoenix/self-reflection

# Should see:
{
  "status": "connected",
  "recent_reviews": 15,
  "average_quality": 3.8,
  "weakest_area": {
    "criterion": "security_coverage",
    "average_score": 3.2
  },
  "improvement_opportunity": "Focus on improving security_coverage scores"
}
```

---

## Stage 4: Config Exports (Make Accessible)

### File: `config/__init__.py`

**Add to existing file**:
```python
# Add to existing exports
from .arize_config import (
    # ... existing exports ...
    is_phoenix_configured,
    get_phoenix_client,
)

# Add Phoenix MCP bridge
try:
    from .phoenix_mcp import get_phoenix_bridge, PhoenixMCPBridge
    _phoenix_available = True
except ImportError:
    _phoenix_available = False

if _phoenix_available:
    __all__.extend([
        "is_phoenix_configured",
        "get_phoenix_client",
        "get_phoenix_bridge",
        "PhoenixMCPBridge",
    ])
```

---

## Implementation Order

### Step 1: Foundation (5 minutes)
1. Update `config/__init__.py` to export Phoenix utilities
2. Test: `from config import get_phoenix_bridge`

### Step 2: Evaluation Integration (15 minutes)
3. Add evaluation to `services/review_service.py`
4. Test: Trigger a review, check Phoenix dashboard

### Step 3: Self-Introspection (20 minutes)
5. Add Phoenix MCP to `services/mcp_service.py`
6. Add context query to `agents/planner.py`
7. Test: Check logs for "Queried N past evaluations"

### Step 4: Demo Endpoint (10 minutes)
8. Add endpoint to `main.py`
9. Test: Hit `/api/debug/phoenix/self-reflection`

**Total Time**: ~50 minutes

---

## Verification Checklist

### After Implementation:

**Step 1: Verify Phoenix Connection**
```bash
# Check startup logs
# Should see: "[✅] Phoenix MCP bridge connected"
```

**Step 2: Trigger Review**
```bash
# Create test MR in GitLab
# Watch logs for evaluation output
```

**Step 3: Check Phoenix Dashboard**
```
1. Go to https://app.phoenix.arize.com
2. Click "Evaluations" tab
3. Should see: New evaluation with scores
```

**Step 4: Verify Self-Introspection**
```bash
# Check logs when second review triggers
# Should see: "[INFO] Queried N past evaluations for context"
```

**Step 5: Test Demo Endpoint**
```bash
curl http://localhost:8000/api/debug/phoenix/self-reflection

# Should return JSON with performance metrics
```

---

## Demo Script for Hackathon

### Setup (1 minute):
1. Show Phoenix dashboard with existing evaluations
2. Show current average quality score
3. Identify weakest area

### Live Demo (2 minutes):

**"Watch the agent self-reflect"**:

1. Create new MR with vulnerability
2. Show agent querying past evaluations:
   ```
   [INFO] Queried 20 past evaluations for context
   [INFO] Average quality: 3.7/5
   [INFO] Weakest area: security_coverage (3.2/5)
   ```
3. Agent performs review with this context
4. Show evaluation appearing in Phoenix dashboard
5. Hit demo endpoint to show self-reflection

**"The agent knows its own weaknesses"**:

```json
{
  "recent_reviews": 21,
  "average_quality": 3.8,
  "weakest_area": {
    "criterion": "security_coverage",
    "average_score": 3.3
  },
  "improvement_opportunity": "Focus on improving security_coverage scores"
}
```

### Narrative:
> "The Gatekeeper doesn't just perform code reviews - it learns from each review.
> Every review is evaluated, and the agent uses that data to improve future performance.
> This is the power of Arize: agents that can self-reflect and self-improve."

---

## Why This Wins

### Meets All Arize Requirements:
- ✅ **Code-owned agent**: Custom WorkflowEngine
- ✅ **OpenInference tracing**: Already working with Arize Cloud
- ✅ **Send traces to Phoenix**: Evaluations sent to Phoenix
- ✅ **Phoenix MCP server**: Agent queries own evaluations
- ✅ **LLM-as-a-Judge**: Every review evaluated
- ✅ **Self-improvement**: Agent uses past performance

### Compelling Story:
1. **Production observability** via Arize Cloud
2. **Quality evaluation** via Phoenix SDK
3. **Self-introspection** via Phoenix MCP
4. **Closed-loop learning** - the agent gets better

This showcases **the full value of Arize for agentic applications**.
