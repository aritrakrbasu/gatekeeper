"""
Self-Improvement Loop for The Gatekeeper.

This module enables the agent to learn from its reviews and improve over time
by analyzing evaluation trends and adapting prompts based on feedback.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from google import genai
from google.genai import types

from config.arize_config import (
    set_span_attributes,
    ENABLE_SELF_IMPROVEMENT,
)
from .evaluators_legacy import EvaluationCriteria, get_evaluator

logger = logging.getLogger(__name__)


class PromptVersion:
    """Represents a version of a prompt."""

    def __init__(
        self,
        version_id: str,
        prompt: str,
        created_at: Optional[str] = None,
        parent_version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.version_id = version_id
        self.prompt = prompt
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.parent_version = parent_version
        self.metadata = metadata or {}
        self.evaluation_scores: List[float] = []

    def add_score(self, score: float):
        """Add an evaluation score."""
        self.evaluation_scores.append(score)

    def get_average_score(self) -> float:
        """Get average evaluation score."""
        if not self.evaluation_scores:
            return 0.0
        return sum(self.evaluation_scores) / len(self.evaluation_scores)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "prompt": self.prompt,
            "created_at": self.created_at,
            "parent_version": self.parent_version,
            "metadata": self.metadata,
            "evaluation_scores": self.evaluation_scores,
            "average_score": self.get_average_score(),
        }


class PromptExperiment:
    """Represents an A/B experiment comparing prompt versions."""

    def __init__(
        self,
        experiment_id: str,
        name: str,
        versions: List[str],
        created_at: Optional[str] = None,
    ):
        self.experiment_id = experiment_id
        self.name = name
        self.versions = versions  # List of version IDs
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.results: Dict[str, List[float]] = {v: [] for v in versions}
        self.status = "running"  # running, completed, abandoned

    def add_result(self, version_id: str, score: float):
        """Add an evaluation result for a version."""
        if version_id in self.results:
            self.results[version_id].append(score)

    def get_winner(self) -> Optional[str]:
        """Get the winning version based on average score."""
        if not self.results or all(len(v) == 0 for v in self.results.values()):
            return None

        averages = {
            v: (sum(scores) / len(scores) if scores else 0)
            for v, scores in self.results.items()
        }
        return max(averages, key=averages.get)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "versions": self.versions,
            "created_at": self.created_at,
            "results": self.results,
            "status": self.status,
            "winner": self.get_winner(),
        }


class SelfImprovingPromptManager:
    """
    Manages prompt versions and experiments for continuous improvement.

    The agent learns from its evaluations and adapts its prompts to improve
    review quality over time.
    """

    def __init__(
        self,
        prompts_dir: Optional[Path] = None,
        versions_dir: Optional[Path] = None,
        experiments_file: Optional[Path] = None,
    ):
        """
        Initialize the prompt manager.

        Args:
            prompts_dir: Directory containing base prompts
            versions_dir: Directory to store prompt versions
            experiments_file: File to store experiment data
        """
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent.parent / "prompts"
        self.versions_dir = versions_dir or self.prompts_dir / "versions"
        self.experiments_file = experiments_file or Path(__file__).parent.parent.parent / "config" / "experiments.json"

        # Create directories
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_file.parent.mkdir(parents=True, exist_ok=True)

        # Load state
        self.prompt_versions: Dict[str, PromptVersion] = {}
        self.experiments: Dict[str, PromptExperiment] = {}

        self._load_state()

    def _load_state(self):
        """Load prompt versions and experiments from disk."""
        # Load versions
        if self.versions_dir.exists():
            for version_file in self.versions_dir.glob("*.json"):
                try:
                    with open(version_file, "r") as f:
                        data = json.load(f)
                        version = PromptVersion(
                            version_id=data["version_id"],
                            prompt=data["prompt"],
                            created_at=data.get("created_at"),
                            parent_version=data.get("parent_version"),
                            metadata=data.get("metadata", {}),
                        )
                        version.evaluation_scores = data.get("evaluation_scores", [])
                        self.prompt_versions[version.version_id] = version
                except Exception as e:
                    logger.warning(f"[⚠️] Failed to load version {version_file}: {e}")

        # Load experiments
        if self.experiments_file.exists():
            try:
                with open(self.experiments_file, "r") as f:
                    data = json.load(f)
                    for exp_data in data.get("experiments", []):
                        exp = PromptExperiment(
                            experiment_id=exp_data["experiment_id"],
                            name=exp_data["name"],
                            versions=exp_data["versions"],
                            created_at=exp_data.get("created_at"),
                        )
                        exp.results = exp_data.get("results", {})
                        exp.status = exp_data.get("status", "running")
                        self.experiments[exp.experiment_id] = exp
            except Exception as e:
                logger.warning(f"[⚠️] Failed to load experiments: {e}")

        logger.info(f"[+] Loaded {len(self.prompt_versions)} prompt versions and {len(self.experiments)} experiments")

    def _save_state(self):
        """Save prompt versions and experiments to disk."""
        # Save versions
        for version in self.prompt_versions.values():
            version_file = self.versions_dir / f"{version.version_id}.json"
            with open(version_file, "w") as f:
                json.dump(version.to_dict(), f, indent=2)

        # Save experiments
        data = {
            "experiments": [exp.to_dict() for exp in self.experiments.values()],
            "last_updated": datetime.utcnow().isoformat(),
        }
        with open(self.experiments_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_base_prompt(self, prompt_name: str) -> str:
        """
        Load a base prompt from the prompts directory.

        Args:
            prompt_name: Name of the prompt (without extension)

        Returns:
            The prompt text
        """
        prompt_path = self.prompts_dir / f"{prompt_name}.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        else:
            logger.warning(f"[⚠️] Prompt file not found: {prompt_path}")
            return ""

    def create_version(
        self,
        base_prompt_name: str,
        modifications: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptVersion:
        """
        Create a new version of a prompt with modifications.

        Args:
            base_prompt_name: Name of the base prompt
            modifications: Description of modifications to make
            metadata: Optional metadata for the version

        Returns:
            The new PromptVersion
        """
        base_prompt = self.load_base_prompt(base_prompt_name)
        if not base_prompt:
            raise ValueError(f"Base prompt '{base_prompt_name}' not found")

        # Generate version ID
        version_id = f"{base_prompt_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Apply modifications using AI
        modified_prompt = self._apply_modifications(base_prompt, modifications)

        # Create version
        version = PromptVersion(
            version_id=version_id,
            prompt=modified_prompt,
            parent_version=base_prompt_name,
            metadata={
                **(metadata or {}),
                "modifications": modifications,
                "base_prompt": base_prompt_name,
            },
        )

        self.prompt_versions[version_id] = version
        self._save_state()

        logger.info(f"[+] Created prompt version: {version_id}")
        return version

    def _apply_modifications(self, prompt: str, modifications: str) -> str:
        """
        Apply modifications to a prompt using AI.

        Args:
            prompt: The original prompt
            modifications: Description of modifications

        Returns:
            The modified prompt
        """
        try:
            client = genai.Client()

            modification_prompt = f"""Modify the following prompt based on these instructions:

