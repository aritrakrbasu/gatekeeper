# Impact Analysis & Atomic Patches Documentation

This document describes the impact analysis and atomic patch features added to The Gatekeeper.

## Overview

The Gatekeeper now includes two powerful analysis capabilities:

1. **Atomic Unified Diff Patches** - Parse diffs into granular, independently applicable hunk-level patches
2. **Impact Analysis** - Identify code affected by changes beyond the directly modified files

## Features

### 1. Atomic Patches

**Purpose**: Enable granular, reversible code changes at the hunk level.

**Capabilities**:

- Parse unified diffs into atomic hunk-level patches
- Each hunk is independently applicable and revertible
- Track patch metadata and dependencies
- Generate unified diffs from atomic patches

**Components**:

- `atomic_patches.py` - Core atomic patch module
- `AtomicPatchParser` - Parse unified diffs into hunks
- `AtomicPatchManager` - Manage, apply, and revert patches
- `DiffHunk` - Dataclass representing a single atomic change
- `AtomicPatch` - Collection of related hunks forming a logical unit

**Example Usage**:

```python
from atomic_patches import AtomicPatchParser, create_patch_summary

parser = AtomicPatchParser(context_lines=3)
patches = parser.parse_unified_diff(diff_text)

# Get a human-readable summary
summary = create_patch_summary(patches)
print(summary)

# Access individual hunks
for patch in patches:
    for hunk in patch.hunks:
        print(f"Hunk {hunk.hunk_id}: {hunk.file_path}:{hunk.old_start}")
```

### 2. Impact Analysis

**Purpose**: Identify potential ripple effects from code changes before and after review.

**Pre-Review Analysis** (runs before AI review):

- Identifies dependencies and call chains
- Detects API/interface changes
- Tracks configuration changes
- Analyzes test coverage impact

**Post-Review Validation** (runs after AI review):

- Validates findings against actual code impact
- Catches issues outside directly changed code
- Correlates AI findings with impact scope

**Components**:

- `impact_analysis.py` - Core impact analysis module
- `GitImpactAnalyzer` - Main analysis engine
- `PythonCodeAnalyzer` - Python-specific code analysis
- `GitNexusWrapper` - Wrapper for external git-nexus tool
- `ImpactReport` - Structured impact findings

**Impact Levels**:

- 🔴 **CRITICAL** - Breaking changes that will definitely cause issues
- 🟠 **HIGH** - Likely to cause issues
- 🟡 **MEDIUM** - May cause issues in certain scenarios
- 🟢 **LOW** - Unlikely to cause issues
- ℹ️ **INFO** - Informational only

**Example Usage**:

```python
from impact_analysis import run_pre_review_analysis

report, context = await run_pre_review_analysis(
    project_id="123",
    mr_iid=42,
    source_branch="feature-branch",
    target_branch="main",
    changed_files=["src/main.py", "tests/test_main.py"],
    gitlab_session=gitlab_session
)

# Get findings by severity
critical_findings = report.get_findings_by_level(ImpactLevel.CRITICAL)

# Generate markdown report
markdown_report = report.to_markdown()
```

## Integration with Main Workflow

### Workflow Sequence

1. **Webhook Received** - GitLab MR webhook triggers analysis
2. **Diff Extraction** - Fetch MR diffs via GitLab MCP
3. **Atomic Patch Parsing** - Parse diffs into hunk-level patches
4. **Pre-Review Impact Analysis** - Identify affected code
5. **AI Review** - Gemini analyzes code with impact context
6. **Post-Review Validation** - Validate findings against impact
7. **Atomic Auto-Fix** - Create granular fixes at hunk level
8. **Reporting** - Post comprehensive review with impact data

### Auto-Fix with Atomic Patches

Instead of full file rewrites, auto-fix now creates atomic hunk-level patches:

```python
# Before: Full file replacement
fix_code = entire_file_content

# After: Atomic hunk fixes
{
  "fixes": [
    {
      "hunk_id": "hunk_abc123",
      "issue": "SQL injection vulnerability",
      "original_lines": ["query = f'SELECT * FROM users WHERE id={user_id}'"],
      "fixed_lines": ["query = 'SELECT * FROM users WHERE id=%s', [user_id]"]
    }
  ]
}
```

## Setup

### Initial Setup

Run the setup script:

```bash
python setup_impact_analysis.py
```

This will:

- Verify Python dependencies
- Check for git-nexus availability
- Create necessary directories
- Provide setup summary

### git-nexus Integration

The system supports git-nexus if available, but works with built-in analysis:

**Option 1: npm (if package exists)**

```bash
npm install -g git-nexus
```

**Option 2: cargo (if available)**

```bash
cargo install git-nexus
```

**Option 3: Built-in Analysis**

- No external dependency required
- Uses Python AST for code analysis
- Leverages git commands for change tracking

## API Reference

### AtomicPatchParser

```python
parser = AtomicPatchParser(context_lines=3)
patches = parser.parse_unified_diff(diff_text)
```

**Parameters**:

- `context_lines` (int): Number of context lines around hunks

**Returns**:

- `List[AtomicPatch]`: Parsed atomic patches

### GitImpactAnalyzer

```python
analyzer = GitImpactAnalyzer()
report = await analyzer.analyze_merge_request(
    project_id="123",
    merge_request_iid=42,
    source_branch="feature",
    target_branch="main",
    changed_files=["file1.py", "file2.py"],
    gitlab_session=session
)
```

**Returns**:

- `ImpactReport`: Complete impact analysis with findings

### ImpactReport

```python
# Get findings by level
critical = report.get_findings_by_level(ImpactLevel.CRITICAL)

# Get findings by type
api_changes = report.get_findings_by_type("api_change")

# Generate markdown
markdown = report.to_markdown()
```

## Storage

### Patch Metadata

Atomic patches are stored in `patches/` directory:

```
patches/
├── mr_42/
│   ├── patch_src_main_py_abc123.json
│   └── patch_src_utils_py_def456.json
```

Each patch file contains:

- Patch ID and description
- List of hunks with metadata
- Dependency information
- Revertibility flag

## Troubleshooting

### Impact Analysis Not Working

1. Check GitLab MCP session is active
2. Verify file permissions for reading repository
3. Check Python version is 3.8+
4. Review logs for specific error messages

### Atomic Patches Not Applying

1. Verify diff format is valid unified diff
2. Check line numbers match actual file content
3. Ensure branch is up to date
4. Review patch metadata in `patches/` directory

### git-nexus Not Found

This is expected if git-nexus is not available:

- System falls back to built-in analysis
- All features remain functional
- Consider installing git-nexus for enhanced analysis

## Future Enhancements

Potential improvements:

1. Support for more languages beyond Python
2. Machine learning for impact prediction
3. Integration with static analysis tools
4. Historical impact trend analysis
5. Automated test selection based on impact
6. Dependency graph visualization

## Contributing

When extending these modules:

1. Maintain backward compatibility
2. Add comprehensive error handling
3. Update documentation
4. Include examples in docstrings
5. Add tests for new features
