# Arize Track Implementation Plan: Arize Cloud-Only Architecture

## Context

**Architecture Decision**: Use **Arize Cloud exclusively** (no Phoenix)

**Current State:**
- ✅ Traces sent to Arize Cloud via `arize.otel.register()`
- ✅ `ArizeCloudClient` can query traces from Arize Cloud
- ✅ Billing service already queries Arize Cloud
- ❌ Evaluations not implemented
- ❌ Self-introspection not implemented

**Simplified Architecture:**
```
┌─────────────────────────────────────────────────────┐
│           The Gatekeeper Agent                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  MR → Agent Review → Arize Cloud Trace              │
│         ↓                                            │
│    Query own traces                                  │
│         ↓                                            │
│    Evaluate quality (LLM-as-a-Judge)                │
│         ↓                                            │
│    Store evaluation feedback                         │
│         ↓                                            │
│    Use past traces to improve                        │
│                                                      │
└─────────────────────────────────────────────────────┘
          All via Arize Cloud
```

---

## Stage 1: LLM-as-a-Judge with Arize Cloud

**Goal**: Evaluate reviews using Arize Cloud traces

### File: `services/review_service.py`

**Approach**: Use Gemini to evaluate the review, then store evaluation as a **trace annotation** in Arize Cloud

**Add after getting AI review** (around line 850):
```python
# ========================================================================
# STAGE 1: Evaluate Review Quality & Store in Arize Cloud
# ========================================================================
try:
    # Use Gemini to evaluate our own review (LLM-as-a-Judge)
    evaluation_prompt = f"""
You are an expert code review evaluator. Evaluate this AI-generated review:

REVIEW TO EVALUATE:
{ai_review}

ORIGINAL CODE DIFF:
{raw_diff_content[:2000]}  # First 2000 chars for context

Rate the review on these criteria (1-5 scale):
1. SECURITY_COVERAGE: Did it catch security vulnerabilities?
2. CLARITY: Is the explanation clear and understandable?
3. ACTIONABILITY: Can the developer act on the feedback?
4. COMPLETENESS: Did it cover all important issues?

Return JSON only:
{{
    "security_coverage": {{"score": 1-5, "reasoning": "..."}},
    "clarity": {{"score": 1-5, "reasoning": "..."}},
    "actionability": {{"score": 1-5, "reasoning": "..."}},
    "completeness": {{"score": 1-5, "reasoning": "..."}}
}}
"""

    from services.gemini_service import ai_client
    eval_response = await ai_client.generate_content(
        prompt=evaluation_prompt,
        system_instruction="You are a strict code review evaluator. Return only valid JSON.",
        temperature=0.1
    )

    # Parse evaluation
    import json
    eval_data = json.loads(eval_response)

    # Calculate average
    scores = [c["score"] for c in eval_data.values()]
    avg_score = sum(scores) / len(scores)

    print(f"[EVALUATION] Review quality: {avg_score:.1f}/5")
    for criterion, data in eval_data.items():
        print(f"[EVALUATION]   {criterion}: {data['score']}/5 - {data['reasoning'][:50]}...")

    # Store evaluation in MongoDB (for self-introspection)
    await mongo_client.insert_one("review_evaluations", {
        "mr_id": mr_iid,
        "project_id": project_id,
        "repository_id": repository_id,
        "average_score": avg_score,
        "evaluations": eval_data,
        "timestamp": datetime.utcnow(),
        "trace_id": None  # Will be linked after trace is complete
    })

except Exception as e:
    print(f"[WARN] Evaluation failed: {e}")
```

**Why This Works:**
- Uses existing Gemini client for evaluation
- Stores evaluations in MongoDB for querying
- Simple, no external dependencies
- Works with Arize Cloud traces

---

## Stage 2: Self-Introspection (Query Arize Cloud)

**Goal**: Before planning, query Arize Cloud for past trace patterns

### File: `agents/planner.py`

