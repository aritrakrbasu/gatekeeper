#!/usr/bin/env python3
"""
Repository Setup Script for Gatekeeper (Option 2: Pre-Index)

This script helps you pre-index repositories for faster Gatekeeper analysis.

Usage:
    python setup_repos.py                    # Interactive setup
    python setup_repos.py --add <project_id> <url>    # Add a repository
    python setup_repos.py --list             # List all repositories
    python setup_repos.py --index            # Pre-index all repositories
    python setup_repos.py --status           # Show repository status
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from repo_manager import RepositoryManager, get_repo_manager


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_repo_table(status: dict):
    """Print repositories in a table format."""
    if not status:
        print("[ℹ️] No repositories configured")
        return

    print(f"{'Repository ID':<25} {'Project ID':<12} {'Cloned':<8} {'Indexed':<8}")
    print("-" * 65)

    for repo_id, info in status.items():
        cloned = "✅" if info['cloned'] else "❌"
        indexed = "✅" if info['indexed'] else "❌"
        print(f"{repo_id:<25} {info['project_id']:<12} {cloned:<8} {indexed:<8}")


async def cmd_add(args):
    """Add a new repository to configuration."""
    manager = get_repo_manager()

    print_header("Adding Repository")

    project_id = args.project_id
    gitlab_url = args.url
    branch = args.branch or "main"
    private_token = args.token

    # Only prompt for input if arguments were not provided via CLI
    if not project_id:
        project_id = input("GitLab Project ID: ").strip()
    if not gitlab_url:
        gitlab_url = input("GitLab Repository URL: ").strip()
    if not args.token and not args.project_id:
        private_token = input("Private Token (optional, press Enter to skip): ").strip() or None

    if not project_id or not gitlab_url:
        print("[❌] Project ID and URL are required")
        return 1

    manager.add_repository(project_id, gitlab_url, branch, private_token)

    # Ask if user wants to clone and index now (only if not specified in CLI)
    should_index = args.index
    if not should_index and not args.project_id:
        should_index = input("\nClone and index now? (y/N): ").strip().lower() == 'y'

    if should_index:
        print("\n[*] Cloning and indexing repository...")
        result = await manager.ensure_repository_ready(project_id, gitlab_url, private_token)
        if result:
            print(f"[✅] Repository {project_id} is ready!")
        else:
            print(f"[⚠️] Repository {project_id} setup incomplete")

    return 0


async def cmd_list(args):
    """List all configured repositories."""
    manager = get_repo_manager()

    print_header("Configured Repositories")
    print_repo_table(manager.get_status())

    return 0


async def cmd_index(args):
    """Pre-index all configured repositories (Option 2)."""
    manager = get_repo_manager()

    if not manager.repositories:
        print("[ℹ️] No repositories configured. Add one with --add first.")
        return 1

    print_header("Pre-Indexing Repositories (Option 2)")
    print("[ℹ️] This will clone and index all configured repositories")
    print("[ℹ️] Press Ctrl+C to cancel if needed\n")

    # Confirm if not forced
    if not args.force:
        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm != 'y':
            print("[ℹ️] Cancelled")
            return 0

    results = await manager.pre_index_repositories()

    print_header("Indexing Results")
    for repo_id, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"{repo_id}: {status}")

    return 0


async def cmd_status(args):
    """Show detailed status of repositories."""
    manager = get_repo_manager()

    print_header("Repository Status")

    if args.project_id:
        # Show specific repository
        status = manager.get_status()
        if args.project_id not in status:
            print(f"[❌] Repository {args.project_id} not found")
            return 1

        info = status[args.project_id]
        print(f"Repository: {args.project_id}")
        print(f"Project ID: {info['project_id']}")
        print(f"GitLab URL: {info['gitlab_url']}")
        print(f"Local Path: {info['local_path']}")
        print(f"Cloned: {'Yes' if info['cloned'] else 'No'}")
        print(f"Indexed: {'Yes' if info['indexed'] else 'No'}")
    else:
        # Show all repositories
        print_repo_table(manager.get_status())

    return 0


async def cmd_remove(args):
    """Remove a repository from configuration."""
    manager = get_repo_manager()

    if args.project_id not in manager.repositories:
        print(f"[❌] Repository {args.project_id} not found")
        return 1

    print(f"[*] Removing repository {args.project_id}...")

    # Remove from config
    del manager.repositories[args.project_id]
    manager.save_config()

    # Ask if user wants to delete local files
    local_path = manager.get_local_path(args.project_id)
    if local_path.exists():
        if args.force or input(f"Delete local files at {local_path}? (y/N): ").strip().lower() == 'y':
            import shutil
            shutil.rmtree(local_path)
            print(f"[✅] Deleted local files")

    print(f"[✅] Repository {args.project_id} removed")

    return 0


async def main():
    parser = argparse.ArgumentParser(
        description="Gatekeeper Repository Manager (Option 2: Pre-Index)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup_repos.py                           # Interactive mode
  python setup_repos.py --add my-project https://gitlab.com/user/repo
  python setup_repos.py --list                    # List all repos
  python setup_repos.py --index                   # Pre-index all repos
  python setup_repos.py --status                  # Show status
  python setup_repos.py --remove my-project       # Remove a repo
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add a repository')
    add_parser.add_argument('project_id', nargs='?', help='GitLab Project ID')
    add_parser.add_argument('url', nargs='?', help='GitLab Repository URL')
    add_parser.add_argument('--branch', default='main', help='Branch name (default: main)')
    add_parser.add_argument('--token', help='Private access token for private repos')
    add_parser.add_argument('--index', action='store_true', help='Clone and index immediately')

    # List command
    list_parser = subparsers.add_parser('list', help='List all repositories')

    # Index command
    index_parser = subparsers.add_parser('index', help='Pre-index all repositories')
    index_parser.add_argument('--force', action='store_true', help='Skip confirmation')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show repository status')
    status_parser.add_argument('project_id', nargs='?', help='Specific repository ID')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a repository')
    remove_parser.add_argument('project_id', help='Repository ID to remove')
    remove_parser.add_argument('--force', action='store_true', help='Skip confirmation')

    args = parser.parse_args()

    if not args.command:
        # Interactive mode
        print_header("Gatekeeper Repository Manager")
        print("No command specified. Use --help for usage information.")
        print("\nQuick start:")
        print("1. Add a repository: python setup_repos.py add <project_id> <url>")
        print("2. Pre-index: python setup_repos.py index")
        print("3. Check status: python setup_repos.py status")
        return 0

    # Execute command
    commands = {
        'add': cmd_add,
        'list': cmd_list,
        'index': cmd_index,
        'status': cmd_status,
        'remove': cmd_remove
    }

    if args.command in commands:
        return await commands[args.command](args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
