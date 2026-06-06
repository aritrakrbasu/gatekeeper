# Arize Track Product Pipeline: Complete Story

## The Architecture Reality

**Critical Understanding**: The Gatekeeper uses **TWO separate observability channels**:

| Channel | Purpose | System | API |
|---------|---------|--------|-----|
| **Production Tracing** | Monitoring, Billing | Arize Cloud | `arize.otel.register()` |
| **Evaluations & Learning** | Self-Improvement | Phoenix | Phoenix SDK + Phoenix MCP |

```
┌─────────────────────────────────────────────────────────────────┐
│                    The Gatekeeper Agent                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  MR arrives ──→ Agent performs review                             │
│                      ↓                                            │
│           ┌──────────────────────┐                               │
│           │  Dual Observability │                               │
│           └──────────────────────┘                               │
│                      ↓                                            │
│         ┌────────────┴────────────┐                              │
│         ↓                         ↓                              │
│  ┌─────────────┐          ┌──────────────┐                      │
│  │ Arize Cloud │          │   Phoenix    │                      │
│  │  (Traces)   │          │ (Evaluations)│                      │
│  └─────────────┘          └──────────────┘                      │
│         ↓                         ↓                              │
│    Billing &              Self-Improvement                       │
│   Monitoring              Loop                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Complete Product Pipeline

### Stage 1: Code Review (Currently Working ✅)

```
GitLab Webhook → Review Service → Gemini AI → Review Posted
                                    ↓
                            Traced to Arize Cloud
                                    ↓
                        Span attributes: mr_id, project_id, file_count
```

**What we have:**
- Traces sent to Arize Cloud via `arize.otel.register()`
- Rich span attributes for filtering
- Used for billing and monitoring

---

### Stage 2: Quality Evaluation (Missing ❌)

**Add after each review:**

```python
# In review_service.py, after getting AI review
from ai_observability import get_phoenix_sdk_evaluator, EvaluationCriteria

evaluator = get_phoenix_sdk_evaluator()
eval_result = await evaluator.evaluate_review_async(
    diff=raw_diff_content,
    review=ai_review_text,
    criteria=[
        EvaluationCriteria.SECURITY_COVERAGE,    # Did we catch security issues?
        EvaluationCriteria.CLARITY,               # Is the review clear?
        EvaluationCriteria.ACTIONABILITY           # Can the developer act on it?
    ]
)
```

**What happens:**
1. Phoenix SDK evaluator runs LLM-as-a-Judge
2. Scores the review on each criterion (1-5 scale)
3. **Sends evaluation to Phoenix** (not Arize Cloud)
4. Links evaluation to the trace via OpenTelemetry context

**Data stored in Phoenix:**
```json
{
  "evaluation_id": "eval_abc123",
  "trace_id": "trace_xyz789",  // Links to Arize Cloud trace
  "criteria": {
    "security_coverage": {"score": 4, "reasoning": "..."},
    "clarity": {"score": 3, "reasoning": "..."},
    "actionability": {"score": 5, "reasoning": "..."}
  },
  "average_score": 4.0,
  "timestamp": "2026-06-05T10:30:00Z"
}
```

---

### Stage 3: Self-Introspection (Missing ❌)

**Before planning the next review:**

```python
# In planner.py, before generating plan
from config.phoenix_mcp import get_phoenix_bridge

bridge = await get_phoenix_bridge()

# Query: What worked well in similar past reviews?
similar_evals = await bridge.get_evaluations(
    limit=20,
    evaluator_name="quality_evaluator"
)

# Analyze patterns
high_quality_patterns = extract_success_patterns(similar_evals)
low_quality_patterns = extract_failure_patterns(similar_evals)

# Inform planning with this context
context["success_patterns"] = high_quality_patterns
context["avoid_patterns"] = low_quality_patterns
```

**What the agent learns:**
- What review patterns get high scores
- What patterns get low scores
- Which types of issues are commonly missed
- Which explanations are clearest

---

### Stage 4: Self-Improvement (Missing ❌)

**After completing a batch of reviews:**

```python
# In engine.py, after task completion
from ai_observability import get_prompt_manager, analyze_and_improve

# Get recent evaluations for this agent
recent_evals = await bridge.get_evaluations(hours_ago=24)

# Analyze: What's the weakest area?
weakness_analysis = await analyze_and_improve(
    recent_evals,
    prompt_name="senior_pr_reviewer"
)

# Example output:
# {
#   "weakest_criterion": "security_coverage",
#   "average_score": 2.8,
#   "suggestion": "Add explicit check for SQL injection patterns"
# }

# Create improved prompt version
new_version = prompt_manager.create_version(
    base_prompt_name="senior_pr_reviewer",
    modifications=weakness_analysis["suggestion"]
)