**Add at beginning of `generate_plan()` method**:
```python
async def generate_plan(self, context, registry, memories=None):
    """
    Generate execution plan using Gemini AI, enhanced with historical trace data.
    """

    # ========================================================================
    # STAGE 2: Self-Introspection - Query Arize Cloud Traces
    # ========================================================================
    arize_context = ""
    try:
        from config.arize_client import get_arize_client
        from services import mongo_client

        # Get Arize Cloud client
        client = await get_arize_client()

        if client and client.is_connected():
            # Query recent traces from Arize Cloud
            recent_traces = await client.get_recent_traces(
                limit=50,
                hours_ago=168,  # Last week
                project_name="gatekeeper"
            )

            if recent_traces:
                # Get evaluations from MongoDB (linked to traces)
                trace_ids = [t.get("trace_id") for t in recent_traces if t.get("trace_id")]

                if trace_ids:
                    evals = await mongo_client.find(
                        "review_evaluations",
                        {"trace_id": {"$in": trace_ids}},
                        limit=20
                    )

                    if evals:
                        # Calculate success patterns
                        avg_quality = sum(e["average_score"] for e in evals) / len(evals)

                        # Find top and bottom performers
                        high_scores = [e for e in evals if e["average_score"] >= 4.0]
                        low_scores = [e for e in evals if e["average_score"] < 3.0]

                        # Extract patterns
                        if high_scores:
                            top_criterion = self._find_strongest_area(high_scores)
                        if low_scores:
                            weak_criterion = self._find_weakest_area(low_scores)

                        arize_context = f"""

[SELF-REFLECTION FROM ARIZE CLOUD TRACES]
Analyzed {len(evals)} past reviews from Arize Cloud
Your average review quality: {avg_quality:.1f}/5

Strengths: {top_criterion if high_scores else 'Yet to be determined'}
Areas to improve: {weak_criterion if low_scores else 'None identified'}

Use this self-reflection to inform your planning.
"""
                        print(f"[INFO] Self-introspection: Queried {len(evals)} evaluations from Arize Cloud traces")

    except Exception as e:
        print(f"[WARN] Arize Cloud self-introspection failed: {e}")
        arize_context = "[Unable to retrieve Arize Cloud trace data]"

    # ... rest of existing planning code
    # Add arize_context to prompt
```

**Add helper method to `Planner` class**:
```python
def _find_strongest_area(self, evals):
    """Find the criterion with highest average scores."""
    criterion_sums = {}
    criterion_counts = {}

    for eval_data in evals:
        for criterion, data in eval_data.get("evaluations", {}).items():
            score = data.get("score", 0)
            criterion_sums[criterion] = criterion_sums.get(criterion, 0) + score
            criterion_counts[criterion] = criterion_counts.get(criterion, 0) + 1

    averages = {c: criterion_sums[c] / criterion_counts[c] for c in criterion_sums}
    return max(averages, key=averages.get) if averages else "None"

def _find_weakest_area(self, evals):
    """Find the criterion with lowest average scores."""
    criterion_sums = {}
    criterion_counts = {}

    for eval_data in evals:
        for criterion, data in eval_data.get("evaluations", {}).items():
            score = data.get("score", 0)
            criterion_sums[criterion] = criterion_sums.get(criterion, 0) + score
            criterion_counts[criterion] = criterion_counts.get(criterion, 0) + 1

    averages = {c: criterion_sums[c] / criterion_counts[c] for c in criterion_sums}
    return min(averages, key=averages.get) if averages else "None"
```

---

## Stage 3: Demo Endpoint (Arize Cloud Self-Reflection)

### File: `main.py`

**Add new endpoint**:
```python
@app.get("/api/debug/arize/self-reflection")
async def show_agent_self_reflection_arize():
    """
    Demo endpoint showing agent introspecting its own performance via Arize Cloud.
    """
    try:
        from config.arize_client import get_arize_client
        from services import mongo_client

        # Get Arize Cloud client
        client = await get_arize_client()

        if not client or not client.is_connected():
            return {
                "error": "Arize Cloud not connected",
                "message": "Configure ARIZE_API_KEY to enable self-reflection"
            }

        # Get recent traces from Arize Cloud
        traces = await client.get_recent_traces(
            limit=100,
            hours_ago=24,
            project_name="gatekeeper"
        )

        # Get linked evaluations
        trace_ids = [t.get("trace_id") for t in traces if t.get("trace_id")]

        evals = []
        if trace_ids:
            evals = await mongo_client.find(
                "review_evaluations",
                {"trace_id": {"$in": trace_ids}},
                limit=50
            )

        if evals:
            # Calculate metrics
            avg_quality = sum(e["average_score"] for e in evals) / len(evals)

            # Find weakest area
            weakest = _calculate_weakest_area(evals)

            return {
                "status": "connected",
                "message": "Agent is self-reflecting via Arize Cloud",
                "data_source": "Arize Cloud",
                "recent_reviews_traced": len(traces),
                "evaluations_performed": len(evals),
                "average_quality": round(avg_quality, 2),
                "weakest_area": weakest,
                "improvement_opportunity": f"Focus on {weakest['criterion']} (avg: {weakest['avg_score']:.1f}/5)"
            }
        else:
            return {
                "status": "connected",
                "message": "Arize Cloud connected but no evaluations yet",
                "recent_reviews_traced": len(traces),
                "suggestion": "Trigger some reviews to generate evaluation data"
            }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }

def _calculate_weakest_area(evals):
    """Helper to find weakest evaluation area."""
    criterion_scores = {}

    for eval_data in evals:
        for criterion, data in eval_data.get("evaluations", {}).items():
            score = data.get("score", 0)
            if criterion not in criterion_scores:
                criterion_scores[criterion] = []
            criterion_scores[criterion].append(score)

    weakest = {"criterion": "None", "avg_score": 0}
    for criterion, scores in criterion_scores.items():
        avg = sum(scores) / len(scores)
        if avg < weakest["avg_score"] or weakest["criterion"] == "None":
            weakest = {"criterion": criterion, "avg_score": avg}

    return weakest
```

