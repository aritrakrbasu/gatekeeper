# The Gatekeeper - Arize Phoenix Hackathon Submission

## Overview

**The Gatekeeper** is an AI-powered code review system that analyzes GitLab merge requests using Google Gemini AI. For the Google Cloud Rapid Agent Hackathon, we've integrated **Arize Phoenix** for comprehensive observability, **LLM-as-a-Judge evaluations**, and a **self-improvement loop** that enables the agent to learn from its reviews.

---

## Hackathon Features Implemented

### 1. ✅ OpenInference Auto-Instrumentation

**Implementation:** `config/arize_config.py`

All Gemini AI calls are automatically traced using OpenInference instrumentation:

- **Traces:** Every code review generation is fully traced
- **Span Attributes:** Custom metadata including MR ID, project ID, file count
- **Token Usage:** Automatic tracking of prompt and completion tokens
- **Latency:** Precise timing for each AI operation

```python
from config.arize_config import init_arize, instrument_google_genai

# Initialize Arize observability
init_arize(project_name="gatekeeper")
instrument_google_genai()

# All genai.Client() calls are now automatically traced
ai_client = genai.Client()
```

**Key Files:**

- `config/arize_config.py` - OpenInference initialization
- `main.py` - Auto-instrumented client usage

---

### 2. ✅ Phoenix MCP Server Integration (Self-Introspection)

**Implementation:** `config/phoenix_mcp.py`

The Gatekeeper can query its own traces, evaluations, and experiments at runtime via the Phoenix MCP bridge:

**Available MCP Tools:**

- `get_recent_traces()` - Retrieve recent review traces
- `get_trace_details()` - Get detailed trace information
- `get_evaluations()` - Fetch LLM-as-a-Judge results
- `get_evaluation_summary()` - Aggregate evaluation metrics
- `get_experiments()` - Access A/B experiment results
- `query_traces_by_metadata()` - Search traces by MR/project
- `get_performance_metrics()` - Latency and success rate stats

```python
from config.phoenix_mcp import get_phoenix_bridge

# Get the Phoenix MCP bridge
bridge = await get_phoenix_bridge()

# Query recent traces
traces = await bridge.get_recent_traces(limit=10, hours_ago=24)

# Get evaluation summary
summary = await bridge.get_evaluation_summary(hours_ago=24)
print(f"Average score: {summary['average_score']}")
```

**Key Files:**

- `config/phoenix_mcp.py` - PhoenixMCPBridge class
- `main.py` - Integration with MCP bridge

---

### 3. ✅ LLM-as-a-Judge Evaluations

**Implementation:** `ai_observability/evaluators.py`

Every code review is automatically evaluated using Gemini as the judge model:

**Evaluation Criteria:**
| Criteria | Description |
|----------|-------------|
| `security_coverage` | Did it catch security vulnerabilities? |
| `code_quality_coverage` | Did it identify quality problems? |
| `actionability` | Are fixes actionable and specific? |
| `clarity` | Is the explanation clear? |
| `completeness` | Did it cover all relevant issues? |
| `correctness` | Are findings accurate (no false positives)? |

```python
from ai_observability import get_evaluator

# Get the evaluator
evaluator = get_evaluator()

# Evaluate a review
result = await evaluator.evaluate_review(
    diff=code_diff,
    review=ai_review,
    criteria=[EvaluationCriteria.SECURITY_COVERAGE, EvaluationCriteria.CLARITY],
)

print(f"Average score: {result['average_score']}/5")
```

**Key Files:**

- `ai_observability/evaluators.py` - ReviewQualityEvaluator class
- Evaluation results logged to Phoenix
- Scores displayed in MR comments

---

### 4. ✅ Self-Improvement Loop (Bonus)

**Implementation:** `ai_observability/self_improvement.py`

The Gatekeeper learns from its evaluations and improves its prompts over time:

**Features:**

- **Prompt Versioning:** Track all prompt versions with timestamps
- **Weakness Analysis:** Identify patterns in low-scoring evaluations
- **A/B Experiments:** Test prompt variations and promote winners
- **Automated Improvement:** AI-suggested prompt modifications

