# Arize & Phoenix Observability Setup Guide

This guide explains how to configure and use **Arize AI observability** and **Phoenix** with The Gatekeeper for the Google Cloud Rapid Agent Hackathon.

## Overview

The Gatekeeper includes comprehensive observability for monitoring all AI operations:

- **OpenInference Tracing** - Automatic tracing via OpenInference instrumentation
- **Phoenix Cloud** - Centralized observability dashboard
- **Phoenix MCP** - Self-introspection capabilities (query own traces)
- **LLM-as-a-Judge** - Automatic evaluation of review quality
- **Self-Improvement** - Agent learns from its reviews

## Prerequisites

1. **Arize Account** - Sign up at [https://arize.com/](https://arize.com/)
2. **Phoenix Cloud Account** - Get free access at [https://app.phoenix.arize.com/](https://app.phoenix.arize.com/)
3. **API Keys** - Space ID, API Key (Arize), and Phoenix API Key

## Quick Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:

- `arize>=7.0.0`
- `arize-otel>=1.0.0`
- `opentelemetry-api>=1.22.0`
- `opentelemetry-sdk>=1.22.0`
- `opentelemetry-instrumentation-fastapi>=0.43b0`

### 2. Configure Environment Variables

Add your credentials to `.env`:

```bash
# Arize AI Observability Configuration
ARIZE_SPACE_ID=your_space_id_here
ARIZE_API_KEY=your_api_key_here

# Phoenix Cloud Configuration
PHOENIX_MODE=cloud
PHOENIX_API_KEY=your_phoenix_api_key_here
PHOENIX_BASE_URL=https://app.phoenix.arize.com

# Feature Flags
ENABLE_EVALUATIONS=true
ENABLE_SELF_IMPROVEMENT=true
JUDGE_MODEL=gemini-3.1-flash-lite
```

**Getting Your Keys:**

- **Arize:** Log in to [https://app.arize.com/](https://app.arize.com/) → Settings → Space API Keys
- **Phoenix:** Log in to [https://app.phoenix.arize.com/](https://app.phoenix.arize.com/) → Settings → API Keys

Both offer free tiers for hackathon participants!

### 3. Verify Configuration

Start the application:

```bash
python main.py
```

You should see one of these messages:

- `[✅] Arize observability initialized successfully` - Working with Arize
- `[i] Arize not configured - running in local-only mode` - Running without Arize (console logging only)

## How It Works

### Observable AI Client

The `ObservableGeminiClient` wraps all Gemini AI calls with automatic logging:

```python
# Old way (no observability)
response = await asyncio.to_thread(
    ai_client.models.generate_content,
    model='gemini-3.1-flash-lite',
    contents=prompt,
    config=types.GenerateContentConfig(...)
)

# New way (with Arize observability)
response = await ai_client.generate_content(
    prompt=prompt,
    system_instruction=system_instruction,
    temperature=0.1,
    operation_name="code_review",  # Tracked in Arize
    metadata={
        "mr_id": mr_iid,
        "project_id": project_id,
    }
)
```

### Tracked Operations

The following operations are automatically tracked:

| Operation             | Description                     | Metadata                   |
| --------------------- | ------------------------------- | -------------------------- |
| `code_review`         | Main security review of MR diff | MR ID, project, file count |
| `auto_fix_generation` | Auto-fix generation for issues  | MR ID, finding count       |

### Metrics Collected

- **Latency**: Time for each AI operation
- **Tokens**: Estimated prompt and completion tokens
- **Success/Error Rate**: Track failures
- **Business Metrics**: MR review time, fix success rate

## Viewing Data in Arize

### 1. Access the Dashboard

Go to [https://app.arize.com/](https://app.arize.com/) and log in.

### 2. View Your Model

Your model will appear as:

- `gatekeeper-gemini-reviewer` (main model)
- `gatekeeper-code_review` (code review operations)
- `gatekeeper-auto_fix_generation` (auto-fix operations)

### 3. Explore Traces

Navigate to **Traces** to see:

- Individual AI generations
- Request/response data
- Timing breakdowns
- Error details

### 4. View Metrics

Navigate to **Metrics** to see:

- AI generation latency (p50, p95, p99)
- Token usage over time
- Error rates
- Throughput

## Local Development

### Running Without Arize

If you don't have Arize credentials, the application still works:

```bash
# Just don't set ARIZE_SPACE_KEY and ARIZE_API_KEY
# The app will run in "local-only mode" with console logging
```

### Using Arize Phoenix (Local)

For local development, you can use Arize Phoenix:

```bash
# Install Phoenix
pip install arize-phoenix

# Start Phoenix server
python -m phoenix.server.main serve

# Update .env to use local Phoenix
ARIZE_ENDPOINT=http://localhost:6006
```

## Troubleshooting

### "Arize not configured" Message

**Cause**: Missing or invalid credentials

**Solution**: Check that `.env` contains valid `ARIZE_SPACE_KEY` and `ARIZE_API_KEY`

### No traces appearing in Arize

**Cause**: Multiple possible issues

**Solutions**:

1. Verify credentials are correct
2. Check network connectivity to `https://api.arize.com`
3. Check application logs for Arize errors
4. Verify model ID matches in Arize dashboard

### Import errors

**Cause**: Missing dependencies

**Solution**: Run `pip install -r requirements.txt`

## Advanced Configuration

### Custom Model ID

To change the model ID tracked in Arize, edit `main.py`:

```python
arize_initialized = init_arize(
    model_id="your-custom-model-id",  # Change this
    enable_otel=True,
)
```

### Disabling OpenTelemetry

To disable distributed tracing:

```python
arize_initialized = init_arize(
    model_id="gatekeeper-gemini-reviewer",
    enable_otel=False,  # Disable OTEL
)
```

### Adding Custom Metrics

See `ai_observability/metrics.py` for the metrics module. To add custom metrics:

```python
from ai_observability import get_metrics

metrics = get_metrics()
metrics.record_custom_metric(
    name="my_custom_metric",
    value=42,
    labels={"label1": "value1"},
)
```

## Security Considerations

- **Never commit** `.env` with real Arize credentials
- Use `.env.example` as a template for others
- Rotate API keys regularly via Arize dashboard
- Use separate spaces for dev/staging/production

## Resources

- [Arize Documentation](https://docs.arize.com/)
- [Arize Python SDK](https://github.com/Arize-ai/arize)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

## Support

For issues with Arize integration:

1. Check the application logs for error messages
2. Verify credentials in Arize dashboard
3. Check [Arize status page](https://status.arize.com/)

---

## Phoenix MCP Integration

The Gatekeeper includes **Phoenix MCP** for self-introspection, allowing the agent to query its own traces, evaluations, and experiments at runtime.

### Phoenix MCP Features

The Phoenix MCP bridge (`config/phoenix_mcp.py`) provides:

- `get_recent_traces()` - Retrieve recent review traces
- `get_trace_details()` - Get detailed trace information
- `get_evaluations()` - Fetch LLM-as-a-Judge results
- `get_evaluation_summary()` - Aggregate evaluation metrics
- `get_experiments()` - Access A/B experiment results
- `get_performance_metrics()` - Latency and success rate stats

### Using Phoenix MCP

```python
from config.phoenix_mcp import get_phoenix_bridge

# Get the bridge
bridge = await get_phoenix_bridge()

# Get recent traces
traces = await bridge.get_recent_traces(limit=10, hours_ago=24)

# Get evaluation summary
summary = await bridge.get_evaluation_summary(hours_ago=24)
print(f"Average quality score: {summary['average_score']}/5")

# Query by metadata
mr_traces = await bridge.query_traces_by_metadata(
    {"mr_id": "123", "project_id": "myproject"}
)
```

### Health Check

The `/health` endpoint includes Phoenix connection status:

```bash
curl http://localhost:8000/health
```

Response includes:

```json
{
  "phoenix_connected": true,
  "evaluations_enabled": true,
  "self_improvement_enabled": true
}
```

---

## LLM-as-a-Judge Evaluations

Every code review is automatically evaluated for quality across multiple criteria.

### Evaluation Criteria

| Criteria                | Description                         | Weight |
| ----------------------- | ----------------------------------- | ------ |
| `security_coverage`     | Security vulnerabilities identified | ★★★    |
| `code_quality_coverage` | Code quality issues identified      | ★★★    |
| `actionability`         | Fixes are actionable                | ★★     |
| `clarity`               | Explanation is clear                | ★★     |
| `completeness`          | All issues covered                  | ★      |
| `correctness`           | No false positives                  | ★★     |

### Running Evaluations

```python
from ai_observability import get_evaluator, EvaluationCriteria

evaluator = get_evaluator()

result = await evaluator.evaluate_review(
    diff=code_diff,
    review=ai_review,
    criteria=[
        EvaluationCriteria.SECURITY_COVERAGE,
        EvaluationCriteria.CLARITY,
    ],
)

print(f"Average score: {result['average_score']}/5")
```

### Viewing Evaluation Results

1. **Phoenix Dashboard:** Navigate to [https://app.phoenix.arize.com/](https://app.phoenix.arize.com/)
2. **Evaluations Tab:** View all evaluation results
3. **Filter by:** Criteria, score range, time period

---

## Self-Improvement Loop

The Gatekeeper learns from its evaluations and improves prompts over time.

### Features

- **Prompt Versioning:** Track all prompt versions
- **Weakness Analysis:** Identify patterns in low scores
- **A/B Experiments:** Test prompt variations
- **Automated Improvement:** AI-suggested modifications

### Using the Self-Improvement System

```python
from ai_observability import get_prompt_manager

manager = get_prompt_manager()

# Analyze weaknesses
weaknesses = manager.analyze_weaknesses(recent_evaluations)

# Create improved version
new_version = manager.create_version(
    base_prompt_name="senior_pr_reviewer",
    modifications="Focus more on SQL injection detection",
)

# Create A/B experiment
experiment = manager.create_experiment(
    name="SQL Injection Focus Test",
    versions=["senior_pr_reviewer", new_version.version_id],
)

# Record results
manager.record_evaluation(
    version_id=new_version.version_id,
    score=4.2,
    experiment_id=experiment.experiment_id,
)

# Get winner
winner = experiment.get_winner()
print(f"Winning version: {winner}")
```

### Storage

- **Prompt Versions:** `prompts/versions/*.json`
- **Experiments:** `config/experiments.json`
- **Analysis:** Tracked in Phoenix datasets

---

## Hackathon Features

For the Google Cloud Rapid Agent Hackathon, The Gatekeeper implements:

✅ **OpenInference Auto-Instrumentation** - All Gemini calls traced
✅ **Phoenix MCP Server** - Self-introspection capabilities
✅ **LLM-as-a-Judge Evaluations** - Automatic quality assessment
✅ **Self-Improvement Loop** - Agent learns from feedback
✅ **Comprehensive Documentation** - See `HACKATHON_SUBMISSION.md`

See `HACKATHON_SUBMISSION.md` for complete hackathon documentation.
