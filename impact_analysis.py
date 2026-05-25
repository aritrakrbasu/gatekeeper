"""
Impact Analysis Module for Code Change Review

This module provides impact analysis capabilities to identify code affected by changes,
including dependencies, call chains, and potential ripple effects beyond the directly
changed files.

Integrates with GitNexus (https://github.com/abhigyanpatwari/GitNexus) for advanced
code intelligence via MCP.
"""

import os
import re
import ast
import asyncio
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ImpactLevel(Enum):
    """Severity levels for impact analysis findings."""
    CRITICAL = "critical"  # Breaking changes that will definitely cause issues
    HIGH = "high"  # Likely to cause issues
    MEDIUM = "medium"  # May cause issues in certain scenarios
    LOW = "low"  # Unlikely to cause issues
    INFO = "info"  # Informational only


# Timeout for MCP tool calls (in seconds) to prevent indefinite hangs
MCP_TIMEOUT = 30


async def call_mcp_tool_with_timeout(session, name: str, arguments: dict, timeout: float = MCP_TIMEOUT):
    """
    Call an MCP tool with a timeout to prevent indefinite hangs.

    Args:
        session: MCP session (gitlab_session, nexus_session, etc.)
        name: Tool name
        arguments: Tool arguments
        timeout: Timeout in seconds

    Returns:
        Tool result

    Raises:
        asyncio.TimeoutError: If the call times out
    """
    return await asyncio.wait_for(
        session.call_tool(name=name, arguments=arguments),
        timeout=timeout
    )


@dataclass
class ImpactFinding:
    """A single impact analysis finding."""
    level: ImpactLevel
    file_path: str
    line_number: int
    description: str
    impact_type: str  # "dependency", "call_chain", "breaking_change", "api_change", etc.
    related_change: str  # Reference to the change that causes this impact
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "level": self.level.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "description": self.description,
            "impact_type": self.impact_type,
            "related_change": self.related_change,
            "suggestion": self.suggestion
        }


@dataclass
class ImpactReport:
    """Complete impact analysis report."""
    project_id: str
    merge_request_iid: int
    source_branch: str
    target_branch: str
    changed_files: Set[str] = field(default_factory=set)
    findings: List[ImpactFinding] = field(default_factory=list)
    analyzed_files: Set[str] = field(default_factory=set)
    execution_time_seconds: float = 0.0

    def add_finding(self, finding: ImpactFinding):
        """Add a finding to the report."""
        self.findings.append(finding)

    def get_findings_by_level(self, level: ImpactLevel) -> List[ImpactFinding]:
        """Get all findings of a specific level."""
        return [f for f in self.findings if f.level == level]

    def get_findings_by_type(self, impact_type: str) -> List[ImpactFinding]:
        """Get all findings of a specific type."""
        return [f for f in self.findings if f.impact_type == impact_type]

    def to_markdown(self) -> str:
        """Generate a markdown summary of the report."""
        lines = [
            "## 🎯 Impact Analysis Report",
            "",
            f"**MR:** !{self.merge_request_iid} | **Branch:** `{self.source_branch}` → `{self.target_branch}`",
            f"**Files Changed:** {len(self.changed_files)} | **Files Analyzed:** {len(self.analyzed_files)}",
            f"**Analysis Time:** {self.execution_time_seconds:.2f}s",
            "",
            "### Findings Summary",
            ""
        ]

        # Count by level
        level_counts = {}
        for finding in self.findings:
            level_counts[finding.level] = level_counts.get(finding.level, 0) + 1

        for level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM, ImpactLevel.LOW, ImpactLevel.INFO]:
            count = level_counts.get(level, 0)
            if count > 0:
                emoji = {
                    ImpactLevel.CRITICAL: "🔴",
                    ImpactLevel.HIGH: "🟠",
                    ImpactLevel.MEDIUM: "🟡",
                    ImpactLevel.LOW: "🟢",
                    ImpactLevel.INFO: "ℹ️"
                }[level]
                lines.append(f"- {emoji} **{level.value.upper()}**: {count} findings")

        lines.append("")
        lines.append("### Detailed Findings")
        lines.append("")

        # Group by impact type
        by_type: Dict[str, List[ImpactFinding]] = {}
        for finding in self.findings:
            if finding.impact_type not in by_type:
                by_type[finding.impact_type] = []
            by_type[finding.impact_type].append(finding)

        for impact_type, findings in sorted(by_type.items()):
            lines.append(f"#### {impact_type.replace('_', ' ').title()}")
            lines.append("")

            for finding in findings[:20]:  # Limit to 20 per type to avoid huge reports
                emoji = {
                    ImpactLevel.CRITICAL: "🔴",
                    ImpactLevel.HIGH: "🟠",
                    ImpactLevel.MEDIUM: "🟡",
                    ImpactLevel.LOW: "🟢",
                    ImpactLevel.INFO: "ℹ️"
                }[finding.level]
                lines.append(f"- {emoji} **{finding.file_path}:{finding.line_number}**")
                lines.append(f"  - {finding.description}")
                if finding.suggestion:
                    lines.append(f"  - 💡 *{finding.suggestion}*")
                lines.append("")

        return '\n'.join(lines)