```python
from ai_observability import get_prompt_manager

manager = get_prompt_manager()

# Analyze recent evaluations for weaknesses
weaknesses = manager.analyze_weaknesses(recent_evaluations)

# Create an improved prompt version
new_version = manager.create_version(
    base_prompt_name="senior_pr_reviewer",
    modifications="Focus more on SQL injection detection",
)

# Create an A/B experiment
experiment = manager.create_experiment(
    name="SQL Injection Focus Test",
    versions=["senior_pr_reviewer", new_version.version_id],
)

# Record evaluation results
manager.record_evaluation(
    version_id=new_version.version_id,
    score=4.2,
    experiment_id=experiment.experiment_id,
)
```

**Key Files:**

- `ai_observability/self_improvement.py` - SelfImprovingPromptManager
- `prompts/versions/` - Version history storage
- `config/experiments.json` - Experiment tracking

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│  ┌──────────────┐  ┌───────────────────┐  ┌─────────────────┐ │
│  │   Arize      │  │  Phoenix MCP      │  │   LLM-as-a-     │ │
│  │   Config     │──▶│  Bridge           │──▶│   Judge         │ │
│  │              │  │  (Self-Introspect)│  │   (Evaluations) │ │
│  └──────────────┘  └───────────────────┘  └─────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│                    ┌─────────────────────┐                     │
│                    │  Self-Improvement   │                     │
│                    │  Loop               │                     │
│                    │  (Prompt Learning)  │                     │
│                    └─────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Phoenix Cloud                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Traces    │  Evaluations    │  Experiments   │ Datasets│    │
│  │  (LLM)     │  (LLM-as-a-Judge)│ (A/B Tests)   │         │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Environment Configuration

Create a `.env` file with the following:

```bash
# Arize Observability
ARIZE_SPACE_ID=your_space_id_here
ARIZE_API_KEY=your_api_key_here

# Phoenix Cloud
PHOENIX_MODE=cloud
PHOENIX_API_KEY=your_phoenix_api_key_here
PHOENIX_BASE_URL=https://app.phoenix.arize.com

# Features
ENABLE_EVALUATIONS=true
ENABLE_SELF_IMPROVEMENT=true
JUDGE_MODEL=gemini-3-flash-preview
```

---

## Verification Steps

### 1. Check OpenInference Tracing

```bash
# Start Gatekeeper
python main.py

# Trigger a PR review via GitLab webhook

# Check Phoenix dashboard for traces
# https://app.phoenix.arize.com
# Navigate to: Traces → Filter by project="gatekeeper"
```

**Expected:** Traces appear with span attributes for MR metadata.

### 2. Test Phoenix MCP Tools

```bash
# Health check includes Phoenix status
curl http://localhost:8000/health

# Response includes:
# "phoenix_connected": true
```

**Expected:** Phoenix connection status reported in health endpoint.

### 3. Verify LLM-as-a-Judge Evaluations

After a code review completes:

```bash
# Check Phoenix for evaluation results
# Navigate to: Evaluations → Filter by model
```

**Expected:** Evaluation scores for each criteria (1-5 scale).

### 4. Test Self-Improvement Loop

```python
# In Python REPL
from ai_observability import get_prompt_manager

manager = get_prompt_manager()

# Create a new prompt version
version = manager.create_version(
    base_prompt_name="senior_pr_reviewer",
    modifications="Add emphasis on performance optimization",
)

# List versions
print(list(manager.prompt_versions.keys()))
```

**Expected:** New version created and stored in `prompts/versions/`.

---

## File Structure

```
the-gatekeeper/
├── config/
│   ├── arize_config.py          # OpenInference initialization
│   ├── phoenix_mcp.py           # Phoenix MCP bridge
│   ├── experiments.json         # A/B experiment tracking
│   └── __init__.py
├── ai_observability/
│   ├── evaluators.py            # LLM-as-a-Judge implementation
│   ├── self_improvement.py      # Self-improvement loop
│   └── __init__.py
├── prompts/
│   ├── senior_pr_reviewer.md    # Base system prompt
│   └── versions/                # Prompt version history
├── main.py                      # FastAPI app with all integrations
├── HACKATHON_SUBMISSION.md      # This file
└── requirements.txt             # Python dependencies
```

