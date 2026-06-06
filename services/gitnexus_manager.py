"""
GitNexus Server Manager

Manages the GitNexus serve subprocess for providing HTTP API endpoints.
The server is started on port 3000.
"""
import asyncio
import subprocess
import httpx
from typing import Optional, Dict, Any


class GitNexusManager:
    """Manages GitNexus serve lifecycle and MCP API calls"""

    def __init__(self, port: int = 3000):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.base_url = f"http://localhost:{port}"
        self._startup_complete = asyncio.Event()
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Start GitNexus serve in background"""
        if self.process:
            print("[GitNexus] Server already running")
            return

        print(f"[GitNexus] Starting serve on port {self.port}...")

        try:
            # Start GitNexus serve using npx
            self.process = subprocess.Popen(
                ["npx", "gitnexus", "serve", f"--port={self.port}", "--host", "0.0.0.0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Wait for server to be ready (check for HTML response)
            for i in range(30):
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{self.base_url}/", timeout=2)
                        if response.status_code == 200 and "html" in response.headers.get("content-type", ""):
                            print(f"[✅] GitNexus serve started successfully on port {self.port}")
                            self._startup_complete.set()
                            # Initialize persistent client for MCP calls
                            self._client = httpx.AsyncClient(
                                headers={"Accept": "application/json, text/event-stream"},
                                timeout=60.0
                            )
                            return
                except Exception:
                    pass

                # Check if process is still running
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    print(f"[❌] GitNexus server process exited unexpectedly")
                    print(f"[GitNexus] stdout: {stdout[:500]}")
                    print(f"[GitNexus] stderr: {stderr[:500]}")
                    self.process = None
                    return

                await asyncio.sleep(1)

            print(f"[⚠️] GitNexus server timeout - may not be fully started")

        except Exception as e:
            print(f"[❌] Failed to start GitNexus server: {e}")
            self.process = None

    async def stop(self):
        """Stop GitNexus serve"""
        if not self.process:
            return

        print("[GitNexus] Stopping serve...")
        try:
            self.process.terminate()
            await asyncio.sleep(2)

            if self.process.poll() is None:
                print("[GitNexus] Force killing server...")
                self.process.kill()

            print("[✅] GitNexus server stopped")
        except Exception as e:
            print(f"[⚠️] Error stopping GitNexus server: {e}")
        finally:
            self.process = None
            if self._client:
                await self._client.aclose()
                self._client = None

    def is_running(self) -> bool:
        """Check if server is running"""
        if not self.process:
            return False
        return self.process.poll() is None

    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a GitNexus MCP tool via HTTP"""
        if not self._client:
            raise RuntimeError("GitNexus client not initialized")

        request_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            response = await self._client.post(
                f"{self.base_url}/api/mcp",
                json=request_payload
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                return {"error": result["error"].get("message", "Unknown error"), "results": []}

            return result.get("result", {"results": []})

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": "Repository not found", "results": []}
            return {"error": f"HTTP {e.response.status_code}", "results": []}
        except Exception as e:
            print(f"[ERROR] GitNexus MCP call error: {e}")
            return {"error": str(e), "results": []}

    async def grep(self, pattern: str, repo: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """Call GitNexus grep tool"""
        args = {"pattern": pattern, "limit": limit}
        if repo:
            args["repo"] = repo
        return await self._call_mcp_tool("grep", args)

    async def file(self, path: str, repo: Optional[str] = None,
                  start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Call GitNexus file tool"""
        args = {"path": path}
        if repo:
            args["repo"] = repo
        if start_line is not None:
            args["start_line"] = start_line
        if end_line is not None:
            args["end_line"] = end_line
        return await self._call_mcp_tool("file", args)


# Global instance
gitnexus_manager = GitNexusManager(port=3000)
