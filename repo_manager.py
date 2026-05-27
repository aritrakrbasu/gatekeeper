"""
Repository Manager for Gatekeeper

Handles repository cloning, indexing, and management for GitNexus integration.

Priority Order:
1. Pre-indexed repositories (Option 2) - Check if already indexed
2. Auto-index on webhook (Option 1) - Clone and index if not found
"""

import os
import subprocess
import json
import base64
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field
import asyncio


@dataclass
class RepositoryConfig:
    """Configuration for a repository to monitor."""
    project_id: str
    gitlab_url: str
    branch: str = "main"
    private_token: Optional[str] = None
    auto_update: bool = True


class RepositoryManager:
    """
    Manages repository cloning, GitNexus indexing, and updates.
    """

    def __init__(self, workspace_path: Optional[Path] = None):
        """
        Initialize the repository manager.

        Args:
            workspace_path: Directory to store cloned repositories. Defaults to ./workspace/projects
        """
        self.workspace_path = workspace_path or (Path(__file__).parent / "workspace" / "projects")
        self.workspace_path.mkdir(parents=True, exist_ok=True)

        # Config file for pre-indexed repositories
        self.config_file = Path(__file__).parent / "config" / "repositories.json"
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        self.repositories: Dict[str, RepositoryConfig] = {}
        self._load_config()

    def _load_config(self):
        """Load repository configurations from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    for repo_id, repo_data in data.items():
                        self.repositories[repo_id] = RepositoryConfig(**repo_data)
                print(f"[+] Loaded {len(self.repositories)} repository configurations")
            except Exception as e:
                print(f"[⚠️] Failed to load repository config: {e}")
        else:
            print("[ℹ️] No repository config found - will use auto-index (Option 1)")
            self._create_default_config()

    def _create_default_config(self):
        """Create a default configuration file."""
        default_config = {
            "example_repository": {
                "project_id": "12345678",
                "gitlab_url": "https://gitlab.com/your-org/your-project",
                "branch": "main",
                "private_token": None,
                "auto_update": True
            }
        }
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        print(f"[+] Created default config at: {self.config_file}")

    def save_config(self):
        """Save current repository configurations to file."""
        data = {
            repo_id: {
                "project_id": repo.project_id,
                "gitlab_url": repo.gitlab_url,
                "branch": repo.branch,
                "private_token": repo.private_token,
                "auto_update": repo.auto_update
            }
            for repo_id, repo in self.repositories.items()
        }
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)

    def add_repository(self, repo_id: str, gitlab_url: str, branch: str = "main", private_token: Optional[str] = None):
        """Add a repository to the configuration."""
        self.repositories[repo_id] = RepositoryConfig(
            project_id=repo_id,
            gitlab_url=gitlab_url,
            branch=branch,
            private_token=private_token
        )
        self.save_config()
        print(f"[+] Added repository: {repo_id}")

    def get_local_path(self, project_id: str) -> Path:
        """Get the local path for a repository."""
        return self.workspace_path / f"project_{project_id}"

    def is_indexed(self, project_id: str) -> bool:
        """Check if a repository is already indexed by GitNexus."""
        local_path = self.get_local_path(project_id)
        gitnexus_dir = local_path / ".gitnexus"
        return gitnexus_dir.exists() and any(gitnexus_dir.iterdir())

    def is_cloned(self, project_id: str) -> bool:
        """Check if a repository is already cloned."""
        local_path = self.get_local_path(project_id)
        git_dir = local_path / ".git"
        exists = git_dir.exists()
        if not exists:
            # Debug: check if directory exists at all
            print(f"[DEBUG] is_cloned check failed for {project_id}")
            print(f"[DEBUG] local_path: {local_path}")
            print(f"[DEBUG] local_path exists: {local_path.exists()}")
            print(f"[DEBUG] git_dir: {git_dir}")
            print(f"[DEBUG] git_dir exists: {git_dir.exists()}")
            if local_path.exists():
                # List what's actually in the directory
                try:
                    contents = list(local_path.iterdir())
                    print(f"[DEBUG] Contents of local_path: {[f.name for f in contents]}")
                except Exception as e:
                    print(f"[DEBUG] Error listing directory: {e}")
        return exists

    async def clone_repository(self, project_id: str, gitlab_url: str, private_token: Optional[str] = None, gitlab_session=None) -> Path:
        """
        Clone a repository from GitLab.
        If gitlab_session is available, downloads files via GitLab MCP.
        Otherwise, falls back to standard git clone.

        Args:
            project_id: GitLab project ID
            gitlab_url: GitLab repository URL
            private_token: Optional GitLab personal access token
            gitlab_session: Active GitLab MCP session for downloading files

        Returns:
            Path to the cloned repository
        """
        local_path = self.get_local_path(project_id)

        # Fallback to standard git clone if no GitLab MCP session is provided
        if gitlab_session is None:
            print(f"[*] Cloning repository {project_id} via git clone...")
            clone_url = gitlab_url
            if private_token:
                if gitlab_url.startswith("https://"):
                    clone_url = gitlab_url.replace("https://", f"https://oauth2:{private_token}@")
            
            try:
                if local_path.exists():
                    import shutil
                    shutil.rmtree(local_path)
                
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "clone", clone_url, str(local_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                print(f"[✅] Repository {project_id} cloned successfully via git clone")
                return local_path
            except subprocess.CalledProcessError as e:
                print(f"[❌] Failed to clone via git clone: {e.stderr}")
                raise Exception(f"Git clone failed: {e.stderr}")
            except Exception as e:
                print(f"[❌] Failed to clone via git clone: {e}")
                raise

        print(f"[*] Downloading repository {project_id} files via GitLab MCP...")

        try:

            # Create the directory structure
            local_path.mkdir(parents=True, exist_ok=True)

            # Get repository files using GitLab MCP
            print(f"[*] Fetching repository tree...")
            
            files_to_download = []
            page_token = None
            import json

            while True:
                arguments = {
                    "project_id": str(project_id),
                    "recursive": True,
                }
                if page_token:
                    arguments["page_token"] = page_token
                    arguments["pagination"] = "keyset"

                tree_result = await gitlab_session.call_tool(
                    name="get_repository_tree",
                    arguments=arguments
                )

                if not (hasattr(tree_result, 'content') and tree_result.content):
                    break

                tree_data = json.loads(tree_result.content[0].text)
                
                items = tree_data
                next_token = None
                if isinstance(tree_data, dict):
                    items = tree_data.get("items", [])
                    next_token = tree_data.get("next_page_token")

                if isinstance(items, list):
                    for item in items:
                        if item.get("type") == "blob":
                            files_to_download.append(item["path"])

                if next_token:
                    page_token = next_token
                else:
                    break

            print(f"[*] Found {len(files_to_download)} files to download")

            # Download each file
            for i, file_path in enumerate(files_to_download):
                if i % 50 == 0:
                    print(f"[*] Downloading file {i+1}/{len(files_to_download)}...")

                try:
                    file_result = await gitlab_session.call_tool(
                        name="get_file_contents",
                        arguments={
                            "project_id": str(project_id),
                            "file_path": file_path,
                        }
                    )

                    if hasattr(file_result, 'content') and file_result.content:
                        file_data = json.loads(file_result.content[0].text)
                        content = file_data.get("content", "")

                        # Decode base64 content if needed
                        if file_data.get("encoding") == "base64":
                            import base64

                            # Fix base64 padding - GitLab sometimes returns improperly padded base64
                            padding_needed = (4 - len(content) % 4) % 4
                            if padding_needed:
                                content += '=' * padding_needed

                            # Handle URL-safe base64 encoding
                            content = content.replace('-', '+').replace('_', '/')

                            content = base64.b64decode(content).decode('utf-8', errors='replace')

                        # Write file to disk
                        full_path = local_path / file_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_text(content, encoding='utf-8')

                except Exception as e:
                    print(f"[⚠️] Failed to download {file_path}: {e}")

            # Create .git marker for is_cloned() check
            (local_path / ".git").mkdir(exist_ok=True)

            print(f"[✅] Repository {project_id} downloaded successfully ({len(files_to_download)} files)")
            return local_path
        except subprocess.TimeoutExpired:
            print(f"[⚠️] Clone timeout for {project_id}")
            raise
        except Exception as e:
            print(f"[❌] Failed to clone {project_id}: {e}")
            # Show git stderr if available
            if isinstance(e, subprocess.CalledProcessError):
                print(f"[❌] Git stderr: {e.stderr}")
            raise

    async def update_repository(self, project_id: str) -> bool:
        """
        Update a cloned repository with latest changes.

        Args:
            project_id: GitLab project ID

        Returns:
            True if successful, False otherwise
        """
        local_path = self.get_local_path(project_id)

        if not self.is_cloned(project_id):
            print(f"[⚠️] Repository {project_id} not cloned, cannot update")
            return False

        print(f"[*] Updating repository {project_id}...")

        try:
            # Fetch latest changes
            await asyncio.to_thread(
                subprocess.run,
                ["git", "fetch", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=local_path
            )

            # Reset to origin/main (or configured branch)
            await asyncio.to_thread(
                subprocess.run,
                ["git", "reset", "--hard", "origin/main"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=local_path
            )

            print(f"[✅] Repository {project_id} updated")
            return True
        except Exception as e:
            print(f"[⚠️] Failed to update {project_id}: {e}")
            return False

    async def index_with_gitnexus(self, project_id: str, force: bool = False) -> bool:
        """
        Index a repository with GitNexus.

        Args:
            project_id: GitLab project ID
            force: Force re-index even if already indexed

        Returns:
            True if successful, False otherwise
        """
        local_path = self.get_local_path(project_id)

        if not self.is_cloned(project_id):
            print(f"[⚠️] Repository {project_id} not cloned, cannot index")
            return False

        if not force and self.is_indexed(project_id):
            print(f"[ℹ️] Repository {project_id} already indexed")
            return True

        print(f"[*] Indexing repository {project_id} with GitNexus...")
        print("[ℹ️] This may take 1-5 minutes depending on repository size...")

        # Determine path to local binary
        root_dir = Path(__file__).parent
        local_bin = root_dir / "node_modules" / ".bin"
        import platform
        if platform.system() == "Windows":
            local_gitnexus = local_bin / "gitnexus.cmd"
            cmd = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus.cmd"
        else:
            local_gitnexus = local_bin / "gitnexus"
            cmd = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus"

        try:
            # Run gitnexus analyze
            result = await asyncio.to_thread(
                subprocess.run,
                [cmd, "analyze"],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout for large repos
                cwd=local_path
            )

            if result.returncode == 0:
                print(f"[✅] Repository {project_id} indexed successfully")
                return True
            else:
                print(f"[⚠️] GitNexus indexing failed for {project_id}")
                print(f"[⚠️] Error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"[⚠️] GitNexus indexing timeout for {project_id}")
            return False
        except FileNotFoundError:
            print(f"[⚠️] GitNexus not found - skipping indexing")
            print("[ℹ️] Install with: npm install -g gitnexus")
            return False
        except Exception as e:
            print(f"[❌] Failed to index {project_id}: {e}")
            return False

    async def ensure_repository_ready(self, project_id: str, gitlab_url: str, private_token: Optional[str] = None, gitlab_session=None) -> Optional[Path]:
        """
        Ensure a repository is cloned and indexed (Priority: Option 2 → Option 1).

        This is the main entry point that combines both options:
        1. First checks if repository is pre-indexed (Option 2)
        2. Falls back to clone and index (Option 1)

        Args:
            project_id: GitLab project ID
            gitlab_url: GitLab repository URL
            private_token: Optional GitLab personal access token

        Returns:
            Path to the repository if ready, None otherwise
        """
        local_path = self.get_local_path(project_id)

        # Option 2: Check if pre-indexed (Priority)
        if self.is_indexed(project_id):
            print(f"[✅] Repository {project_id} found pre-indexed (Option 2)")
            # Update if auto_update is enabled
            if project_id in self.repositories and self.repositories[project_id].auto_update:
                await self.update_repository(project_id)
            return local_path

        # Option 2a: Cloned but not indexed
        if self.is_cloned(project_id):
            print(f"[ℹ️] Repository {project_id} cloned but not indexed")
            if await self.index_with_gitnexus(project_id):
                return local_path
            return None

        # Option 1: Clone and index (Fallback)
        print(f"[ℹ️] Repository {project_id} not found, using auto-index (Option 1)")

        try:
            # Clone the repository using GitLab MCP
            await self.clone_repository(project_id, gitlab_url, private_token, gitlab_session)

            # Index with GitNexus
            if await self.index_with_gitnexus(project_id):
                # Save to config for future use
                self.add_repository(str(project_id), gitlab_url)
                return local_path

            return None

        except Exception as e:
            print(f"[❌] Failed to prepare repository {project_id}: {e}")
            return None

    async def pre_index_repositories(self) -> Dict[str, bool]:
        """
        Pre-index all configured repositories (Option 2 setup).

        Returns:
            Dict mapping project_id to success status
        """
        print(f"[*] Pre-indexing {len(self.repositories)} configured repositories...")
        print("[*] This may take several minutes for large repositories...")

        results = {}

        for repo_id, repo_config in self.repositories.items():
            print(f"\n[*] Processing {repo_id}...")

            try:
                # Clone if needed
                if not self.is_cloned(repo_config.project_id):
                    await self.clone_repository(
                        repo_config.project_id,
                        repo_config.gitlab_url,
                        repo_config.private_token
                    )

                # Index with GitNexus
                success = await self.index_with_gitnexus(repo_config.project_id)
                results[repo_id] = success

                if success:
                    print(f"[✅] {repo_id} ready")
                else:
                    print(f"[⚠️] {repo_id} failed")

            except Exception as e:
                print(f"[❌] {repo_id} error: {e}")
                results[repo_id] = False

        # Summary
        successful = sum(1 for v in results.values() if v)
        print(f"\n[+] Pre-indexing complete: {successful}/{len(results)} repositories ready")

        return results

    def get_status(self) -> Dict[str, Dict[str, any]]:
        """Get status of all repositories."""
        status = {}

        for repo_id, repo_config in self.repositories.items():
            local_path = self.get_local_path(repo_config.project_id)
            status[repo_id] = {
                "project_id": repo_config.project_id,
                "gitlab_url": repo_config.gitlab_url,
                "cloned": self.is_cloned(repo_config.project_id),
                "indexed": self.is_indexed(repo_config.project_id),
                "local_path": str(local_path) if local_path.exists() else None
            }

        return status


# Singleton instance for use across the application
_repo_manager: Optional[RepositoryManager] = None


def get_repo_manager() -> RepositoryManager:
    """Get the singleton repository manager instance."""
    global _repo_manager
    if _repo_manager is None:
        _repo_manager = RepositoryManager()
    return _repo_manager
