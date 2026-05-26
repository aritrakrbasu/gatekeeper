# Migration to Phoenix SDK LLM Evaluations

## Context

The Gatekeeper currently uses a **custom LLM-as-a-Judge implementation** with:

- Direct Gemini API calls with regex-based score extraction
- Manual span attribute setting for Phoenix integration
- Custom PhoenixEvaluationExporter for sending evaluations to Evaluations tab
- Hand-rolled concurrency and error handling

**Problem**: The custom implementation is fragile (regex parsing), lacks built-in rate limiting, and requires significant maintenance.

**Solution**: Migrate to Phoenix SDK's built-in `ClassificationEvaluator` which provides:

- **Function calling** for reliable structured JSON output (no more regex)
- **Built-in rate limiting** and dynamic concurrency (up to 20x speedup)
- **Automatic OpenTelemetry tracing** (no manual span attributes)
- **Native evaluation export** to Phoenix Evaluations tab

## Implementation Approach

### Phase 1: Create Phoenix SDK-Based Evaluator

**File: `ai_observability/phoenix_sdk_evaluator.py`** (NEW)

Create a new evaluator module using Phoenix SDK patterns:

```python
from phoenix.evals import ClassificationEvaluator, LLM, LLMEvaluators
from phoenix.evals import async_evaluate_dataframe, evaluate_dataframe
import pandas as pd
import asyncio
from typing import List, Dict, Any, Optional
from enum import Enum

class PhoenixSDKEvaluator:
    """
    Phoenix SDK-based evaluator with function calling for structured output.

    Key advantages over custom implementation:
    - Function calling for reliable JSON output (no regex parsing)
    - Built-in rate limiting and concurrency (up to 20x faster)
    - Automatic OpenTelemetry tracing
    - Native evaluation export to Phoenix Evaluations tab
    """
    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite",
        concurrency: int = 4,
        max_retries: int = 3
    ):
        self.llm = LLM(provider="google", model=model)
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.evaluators = self._create_evaluators()

    def _create_evaluators(self) -> Dict[str, ClassificationEvaluator]:
        """Create Phoenix evaluators for each criterion with refined prompts."""
        return {
            "security_coverage": ClassificationEvaluator(
                name="security_coverage",
                llm=self.llm,
                prompt_template=self.SECURITY_PROMPT,
                choices={
                    "critical": 5.0,
                    "high": 4.0,
                    "medium": 3.0,
                    "low": 2.0,
                    "poor": 1.0
                },
                include_explanation=True
            ),
            "code_quality_coverage": ClassificationEvaluator(
                name="code_quality_coverage",
                llm=self.llm,
                prompt_template=self.CODE_QUALITY_PROMPT,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0
                },
                include_explanation=True
            ),
            # ... other 7 criteria
        }

    async def evaluate_review_async(
        self,
        diff: str,
        review: str,
        criteria: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a code review using Phoenix SDK with async execution.

        Phoenix SDK handles:
        - Rate limiting and retries automatically
        - Concurrent evaluation of multiple criteria
        - Structured JSON output via function calling
        - Automatic OpenTelemetry tracing
        """
        # Prepare evaluation dataframe
        df = pd.DataFrame([{
            "diff": diff[:10000],
            "review": review[:10000],
        }])

        # Select evaluators for requested criteria
        selected_evaluators = [
            self.evaluators[c] for c in criteria if c in self.evaluators
        ]

        # Run async evaluation with built-in rate limiting
        results = await async_evaluate_dataframe(
            dataframe=df,
            evaluators=selected_evaluators,
            concurrency=self.concurrency,
            max_retries=self.max_retries,
            exit_on_error=False
        )

        # Convert Phoenix SDK results to expected format
        return self._format_results(results, metadata)

    def _format_results(self, results: pd.DataFrame, metadata: Dict) -> Dict:
        """Convert Phoenix SDK results to legacy-compatible format."""
        return {
            "average_score": results["score"].mean(),
            "evaluations": [
                {
                    "criteria": row["name"],
                    "score": row["score"],
                    "explanation": row.get("explanation", "")
                }
                for _, row in results.iterrows()
            ],
            "timestamp": pd.Timestamp.now().isoformat(),
            "metadata": metadata or {}
        }
```

**Evaluation Schema** (Phoenix SDK automatically generates function calling schema):

```python
# Phoenix SDK auto-generates this schema for each evaluator:
{
    "name": "security_coverage",
    "parameters": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low", "poor"]
            },
            "explanation": {
                "type": "string"
            }
        },
        "required": ["label", "explanation"]
    }
}
```

