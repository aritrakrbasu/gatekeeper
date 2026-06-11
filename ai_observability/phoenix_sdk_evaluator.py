"""
Phoenix SDK-based LLM-as-a-Judge Evaluator.

This module replaces the custom Gemini-based evaluator with Phoenix SDK's
ClassificationEvaluator, providing:
- Function calling for reliable structured JSON output (no more regex)
- Built-in rate limiting and dynamic concurrency (up to 20x faster)
- Automatic OpenTelemetry tracing
- Native evaluation export to Phoenix Evaluations tab
"""

import os
import logging
import asyncio
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from arize.prompts.types import LlmProvider
import pandas as pd

try:
    from phoenix.evals import ClassificationEvaluator, LLM
    from phoenix.evals import async_evaluate_dataframe, evaluate_dataframe
    PHOENIX_AVAILABLE = True
except ImportError:
    PHOENIX_AVAILABLE = False
    logging.warning("[⚠️] Phoenix SDK not available - falling back to legacy evaluator")

logger = logging.getLogger(__name__)


class EvaluationCriteria(Enum):
    """Evaluation criteria for code review and auto-fix quality."""

    # Code Review Criteria
    SECURITY_COVERAGE = "security_coverage"
    """Did the review catch security vulnerabilities?"""

    CODE_QUALITY_COVERAGE = "code_quality_coverage"
    """Did the review identify code quality issues?"""

    ACTIONABILITY = "actionability"
    """Are the suggested fixes actionable and specific?"""

    CLARITY = "clarity"
    """Is the review explanation clear and well-structured?"""

    COMPLETENESS = "completeness"
    """Did the review cover all relevant issues?"""

    CORRECTNESS = "correctness"
    """Are the findings accurate and not false positives?"""

    # Auto-Fix Criteria
    FIX_CORRECTNESS = "fix_correctness"
    """Do the auto-fixes correctly solve the identified issues?"""

    FIX_SAFETY = "fix_safety"
    """Are the auto-fixes safe and don't introduce new bugs?"""

    FIX_COMPLETENESS = "fix_completeness"
    """Do the auto-fixes cover all identified issues?"""