class PythonCodeAnalyzer:
    """
    Analyzes Python code to extract dependencies, function calls, and class relationships.
    """

    def __init__(self, file_content: str, file_path: str):
        """Initialize analyzer with file content."""
        self.file_content = file_content
        self.file_path = file_path
        self.tree = None
        self.imports: Set[str] = set()
        self.function_definitions: Dict[str, Tuple[int, List[str]]] = {}  # name -> (line, calls)
        self.class_definitions: Dict[str, Tuple[int, List[str]]] = {}  # name -> (line, methods)
        self.function_calls: List[Tuple[int, str]] = []  # (line, called_function)

        try:
            self.tree = ast.parse(file_content)
            self._analyze()
        except SyntaxError:
            pass  # File might not be valid Python

    def _analyze(self):
        """Perform AST analysis."""
        if not self.tree:
            return

        for node in ast.walk(self.tree):
            # Track imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports.add(node.module.split('.')[0])

            # Track function definitions
            if isinstance(node, ast.FunctionDef):
                calls = self._extract_calls(node)
                self.function_definitions[node.name] = (node.lineno, calls)

            # Track class definitions
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                self.class_definitions[node.name] = (node.lineno, methods)

    def _extract_calls(self, node: ast.AST) -> List[str]:
        """Extract function calls from a node."""
        calls = []

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)

        return calls

    def get_function_at_line(self, line: int) -> Optional[str]:
        """Get the function name containing a given line."""
        for func_name, (func_line, _) in self.function_definitions.items():
            # Simple check - in real code would need to account for function length
            if func_line <= line:
                return func_name
        return None

    def get_functions_calling(self, function_name: str) -> List[Tuple[str, int]]:
        """
        Find functions that call the given function.

        Returns:
            List of (caller_function_name, line_number) tuples
        """
        callers = []

        for func_name, (func_line, calls) in self.function_definitions.items():
            if function_name in calls:
                callers.append((func_name, func_line))

        return callers