Original Prompt:
{prompt}

Modifications:
{modifications}

Return only the modified prompt, nothing else."""

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=modification_prompt,
                config=types.GenerateContentConfig(temperature=0.1),
            )

            return response.text.strip()
        except Exception as e:
            logger.warning(f"[⚠️] Failed to apply modifications with AI: {e}")
            # Fallback: append modifications
            return f"{prompt}\n\n# Additional Instructions\n{modifications}"

    def create_experiment(
        self,
        name: str,
        versions: List[str],
    ) -> PromptExperiment:
        """
        Create an A/B experiment comparing prompt versions.

        Args:
            name: Experiment name
            versions: List of version IDs to compare

        Returns:
            The new PromptExperiment
        """
        experiment_id = f"exp_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        experiment = PromptExperiment(
            experiment_id=experiment_id,
            name=name,
            versions=versions,
        )

        self.experiments[experiment_id] = experiment
        self._save_state()

        logger.info(f"[+] Created experiment: {experiment_id} comparing {len(versions)} versions")
        return experiment

    def record_evaluation(
        self,
        version_id: str,
        score: float,
        experiment_id: Optional[str] = None,
    ):
        """
        Record an evaluation score for a prompt version.

        Args:
            version_id: The prompt version ID
            score: The evaluation score
            experiment_id: Optional experiment ID
        """
        if version_id in self.prompt_versions:
            self.prompt_versions[version_id].add_score(score)

        if experiment_id and experiment_id in self.experiments:
            self.experiments[experiment_id].add_result(version_id, score)

        self._save_state()

    def analyze_weaknesses(
        self,
        recent_evaluations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze recent evaluations to identify weakness patterns.

        Args:
            recent_evaluations: List of recent evaluation results

        Returns:
            Dictionary with weakness analysis
        """
        if not recent_evaluations:
            return {"weaknesses": [], "recommendations": []}

        # Aggregate scores by criteria
        criteria_scores = defaultdict(list)
        for eval_result in recent_evaluations:
            for eval_data in eval_result.get("evaluations", []):
                criteria = eval_data.get("criteria")
                score = eval_data.get("score")
                if criteria and score is not None:
                    criteria_scores[criteria].append(score)

        # Identify weaknesses (average score < 3)
        weaknesses = []
        recommendations = []

        for criteria, scores in criteria_scores.items():
            avg_score = sum(scores) / len(scores)
            if avg_score < 3.0:
                weaknesses.append({
                    "criteria": criteria,
                    "average_score": avg_score,
                    "sample_count": len(scores),
                })

                # Generate recommendation
                recommendation = self._generate_improvement_recommendation(criteria, avg_score)
                recommendations.append(recommendation)

        return {
            "weaknesses": weaknesses,
            "recommendations": recommendations,
        }

    def _generate_improvement_recommendation(
        self,
        criteria: str,
        current_score: float,
    ) -> str:
        """Generate an improvement recommendation for a criteria."""
        recommendations = {
            EvaluationCriteria.SECURITY_COVERAGE.value: (
                "Focus on identifying security vulnerabilities. "
                "Add checks for: SQL injection, XSS, hardcoded secrets, "
                "insecure defaults, missing authentication, etc."
            ),
            EvaluationCriteria.CODE_QUALITY_COVERAGE.value: (
                "Improve code quality issue detection. "
                "Look for: code smells, anti-patterns, naming issues, "
                "lack of modularity, performance problems."
            ),
            EvaluationCriteria.ACTIONABILITY.value: (
                "Make fix suggestions more specific and actionable. "
                "Include: code examples, step-by-step instructions, "
                "file paths and line numbers."
            ),
            EvaluationCriteria.CLARITY.value: (
                "Improve explanation clarity. "
                "Use: clear structure, concise language, "
                "appropriate technical detail, visual formatting."
            ),
            EvaluationCriteria.COMPLETENESS.value: (
                "Ensure comprehensive coverage. "
                "Check for: missed edge cases, all file types reviewed, "
                "relevant standards considered."
            ),
            EvaluationCriteria.CORRECTNESS.value: (
                "Reduce false positives. "
                "Verify: findings are real issues, context is considered, "
                "false alarms minimized."
            ),
        }

        return recommendations.get(
            criteria,
            f"Improve performance on {criteria} (current score: {current_score:.1f}/5)",
        )

    def suggest_prompt_improvements(
        self,
        weakness_analysis: Dict[str, Any],
    ) -> List[str]:
        """
        Suggest prompt improvements based on weakness analysis.

        Args:
            weakness_analysis: Result from analyze_weaknesses()

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        for weakness in weakness_analysis.get("weaknesses", []):
            criteria = weakness["criteria"]
            suggestions.append(
                f"Add emphasis on {criteria.replace('_', ' ')} to the prompt"
            )

        for recommendation in weakness_analysis.get("recommendations", []):
            suggestions.append(recommendation)

        return suggestions

    def get_best_version(
        self,
        base_prompt_name: str,
        min_evaluations: int = 5,
    ) -> Optional[str]:
        """
        Get the best performing version of a prompt.

        Args:
            base_prompt_name: Base prompt name
            min_evaluations: Minimum number of evaluations required

        Returns:
            Version ID of the best version, or None
        """
        # Find all versions of this prompt
        versions = [
            (v_id, v)
            for v_id, v in self.prompt_versions.items()
            if v.parent_version == base_prompt_name or v_id.startswith(base_prompt_name)
        ]

        # Filter by minimum evaluations
        versions = [
            (v_id, v)
            for v_id, v in versions
            if len(v.evaluation_scores) >= min_evaluations
        ]

        if not versions:
            return None

        # Get version with highest average score
        best_version_id, best_version = max(
            versions,
            key=lambda x: x[1].get_average_score(),
        )

        logger.info(
            f"[+] Best version for {base_prompt_name}: {best_version_id} "
            f"(score: {best_version.get_average_score():.2f})"
        )

        return best_version_id

    def get_version_prompt(self, version_id: str) -> Optional[str]:
        """Get the prompt text for a version."""
        version = self.prompt_versions.get(version_id)
        return version.prompt if version else None


# Global prompt manager instance
_prompt_manager: Optional[SelfImprovingPromptManager] = None


def get_prompt_manager() -> SelfImprovingPromptManager:
    """
    Get the global prompt manager instance.

    Returns:
        The SelfImprovingPromptManager instance
    """
    global _prompt_manager

    if _prompt_manager is None and ENABLE_SELF_IMPROVEMENT:
        _prompt_manager = SelfImprovingPromptManager()

    return _prompt_manager


async def analyze_and_improve(
    recent_evaluations: List[Dict[str, Any]],
    prompt_name: str = "senior_pr_reviewer",
) -> Dict[str, Any]:
    """
    Analyze recent evaluations and suggest improvements.

    This is a convenience function that combines weakness analysis
    with prompt improvement suggestions.

    Args:
        recent_evaluations: List of recent evaluation results
        prompt_name: Name of the prompt to improve

    Returns:
        Dictionary with analysis and suggestions
    """
    if not ENABLE_SELF_IMPROVEMENT:
        return {"enabled": False, "message": "Self-improvement is disabled"}

    manager = get_prompt_manager()
    if not manager:
        return {"enabled": False, "message": "Prompt manager not initialized"}

    # Analyze weaknesses
    weakness_analysis = manager.analyze_weaknesses(recent_evaluations)

    # Generate suggestions
    suggestions = manager.suggest_prompt_improvements(weakness_analysis)

    return {
        "enabled": True,
        "weakness_analysis": weakness_analysis,
        "suggestions": suggestions,
        "current_best_version": manager.get_best_version(prompt_name),
    }
