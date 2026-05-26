"""
Setup script for Impact Analysis Tools

This script helps set up the necessary dependencies for impact analysis,
including git-nexus (if available) or falls back to built-in analysis.
"""

import subprocess
import sys
import platform
from pathlib import Path


def check_python_version():
    """Check Python version compatibility."""
    if sys.version_info < (3, 8):
        print("[❌] Python 3.8+ is required for impact analysis features")
        return False
    print(f"[✅] Python version: {sys.version}")
    return True


def install_npm_nexus():
    """
    Attempt to install git-nexus via npm.

    GitNexus is available on npm as 'gitnexus'.
    Installation: npm install -g gitnexus
    """
    print("\n[*] Checking for npm...")

    try:
        result = subprocess.run(
            ['npm', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"[✅] npm version: {result.stdout.strip()}")

            # Check if gitnexus is already installed
            check_result = subprocess.run(
                ['npm', 'list', '-g', 'gitnexus'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if check_result.returncode == 0 and 'gitnexus' in check_result.stdout:
                print("[✅] gitnexus is already installed globally")
                return True

            print("\n[*] Installing gitnexus via npm...")
            print("[ℹ️] Package: gitnexus (from https://github.com/abhigyanpatwari/GitNexus)")
            print("[ℹ️] This may take a minute...")

            # Install gitnexus
            install_result = subprocess.run(
                ['npm', 'install', '-g', 'gitnexus'],
                capture_output=True,
                text=True,
                timeout=120  # 2 minutes timeout
            )

            if install_result.returncode == 0:
                print("[✅] gitnexus installed successfully via npm")
                print("[ℹ️] GitNexus MCP server will be available on next start")
                return True
            else:
                print("[⚠️] gitnexus installation failed")
                print(f"[ℹ️] Error: {install_result.stderr}")
                print("[ℹ️] Built-in impact analysis will be used as fallback")
                return False

    except FileNotFoundError:
        print("[⚠️] npm not found - git-nexus features will use built-in analysis")
        return False
    except subprocess.TimeoutExpired:
        print("[⚠️] npm install timed out - you can install manually: npm install -g gitnexus")
        return False
    except Exception as e:
        print(f"[⚠️] Error checking/installing npm: {e}")
        return False


def check_nexus_installation():
    """Check if gitnexus is installed and working."""
    print("\n[*] Checking gitnexus installation...")

    # Determine path to local binary
    root_dir = Path(__file__).parent
    local_bin = root_dir / "node_modules" / ".bin"
    if platform.system() == "Windows":
        local_gitnexus = local_bin / "gitnexus.cmd"
        cmd = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus.cmd"
    else:
        local_gitnexus = local_bin / "gitnexus"
        cmd = str(local_gitnexus) if local_gitnexus.exists() else "gitnexus"

    try:
        # Try running gitnexus --version
        result = subprocess.run(
            [cmd, '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            print(f"[✅] gitnexus found: {result.stdout.strip()}")
            return True
        else:
            print("[ℹ️] gitnexus not found or not working")
            return False

    except FileNotFoundError:
        print("[ℹ️] gitnexus command not found in PATH")
        print("[ℹ️] Install with: npm install -g gitnexus")
        return False
    except Exception as e:
        print(f"[⚠️] Error checking gitnexus: {e}")
        return False


def create_patches_directory():
    """Create directory for storing atomic patch metadata."""
    patches_dir = Path(__file__).parent / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    print(f"[✅] Created patches directory: {patches_dir}")
    return patches_dir


def verify_dependencies():
    """Verify Python dependencies are installed."""
    print("\n[*] Verifying Python dependencies...")

    required_modules = ['ast', 'asyncio', 'json', 're', 'pathlib', 'dataclasses']
    missing = []

    for module in required_modules:
        try:
            __import__(module)
            print(f"  [✅] {module}")
        except ImportError:
            missing.append(module)
            print(f"  [❌] {module}")

    if missing:
        print(f"\n[❌] Missing modules: {missing}")
        return False

    print("[✅] All required Python modules available")
    return True


def main():
    """Run the setup process."""
    print("=" * 60)
    print("Gatekeeper Impact Analysis Setup")
    print("=" * 60)

    success = True

    # Check Python version
    if not check_python_version():
        success = False

    # Check Python dependencies
    if not verify_dependencies():
        success = False

    # Try npm installation
    npm_available = install_npm_nexus()

    # Check if gitnexus is working
    nexus_working = check_nexus_installation()

    # Create necessary directories
    create_patches_directory()

    # Summary
    print("\n" + "=" * 60)
    print("Setup Summary")
    print("=" * 60)

    if success:
        print("[✅] Basic setup complete!")

        if nexus_working:
            print("[✅] GitNexus integration available via MCP")
            print("[ℹ️] GitNexus provides:")
            print("    - Blast radius analysis (impact tool)")
            print("    - Git-diff impact detection")
            print("    - 360-degree symbol context")
            print("    - Process-grouped search")
        else:
            print("[ℹ️] Using built-in impact analysis (GitNexus not installed)")
            print("[ℹ️] Built-in analysis includes:")
            print("    - Dependency tracking via AST")
            print("    - API change detection")
            print("    - Configuration change tracking")
            print("    - Test coverage impact analysis")
            print("\n[ℹ️] To install GitNexus: npm install -g gitnexus")

        print("\n[✅] Impact analysis features are ready to use!")
        return 0
    else:
        print("[❌] Setup incomplete - please fix the errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
