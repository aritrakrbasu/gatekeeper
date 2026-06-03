"""
WebSocket Connection Manager for real-time progress updates.

Manages WebSocket connections for merge request progress broadcasting.
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Optional


class ConnectionManager:
    """
    Manages active WebSocket connections for progress broadcasting.

    Tracks connections per (repo_id, mr_iid) tuple and broadcasts
    progress events to all subscribers of a specific merge request.
    """

    def __init__(self):
        # Map: (repo_id, mr_iid) -> Set of WebSocket connections
        self.active_connections: Dict[tuple, Set[WebSocket]] = {}
        # Map: websocket -> (repo_id, mr_iid) for reverse lookup
        self.connection_subscriptions: Dict[WebSocket, tuple] = {}

    async def connect(self, websocket: WebSocket, repo_id: str, mr_iid: int):
        """
        Track an already-accepted WebSocket connection.

        Note: The connection must already be accepted via websocket.accept()
        before calling this method.

        Args:
            websocket: The WebSocket connection to track (already accepted)
            repo_id: Repository ID for the merge request
            mr_iid: Merge request IID
        """
        key = (repo_id, mr_iid)

        if key not in self.active_connections:
            self.active_connections[key] = set()

        self.active_connections[key].add(websocket)
        self.connection_subscriptions[websocket] = key

        print(f"[WS] Client connected to {repo_id}/!{mr_iid} - "
              f"Active connections for this MR: {len(self.active_connections[key])}")

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "🔗 Connected to real-time progress stream",
                "repo_id": repo_id,
                "mr_iid": mr_iid
            }
        })

    async def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from tracking.

        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.connection_subscriptions:
            key = self.connection_subscriptions[websocket]

            if key in self.active_connections:
                self.active_connections[key].discard(websocket)
                if not self.active_connections[key]:
                    # Clean up empty key
                    del self.active_connections[key]
                    print(f"[WS] No more active connections for {key[0]}/!{key[1]}")

            del self.connection_subscriptions[websocket]
            print(f"[WS] Client disconnected")

    async def broadcast_progress(self, repo_id: str, mr_iid: int, event: dict):
        """
        Broadcast a progress event to all subscribers of a specific MR.

        Args:
            repo_id: Repository ID
            mr_iid: Merge request IID
            event: Event data to broadcast (will be JSON-encoded)
        """
        key = (repo_id, mr_iid)

        if key not in self.active_connections:
            # No active connections for this MR
            return

        disconnected = set()

        for connection in self.active_connections[key]:
            try:
                await connection.send_json(event)
            except Exception as e:
                print(f"[WS] Failed to send to client: {e}")
                disconnected.add(connection)

        # Clean up dead connections
        for conn in disconnected:
            await self.disconnect(conn)

    def get_connection_count(self, repo_id: str, mr_iid: int) -> int:
        """
        Get the number of active connections for a specific MR.

        Args:
            repo_id: Repository ID
            mr_iid: Merge request IID

        Returns:
            Number of active connections
        """
        key = (repo_id, mr_iid)
        return len(self.active_connections.get(key, set()))

    def get_total_connections(self) -> int:
        """
        Get the total number of active WebSocket connections.

        Returns:
            Total number of connections across all MRs
        """
        return len(self.connection_subscriptions)


# Global singleton instance
manager = ConnectionManager()


class RepositoryEventManager:
    """
    Manages WebSocket connections for repository-wide events.

    Tracks connections per repository and broadcasts events like:
    - New MR created
    - Analysis started
    - Analysis completed
    - MR status changed
    """

    def __init__(self):
        # Map: repo_id -> Set of WebSocket connections
        self.repository_connections: Dict[str, Set[WebSocket]] = {}
        # Map: websocket -> repo_id for reverse lookup
        self.connection_repositories: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, repo_id: str):
        """
        Track a WebSocket connection for repository events.

        Note: The connection must already be accepted via websocket.accept()
        before calling this method.

        Args:
            websocket: The WebSocket connection to track (already accepted)
            repo_id: Repository ID
        """
        if repo_id not in self.repository_connections:
            self.repository_connections[repo_id] = set()

        self.repository_connections[repo_id].add(websocket)
        self.connection_repositories[websocket] = repo_id

        print(f"[WS-Repo] Client connected to repository {repo_id} - "
              f"Active connections: {len(self.repository_connections[repo_id])}")

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "🔗 Connected to repository event stream",
                "repo_id": repo_id
            }
        })

    async def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from tracking.

        Args:
            websocket: The WebSocket connection to remove
        """
        if websocket in self.connection_repositories:
            repo_id = self.connection_repositories[websocket]

            if repo_id in self.repository_connections:
                self.repository_connections[repo_id].discard(websocket)
                if not self.repository_connections[repo_id]:
                    # Clean up empty repository
                    del self.repository_connections[repo_id]
                    print(f"[WS-Repo] No more active connections for repository {repo_id}")

            del self.connection_repositories[websocket]
            print(f"[WS-Repo] Client disconnected")

    async def broadcast_event(self, repo_id: str, event: dict):
        """
        Broadcast an event to all subscribers of a repository.

        Args:
            repo_id: Repository ID
            event: Event data to broadcast (will be JSON-encoded)
        """
        if repo_id not in self.repository_connections:
            # No active connections for this repository
            return

        disconnected = set()

        for connection in self.repository_connections[repo_id]:
            try:
                await connection.send_json(event)
            except Exception as e:
                print(f"[WS-Repo] Failed to send to client: {e}")
                disconnected.add(connection)

        # Clean up dead connections
        for conn in disconnected:
            await self.disconnect(conn)

    def get_connection_count(self, repo_id: str) -> int:
        """
        Get the number of active connections for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Number of active connections
        """
        return len(self.repository_connections.get(repo_id, set()))

    def get_total_connections(self) -> int:
        """
        Get the total number of active WebSocket connections.

        Returns:
            Total number of connections across all repositories
        """
        return len(self.connection_repositories)


# Global singleton instance for repository events
repository_manager = RepositoryEventManager()