**Key changes from current implementation:**
| Current (Custom) | Phoenix SDK |
|------------------|-------------|
| `client.models.generate_content()` | `ClassificationEvaluator.evaluate()` |
| Regex score extraction | Function calling (automatic JSON) |
| Manual `set_span_attributes()` | Auto-traced by Phoenix |
| Custom `PhoenixEvaluationExporter` | Built-in evaluation logging |

### Phase 2: Refine Prompts for Function Calling

Refine existing prompts to be optimized for Phoenix's function calling approach. Add explicit JSON output instructions and clear scoring rubrics:

**Current prompt format** (evaluators.py:81-222):

```python
EVALUATION_PROMPTS = {
    EvaluationCriteria.SECURITY_COVERAGE: """
You are evaluating a code review for security vulnerability coverage.

Code Diff:
{diff}

Review:
{review}

Evaluate: Did this review adequately identify security vulnerabilities?
...
"""
}
```

**Refined Phoenix SDK format** (optimized for function calling):

```python
SECURITY_PROMPT = """
You are evaluating a code review for security vulnerability coverage.

CODE DIFF:
{diff}

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Critical): Identifies all security vulnerabilities with precise locations
- 4 (High): Catches most security issues, may miss minor ones
- 3 (Medium): Identifies obvious vulnerabilities but misses subtle ones
- 2 (Low): Misses important security issues or has false positives
- 1 (Poor): Fails to identify security vulnerabilities entirely

SECURITY CONCERNS TO EVALUATE:
- SQL injection, XSS, CSRF vulnerabilities
- Hardcoded secrets, API keys, passwords
- Insecure default configurations
- Missing authentication/authorization
- Insecure cryptographic implementations

Return a JSON object with 'score' (1-5), 'label' (critical/high/medium/low/poor), and 'explanation'.
"""
```

### Phase 3: Update Integration Points

**File: `main.py`** (MODIFY)

Change evaluator calls from:

```python
evaluator = get_evaluator()
eval_result = await evaluator.evaluate_review(
    diff=raw_diff_content[:5000],
    review=audit_report[:10000],
    criteria=[...],
    metadata={...}
)
```

To:

```python
evaluator = get_phoenix_sdk_evaluator()
eval_result = await evaluator.evaluate_review_async(
    diff=raw_diff_content[:5000],
    review=audit_report[:10000],
    criteria=[...],
    metadata={...}
)
```

### Phase 4: Remove Manual Tracing Code

**Delete/Deprecate these functions:**

- `set_span_attributes()` calls in evaluators.py (auto-traced by Phoenix)
- `_log_to_phoenix()` method (replaced by SDK's automatic logging)
- `PhoenixEvaluationExporter.flush_async()` (SDK handles exports)

**Keep:**

- `trace_utils.py` for trace ID extraction (still needed for linking)
- `__init__.py` exports

### Phase 5: Update Dependencies

**File: `requirements.txt`** (VERIFY)

Ensure Phoenix SDK is properly configured:

```
phoenix>=6.0.0  # Already present
arize-phoenix>=6.0.0  # Already present
```

## Files to Modify

| File                                        | Action | Description                                               |
| ------------------------------------------- | ------ | --------------------------------------------------------- |
| `ai_observability/phoenix_sdk_evaluator.py` | CREATE | New Phoenix SDK-based evaluator                           |
| `ai_observability/__init__.py`              | MODIFY | Export new evaluator, keep old for backward compatibility |
| `ai_observability/evaluators.py`            | RENAME | Rename to `evaluators_legacy.py` for backup               |
| `main.py`                                   | MODIFY | Update evaluator import and calls                         |
| `requirements.txt`                          | VERIFY | Ensure Phoenix SDK dependencies present                   |

## Verification Steps

1. **Unit Test**: Run evaluator with sample diff and review

   ```python
   evaluator = get_phoenix_sdk_evaluator()
   result = await evaluator.evaluate_review_async(
       diff="+ const API_KEY = '123'",
       review="Found hardcoded secret",
       criteria=[EvaluationCriteria.SECURITY_COVERAGE]
   )
   assert result["evaluations"][0]["score"] >= 4
   ```

2. **Integration Test**: Process a test GitLab webhook
   - Verify evaluation appears in Phoenix dashboard
   - Check Evaluations tab for exported records
   - Confirm span attributes are auto-set

3. **Performance Test**: Compare execution time
   - Old implementation: ~30s for 4 criteria
   - Phoenix SDK: ~5s with concurrency=4

4. **Trace Verification**: Check OpenTelemetry traces
   - Confirm `evaluation.code_review_quality` span exists
   - Verify `eval_security_coverage` attribute is set automatically

## Rollback Plan

If issues arise:

1. Revert `main.py` import to use `evaluators_legacy.py`
2. Comment out new Phoenix SDK evaluator in `__init__.py`
3. Restart service - old implementation resumes

No database migrations or external dependencies required.