class GitImpactAnalyzer:
    """
    Main impact analysis engine combining GitNexus with fallback code analysis.
    """

    def __init__(self, repo_path: Optional[Path] = None, nexus_session=None):
        """
        Initialize the analyzer.

        Args:
            repo_path: Path to the git repository. If None, assumes current directory.
            nexus_session: Active GitNexus MCP session for advanced analysis
        """
        self.repo_path = repo_path or Path.cwd()
        self.nexus = GitNexusWrapper(nexus_session, repo_path)
        self.findings_cache: Dict[str, List[ImpactFinding]] = {}

    async def analyze_merge_request(
        self,
        project_id: str,
        merge_request_iid: int,
        source_branch: str,
        target_branch: str,
        changed_files: List[str],
        gitlab_session=None
    ) -> ImpactReport:
        """
        Perform comprehensive impact analysis for a merge request.

        Args:
            project_id: GitLab project ID
            merge_request_iid: Merge request IID
            source_branch: Source branch
            target_branch: Target branch
            changed_files: List of changed file paths
            gitlab_session: Optional GitLab MCP session for fetching file contents

        Returns:
            ImpactReport with all findings
        """
        import time
        start_time = time.time()

        report = ImpactReport(
            project_id=project_id,
            merge_request_iid=merge_request_iid,
            source_branch=source_branch,
            target_branch=target_branch,
            changed_files=set(changed_files)
        )

        # 1. Pre-review: Identify dependencies and call chains
        await self._analyze_dependencies(report, changed_files, gitlab_session)

        # 2. Check for breaking API changes
        await self._analyze_api_changes(report, changed_files, gitlab_session)

        # 3. Check for configuration/environment changes
        await self._analyze_config_changes(report, changed_files, gitlab_session)

        # 4. Analyze test coverage impact
        await self._analyze_test_impact(report, changed_files, gitlab_session)

        report.execution_time_seconds = time.time() - start_time
        return report

    async def _analyze_dependencies(
        self,
        report: ImpactReport,
        changed_files: List[str],
        gitlab_session
    ):
        """Analyze dependency relationships and call chains."""
        if not gitlab_session:
            return

        python_files = [f for f in changed_files if f.endswith('.py')]

        for file_path in python_files:
            try:
                # Fetch file content from target branch (with timeout to prevent hangs)
                result = await asyncio.wait_for(
                    gitlab_session.call_tool(
                        name="get_file_contents",
                        arguments={
                            "project_id": str(report.project_id),
                            "file_path": file_path,
                            "ref": report.target_branch
                        }
                    ),
                    timeout=MCP_TIMEOUT
                )

                # Parse and analyze
                content = str(result.content)
                analyzer = PythonCodeAnalyzer(content, file_path)

                report.analyzed_files.add(file_path)

                # Check for changes to public functions
                for func_name, (line, calls) in analyzer.function_definitions.items():
                    if not func_name.startswith('_'):  # Public function
                        # This is a change that might affect callers
                        report.add_finding(ImpactFinding(
                            level=ImpactLevel.MEDIUM,
                            file_path=file_path,
                            line_number=line,
                            description=f"Public function `{func_name}` has been modified. "
                                       f"Check all call sites for compatibility.",
                            impact_type="call_chain",
                            related_change=f"Function {func_name} in {file_path}",
                            suggestion="Review all files that import and call this function."
                        ))

            except asyncio.TimeoutError:
                print(f"[⏱️] Timeout fetching file {file_path} from GitLab MCP (>{MCP_TIMEOUT}s)")
            except Exception as e:
                print(f"[⚠️] Could not analyze dependencies for {file_path}: {e}")

    async def _analyze_api_changes(
        self,
        report: ImpactReport,
        changed_files: List[str],
        gitlab_session
    ):
        """Analyze API/interface changes that could break consumers."""
        api_patterns = {
            'routes': re.compile(r'@.*\.(route|get|post|put|delete|patch)', re.IGNORECASE),
            'api_decorators': re.compile(r'@api\.', re.IGNORECASE),
            'fastapi': re.compile(r'@.*\.(get|post|put|delete|patch)\(', re.IGNORECASE),
            'schema_changes': re.compile(r'class.*\(.*Base.*\):', re.IGNORECASE),
        }

        for file_path in changed_files:
            if not any(file_path.endswith(ext) for ext in ['.py', '.js', '.ts']):
                continue

            try:
                # Fetch file content (with timeout to prevent hangs)
                result = await asyncio.wait_for(
                    gitlab_session.call_tool(
                        name="get_file_contents",
                        arguments={
                            "project_id": str(report.project_id),
                            "file_path": file_path,
                            "ref": report.target_branch
                        }
                    ),
                    timeout=MCP_TIMEOUT
                )

                content = str(result.content)

                # Check for API definitions
                if any(pattern.search(content) for pattern in api_patterns.values()):
                    report.add_finding(ImpactFinding(
                        level=ImpactLevel.HIGH,
                        file_path=file_path,
                        line_number=1,
                        description="This file contains API route definitions. Changes may affect API consumers.",
                        impact_type="api_change",
                        related_change=file_path,
                        suggestion="Review API documentation and notify consumers of breaking changes."
                    ))

            except asyncio.TimeoutError:
                print(f"[⏱️] Timeout fetching file {file_path} from GitLab MCP (>{MCP_TIMEOUT}s)")
            except Exception as e:
                print(f"[⚠️] Could not analyze API changes for {file_path}: {e}")

    async def _analyze_config_changes(
        self,
        report: ImpactReport,
        changed_files: List[str],
        gitlab_session
    ):
        """Analyze configuration and environment variable changes."""
        config_files = [
            '.env', '.env.example', '.env.local',
            'config.py', 'settings.py', 'settings/*.py',
            'docker-compose.yml', 'Dockerfile',
            'package.json', 'requirements.txt', 'pyproject.toml'
        ]

        for file_path in changed_files:
            if any(file_path == cf or file_path.endswith(cf) for cf in config_files):
                report.add_finding(ImpactFinding(
                    level=ImpactLevel.HIGH,
                    file_path=file_path,
                    line_number=1,
                    description=f"Configuration file `{file_path}` has been modified. "
                               f"This may require deployment updates or environment changes.",
                    impact_type="config_change",
                    related_change=file_path,
                    suggestion="Ensure all environments are updated with new configuration."
                ))

    async def _analyze_test_impact(
        self,
        report: ImpactReport,
        changed_files: List[str],
        gitlab_session
    ):
        """Analyze which tests need to be run based on changes."""
        test_files = [f for f in changed_files if 'test' in f.lower()]

        source_files = [f for f in changed_files
                       if not any(x in f.lower() for x in ['test', 'spec', 'mock'])]

        if not source_files:
            return

        # Map source files to likely test files
        for source_file in source_files:
            if source_file.endswith('.py'):
                # Suggest test file
                test_file = source_file.replace('.py', '_test.py')
                test_file_alt = source_file.replace('.py', '.test.py')
                test_file_path = f"tests/{source_file}"

                report.add_finding(ImpactFinding(
                    level=ImpactLevel.INFO,
                    file_path=source_file,
                    line_number=1,
                    description=f"Source file modified. Run tests: `{test_file}`, `{test_file_alt}`, or `{test_file_path}`",
                    impact_type="test_coverage",
                    related_change=source_file,
                    suggestion=f"Ensure tests for {source_file} are updated and passing."
                ))

    async def post_review_validation(
        self,
        report: ImpactReport,
        review_findings: List[dict],
        gitlab_session
    ) -> List[ImpactFinding]:
        """
        Perform post-review validation to catch issues outside changed code.

        Args:
            report: The original impact report
            review_findings: Findings from the AI review
            gitlab_session: GitLab MCP session

        Returns:
            Additional findings discovered during validation
        """
        validation_findings = []

        # Check if review found issues that might have broader impact
        for finding in review_findings:
            # If security issues found in changed functions, check their callers
            if finding.get('severity') == 'high':
                # This would need more sophisticated analysis in production
                pass

        return validation_findings


