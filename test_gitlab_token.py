"""
Quick test to verify GitLab token and MCP server connectivity.
"""
import asyncio
import os
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

async def test_gitlab_token():
    """Test if the GitLab token is valid."""
    # Use the new unencrypted test token
    token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    if not token:
        print("ERROR: No token available")
        return False

    print(f"Token found (length: {len(token)})")

    # Test token with a simple API call
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://gitlab.com/api/v4/user",
                headers={"PRIVATE-TOKEN": token}
            )
            if response.status_code == 200:
                user = response.json()
                print(f"OK: Token is valid for user: {user.get('username', 'unknown')}")
                return True
            else:
                print(f"ERROR: Token validation failed with status {response.status_code}")
                print(f"Response: {response.text[:200]}")
                return False
    except Exception as e:
        print(f"ERROR: Token validation request failed: {e}")
        return False


async def test_mcp_server_directly():
    """Test if the MCP server can start."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import Implementation

    # Use the new unencrypted test token
    token = "glpat-ToO6ZlkYTyqIC2zlEJnjCmM6MQpvOjEKdTpuNXJxYQ8.01.1702k8efa"

    if not token:
        print("ERROR: No token available")
        return False

    is_windows = Path(__file__).parent.name == "Windows"
    if is_windows:
        node_cmd = r"C:\Program Files\nodejs\node.exe" if Path(r"C:\Program Files\nodejs\node.exe").exists() else "node"
    else:
        node_cmd = "node"

    root_dir = Path(__file__).parent
    local_gitlab = root_dir / "node_modules" / "@zereight" / "mcp-gitlab" / "build" / "index.js"
    if local_gitlab.exists():
        gitlab_js_path = str(local_gitlab.resolve())
    else:
        gitlab_js_path = r"C:\Users\BCSKOL36\AppData\Roaming\npm\node_modules\@zereight\mcp-gitlab\build\index.js"

    print(f"\nTesting MCP server directly:")
    print(f"  Node.js: {node_cmd}")
    print(f"  MCP server: {gitlab_js_path}")

    gitlab_params = StdioServerParameters(
        command=node_cmd,
        args=[gitlab_js_path],
        env={
            **os.environ,
            "GITLAB_PERSONAL_ACCESS_TOKEN": token,
            "GITLAB_URL": "https://gitlab.com"
        }
    )

    try:
        print("  Starting stdio_client...")
        async with stdio_client(gitlab_params) as (read, write):
            print("  stdio_client connected, creating session...")
            await asyncio.sleep(0.5)  # Give subprocess time to start

            sess = ClientSession(read, write, client_info=Implementation(name="test", version="1.0.0"))
            print("  Calling sess.initialize()...")

            await asyncio.wait_for(sess.initialize(), timeout=30.0)
            print("  OK: Session initialized!")

            tools = await sess.list_tools()
            print(f"  OK: Found {len(tools.tools)} tools")

            return True

    except asyncio.TimeoutError:
        print("  ERROR: Session initialization timed out")
        return False
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    print("=" * 60)
    print("GitLab Token and MCP Server Test")
    print("=" * 60)

    token_ok = await test_gitlab_token()
    mcp_ok = await test_mcp_server_directly()

    print("\n" + "=" * 60)
    print("Results:")
    print(f"  Token valid: {token_ok}")
    print(f"  MCP server: {mcp_ok}")
    print("=" * 60)

    return 0 if (token_ok and mcp_ok) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
