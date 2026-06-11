"""
LLM-as-a-Judge Evaluators for Code Review Quality.

This module provides automatic evaluation of code review quality using
Gemini as the judge model, enabling continuous assessment of The Gatekeeper's
performance.
"""

import os
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

from google import genai
from google.genai import types

from config.arize_config import (
    get_phoenix_client,
    is_phoenix_configured,
    is_arize_initialized,
    set_span_attributes,
)

from .trace_utils import (
    get_current_trace_id,
    link_evaluation_to_trace,
    get_current_span_id,
)

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

    FIX_SYNTAX_VALIDITY = "fix_syntax_validity"
    """Are the auto-fixes syntactically valid and usable?"""


class ReviewQualityEvaluator:
    """
    LLM-as-a-Judge evaluator for code review quality.

    Uses Gemini to evaluate the quality of code reviews based on multiple criteria.
    """

    # Fallback evaluation prompts for each criteria (used if Arize AX is unavailable)
    EVALUATION_PROMPTS = {
        EvaluationCriteria.SECURITY_COVERAGE: """
You are evaluating a code review for security vulnerability coverage.

Code Diff:
{diff}

Review:
{review}

Evaluate: Did this review adequately identify security vulnerabilities?
Consider: SQL injection, XSS, hardcoded secrets, insecure defaults, etc.

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.CODE_QUALITY_COVERAGE: """
You are evaluating a code review for code quality issue coverage.

Code Diff:
{diff}

Review:
{review}

Evaluate: Did this review identify code quality problems?
Consider: Code smells, anti-patterns, maintainability, performance issues, etc.

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.ACTIONABILITY: """
You are evaluating the actionability of a code review.

Review:
{review}

Evaluate: Are the suggested fixes actionable and specific?
Consider: Are steps clear? Can a developer implement them? Are examples provided?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.CLARITY: """
You are evaluating the clarity of a code review.

Review:
{review}

Evaluate: Is the review explanation clear and well-structured?
Consider: Is it easy to understand? Is the language precise? Is formatting good?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.COMPLETENESS: """
You are evaluating the completeness of a code review.

Code Diff:
{diff}

Review:
{review}

Evaluate: Did this review cover all relevant issues?
Consider: Were important issues missed? Was the scope appropriate?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.CORRECTNESS: """
You are evaluating the correctness of a code review.

Code Diff:
{diff}

Review:
{review}

Evaluate: Are the findings accurate and not false positives?
Consider: Are identified issues real? Are there any false alarms?

Rate from 1-5 and explain your score.
""",

        # Auto-Fix Evaluation Prompts
        EvaluationCriteria.FIX_CORRECTNESS: """
You are evaluating auto-generated code fixes for correctness.

Original Issues:
{review}

Generated Fixes:
{fixes}

Evaluate: Do these fixes correctly solve the identified issues?
Consider: Do the fixes address the root cause? Are they accurate? Do they follow best practices?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.FIX_SAFETY: """
You are evaluating auto-generated code fixes for safety.

Original Issues:
{review}

Generated Fixes:
{fixes}

Evaluate: Are these fixes safe and don't introduce new bugs?
Consider: Do they maintain existing functionality? Are there side effects? Is error handling preserved?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.FIX_COMPLETENESS: """
You are evaluating auto-generated code fixes for completeness.

Original Issues:
{review}

Generated Fixes:
{fixes}

Evaluate: Do these fixes cover all identified issues?
Consider: Are all security issues addressed? Are partial fixes acceptable? Are critical issues prioritized?

Rate from 1-5 and explain your score.
""",

        EvaluationCriteria.FIX_SYNTAX_VALIDITY: """
You are evaluating auto-generated code fixes for syntax validity.

Generated Fixes:
{fixes}

Evaluate: Are these fixes syntactically valid and directly usable?
Consider: Is the code valid syntax? Are imports included? Are variable names consistent?

Rate from 1-5 and explain your score.
""",
    }

    # Parse score from response
    SCORE_PARSER_PROMPT = """
Extract the numeric score (1-5) from this evaluation response:

{response}

Return only the number, nothing else.
"""

    def __init__(
        self,
        judge_model: str = "gemini-3-flash-preview",
        phoenix_client=None,
    ):
        """
        Initialize the evaluator.

        Args:
            judge_model: The Gemini model to use as judge
            phoenix_client: Optional Phoenix client for logging evaluations
        """
        self.judge_model = judge_model
        self.phoenix_client = phoenix_client or get_phoenix_client()
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Get or create the Gemini client."""
        if self._client is None:
            self._client = genai.Client()
        return self._client

    async def _get_evaluation_prompt(self, criterion: EvaluationCriteria) -> str:
        """
        Get evaluation prompt for a specific criterion from Arize AX.

        Args:
            criterion: The evaluation criterion

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
                print(f"[WARN] Failed to load {prompt_id} from Arize AX: {e}, using fallback")

        # Fallback to hardcoded prompts
        return self.EVALUATION_PROMPTS.get(criterion, "")

    async def evaluate_review(
        self,
        diff: str,
        review: str,
        criteria: Optional[List[EvaluationCriteria]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a code review against specified criteria.

        Args:
            diff: The code diff that was reviewed
            review: The code review text
            criteria: List of criteria to evaluate (defaults to all)
            metadata: Optional metadata to attach to the evaluation

        Returns:
            Dictionary with evaluation results
        """
        if criteria is None:
            criteria = list(EvaluationCriteria)

        # Set span attributes for tracing
        if metadata:
            set_span_attributes(
                evaluation_type="code_review_quality",
                criteria_count=len(criteria),
                **{k: v for k, v in metadata.items() if k not in ["diff", "review"]}
            )

        results = {}
        total_score = 0
        evaluations = []

        client = self._get_client()

        for criterion in criteria:
            try:
                # Get evaluation prompt for this criteria (from Arize AX or fallback)
                prompt_template = await self._get_evaluation_prompt(criterion)
                prompt = prompt_template.format(
                    diff=diff[:10000],  # Limit size
                    review=review[:10000],
                )

                # Get evaluation from judge model
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.judge_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,  # Low temperature for consistent scoring
                    ),
                )

                evaluation_text = response.text

                # Extract score from response
                score = await self._extract_score(evaluation_text)

                results[criterion.value] = {
                    "score": score,
                    "explanation": evaluation_text,
                    "criterion": criterion.value,
                }

                total_score += score
                evaluations.append({
                    "criteria": criterion.value,
                    "score": score,
                    "explanation": evaluation_text,
                })

                logger.info(f"[+] Evaluated {criterion.value}: {score}/5")

            except Exception as e:
                logger.error(f"[x] Failed to evaluate {criterion.value}: {e}")
                results[criterion.value] = {
                    "score": 0,
                    "explanation": f"Evaluation failed: {str(e)}",
                    "criterion": criterion.value,
                }

        # Calculate average score
        average_score = total_score / len(criteria) if criteria else 0

        evaluation_result = {
            "average_score": round(average_score, 2),
            "total_score": total_score,
            "criteria_evaluated": len(criteria),
            "evaluations": evaluations,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        # Link evaluation to current trace for Arize dashboard visibility
        evaluation_result = link_evaluation_to_trace(evaluation_result)

        # Log to Phoenix if configured
        await self._log_to_phoenix(evaluation_result)

        return evaluation_result

    async def evaluate_auto_fix(
        self,
        fixes: str,
        review: str,
        criteria: Optional[List[EvaluationCriteria]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate auto-generated fixes for quality.

        Args:
            fixes: The generated fixes (JSON or text description)
            review: The original review/audit report that prompted the fixes
            criteria: List of criteria to evaluate (defaults to auto-fix criteria)
            metadata: Optional metadata to attach to the evaluation

        Returns:
            Dictionary with evaluation results
        """
        if criteria is None:
            criteria = [
                EvaluationCriteria.FIX_CORRECTNESS,
                EvaluationCriteria.FIX_SAFETY,
                EvaluationCriteria.FIX_COMPLETENESS,
            ]

        # Set span attributes for tracing
        if metadata:
            set_span_attributes(
                evaluation_type="auto_fix_quality",
                criteria_count=len(criteria),
                **{k: v for k, v in metadata.items() if k not in ["fixes", "review"]}
            )

        results = {}
        total_score = 0
        evaluations = []

        client = self._get_client()

        for criterion in criteria:
            try:
                # Get evaluation prompt for this criteria
                prompt = self.EVALUATION_PROMPTS[criterion].format(
                    fixes=fixes[:10000],  # Limit size
                    review=review[:10000],
                )

                # Get evaluation from judge model
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.judge_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,  # Low temperature for consistent scoring
                    ),
                )

                evaluation_text = response.text

                # Extract score from response
                score = await self._extract_score(evaluation_text)

                results[criterion.value] = {
                    "score": score,
                    "explanation": evaluation_text,
                    "criterion": criterion.value,
                }

                total_score += score
                evaluations.append({
                    "criteria": criterion.value,
                    "score": score,
                    "explanation": evaluation_text,
                })

                logger.info(f"[+] Evaluated {criterion.value}: {score}/5")

            except Exception as e:
                logger.error(f"[x] Failed to evaluate {criterion.value}: {e}")
                results[criterion.value] = {
                    "score": 0,
                    "explanation": f"Evaluation failed: {str(e)}",
                    "criterion": criterion.value,
                }

        # Calculate average score
        average_score = total_score / len(criteria) if criteria else 0

        evaluation_result = {
            "average_score": round(average_score, 2),
            "total_score": total_score,
            "criteria_evaluated": len(criteria),
            "evaluations": evaluations,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        # Link evaluation to current trace for Arize dashboard visibility
        evaluation_result = link_evaluation_to_trace(evaluation_result)

        # Log to Phoenix if configured
        await self._log_to_phoenix(evaluation_result)

        return evaluation_result

    async def _extract_score(self, evaluation_text: str) -> int:
        """
        Extract numeric score from evaluation response.

        Args:
            evaluation_text: The evaluation response text

        Returns:
            Score from 1-5
        """
        client = self._get_client()

        try:
            # Try to extract score using regex first
            import re
            score_match = re.search(r'(\d)[\s\/]*(?:out\s+of\s+)?5', evaluation_text)
            if score_match:
                return int(score_match.group(1))

            # Fallback: ask LLM to extract
            prompt = self.SCORE_PARSER_PROMPT.format(response=evaluation_text)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.judge_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0),
            )

            score_text = response.text.strip()
            score = int(score_text) if score_text.isdigit() else 3  # Default to middle

            return max(1, min(5, score))  # Clamp to 1-5

        except Exception as e:
            logger.warning(f"[⚠️] Failed to extract score: {e}")
            return 3  # Default score

    async def _log_to_phoenix(self, evaluation_result: Dict[str, Any]):
        """Log evaluation to Phoenix for tracking and self-improvement.

        This sets evaluation attributes on the CURRENT span (which should be
        the evaluation.code_review_quality span created in main.py).
        """
        logger.info(f"[*] Starting _log_to_phoenix...")
        logger.info(f"[*] Arize initialized: {is_arize_initialized()}")
        logger.info(f"[*] Phoenix configured: {is_phoenix_configured()}")
        logger.info(f"[*] Evaluation result keys: {list(evaluation_result.keys())}")

        # Check if Arize is initialized for span attributes
        if not is_arize_initialized():
            logger.warning("[⚠️] Arize not initialized - evaluation attributes won't be sent to dashboard")
            logger.info("[ℹ️] Set ARIZE_SPACE_ID and ARIZE_API_KEY in .env to enable evaluation logging")
            return

        try:
            # Get trace ID from evaluation result (linked by link_evaluation_to_trace)
            trace_id = evaluation_result.get("linked_trace_id") or evaluation_result.get("trace_id")

            logger.info(f"[*] Trace ID from evaluation result: {trace_id[:12] if trace_id else 'None'}...")

            if not trace_id:
                # Try to get current trace ID as fallback
                trace_id = get_current_trace_id()
                logger.info(f"[*] Trace ID from get_current_trace_id(): {trace_id[:12] if trace_id else 'None'}...")

            # Import here to avoid circular dependency
            from config.arize_config import set_span_attributes

            # Build evaluation metadata - all values must be strings for Arize
            evaluation_metadata = {
                "evaluation_type": "code_review_quality",
                "average_score": str(evaluation_result['average_score']),
                "criteria_evaluated": str(evaluation_result['criteria_evaluated']),
                "timestamp": evaluation_result['timestamp'],
            }

            logger.info(f"[*] Base evaluation metadata: {list(evaluation_metadata.keys())}")

            # Add trace ID if available - this is the key for linking
            if trace_id:
                evaluation_metadata["trace_id"] = trace_id
                evaluation_metadata["linked_trace_id"] = trace_id
                logger.info(f"[✅] Added trace_id linkage: {trace_id[:12]}...")

            # Add per-criteria scores - THIS IS WHERE eval_security_coverage IS SET
            eval_list = evaluation_result.get('evaluations', [])
            logger.info(f"[*] Processing {len(eval_list)} individual evaluations...")

            for eval_data in eval_list:
                criteria = eval_data.get('criteria', 'unknown')
                score = eval_data.get('score', 0)
                attr_name = f"eval_{criteria}"
                evaluation_metadata[attr_name] = str(score)
                logger.info(f"[✅] Setting attribute '{attr_name}' = {score}")

            logger.info(f"[*] Final evaluation metadata keys: {list(evaluation_metadata.keys())}")
            logger.info(f"[*] About to call set_span_attributes with {len(evaluation_metadata)} attributes...")

            # Set as span attributes on the CURRENT span (from main.py)
            set_span_attributes(**evaluation_metadata)

            # Log success
            logger.info(f"[✅] Evaluation logged to Phoenix/Arize - Score: {evaluation_result['average_score']}/5" +
                       (f" (Trace: {trace_id[:12]}...)" if trace_id else ""))

            # Verify the attributes were set
            from opentelemetry import trace
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                logger.info(f"[✅] Attributes set on span: {current_span.name}")
            else:
                logger.warning(f"[⚠️] No active/recording span when setting attributes!")

            # --- EXPORT FORMAL EVALUATIONS TO PHOENIX EVALUATIONS TAB ---
            # This creates evaluation records that appear in the Phoenix Evaluations tab
            try:
                from .phoenix_evaluations import get_evaluation_exporter

                # Get the current span ID
                span_id = get_current_span_id()
                if not span_id:
                    logger.warning("[⚠️] No span ID available - cannot export formal evaluation to Phoenix Evaluations tab")
                else:
                    logger.info(f"[*] Exporting formal evaluation records to Phoenix Evaluations tab...")

                    exporter = get_evaluation_exporter()

                    # Export each criteria as a separate evaluation record
                    eval_list = evaluation_result.get('evaluations', [])
                    for eval_data in eval_list:
                        criteria = eval_data.get('criteria', 'unknown')
                        score = eval_data.get('score', 0)
                        explanation = eval_data.get('explanation', '')

                        # Convert score to 0-1 range for Phoenix (5/5 = 1.0, 1/5 = 0.2)
                        normalized_score = score / 5.0

                        # Determine label based on score
                        if score >= 4:
                            label = "pass"
                        elif score >= 3:
                            label = "acceptable"
                        else:
                            label = "fail"

                        # Export to Phoenix
                        exporter.add_evaluation(
                            span_id=span_id,
                            eval_name=criteria,
                            score=normalized_score,
                            label=label,
                            explanation=explanation[:500],  # Limit explanation length
                            metadata={
                                "raw_score": str(score),
                                "average_score": str(evaluation_result['average_score']),
                                "evaluation_type": evaluation_result.get('metadata', {}).get('evaluation_type', 'unknown'),
                            }
                        )

                    # Flush evaluations to Phoenix - THIS IS THE KEY STEP!
                    logger.info(f"[*] Flushing {len(eval_list)} evaluations to Phoenix Evaluations tab...")

                    # Use async flush since we're making HTTP calls
                    try:
                        flush_success = await exporter.flush_async()
                    except RuntimeError:
                        # If we can't use async (no event loop), fall back to sync
                        flush_success = exporter.flush()

                    if flush_success:
                        logger.info(f"[✅] Exported {len(eval_list)} evaluation records to Phoenix Evaluations tab")
                    else:
                        logger.warning(f"[⚠️] Evaluation export had issues - check logs for details")

            except ImportError:
                pass  # Phoenix evaluation exporter not available
            except Exception as export_err:
                logger.warning(f"[⚠️] Failed to export formal evaluations to Phoenix: {export_err}")

        except Exception as e:
            logger.warning(f"[⚠️] Failed to log evaluation to Phoenix: {e}")

    def format_evaluation_markdown(self, evaluation_result: Dict[str, Any]) -> str:
        """
        Format evaluation results as Markdown.

        Args:
            evaluation_result: The evaluation result dictionary

        Returns:
            Formatted Markdown string
        """
        lines = [
            "### 📊 Code Review Quality Evaluation",
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
            lines.append(f"{explanation[:200]}...")
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
            "### 📊 Auto-Fix Quality Evaluation",
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
            lines.append(f"{explanation[:200]}...")
            lines.append("")

        return "\n".join(lines)


class BatchEvaluator:
    """
    Evaluates multiple reviews and aggregates results.

    Useful for tracking quality over time and comparing prompt versions.
    """

    def __init__(self, base_evaluator: ReviewQualityEvaluator):
        """
        Initialize the batch evaluator.

        Args:
            base_evaluator: The base evaluator to use
        """
        self.base_evaluator = base_evaluator
        self._evaluations: List[Dict[str, Any]] = []

    async def evaluate_batch(
        self,
        reviews: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluate multiple reviews.

        Args:
            reviews: List of dicts with 'diff', 'review', and optional 'metadata'

        Returns:
            Aggregated evaluation results
        """
        results = []

        for review_data in reviews:
            try:
                result = await self.base_evaluator.evaluate_review(
                    diff=review_data.get("diff", ""),
                    review=review_data.get("review", ""),
                    metadata=review_data.get("metadata"),
                )
                results.append(result)
            except Exception as e:
                logger.error(f"[x] Failed to evaluate review: {e}")

        # Calculate aggregates
        if results:
            avg_score = sum(r["average_score"] for r in results) / len(results)
            high_quality = sum(1 for r in results if r["average_score"] >= 4)
            low_quality = sum(1 for r in results if r["average_score"] < 3)
        else:
            avg_score = 0
            high_quality = 0
            low_quality = 0

        return {
            "total_evaluations": len(results),
            "average_score": round(avg_score, 2),
            "high_quality_count": high_quality,
            "low_quality_count": low_quality,
            "results": results,
        }

    def get_criteria_trends(self, evaluations: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """
        Extract score trends for each criteria over time.

        Args:
            evaluations: List of evaluation results

        Returns:
            Dict mapping criteria to list of scores
        """
        trends = {}

        for eval_result in evaluations:
            for eval_data in eval_result.get("evaluations", []):
                criteria = eval_data.get("criteria")
                score = eval_data.get("score")

                if criteria not in trends:
                    trends[criteria] = []
                trends[criteria].append(score)

        return trends


# Global evaluator instance
_evaluator: Optional[ReviewQualityEvaluator] = None


def get_evaluator() -> ReviewQualityEvaluator:
    """
    Get the global evaluator instance.

    Returns:
        The ReviewQualityEvaluator instance
    """
    global _evaluator

    if _evaluator is None:
        judge_model = os.getenv("JUDGE_MODEL", "gemini-3-flash-preview")
        _evaluator = ReviewQualityEvaluator(judge_model=judge_model)

    return _evaluator
