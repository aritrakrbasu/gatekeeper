"""
Atomic Unified Diff Patch Module

This module provides functionality to parse unified diffs into atomic hunk-level patches
that can be independently applied and reverted. Each hunk represents a minimal,
self-contained change unit.
"""

import re
import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from pathlib import Path


@dataclass
class DiffHunk:
    """
    Represents a single atomic hunk from a unified diff.

    A hunk is a contiguous section of changes that can be applied independently.
    """
    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    lines: List[str]  # The actual diff lines (starting with +, -, or space)
    hunk_id: str = field(init=False)
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Generate a unique ID for this hunk based on its content."""
        content_hash = hashlib.sha256(
            f"{self.file_path}:{self.old_start}:{self.new_start}:{''.join(self.lines)}".encode()
        ).hexdigest()[:16]
        self.hunk_id = f"hunk_{content_hash}"

    def to_dict(self) -> dict:
        """Convert hunk to dictionary for serialization."""
        return {
            "hunk_id": self.hunk_id,
            "file_path": self.file_path,
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "header": self.header,
            "lines": self.lines,
            "context_before": self.context_before,
            "context_after": self.context_after
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DiffHunk':
        """Create hunk from dictionary."""
        hunk = cls(
            file_path=data["file_path"],
            old_start=data["old_start"],
            old_count=data["old_count"],
            new_start=data["new_start"],
            new_count=data["new_count"],
            header=data["header"],
            lines=data["lines"],
            context_before=data.get("context_before", []),
            context_after=data.get("context_after", [])
        )
        hunk.hunk_id = data["hunk_id"]
        return hunk


@dataclass
class AtomicPatch:
    """
    A collection of related hunks that form a logical change unit.

    Patches can span multiple files and hunks, allowing for semantic grouping.
    """
    patch_id: str
    description: str
    hunks: List[DiffHunk] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # IDs of patches this depends on
    revertible: bool = True

    def add_hunk(self, hunk: DiffHunk):
        """Add a hunk to this patch."""
        self.hunks.append(hunk)

    def to_dict(self) -> dict:
        """Convert patch to dictionary for serialization."""
        return {
            "patch_id": self.patch_id,
            "description": self.description,
            "hunks": [h.to_dict() for h in self.hunks],
            "metadata": self.metadata,
            "dependencies": self.dependencies,
            "revertible": self.revertible
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AtomicPatch':
        """Create patch from dictionary."""
        patch = cls(
            patch_id=data["patch_id"],
            description=data["description"],
            metadata=data.get("metadata", {}),
            dependencies=data.get("dependencies", []),
            revertible=data.get("revertible", True)
        )
        patch.hunks = [DiffHunk.from_dict(h) for h in data.get("hunks", [])]
        return patch


class AtomicPatchParser:
    """
    Parser for unified diffs into atomic hunk-level patches.
    """

    # Regex patterns for unified diff parsing
    HUNK_HEADER_RE = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@')
    FILE_HEADER_RE = re.compile(r'^diff --git a/(.+?) b/(.+)$')
    INDEX_HEADER_RE = re.compile(r'^index [a-f0-9]+\.\.[a-f0-9]+(?:\s+(\d+))?$')
    NEW_FILE_RE = re.compile(r'^new file mode \d+$')
    DELETED_FILE_RE = re.compile(r'^deleted file mode \d+$')

    def __init__(self, context_lines: int = 3):
        """
        Initialize the parser.

        Args:
            context_lines: Number of context lines to preserve around each hunk
        """
        self.context_lines = context_lines

    def parse_unified_diff(self, diff_text: str) -> List[AtomicPatch]:
        """
        Parse a unified diff into atomic patches.

        Args:
            diff_text: The unified diff text to parse

        Returns:
            List of AtomicPatch objects, each containing one or more hunks
        """
        if not diff_text:
            return []

        lines = diff_text.split('\n')
        patches = []
        current_file = None
        current_hunks = []
        i = 0
        max_iterations = len(lines) * 2  # Safeguard against infinite loops
        iterations = 0

        while i < len(lines) and iterations < max_iterations:
            iterations += 1
            line = lines[i]

            # Check for file header
            file_match = self.FILE_HEADER_RE.match(line)
            if file_match:
                # Save previous file's hunks as a patch if any
                if current_file and current_hunks:
                    patches.append(self._create_file_patch(current_file, current_hunks))
                    current_hunks = []

                current_file = file_match.group(2)  # Get the new file path
                i += 1
                continue

            # Check for hunk header
            hunk_match = self.HUNK_HEADER_RE.match(line)
            if hunk_match and current_file:
                try:
                    hunk = self._parse_hunk(lines, i, current_file)
                    if hunk:
                        current_hunks.append(hunk)
                except Exception as e:
                    print(f"[⚠️] Error parsing hunk at line {i}: {e}")

                # Move past the hunk header
                i += 1
                # Skip to end of this hunk or next file/hunk
                while i < len(lines) and not lines[i].startswith('@@') and not lines[i].startswith('diff'):
                    i += 1
                continue

            i += 1

        if iterations >= max_iterations:
            print(f"[⚠️] Parser hit max iterations safeguard - possible infinite loop")

        # Don't forget the last file
        if current_file and current_hunks:
            patches.append(self._create_file_patch(current_file, current_hunks))

        return patches

    def _parse_hunk(self, lines: List[str], start_idx: int, file_path: str) -> Optional[DiffHunk]:
        """Parse a single hunk starting at the given index."""
        header_line = lines[start_idx]
        match = self.HUNK_HEADER_RE.match(header_line)

        if not match:
            return None

        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) else 1

        hunk_lines = []
        context_before = []
        context_after = []
        i = start_idx + 1
        max_iterations = abs(old_count + new_count) * 10 + 1000  # Reasonable limit
        iterations = 0

        # Parse hunk content
        while i < len(lines) and iterations < max_iterations:
            iterations += 1
            line = lines[i]

            # End of hunk
            if line.startswith('@@') or line.startswith('diff') or line.startswith('index'):
                break

            # Collect lines
            if line.startswith('+') or line.startswith('-') or line.startswith(' '):
                hunk_lines.append(line)
            elif line.strip() == '\\ No newline at end of file':
                pass  # Ignore this marker
            else:
                # Context line outside the main hunk
                if not hunk_lines:
                    context_before.append(line)
                else:
                    context_after.append(line)

            i += 1

        if iterations >= max_iterations:
            print(f"[⚠️] Hunk parser hit max iterations safeguard at line {start_idx}")

        return DiffHunk(
            file_path=file_path,
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            header=header_line,
            lines=hunk_lines,
            context_before=context_before,
            context_after=context_after
        )

    def _create_file_patch(self, file_path: str, hunks: List[DiffHunk]) -> AtomicPatch:
        """Create an atomic patch for a single file's changes."""
        patch_id = f"patch_{file_path.replace('/', '_').replace('.', '_')}_{len(hunks)}"
        return AtomicPatch(
            patch_id=patch_id,
            description=f"Changes to {file_path} ({len(hunks)} hunk(s))",
            hunks=hunks,
            metadata={"file_path": file_path, "hunk_count": len(hunks)}
        )


