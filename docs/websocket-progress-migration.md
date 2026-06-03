# Plan: Replace Progress API with WebSocket Real-Time Updates

## Context

The current implementation uses a `/progress` API endpoint that:
- Stores progress logs in MongoDB's `merge_requests` collection (`progress_logs` array)
- Frontend polls every 2-3 seconds using React Query
- Shows technical messages like "calling gitnexus_grep" which aren't user-friendly

This plan replaces that with a WebSocket-based real-time progress system with:
- Pure real-time broadcasting (no MongoDB storage)
- User-friendly messages with emojis and engaging descriptions
- Required JWT authentication via query parameter
- No historical logs (late joiners only see final analysis results)

---

## Implementation Plan

### Phase 1: Backend WebSocket Infrastructure

#### 1. Create WebSocket Connection Manager
**File**: `services/websocket_manager.py` (NEW)

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json

class ConnectionManager:
    def __init__(self):
        # Map: (repo_id, mr_iid) -> Set of WebSocket connections
        self.active_connections: Dict[tuple, Set[WebSocket]] = {}
        # Map: websocket -> (repo_id, mr_iid) for reverse lookup
        self.connection_subscriptions: Dict[WebSocket, tuple] = {}
    
    async def connect(self, websocket: WebSocket, repo_id: str, mr_iid: int):
        """Accept connection and track subscription"""
        await websocket.accept()
        key = (repo_id, mr_iid)
        if key not in self.active_connections:
            self.active_connections[key] = set()
        self.active_connections[key].add(websocket)
        self.connection_subscriptions[websocket] = key
    
    async def disconnect(self, websocket: WebSocket):
        """Remove connection from tracking"""
        if websocket in self.connection_subscriptions:
            key = self.connection_subscriptions[websocket]
            if key in self.active_connections:
                self.active_connections[key].discard(websocket)
                if not self.active_connections[key]:
                    del self.active_connections[key]
            del self.connection_subscriptions[websocket]
    
    async def broadcast_progress(self, repo_id: str, mr_iid: int, event: dict):
        """Broadcast progress event to all subscribers of this MR"""
        key = (repo_id, mr_iid)
        if key in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[key]:
                try:
                    await connection.send_json(event)
                except Exception:
                    disconnected.add(connection)
            
            # Clean up dead connections
            for conn in disconnected:
                await self.disconnect(conn)

# Global manager instance
manager = ConnectionManager()
```

#### 2. Create User-Friendly Message Mapping
**File**: `services/progress_messages.py` (NEW)

Maps technical steps to engaging user messages with emojis.

```python
from typing import Dict, Optional

# Mapping of technical steps to user-friendly messages
PROGRESS_MESSAGES = {
    "received": "🔔 Merge request received - preparing for analysis",
    "starting": "🚀 Gatekeeper security analysis started",
    "fetching": "📡 Retrieving code changes from GitLab",
    "diff_fetched": "✅ Code changes retrieved successfully",
    "schema_check_running": "🗄️ Examining database schema for potential issues",
    "schema_check_completed": "✅ Database schema analysis complete",
    "clone_failed": "⚠️ Repository clone encountered an issue - continuing with available data",
    
    # GitNexus tools - user-friendly alternatives
    "gitnexus_grep": "🔍 Searching codebase for relevant patterns",
    "gitnexus_file": "📖 Analyzing file contents",
    "impact_analysis_running": "📊 Analyzing code impact and dependencies",
    "impact_analysis_completed": "✅ Impact analysis complete",
    
    # AI analysis
    "ai_analysis_running": "🤖 Running AI-powered security and code quality review",
    "ai_analysis_thinking": "🧠 Deep learning models analyzing your code...",
    "ai_analysis_completed": "✅ AI analysis complete",
    
    # Auto-fix
    "auto_fix_running": "🔧 Analyzing issues for automatic fixes",
    "auto_fix_completed": "✅ Auto-fix analysis complete",
    
    # Completion
    "completed": "🎉 Review completed successfully - Report published",
    
    # Errors
    "error": "❌ Analysis encountered an error"
}

def get_user_friendly_message(step: str, **kwargs) -> str:
    """Get user-friendly message for a progress step"""
    message = PROGRESS_MESSAGES.get(step)
    if not message:
        # Fallback for unknown steps - make it generic
        return "🔄 Processing your request..."
    return message

def get_message_category(step: str) -> str:
    """Get category for styling purposes"""
    if "error" in step or "failed" in step:
        return "error"
    elif "completed" in step:
        return "success"
    elif "running" in step or "thinking" in step:
        return "running"
    return "info"