class PhoenixSDKEvaluator:
    """
    Phoenix SDK-based evaluator with function calling for structured output.

    This evaluator uses Phoenix SDK's ClassificationEvaluator which provides:
    - Function calling (tool use) for reliable JSON output
    - Built-in rate limiting and retries
    - Dynamic concurrency for performance optimization
    - Automatic OpenTelemetry tracing
    - Native export to Phoenix Evaluations tab

    Example:
        evaluator = PhoenixSDKEvaluator(model="gemini-3-flash-preview")
        result = await evaluator.evaluate_review_async(
            diff="+ const API_KEY = '123'",
            review="Found hardcoded secret",
            criteria=[EvaluationCriteria.SECURITY_COVERAGE]
        )
        print(result["average_score"])  # 5.0
    """

    # Refined prompts optimized for function calling with explicit scoring rubrics
    SECURITY_COVERAGE_PROMPT = """
You are evaluating a code review for security vulnerability coverage.

CODE DIFF:
{diff}

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Critical): Identifies all security vulnerabilities with precise locations and severity
- 4 (High): Catches most security issues, may miss some edge cases or minor issues
- 3 (Medium): Identifies obvious vulnerabilities but misses subtle or complex ones
- 2 (Low): Misses important security issues, has significant false positives, or provides vague findings
- 1 (Poor): Fails to identify security vulnerabilities entirely or provides irrelevant feedback

SECURITY CONCERNS TO EVALUATE:
- SQL injection, XSS, CSRF, SSRF vulnerabilities
- Hardcoded secrets, API keys, passwords, tokens
- Insecure default configurations or settings
- Missing authentication/authorization checks
- Insecure cryptographic implementations or random number generation
- Path traversal, command injection, deserialization flaws
- Information disclosure, security misconfigurations

Analyze the review against the code diff and rate according to the rubric above.
"""

    CODE_QUALITY_COVERAGE_PROMPT = """
You are evaluating a code review for code quality issue coverage.

CODE DIFF:
{diff}

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Excellent): Identifies all quality issues with specific, actionable feedback
- 4 (Good): Catches most quality problems, provides useful suggestions
- 3 (Adequate): Identifies obvious quality issues but lacks depth or specificity
- 2 (Fair): Misses important quality problems or provides generic feedback
- 1 (Poor): Fails to identify code quality issues or provides irrelevant comments

CODE QUALITY ASPECTS TO EVALUATE:
- Code smells (long functions, duplicate code, complex logic)
- Anti-patterns and design violations
- Maintainability concerns (naming, structure, modularity)
- Performance issues (inefficient algorithms, resource leaks)
- Error handling and edge cases
- Type safety, null checks, validation
- Code organization and readability
- Test coverage and test quality

Analyze the review against the code diff and rate according to the rubric above.
"""

    ACTIONABILITY_PROMPT = """
You are evaluating the actionability of a code review.

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Excellent): Provides specific, step-by-step fixes with code examples
- 4 (Good): Clear, actionable recommendations with sufficient detail
- 3 (Adequate): General guidance that requires some interpretation
- 2 (Fair): Vague suggestions lacking specific steps or examples
- 1 (Poor): Abstract feedback with no clear path to implementation

ACTIONABILITY FACTORS:
- Are specific files, functions, and line numbers mentioned?
- Are code examples or before/after comparisons provided?
- Is the fix clearly explained with implementation steps?
- Are priorities or severity levels assigned to issues?
- Can a developer implement the fixes without clarification?
- Are dependencies or prerequisites mentioned if needed?

Analyze the review and rate how actionable the recommendations are.
"""

    CLARITY_PROMPT = """
You are evaluating the clarity of a code review.

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Excellent): Crystal clear, well-structured, precise language
- 4 (Good): Clear and easy to understand with minor improvements possible
- 3 (Adequate): Understandable but requires effort to parse
- 2 (Fair): Confusing structure, ambiguous language, or poor organization
- 1 (Poor): Difficult to understand, contradictory, or incoherent

CLARITY FACTORS:
- Is the language precise and unambiguous?
- Is the structure logical and easy to follow?
- Are technical terms used correctly?
- Is the formatting and organization clear?
- Are explanations concise yet complete?
- Is the tone appropriate and professional?

Analyze the review and rate its clarity and communication quality.
"""

    COMPLETENESS_PROMPT = """
You are evaluating the completeness of a code review.

CODE DIFF:
{diff}

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Excellent): Comprehensive coverage of all relevant issues
- 4 (Good): Covers most important aspects with only minor omissions
- 3 (Adequate): Addresses key areas but misses some significant issues
- 2 (Fair): Limited scope, overlooks important categories of problems
- 1 (Poor): Misses critical issues or focuses on trivial concerns

COMPLETENESS ASPECTS:
- Security vulnerabilities
- Functional correctness and bugs
- Code quality and maintainability
- Performance implications
- Error handling and edge cases
- Testing considerations
- Documentation needs
- Breaking changes or migration concerns

Compare the review against the code diff and rate the completeness of coverage.
"""

    CORRECTNESS_PROMPT = """
You are evaluating the correctness of a code review.

CODE DIFF:
{diff}

CODE REVIEW:
{review}

SCORING RUBRIC:
- 5 (Excellent): All findings are accurate, no false positives
- 4 (Good): Mostly accurate with minimal false positives
- 3 (Adequate): Generally correct but some questionable findings
- 2 (Fair): Significant false positives or missed actual issues
- 1 (Poor): Findings are incorrect or based on misunderstandings

CORRECTNESS FACTORS:
- Are identified issues actually present in the code?
- Are the severity assessments appropriate?
- Are the suggested fixes technically sound?
- Are there false alarms or misidentified problems?
- Does the reviewer demonstrate understanding of the code?
- Are edge cases and scenarios considered accurately?

Verify the review findings against the actual code diff and rate accuracy.
"""

    # Auto-fix evaluation prompts
    FIX_CORRECTNESS_PROMPT = """
You are evaluating auto-generated code fixes for correctness.

ORIGINAL ISSUES:
{review}

GENERATED FIXES:
{fixes}

SCORING RUBRIC:
- 5 (Excellent): Fixes correctly address all root causes with precise solutions
- 4 (Good): Fixes solve most issues with minor adjustments needed
- 3 (Adequate): Partial fixes that address symptoms but not root causes
- 2 (Fair): Fixes are incomplete or introduce new issues
- 1 (Poor): Fixes are incorrect or make problems worse

CORRECTNESS FACTORS:
- Do the fixes address the actual root cause?
- Are the solutions technically sound?
- Do they follow best practices for the language/framework?
- Are edge cases considered?
- Is the logic correct and complete?
- Would these fixes resolve the identified issues?

Evaluate whether the generated fixes correctly solve the original issues.
"""

    FIX_SAFETY_PROMPT = """
You are evaluating auto-generated code fixes for safety.

ORIGINAL ISSUES:
{review}

GENERATED FIXES:
{fixes}

SCORING RUBRIC:
- 5 (Excellent): Completely safe, preserves all functionality
- 4 (Good): Safe with minor isolated risks
- 3 (Adequate): Generally safe with some areas needing review
- 2 (Fair): Introduces potential issues or breaking changes
- 1 (Poor): Dangerous changes that break functionality

SAFETY FACTORS:
- Do fixes maintain existing functionality?
- Are there side effects or unintended consequences?
- Is error handling preserved?
- Are type signatures and contracts maintained?
- Could these fixes introduce new bugs?
- Are backward compatibility concerns addressed?
- Is thread safety or concurrency considered if relevant?

Evaluate whether the fixes are safe to apply without introducing problems.
"""

    FIX_COMPLETENESS_PROMPT = """
You are evaluating auto-generated code fixes for completeness.

ORIGINAL ISSUES:
{review}

GENERATED FIXES:
{fixes}

SCORING RUBRIC:
- 5 (Excellent): All issues are addressed with comprehensive fixes
- 4 (Good): Most issues fixed with only minor gaps
- 3 (Adequate): Core issues addressed but incomplete coverage
- 2 (Fair): Significant issues left unfixed
- 1 (Poor): Critical issues missed or ignored

COMPLETENESS FACTORS:
- Are all security vulnerabilities addressed?
- Are all code quality issues fixed?
- Are all functional bugs corrected?
- Are minor issues also addressed?
- Are follow-up requirements mentioned if incomplete?
- Is the scope of fixes appropriate for the original review?

Evaluate whether the fixes comprehensively address all identified issues.
"""

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        concurrency: int = 4,
        max_retries: int = 3,
    ):
        """
        Initialize the Phoenix SDK evaluator.

        Args:
            model: The Gemini model to use as judge (default: gemini-3-flash-preview)
            concurrency: Maximum concurrent evaluation requests (default: 4)
            max_retries: Maximum retries for failed evaluations (default: 3)
        """
        if not PHOENIX_AVAILABLE:
            raise ImportError(
                "Phoenix SDK is not installed. "
                "Install with: pip install arize-phoenix>=6.0.0"
            )

        self.model = model
        self.concurrency = concurrency
        self.max_retries = max_retries

        # Initialize LLM wrapper for Gemini
        self.llm = LLM(provider=LlmProvider.VERTEX_AI, model=model)

        # Create evaluators for all criteria (will be loaded asynchronously on first use)
        self.evaluators = None  # Lazy-loaded

        logger.info(
            f"[✅] Phoenix SDK Evaluator initialized: model={model}, "
            f"concurrency={concurrency}, max_retries={max_retries}"
        )

    async def _get_evaluator_prompt(self, criterion: EvaluationCriteria, fallback_prompt: str) -> str:
        """
        Get evaluation prompt from Arize AX with fallback to class constant.

        Args:
            criterion: The evaluation criterion
            fallback_prompt: The fallback prompt from class constant

        Returns:
            Evaluation prompt template
        """
        # Mapping of criteria to prompt IDs
        prompt_id_mapping = {
            EvaluationCriteria.SECURITY_COVERAGE: "eval_security",
            EvaluationCriteria.CODE_QUALITY_COVERAGE: "eval_quality",
            EvaluationCriteria.ACTIONABILITY: "eval_actionability",
            EvaluationCriteria.CLARITY: "eval_clarity",
            EvaluationCriteria.COMPLETENESS: "eval_completeness",
            EvaluationCriteria.CORRECTNESS: "eval_correctness",
        }

        prompt_id = prompt_id_mapping.get(criterion)

        if prompt_id:
            try:
                from config.prompts import load_prompt
                return await load_prompt(prompt_id, label="production")
            except Exception as e:
                logger.debug(f"[DEBUG] Failed to load {prompt_id} from Arize AX: {e}, using fallback")

        return fallback_prompt

    async def _create_evaluators(self) -> Dict[str, ClassificationEvaluator]:
        """Create Phoenix ClassificationEvaluators for each criterion."""
        # Load prompts from Arize AX (with fallbacks)
        security_prompt = await self._get_evaluator_prompt(EvaluationCriteria.SECURITY_COVERAGE, self.SECURITY_COVERAGE_PROMPT)
        quality_prompt = await self._get_evaluator_prompt(EvaluationCriteria.CODE_QUALITY_COVERAGE, self.CODE_QUALITY_COVERAGE_PROMPT)
        actionability_prompt = await self._get_evaluator_prompt(EvaluationCriteria.ACTIONABILITY, self.ACTIONABILITY_PROMPT)
        clarity_prompt = await self._get_evaluator_prompt(EvaluationCriteria.CLARITY, self.CLARITY_PROMPT)
        completeness_prompt = await self._get_evaluator_prompt(EvaluationCriteria.COMPLETENESS, self.COMPLETENESS_PROMPT)
        correctness_prompt = await self._get_evaluator_prompt(EvaluationCriteria.CORRECTNESS, self.CORRECTNESS_PROMPT)

        return {
            # Code Review Evaluators
            EvaluationCriteria.SECURITY_COVERAGE.value: ClassificationEvaluator(
                name="security_coverage",
                llm=self.llm,
                prompt_template=security_prompt,
                choices={
                    "critical": 5.0,
                    "high": 4.0,
                    "medium": 3.0,
                    "low": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.CODE_QUALITY_COVERAGE.value: ClassificationEvaluator(
                name="code_quality_coverage",
                llm=self.llm,
                prompt_template=quality_prompt,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.ACTIONABILITY.value: ClassificationEvaluator(
                name="actionability",
                llm=self.llm,
                prompt_template=actionability_prompt,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.CLARITY.value: ClassificationEvaluator(
                name="clarity",
                llm=self.llm,
                prompt_template=clarity_prompt,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.COMPLETENESS.value: ClassificationEvaluator(
                name="completeness",
                llm=self.llm,
                prompt_template=completeness_prompt,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.CORRECTNESS.value: ClassificationEvaluator(
                name="correctness",
                llm=self.llm,
                prompt_template=correctness_prompt,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            # Auto-Fix Evaluators (using class constants as fallbacks)
            EvaluationCriteria.FIX_CORRECTNESS.value: ClassificationEvaluator(
                name="fix_correctness",
                llm=self.llm,
                prompt_template=self.FIX_CORRECTNESS_PROMPT,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.FIX_SAFETY.value: ClassificationEvaluator(
                name="fix_safety",
                llm=self.llm,
                prompt_template=self.FIX_SAFETY_PROMPT,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
            EvaluationCriteria.FIX_COMPLETENESS.value: ClassificationEvaluator(
                name="fix_completeness",
                llm=self.llm,
                prompt_template=self.FIX_COMPLETENESS_PROMPT,
                choices={
                    "excellent": 5.0,
                    "good": 4.0,
                    "adequate": 3.0,
                    "fair": 2.0,
                    "poor": 1.0,
                },
                include_explanation=True,
            ),
        }

    async def _get_evaluators(self) -> Dict[str, ClassificationEvaluator]:
        """Get evaluators, initializing them on first use."""
        if self.evaluators is None:
            self.evaluators = await self._create_evaluators()
        return self.evaluators

    async def evaluate_review_async(
        self,
        diff: str,
        review: str,
        criteria: Optional[List[EvaluationCriteria]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a code review using Phoenix SDK with async execution.

        Phoenix SDK automatically handles:
        - Rate limiting and retries
        - Concurrent evaluation of multiple criteria
        - Structured JSON output via function calling
        - OpenTelemetry tracing
        - Export to Phoenix Evaluations tab

        Args:
            diff: The code diff that was reviewed (limited to 10000 chars)
            review: The code review text (limited to 10000 chars)
            criteria: List of criteria to evaluate (defaults to all code review criteria)
            metadata: Optional metadata to attach to the evaluation

        Returns:
            Dictionary with evaluation results including:
            - average_score: Mean score across all criteria
            - evaluations: List of individual criterion results
            - timestamp: ISO format timestamp
            - metadata: Provided metadata
        """
        if criteria is None:
            # Default to code review criteria
            criteria = [
                EvaluationCriteria.SECURITY_COVERAGE,
                EvaluationCriteria.CODE_QUALITY_COVERAGE,
                EvaluationCriteria.ACTIONABILITY,
                EvaluationCriteria.CLARITY,
            ]

        # Prepare evaluation dataframe
        df = pd.DataFrame([{
            "diff": diff[:10000],
            "review": review[:10000],
        }])

        # Select evaluators for requested criteria
        evaluators = await self._get_evaluators()
        selected_evaluators = [
            evaluators[c.value]
            for c in criteria
            if c.value in evaluators
        ]

        if not selected_evaluators:
            logger.warning("[⚠️] No valid evaluators found for criteria: {criteria}")
            return self._empty_result(metadata)

        logger.info(
            f"[*] Starting Phoenix SDK evaluation: {len(selected_evaluators)} criteria, "
            f"concurrency={self.concurrency}"
        )

        try:
            # Debug: Log input data
            logger.debug(f"[DEBUG] Input DataFrame shape: {df.shape}")
            logger.debug(f"[DEBUG] Input DataFrame columns: {list(df.columns)}")

            # Debug: Log selected evaluators
            for eval in selected_evaluators:
                logger.debug(f"[DEBUG] Selected evaluator: {eval.name if hasattr(eval, 'name') else type(eval).__name__}")

            # Run async evaluation with built-in rate limiting
            logger.info("[*] Calling Phoenix SDK async_evaluate_dataframe...")
            results = await async_evaluate_dataframe(
                dataframe=df,
                evaluators=selected_evaluators,
                concurrency=self.concurrency,
                max_retries=self.max_retries,
                exit_on_error=False,
            )

            logger.info(f"[✅] Phoenix SDK returned results: type={type(results)}, shape={results.shape if hasattr(results, 'shape') else 'N/A'}")

            # Convert Phoenix SDK results to legacy-compatible format
            return self._format_results(results, metadata)

        except Exception as e:
            logger.error(f"[x] Phoenix SDK evaluation failed: {e}")
            import traceback
            logger.error(f"[x] Traceback: {traceback.format_exc()}")
            # Return empty result on error
            return self._empty_result(metadata, error=str(e))

    async def evaluate_auto_fix_async(
        self,
        fixes: str,
        review: str,
        criteria: Optional[List[EvaluationCriteria]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate auto-generated fixes using Phoenix SDK.

        Args:
            fixes: The generated fixes (JSON or text description)
            review: The original review/audit report
            criteria: List of criteria to evaluate (defaults to auto-fix criteria)
            metadata: Optional metadata to attach to the evaluation

        Returns:
            Dictionary with evaluation results
        """
        if criteria is None:
            # Default to auto-fix criteria
            criteria = [
                EvaluationCriteria.FIX_CORRECTNESS,
                EvaluationCriteria.FIX_SAFETY,
                EvaluationCriteria.FIX_COMPLETENESS,
            ]

        # Prepare evaluation dataframe
        df = pd.DataFrame([{
            "fixes": fixes[:10000],
            "review": review[:10000],
        }])

        # Select evaluators for requested criteria
        evaluators = await self._get_evaluators()
        selected_evaluators = [
            evaluators[c.value]
            for c in criteria
            if c.value in evaluators
        ]

        if not selected_evaluators:
            logger.warning(f"[⚠️] No valid evaluators found for criteria: {criteria}")
            return self._empty_result(metadata)

        logger.info(
            f"[*] Starting Phoenix SDK auto-fix evaluation: "
            f"{len(selected_evaluators)} criteria"
        )

        try:
            # Run async evaluation
            results = await async_evaluate_dataframe(
                dataframe=df,
                evaluators=selected_evaluators,
                concurrency=self.concurrency,
                max_retries=self.max_retries,
                exit_on_error=False,
            )

            return self._format_results(results, metadata)

        except Exception as e:
            logger.error(f"[x] Phoenix SDK auto-fix evaluation failed: {e}")
            return self._empty_result(metadata, error=str(e))

    def _format_results(
        self,
        results: pd.DataFrame,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Convert Phoenix SDK results to legacy-compatible format and export to Phoenix.

        Phoenix SDK returns results with columns like:
        - {evaluator_name}_score: Dict with 'score', 'label', 'explanation', 'metadata', etc.
        - {evaluator_name}_execution_details: Dict with 'status', 'exceptions', etc.

        Args:
            results: DataFrame from Phoenix SDK evaluation
            metadata: Optional metadata to include

        Returns:
            Formatted results dictionary compatible with legacy code
        """
        evaluations = []

        # Debug: Log the DataFrame structure
        logger.debug(f"[DEBUG] Phoenix SDK results DataFrame shape: {results.shape}")
        logger.debug(f"[DEBUG] Phoenix SDK results columns: {list(results.columns)}")

        # Find all evaluator score columns (they end with _score)
        score_columns = [col for col in results.columns if col.endswith("_score")]
        logger.debug(f"[DEBUG] Found score columns: {score_columns}")

        for idx, row in results.iterrows():
            # Process each evaluator score column
            for col in score_columns:
                # Extract evaluator name from column name (remove "_score" suffix)
                criteria_name = col[:-6]  # Remove "_score" suffix

                # Get the evaluation dict from the column
                eval_dict = row[col]

                # Phoenix SDK returns the evaluation as a dictionary
                if isinstance(eval_dict, dict):
                    score = float(eval_dict.get("score", 0))
                    label = eval_dict.get("label", "")
                    explanation = eval_dict.get("explanation", "")
                    kind = eval_dict.get("kind", "llm")
                    direction = eval_dict.get("direction", "maximize")
                else:
                    # Fallback: try to convert directly
                    logger.warning(f"[⚠️] Unexpected eval_dict type for {criteria_name}: {type(eval_dict)}")
                    score = 0.0
                    label = ""
                    explanation = ""

                evaluations.append({
                    "criteria": criteria_name,
                    "score": score,
                    "label": label,
                    "explanation": explanation,
                    "kind": kind,
                    "direction": direction,
                })

                logger.debug(f"[DEBUG] {criteria_name}: score={score}, label={label}")

        # Calculate average score
        scores = [e["score"] for e in evaluations if e["score"] > 0]
        average_score = sum(scores) / len(scores) if scores else 0.0

        result = {
            "average_score": round(average_score, 2),
            "total_score": sum(scores),
            "criteria_evaluated": len(evaluations),
            "evaluations": evaluations,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        logger.info(
            f"[✅] Phoenix SDK evaluation complete: "
            f"avg_score={average_score:.2f}, criteria={len(evaluations)}"
        )

        # Export evaluations to Phoenix Cloud or self-hosted Phoenix
        if evaluations:
            self._export_evaluations_to_phoenix(evaluations)

        return result

    def _export_evaluations_to_phoenix(self, evaluations: List[Dict[str, Any]]) -> bool:
        """
        Export evaluation records to Phoenix (Cloud or self-hosted).

        Args:
            evaluations: List of evaluation dictionaries

        Returns:
            True if export was successful, False otherwise
        """
        try:
            # Check which Phoenix mode we're using
            phoenix_mode = os.getenv("PHOENIX_MODE", "cloud")

            if phoenix_mode == "cloud":
                # For Phoenix Cloud, use Arize Cloud exporter
                return self._export_to_phoenix_cloud(evaluations)
            else:
                # For self-hosted Phoenix, try log_evaluations
                return self._export_to_phoenix_self_hosted(evaluations)

        except Exception as e:
            logger.warning(f"[⚠️] Failed to export evaluations: {e}")
            import traceback
            logger.debug(f"[DEBUG] Export error: {traceback.format_exc()[:500]}")
            return False

    def _export_to_phoenix_cloud(self, evaluations: List[Dict[str, Any]]) -> bool:
        """Export evaluations to Arize Phoenix Cloud via span attributes."""
        try:
            from opentelemetry import trace

            # Get current span for setting attributes
            current_span = trace.get_current_span()

            if not current_span or not current_span.is_recording():
                logger.warning("[⚠️] No active span - cannot set evaluation attributes")
                return False

            # Set evaluation attributes directly on the current span
            # Phoenix Cloud displays these in the Span Details
            for eval_data in evaluations:
                criteria = eval_data["criteria"]
                score = eval_data["score"]
                label = eval_data.get("label", "")

                # Set span attributes for Phoenix Cloud
                current_span.set_attributes({
                    f"{criteria}_score": score,
                    f"{criteria}_label": label,
                })

                logger.info(f"[✅] Set span attribute: {criteria}_score={score}, {criteria}_label={label}")

            return True

        except Exception as e:
            logger.warning(f"[⚠️] Failed to set evaluation attributes: {e}")
            return False

    def _export_to_phoenix_self_hosted(self, evaluations: List[Dict[str, Any]]) -> bool:
        """Export evaluations to self-hosted Phoenix instance."""
        try:
            from phoenix.trace.evaluations import log_evaluations
            from opentelemetry import trace

            # Get current span ID for linking
            current_span = trace.get_current_span()
            span_id = None
            if current_span and current_span.is_recording():
                from opentelemetry.trace import format_span_id
                span_context = current_span.get_span_context()
                if span_context.is_valid:
                    span_id = format_span_id(span_context.span_id)

            if not span_id:
                logger.debug("[DEBUG] No active span found - using span_id from evaluation context")
                span_id = "unknown"

            # Group evaluations by name for export
            eval_groups: Dict[str, List[Dict]] = {}
            for eval_data in evaluations:
                criteria_name = eval_data["criteria"]
                if criteria_name not in eval_groups:
                    eval_groups[criteria_name] = []
                eval_groups[criteria_name].append(eval_data)

            # Export each evaluation type
            exported_count = 0
            for eval_name, evals in eval_groups.items():
                try:
                    # Create DataFrame for Phoenix
                    rows = []
                    for eval_data in evals:
                        row = {
                            "span_id": span_id,
                            "score": eval_data["score"],
                        }
                        if eval_data.get("label"):
                            row["label"] = eval_data["label"]
                        if eval_data.get("explanation"):
                            row["explanation"] = eval_data["explanation"][:1000]

                        rows.append(row)

                    df = pd.DataFrame(rows)

                    if not df.empty:
                        # Log to Phoenix - this creates evaluation records in the Evaluations tab
                        log_evaluations(
                            dataframe=df,
                            eval_name=eval_name,
                        )
                        exported_count += len(df)
                        logger.info(f"[✅] Exported {len(df)} '{eval_name}' evaluations to Phoenix Evaluations tab")

                except Exception as e:
                    logger.error(f"[x] Failed to export evaluation '{eval_name}': {e}")

            if exported_count > 0:
                logger.info(f"[✅] Total evaluations exported to Phoenix Evaluations tab: {exported_count}")
                return True

        except ImportError:
            logger.warning("[⚠️] Phoenix evaluation export not available - evaluations logged as span attributes only")
        except Exception as e:
            logger.warning(f"[⚠️] Failed to export evaluations to Phoenix: {e}")
            import traceback
            logger.debug(f"[DEBUG] Export error: {traceback.format_exc()[:500]}")

        return False

    def _empty_result(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return an empty result when evaluation fails."""
        return {
            "average_score": 0.0,
            "total_score": 0.0,
            "criteria_evaluated": 0,
            "evaluations": [],
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "error": error,
        }

    def format_evaluation_markdown(self, evaluation_result: Dict[str, Any]) -> str:
        """
        Format evaluation results as Markdown.

        Args:
            evaluation_result: The evaluation result dictionary

        Returns:
            Formatted Markdown string
        """
        lines = [
            "### 📊 Code Review Quality Evaluation (Phoenix SDK)",
            "",
            f"**Overall Score:** {evaluation_result['average_score']}/5 ⭐",
            "",
            "#### Criteria Breakdown:",
            "",
        ]

        for eval_data in evaluation_result.get("evaluations", []):
            criteria = eval_data.get("criteria", "unknown")
            score = eval_data.get("score", 0)
            explanation = eval_data.get("explanation", "")

            # Score emoji
            emoji = "🟢" if score >= 4 else "🟡" if score >= 3 else "🔴"

            lines.append(f"**{emoji} {criteria.replace('_', ' ').title()}:** {score}/5")
            lines.append("")
            lines.append(f"{explanation[:300]}...")
            lines.append("")

        return "\n".join(lines)

    def format_auto_fix_evaluation_markdown(self, evaluation_result: Dict[str, Any]) -> str:
        """
        Format auto-fix evaluation results as Markdown.

        Args:
            evaluation_result: The evaluation result dictionary

        Returns:
            Formatted Markdown string
        """
        lines = [
            "### 📊 Auto-Fix Quality Evaluation (Phoenix SDK)",
            "",
            f"**Overall Score:** {evaluation_result['average_score']}/5 ⭐",
            "",
            "#### Criteria Breakdown:",
            "",
        ]

        for eval_data in evaluation_result.get("evaluations", []):
            criteria = eval_data.get("criteria", "unknown")
            score = eval_data.get("score", 0)
            explanation = eval_data.get("explanation", "")

            # Score emoji
            emoji = "🟢" if score >= 4 else "🟡" if score >= 3 else "🔴"

            lines.append(f"**{emoji} {criteria.replace('_', ' ').title()}:** {score}/5")
            lines.append("")
            lines.append(f"{explanation[:300]}...")
            lines.append("")

        return "\n".join(lines)


# Global evaluator instance
_phoenix_sdk_evaluator: Optional[PhoenixSDKEvaluator] = None


def get_phoenix_sdk_evaluator() -> PhoenixSDKEvaluator:
    """
    Get the global Phoenix SDK evaluator instance.

    Returns:
        The PhoenixSDKEvaluator instance (singleton)
    """
    global _phoenix_sdk_evaluator

    if _phoenix_sdk_evaluator is None:
        # Get configuration from environment
        model = os.getenv("JUDGE_MODEL", "gemini-3-flash-preview")
        concurrency = int(os.getenv("PHOENIX_EVAL_CONCURRENCY", "4"))
        max_retries = int(os.getenv("PHOENIX_EVAL_MAX_RETRIES", "3"))

        _phoenix_sdk_evaluator = PhoenixSDKEvaluator(
            model=model,
            concurrency=concurrency,
            max_retries=max_retries,
        )

    return _phoenix_sdk_evaluator