class GitNexusWrapper:
    """
    Wrapper for integrating with GitNexus MCP server.

    GitNexus provides:
    - impact(): Blast radius analysis with depth grouping and confidence
    - detect_changes(): Git-diff impact — maps changed lines to affected processes
    - context(): 360-degree symbol view — categorized refs, process participation
    - query(): Process-grouped hybrid search (BM25 + semantic + RRF)

    Installation: npm install -g gitnexus
    MCP Server: gitnexus mcp (or npx -y gitnexus@latest mcp)
    """

    def __init__(self, nexus_session=None, repo_path: Optional[Path] = None):
        """
        Initialize the wrapper.

        Args:
            nexus_session: Active MCP ClientSession for GitNexus
            repo_path: Path to the repository (for fallback operations)
        """
        self.nexus_session = nexus_session
        self.repo_path = repo_path or Path.cwd()
        self.nexus_available = nexus_session is not None

    async def get_impact_scope(
        self,
        target: str,
        direction: str = "upstream",
        max_depth: int = 3,
        min_confidence: float = 0.7,
        repo: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Get impact scope using GitNexus impact tool.

        Args:
            target: Symbol name to analyze (e.g., "UserService", "validateUser")
            direction: "upstream" (what depends on this) or "downstream" (what this depends on)
            max_depth: How deep to trace dependencies
            min_confidence: Minimum confidence threshold (0.0-1.0)
            repo: Repository name (if multiple repos indexed)

        Returns:
            Dict with impact data including affected symbols, processes, and confidence scores
        """
        if not self.nexus_available:
            return await self._git_fallback_impact_scope(target, direction)

        try:
            result = await asyncio.wait_for(
                self.nexus_session.call_tool(
                    name="impact",
                    arguments={
                        "target": target,
                        "direction": direction,
                        "maxDepth": max_depth,
                        "minConfidence": min_confidence,
                        "repo": repo
                    }
                ),
                timeout=MCP_TIMEOUT
            )

            return self._parse_nexus_impact_result(result)

        except Exception as e:
            print(f"[⚠️] GitNexus impact analysis failed: {e}")
            return await self._git_fallback_impact_scope(target, direction)

    async def detect_changes_impact(
        self,
        repo: Optional[str] = None,
        scope: str = "all"
    ) -> Dict[str, any]:
        """
        Detect impact of uncommitted changes using GitNexus detect_changes.

        Args:
            repo: Repository name
            scope: "all", "staged", or "unstaged"

        Returns:
            Dict with changed symbols, affected processes, and risk level
        """
        if not self.nexus_available:
            return {"changed_symbols": [], "affected_processes": [], "risk_level": "unknown"}

        try:
            result = await asyncio.wait_for(
                self.nexus_session.call_tool(
                    name="detect_changes",
                    arguments={
                        "repo": repo,
                        "scope": scope
                    }
                ),
                timeout=MCP_TIMEOUT
            )

            return self._parse_nexus_detect_changes_result(result)

        except Exception as e:
            print(f"[⚠️] GitNexus detect_changes failed: {e}")
            return {"changed_symbols": [], "affected_processes": [], "risk_level": "unknown"}

    async def get_symbol_context(
        self,
        symbol_name: str,
        repo: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Get 360-degree context for a symbol using GitNexus context tool.

        Args:
            symbol_name: Name of the symbol to analyze
            repo: Repository name

        Returns:
            Dict with incoming/outgoing references, process participation, etc.
        """
        if not self.nexus_available:
            return {"symbol": None, "incoming": {}, "outgoing": {}, "processes": []}

        try:
            result = await asyncio.wait_for(
                self.nexus_session.call_tool(
                    name="context",
                    arguments={
                        "name": symbol_name,
                        "repo": repo
                    }
                ),
                timeout=MCP_TIMEOUT
            )

            return self._parse_nexus_context_result(result)

        except Exception as e:
            print(f"[⚠️] GitNexus context failed: {e}")
            return {"symbol": symbol_name, "incoming": {}, "outgoing": {}, "processes": []}

    async def query_codebase(
        self,
        query: str,
        repo: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, any]:
        """
        Search the codebase using GitNexus query tool.

        Args:
            query: Search query
            repo: Repository name
            limit: Max results

        Returns:
            Dict with process-grouped search results
        """
        if not self.nexus_available:
            return {"processes": [], "definitions": [], "process_symbols": []}

        try:
            result = await asyncio.wait_for(
                self.nexus_session.call_tool(
                    name="query",
                    arguments={
                        "query": query,
                        "repo": repo,
                        "limit": limit
                    }
                ),
                timeout=MCP_TIMEOUT
            )

            return self._parse_nexus_query_result(result)

        except Exception as e:
            print(f"[⚠️] GitNexus query failed: {e}")
            return {"processes": [], "definitions": [], "process_symbols": []}

    def _parse_nexus_impact_result(self, result) -> Dict[str, any]:
        """Parse GitNexus impact tool result."""
        try:
            if hasattr(result, 'content') and result.content:
                content = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                data = json.loads(content)
                return data
        except Exception as e:
            print(f"[⚠️] Failed to parse impact result: {e}")
        return {"affected": [], "processes": [], "confidence": 0}

    def _parse_nexus_detect_changes_result(self, result) -> Dict[str, any]:
        """Parse GitNexus detect_changes tool result."""
        try:
            if hasattr(result, 'content') and result.content:
                content = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                data = json.loads(content)
                return data
        except Exception as e:
            print(f"[⚠️] Failed to parse detect_changes result: {e}")
        return {"changed_symbols": [], "affected_processes": [], "risk_level": "unknown"}

    def _parse_nexus_context_result(self, result) -> Dict[str, any]:
        """Parse GitNexus context tool result."""
        try:
            if hasattr(result, 'content') and result.content:
                content = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                data = json.loads(content)
                return data
        except Exception as e:
            print(f"[⚠️] Failed to parse context result: {e}")
        return {"symbol": None, "incoming": {}, "outgoing": {}, "processes": []}

    def _parse_nexus_query_result(self, result) -> Dict[str, any]:
        """Parse GitNexus query tool result."""
        try:
            if hasattr(result, 'content') and result.content:
                content = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                data = json.loads(content)
                return data
        except Exception as e:
            print(f"[⚠️] Failed to parse query result: {e}")
        return {"processes": [], "definitions": [], "process_symbols": []}

    async def _git_fallback_impact_scope(self, target: str, direction: str = "upstream") -> Dict[str, any]:
        """
        Fallback using standard git commands when GitNexus is not available.

        This provides basic impact analysis without GitNexus.
        """
        try:
            # Use pathlib to list files instead of git (avoids credential popups)
            repo_path = Path(self.repo_path)
            if not repo_path.exists():
                return {"affected": [], "processes": [], "confidence": 0}

            # Find common code files
            files = []
            for pattern in ['*.py', '*.js', '*.ts', '*.jsx', '*.tsx']:
                files.extend([str(f.relative_to(repo_path)) for f in repo_path.rglob(pattern)])

            return {
                "affected": files[:10],  # Limit results
                "processes": [],
                "confidence": 0.5,
                "fallback": True,
                "message": "GitNexus not available - using basic file system analysis"
            }
        except Exception as e:
            print(f"[⚠️] File system fallback failed: {e}")
            return {"affected": [], "processes": [], "confidence": 0}

            files = [f.strip() for f in result.stdout.split('\n') if f.strip()]

            return {
                "affected": files[:10],  # Limit results
                "processes": [],
                "confidence": 0.5,
                "fallback": True,
                "message": "GitNexus not available - using basic git analysis"
            }
        except Exception as e:
            print(f"[⚠️] Git fallback failed: {e}")
            return {"affected": [], "processes": [], "confidence": 0}

    def _parse_nexus_output(self, output: str) -> Dict[str, List[str]]:
        """Parse git-nexus output format."""
        # This would be adapted based on actual git-nexus output format
        return {
            "files": [],
            "functions": [],
            "modules": []
        }


async def run_pre_review_analysis(
    project_id: str,
    mr_iid: int,
    source_branch: str,
    target_branch: str,
    changed_files: List[str],
    gitlab_session,
    nexus_session=None
) -> Tuple[ImpactReport, str]:
    """
    Run pre-review impact analysis and return report + context string.

    The context string can be included in the AI review prompt for better analysis.

    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        source_branch: Source branch
        target_branch: Target branch
        changed_files: List of changed files
        gitlab_session: GitLab MCP session
        nexus_session: Optional GitNexus MCP session for advanced analysis
    """
    analyzer = GitImpactAnalyzer(nexus_session=nexus_session)

    report = await analyzer.analyze_merge_request(
        project_id=project_id,
        merge_request_iid=mr_iid,
        source_branch=source_branch,
        target_branch=target_branch,
        changed_files=changed_files,
        gitlab_session=gitlab_session
    )

    # Generate context for AI review
    context = f"""
## Impact Analysis Context

The following impact analysis was performed before review:

- **Changed Files**: {len(report.changed_files)}
- **Analyzed Files**: {len(report.analyzed_files)}
- **Key Findings**: {len(report.findings)}

### Critical Impact Areas:
{chr(10).join(f"- [{f.level.value.upper()}] {f.file_path}: {f.description}" for f in report.findings if f.level in [ImpactLevel.CRITICAL, ImpactLevel.HIGH])}

### Medium Priority Findings:
{chr(10).join(f"- [{f.level.value.upper()}] {f.file_path}: {f.description}" for f in report.findings if f.level == ImpactLevel.MEDIUM)[:500]}

---

*The reviewer should pay special attention to these impact areas when evaluating the changes.*
"""

    return report, context


async def run_post_review_validation(
    pre_review_report: ImpactReport,
    ai_review_findings: List[dict],
    gitlab_session,
    nexus_session=None
) -> List[ImpactFinding]:
    """
    Run post-review validation to catch issues outside directly changed code.

    Args:
        pre_review_report: Report from pre-review analysis
        ai_review_findings: Findings from the AI review
        gitlab_session: GitLab MCP session
        nexus_session: Optional GitNexus MCP session for advanced validation

    Returns:
        Additional findings discovered during validation
    """
    analyzer = GitImpactAnalyzer(nexus_session=nexus_session)

    validation_findings = await analyzer.post_review_validation(
        report=pre_review_report,
        review_findings=ai_review_findings,
        gitlab_session=gitlab_session
    )

    return validation_findings
