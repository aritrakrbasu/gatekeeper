#!/usr/bin/env python3
"""
Check MongoDB MCP installation and configuration.

This script helps diagnose MongoDB connectivity issues.
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_mongodb_mcp_installed():
    """Check if MongoDB MCP server is installed globally."""
    try:
        result = subprocess.run(
            ["npm", "list", "-g", "mongodb-mcp-server"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and "mongodb-mcp-server" in result.stdout:
            print("✅ MongoDB MCP server is installed globally")
            return True
        else:
            print("❌ MongoDB MCP server is NOT installed globally")
            return False
    except FileNotFoundError:
        print("❌ npm is not installed or not in PATH")
        return False
    except Exception as e:
        print(f"❌ Error checking MongoDB MCP: {e}")
        return False

def check_connection_string():
    """Check if MongoDB connection string is configured."""
    connection_string = os.getenv("MDB_MCP_CONNECTION_STRING", "")
    if connection_string:
        print(f"✅ MDB_MCP_CONNECTION_STRING is set")
        # Show partial connection string for security
        if len(connection_string) > 30:
            print(f"   {connection_string[:20]}...{connection_string[-10:]}")
        else:
            print(f"   Length: {len(connection_string)} characters")
        return True
    else:
        print("❌ MDB_MCP_CONNECTION_STRING is NOT set in .env file")
        print("\n📝 Add this to your .env file:")
        print("MDB_MCP_CONNECTION_STRING=mongodb+srv://username:password@cluster.mongodb.net/?appName=Cluster0")
        return False

def check_local_installation():
    """Check if MongoDB MCP is installed locally."""
    local_mcp = Path(__file__).parent.parent / "node_modules" / "mongodb-mcp-server"
    if local_mcp.exists():
        print(f"✅ MongoDB MCP found locally at: {local_mcp}")
        return True
    else:
        print(f"⚠️  MongoDB MCP not found locally")
        return False

def main():
    print("=" * 60)
    print("MongoDB MCP Configuration Check")
    print("=" * 60)
    print()

    checks = []

    # Check npm
    print("1. Checking npm installation...")
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        print(f"   ✅ npm version: {result.stdout.strip()}")
        checks.append(True)
    except:
        print("   ❌ npm not found")
        checks.append(False)
    print()

    # Check global installation
    print("2. Checking global MongoDB MCP installation...")
    checks.append(check_mongodb_mcp_installed())
    print()

    # Check local installation
    print("3. Checking local MongoDB MCP installation...")
    checks.append(check_local_installation())
    print()

    # Check connection string
    print("4. Checking MDB_MCP_CONNECTION_STRING...")
    checks.append(check_connection_string())
    print()

    # Summary
    print("=" * 60)
    if all(checks):
        print("✅ All checks passed! MongoDB MCP should work correctly.")
        print("\n🚀 Start the server with: python main.py")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("\n📝 Installation instructions:")
        if not checks[1]:  # Global installation failed
            print("   npm install -g mongodb-mcp-server")
        if not checks[2]:  # Local installation failed
            print("   npm install mongodb-mcp-server")
        if not checks[3]:  # Connection string missing
            print("   Add MDB_MCP_CONNECTION_STRING to .env file")
    print("=" * 60)

if __name__ == "__main__":
    main()