```

#### 3. Add WebSocket Endpoint
**File**: `main.py` (MODIFY - after line 456)

Add the WebSocket route:

```python
from services.websocket_manager import manager
from services.auth_service import auth_service

@app.websocket("/ws/repositories/{repo_id}/mrs/{mr_iid}/progress")
async def websocket_progress_endpoint(
    websocket: WebSocket,
    repo_id: str,
    mr_iid: int,
    token: Optional[str] = None
):
    """WebSocket endpoint for real-time MR progress updates
    
    Authentication: Required via ?token= JWT query parameter
    """
    # Validate JWT token
    if not token:
        await websocket.close(code=1008, reason="Token required")
        return
    
    try:
        # Remove "Bearer " prefix if present
        clean_token = token.replace("Bearer ", "") if token.startswith("Bearer ") else token
        user_info = auth_service.verify_token(clean_token)
    except Exception as e:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Connect to manager
    await manager.connect(websocket, repo_id, mr_iid)
    
    try:
        # Keep connection alive and handle ping/pong
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error for {repo_id}/!{mr_iid}: {e}")
        manager.disconnect(websocket)
```

#### 4. Update Progress Broadcasting in Review Service
**File**: `services/review_service.py` (MODIFY - lines 482-493)

Replace the `add_log` helper function to broadcast via WebSocket:

```python
async def add_log(step: str, status: str = "running", **kwargs):
    """Broadcast progress log via WebSocket (no MongoDB storage)"""
    try:
        from services.websocket_manager import manager
        from services.progress_messages import get_user_friendly_message, get_message_category
        
        message = get_user_friendly_message(step, **kwargs)
        category = get_message_category(step)
        
        await manager.broadcast_progress(
            repo_id=str(project_id),
            mr_iid=int(mr_iid),
            event={
                "type": "progress",
                "data": {
                    "step": step,
                    "message": message,
                    "status": status,
                    "category": category,
                    "timestamp": time.time()
                }
            }
        )
    except Exception as log_err:
        print(f"[WARN] Failed to broadcast progress log: {log_err}")
```

#### 5. Add Progress Broadcasting in Gemini Service
**File**: `services/gemini_service.py` (MODIFY - around line 436)

Add WebSocket broadcasts when GitNexus tools are called:

```python
# In call_gitnexus_grep function
async def call_gitnexus_grep(pattern, **kwargs):
    print(f"[INFO][GitNexus Grep] Tool called by Gemini", flush=True)
    
    # Broadcast progress if MR context is available
    # Note: Need to pass repo_id/mr_iid through call chain or use context
    # This will be handled by the review_service wrapper