---

## Technical Implementation Details

### OpenInference Instrumentation

We use `openinference-instrumentation-google-genai` for automatic tracing:

```python
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

# This instruments all genai.Client() calls automatically
GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
```

**Benefits:**

- Zero code changes needed for tracing
- Automatic span propagation
- Built-in token usage tracking
- Standardized span attributes

### Phoenix MCP Bridge

The PhoenixMCPBridge class wraps the Phoenix REST API:

```python
class PhoenixMCPBridge:
    async def get_recent_traces(self, limit=10, span_name=None)
    async def get_evaluations(self, limit=50, evaluator_name=None)
    async def get_evaluation_summary(self, hours_ago=24)
    async def get_experiments(self, limit=20)
```

**Integration:** Added to main.py's boot_mcp_bridge() function alongside MongoDB, GitLab, and GitNexus MCP connections.

### LLM-as-a-Judge Implementation

The ReviewQualityEvaluator uses Gemini to evaluate review quality:

1. For each criteria, construct a specialized evaluation prompt
2. Call Gemini with the code diff and review
3. Extract score (1-5) from the evaluation response
4. Aggregate scores and calculate average
5. Log results to Phoenix

**Evaluation Flow:**

```
Code Diff + AI Review → Judge Model → Score + Explanation → Phoenix
```

### Self-Improvement Loop

The SelfImprovingPromptManager enables continuous learning:

1. **Collect** evaluation scores over time
2. **Analyze** criteria with low scores (< 3.0)
3. **Generate** improvement suggestions using AI
4. **Create** new prompt versions with modifications
5. **Test** versions via A/B experiments
6. **Promote** winning variants

**Learning Loop:**

```
Reviews → Evaluations → Weakness Analysis → Prompt Version → A/B Test → Better Prompts
                                                                    ↓
                                                            Improved Reviews
```

---

## Success Criteria

- [x] All Gemini calls traced with OpenInference
- [x] Phoenix MCP server configured and accessible
- [x] LLM-as-a-Judge evaluations run on each review
- [x] Evaluation scores visible in MR comments
- [x] Self-improvement updates prompts based on feedback
- [x] Phoenix dashboard shows quality trends
- [x] Hackathon submission documentation complete

---

## Demo Scenarios

### Scenario 1: Security Vulnerability Detection

1. Create a PR with SQL injection vulnerability
2. Gatekeeper reviews the code
3. Phoenix traces the review generation
4. LLM-as-a-Judge evaluates security_coverage
5. If score < 4, self-improvement suggests adding emphasis on SQL injection
6. Next review uses improved prompt

### Scenario 2: Review Quality Tracking

1. Gatekeeper processes multiple PRs
2. Each review is evaluated across 6 criteria
3. Phoenix dashboard shows quality trends over time
4. Identify which criteria need improvement
5. Create targeted prompt versions

### Scenario 3: A/B Experiment

1. Create two prompt versions (current vs. improved)
2. Run A/B experiment for 50 reviews
3. Phoenix tracks scores for each version
4. Declare winner based on average score
5. Promote winning version to default

---

## Resources

- **Phoenix Cloud:** https://app.phoenix.arize.com
- **Phoenix Documentation:** https://docs.arize.com/phoenix
- **OpenInference GitHub:** https://github.com/Arize-ai/openinference
- **Phoenix MCP Server:** https://github.com/Arize-ai/phoenix-mcp

---

## Future Enhancements

1. **Dataset Management:** Store reviewed code as datasets for few-shot learning
2. **Custom Evaluators:** Domain-specific evaluators for different languages
3. **Real-time Dashboards:** Custom Phoenix dashboards for monitoring
4. **Feedback Integration:** User feedback correlated with LLM-as-a-Judge scores
5. **Prompt Templates:** Parameterized prompts for different review types

---

## Contact

For questions about this hackathon submission:

- Project: The Gatekeeper
- Track: Arize Phoenix Hackathon
- Challenge: Google Cloud Rapid Agent Hackathon