# Log the improvement
memory.log_message("system", f"Created prompt v{new_version.version_number} "
                              f"to address {weakness_analysis['weakest_criterion']}")
```

**What changes:**
- Prompt version v1.0 → v1.1 → v1.2 → ...
- Each version addresses a specific weakness
- A/B tests can compare versions
- Agent uses the best-performing version

---

## The Demo Story

### Narrator Script:

> "The Gatekeeper doesn't just perform code reviews - it learns from each review to get better over time. Let me show you how Arize makes this possible."

### Demo Flow:

#### 1. **Show the Current State**
```
Phoenix Dashboard → Evaluations Tab
- 150 reviews evaluated
- Average quality: 3.8/5
- Weakest area: Security coverage (2.9/5)
```

#### 2. **Trigger a New Review**
```
GitLab MR #456 → New vulnerability in authentication code

Agent queries Phoenix:
- "What did I miss in similar security reviews?"
- "What patterns got high security scores?"

→ Uses this context to perform review
```

#### 3. **Show Real-Time Evaluation**
```
Phoenix Dashboard → New evaluation appears
- Security coverage: 4/5 (improved!)
- Clarity: 4/5
- Actionability: 5/5
```

#### 4. **Show Self-Improvement**
```
Agent analyzes last 24 hours of evaluations:
→ "My security reviews improved 15% after focusing on auth patterns"
→ Creates new prompt version v1.3 with this knowledge
```

#### 5. **Show the Loop**
```
Execute → Evaluate → Learn → Improve → Execute (better)
```

---

## Why This Wins the Arize Track

### 1. **Self-Introspection** ✅
- Agent queries its own evaluations via Phoenix MCP
- Uses past performance to inform current decisions
- Demonstrates true self-reflection

### 2. **LLM-as-a-Judge** ✅
- Every review is automatically evaluated
- Uses Phoenix SDK evaluator with function calling
- Evaluations linked to traces via OpenTelemetry

### 3. **Self-Improvement** ✅
- Agent identifies weaknesses in its own reviews
- Creates prompt versions to address weaknesses
- Measurable improvement over time

### 4. **Production Ready** ✅
- Traces to Arize Cloud for monitoring
- Evaluations to Phoenix for learning
- Dual-channel architecture

---

## Implementation Priority

### Must Have (Core Story):
1. ✅ **Stage 2: Quality Evaluation**
   - Add Phoenix SDK evaluator to review_service.py
   - Every review gets evaluated
   - Evaluations visible in Phoenix dashboard

2. ✅ **Stage 3: Self-Introspection**
   - Add Phoenix MCP bridge to planner.py
   - Agent queries past evaluations before planning
   - Show query in logs/demo

3. ✅ **Demo Endpoint**
   - `/api/debug/phoenix/self-reflection`
   - Shows agent's own performance analysis

### Nice to Have (Complete Story):
4. **Stage 4: Self-Improvement**
   - Automated prompt versioning
   - A/B testing of prompt versions
   - Measurable improvement tracking

---

## Key Files to Modify

| File | Change | Purpose |
|------|--------|---------|
| `services/review_service.py` | Add evaluation after review | Stage 2 |
| `agents/planner.py` | Query Phoenix before planning | Stage 3 |
| `services/mcp_service.py` | Add Phoenix MCP session | Stage 3 |
| `config/__init__.py` | Export get_phoenix_bridge | Stage 3 |
| `main.py` | Add demo endpoint | Demo |

---

## Verification Checklist

### End-to-End Test:
1. [ ] Start app with Phoenix configured
2. [ ] Create test MR
3. [ ] Watch console: "Evaluating review quality..."
4. [ ] Check Phoenix dashboard: Evaluation appears
5. [ ] Create another MR
6. [ ] Watch console: "Querying 20 past evaluations..."
7. [ ] Hit `/api/debug/phoenix/self-reflection`
8. [ ] See performance trends

### Success Metrics:
- [ ] Every review has an evaluation in Phoenix
- [ ] Planner queries Phoenix before planning
- [ ] Demo endpoint shows self-reflection data
- [ ] Measurable improvement in evaluation scores

---

## Why This Actually Works

**The Architecture is Already There:**
- ✅ Phoenix client initialization exists
- ✅ Phoenix SDK evaluator exists
- ✅ Phoenix MCP bridge exists
- ✅ OpenTelemetry linking exists

**What's Missing:**
- ❌ Actually calling the evaluator
- ❌ Actually querying Phoenix
- ❌ Actually using the data

**The Fix:**
Connect the existing pieces together into a working pipeline.

This isn't about building new infrastructure - it's about **using what already exists** to create a closed-loop learning system that showcases Arize's full value for agentic applications.