```

**Important**: Since `gemini_service.py` doesn't have direct access to `repo_id` and `mr_iid`, the progress broadcasts will be handled by `review_service.py` which orchestrates the calls. The technical function names will be replaced with user-friendly messages at the orchestration layer.

#### 6. Remove MongoDB Progress Log Functions
**File**: `services/repository_service.py` (MODIFY - lines 2172-2258)

Remove these functions:
- `add_mr_progress_log()`
- `get_mr_progress_logs()`

These are no longer needed since we're not storing progress logs.

#### 7. Remove /progress API Endpoint
**File**: `main.py` (MODIFY - lines 437-456)

Remove the entire `/api/repositories/{repo_id}/mrs/{mr_iid}/progress` endpoint.

---

### Phase 2: Frontend WebSocket Client

#### 1. Create WebSocket Hook
**File**: `frontend/gatekeeper/src/hooks/useWebSocketProgress.js` (NEW)

```javascript
import { useEffect, useState, useCallback, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export function useWebSocketProgress(repoId, mrIid, enabled = true) {
  const { token } = useAuth();
  const [logs, setLogs] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY = 3000;

  const connect = useCallback(() => {
    if (!repoId || !mrIid || !enabled) return;

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close();
    }

    const wsUrl = `${WS_BASE_URL}/ws/repositories/${repoId}/mrs/${mrIid}/progress?token=${token}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[WS] Connected to progress stream');
      setIsConnected(true);
      setError(null);
      reconnectAttempts.current = 0;
      
      ws.pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'progress') {
          setLogs(prev => {
            const exists = prev.some(log => 
              log.step === data.data.step && 
              Math.abs(log.timestamp - data.data.timestamp) < 0.1
            );
            if (exists) return prev;
            return [...prev, data.data];
          });
        }
      } catch (err) {
        console.error('[WS] Failed to parse message:', err);
      }
    };

    ws.onclose = (event) => {
      console.log('[WS] Connection closed:', event.code, event.reason);
      setIsConnected(false);
      
      if (ws.pingInterval) clearInterval(ws.pingInterval);

      if (event.code !== 1000 && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => connect(), RECONNECT_DELAY * reconnectAttempts.current);
      } else if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        setError('Connection lost. Please refresh the page.');
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] WebSocket error:', err);
      setError('Connection error. Retrying...');
    };

    wsRef.current = ws;
  }, [repoId, mrIid, token, enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close(1000, 'Component unmounted');
    };
  }, [connect]);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    connect();
  }, [connect]);

  return { logs, isConnected, error, reconnect };
}
```

#### 2. Update ProgressLogsViewer Component
**File**: `frontend/gatekeeper/src/pages/RepoDetails.jsx` (MODIFY - lines 2047-2103)

Replace the polling-based implementation with WebSocket:

```jsx
const ProgressLogsViewer = ({ repoId, mrIid, isReviewing }) => {
  const { logs, isConnected, error, reconnect } = useWebSocketProgress(
    repoId, 
    mrIid, 
    isReviewing
  );

  if (!isReviewing && logs.length === 0) {
    return null;
  }

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden">
      <div className="px-4 py-3 bg-slate-800/50 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isReviewing && (
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
          )}
          <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Analysis Progress
          </span>
        </div>
        <div className="flex items-center gap-2">
          {error && (
            <button 
              onClick={reconnect}
              className="text-[10px] text-amber-400 font-medium hover:text-amber-300"
            >
              Reconnect
            </button>
          )}
          {isReviewing && isConnected ? (
            <span className="text-[10px] text-emerald-400 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              Live
            </span>
          ) : isReviewing ? (
            <span className="text-[10px] text-amber-400 font-medium">Connecting...</span>
          ) : null}
        </div>
      </div>
      <div className="p-4 max-h-48 overflow-y-auto space-y-2 font-mono text-xs">
        {logs.map((log, idx) => (
          <div key={idx} className="flex items-start gap-2">
            <span className="text-slate-500 shrink-0">
              {new Date(log.timestamp * 1000).toLocaleTimeString("en-US", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span
              className={`flex-1 ${
                log.category === 'running' ? 'text-blue-400' :
                log.category === 'success' ? 'text-emerald-400' :
                log.category === 'error' ? 'text-rose-400' :
                'text-slate-300'
              }`}
            >
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
```

#### 3. Deprecate Old Polling Hook
**File**: `frontend/gatekeeper/src/services/queries.js` (MODIFY - lines 562-570)

Mark as deprecated:

```javascript
/**
 * @deprecated Use useWebSocketProgress instead for real-time updates
 * This will be removed in v2.0
 */
export function useMRProgressLogs(repoId, mrIid, options = {}) {
  return useQuery({
    queryKey: ['mrProgress', repoId, mrIid],
    queryFn: () => api.getMRProgressLogs(repoId, mrIid),
    enabled: false, // Disabled by default
  });
}
```

---

### Phase 3: Environment Configuration

#### Backend
No additional dependencies needed - FastAPI includes WebSocket support.

#### Frontend
No additional npm packages - WebSocket API is native to browsers.

Add to `frontend/gatekeeper/.env.development`:
```
VITE_WS_URL=ws://localhost:8000
```

Add to `frontend/gatekeeper/.env.production`:
```
VITE_WS_URL=wss://your-api-domain.com
```

---

## Critical Files Summary

| File | Action | Description |
|------|--------|-------------|
| `services/websocket_manager.py` | CREATE | WebSocket connection lifecycle manager |
| `services/progress_messages.py` | CREATE | User-friendly message mappings |
| `main.py` | MODIFY | Add WebSocket endpoint, remove `/progress` API |
| `services/review_service.py` | MODIFY | Update `add_log()` to broadcast via WebSocket |
| `services/repository_service.py` | MODIFY | Remove `add_mr_progress_log()` and `get_mr_progress_logs()` |
| `services/gemini_service.py` | MODIFY | No direct changes (handled by review_service) |
| `frontend/gatekeeper/src/hooks/useWebSocketProgress.js` | CREATE | WebSocket client hook |
| `frontend/gatekeeper/src/pages/RepoDetails.jsx` | MODIFY | Update ProgressLogsViewer to use WebSocket |
| `frontend/gatekeeper/src/services/queries.js` | MODIFY | Deprecate polling hook |

---

## Verification

### Backend Testing
1. Test WebSocket connection with valid/invalid tokens
2. Test message broadcasting during analysis
3. Test connection cleanup on disconnect
4. Test multiple concurrent connections

### Frontend Testing
1. Test WebSocket connection establishment
2. Test real-time message display
3. Test reconnection on disconnect
4. Test error handling

### End-to-End
1. Trigger a GitLab webhook
2. Open frontend and observe real-time progress
3. Verify user-friendly messages are shown
4. Verify final analysis results display correctly