class AtomicPatchManager:
    """
    Manages atomic patches with apply, revert, and query capabilities.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the patch manager.

        Args:
            storage_path: Path to store patch metadata. If None, uses in-memory only.
        """
        self.storage_path = storage_path
        self.patches: Dict[str, AtomicPatch] = {}
        self.applied_patches: Dict[str, List[str]] = {}  # project_id -> list of patch_ids

        if storage_path:
            storage_path.mkdir(parents=True, exist_ok=True)
            self._load_state()

    def add_patches(self, project_id: str, patches: List[AtomicPatch]):
        """Register patches for a project."""
        if project_id not in self.applied_patches:
            self.applied_patches[project_id] = []

        for patch in patches:
            self.patches[patch.patch_id] = patch
            self._save_patch(patch)

    def get_patch(self, patch_id: str) -> Optional[AtomicPatch]:
        """Retrieve a patch by ID."""
        return self.patches.get(patch_id)

    def get_patches_for_project(self, project_id: str) -> List[AtomicPatch]:
        """Get all patches for a project."""
        patch_ids = self.applied_patches.get(project_id, [])
        return [self.patches[pid] for pid in patch_ids if pid in self.patches]

    def create_revert_patch(self, patch_id: str) -> Optional[AtomicPatch]:
        """
        Create a patch that reverts the specified patch.

        Args:
            patch_id: ID of the patch to revert

        Returns:
            A new AtomicPatch that reverts the original, or None if patch not found
        """
        original = self.get_patch(patch_id)
        if not original:
            return None

        revert_hunks = []
        for hunk in original.hunks:
            # Reverse the lines: + becomes -, - becomes +
            reversed_lines = []
            for line in hunk.lines:
                if line.startswith('+'):
                    reversed_lines.append('-' + line[1:])
                elif line.startswith('-'):
                    reversed_lines.append('+' + line[1:])
                else:
                    reversed_lines.append(line)  # Context lines stay the same

            revert_hunks.append(DiffHunk(
                file_path=hunk.file_path,
                old_start=hunk.new_start,  # Swap old/new for revert
                old_count=hunk.new_count,
                new_start=hunk.old_start,
                new_count=hunk.old_count,
                header=f"@@ -{hunk.new_start},{hunk.new_count} +{hunk.old_start},{hunk.old_count} @@",
                lines=reversed_lines,
                context_before=hunk.context_after,  # Swap contexts too
                context_after=hunk.context_before
            ))

        revert_patch = AtomicPatch(
            patch_id=f"revert_{patch_id}",
            description=f"Revert: {original.description}",
            hunks=revert_hunks,
            metadata={"revert_of": patch_id},
            dependencies=[patch_id]
        )

        return revert_patch

    def generate_unified_diff(self, patch: AtomicPatch) -> str:
        """
        Generate a unified diff string from an AtomicPatch.

        Args:
            patch: The patch to convert

        Returns:
            A unified diff format string
        """
        lines = []

        for hunk in patch.hunks:
            # File header
            lines.append(f"diff --git a/{hunk.file_path} b/{hunk.file_path}")

            # Hunk header
            old_count = hunk.old_count if hunk.old_count > 0 else 1
            new_count = hunk.new_count if hunk.new_count > 0 else 1
            lines.append(f"@@ -{hunk.old_start},{old_count} +{hunk.new_start},{new_count} @@ {hunk.header.split('@@', 1)[1].strip() if '@@' in hunk.header else ''}")

            # Context before
            for ctx_line in hunk.context_before:
                lines.append(f" {ctx_line}")

            # Hunk content
            for line in hunk.lines:
                lines.append(line)

            # Context after
            for ctx_line in hunk.context_after:
                lines.append(f" {ctx_line}")

            lines.append("")  # Blank line between hunks

        return '\n'.join(lines)

    def _save_patch(self, patch: AtomicPatch):
        """Save patch metadata to storage."""
        if not self.storage_path:
            return

        patch_file = self.storage_path / f"{patch.patch_id}.json"
        with open(patch_file, 'w') as f:
            json.dump(patch.to_dict(), f, indent=2)

    def _load_state(self):
        """Load patch metadata from storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        for patch_file in self.storage_path.glob("*.json"):
            try:
                with open(patch_file, 'r') as f:
                    data = json.load(f)
                    patch = AtomicPatch.from_dict(data)
                    self.patches[patch.patch_id] = patch
            except Exception as e:
                print(f"[⚠️] Failed to load patch from {patch_file}: {e}")


def extract_hunks_from_gitlab_diff(gitlab_diff_response: str) -> List[DiffHunk]:
    """
    Extract individual hunks from a GitLab diff response.

    This is a convenience function for working directly with GitLab MCP responses.

    Args:
        gitlab_diff_response: The raw diff content from GitLab

    Returns:
        List of DiffHunk objects
    """
    parser = AtomicPatchParser()
    patches = parser.parse_unified_diff(gitlab_diff_response)

    all_hunks = []
    for patch in patches:
        all_hunks.extend(patch.hunks)

    return all_hunks


# Convenience function for creating a summary of patches
def create_patch_summary(patches: List[AtomicPatch]) -> str:
    """Create a human-readable summary of patches."""
    if not patches:
        return "No patches found."

    lines = ["## Atomic Patch Summary", ""]
    lines.append(f"Total patches: {len(patches)}")
    lines.append(f"Total hunks: {sum(len(p.hunks) for p in patches)}")
    lines.append("")

    for i, patch in enumerate(patches, 1):
        lines.append(f"### Patch {i}: `{patch.patch_id}`")
        lines.append(f"**Description**: {patch.description}")
        lines.append(f"**Files**: {', '.join(set(h.file_path for h in patch.hunks))}")
        lines.append(f"**Hunks**: {len(patch.hunks)}")
        lines.append("")

        for j, hunk in enumerate(patch.hunks, 1):
            lines.append(f"  - Hunk {j}: `{hunk.hunk_id}`")
            lines.append(f"    Location: {hunk.file_path}:{hunk.old_start}->{hunk.new_start}")
            lines.append(f"    Changes: {len([l for l in hunk.lines if l.startswith('+')])} additions, "
                        f"{len([l for l in hunk.lines if l.startswith('-')])} deletions")
            lines.append(f"    Header: {hunk.header}")
            lines.append(f"    Content:")
            for line in hunk.lines[:10]:  # Show first 10 lines
                lines.append(f"      {line}")
            if len(hunk.lines) > 10:
                lines.append(f"      ... ({len(hunk.lines) - 10} more lines)")
            lines.append("")

        lines.append("")

    return '\n'.join(lines)