---

## Stage 4: Config Exports

### File: `config/__init__.py`

**Update to export Arize Cloud utilities**:
```python
from .arize_client import get_arize_client, ArizeCloudClient

__all__.extend([
    "get_arize_client",
    "ArizeCloudClient",
])
```

---

## Implementation Order

### Step 1: Config Updates (2 minutes)
1. Update `config/__init__.py` to export `get_arize_client`

### Step 2: Evaluation Integration (15 minutes)
2. Add evaluation to `services/review_service.py`
3. Test: Trigger review, check MongoDB for evaluation

### Step 3: Self-Introspection (20 minutes)
4. Add helper methods to `agents/planner.py`
5. Add Arize Cloud query to `generate_plan()`
6. Test: Check logs for self-reflection message

### Step 4: Demo Endpoint (10 minutes)
7. Add endpoint to `main.py`
8. Test: Hit `/api/debug/arize/self-reflection`

**Total Time**: ~47 minutes

---

## Data Flow (Arize Cloud Only)

```
1. MR Arrives
   ↓
2. Agent Performs Review
   ↓
3. Review Traced to Arize Cloud (automatic via arize.otel)
   ↓
4. Gemini Evaluates Review (LLM-as-a-Judge)
   ↓
5. Evaluation Stored in MongoDB (with trace_id reference)
   ↓
6. Next Review: Query Arize Cloud for traces
   ↓
7. Get Evaluations from MongoDB (linked to traces)
   ↓
8. Use Patterns to Plan Better Review
   ↓
9. Perform Better Review → Better Trace → Better Evaluation
```

---

## Demo Script for Hackathon

### Setup (30 seconds):
1. Show Arize Cloud dashboard with traces
2. Show MongoDB has evaluation data
3. Explain the closed loop

### Live Demo (2 minutes):

**"Watch the agent self-reflect via Arize Cloud"**:

1. Create new MR
2. Show logs:
   ```
   [INFO] Performing code review...
   [INFO] Review quality: 4.2/5
   [INFO]   security_coverage: 5/5 - Excellent catch of auth bypass
   [INFO] Self-introspection: Queried 15 evaluations from Arize Cloud traces
   [INFO] Average quality: 3.9/5
   [INFO] Strengths: security_coverage
   [INFO] Areas to improve: clarity
   ```
3. Show demo endpoint output

### Narrative:
> "The Gatekeeper uses Arize Cloud for complete observability:
> - Every review is traced to Arize Cloud
> - Every review is evaluated for quality
> - The agent queries its own traces to learn patterns
> - Each review improves based on past performance
>
> This is the power of Arize Cloud for agentic applications."

---

## Why This Wins

### Meets All Arize Requirements:
- ✅ **Code-owned agent**: Custom WorkflowEngine
- ✅ **OpenInference tracing**: Arize Cloud via `arize.otel.register()`
- ✅ **Send traces to Arize Cloud**: Already working
- ✅ **Self-introspection**: Query own traces via Arize Cloud SDK
- ✅ **LLM-as-a-Judge**: Evaluate reviews using Gemini
- ✅ **Self-improvement**: Learn from trace patterns

### Advantages of Arize Cloud-Only:
1. **Simpler architecture**: Single platform
2. **Production-ready**: Arize Cloud is designed for production
3. **Billing integration**: Already uses Arize Cloud traces
4. **No Phoenix dependency**: One less system to manage

### Compelling Story:
- All traces in one place (Arize Cloud)
- Agent can query its own history
- Measurable improvement over time
- Production-ready from day one

This showcases **Arize Cloud as the complete observability solution for agentic applications**.
