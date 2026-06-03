/**
 * WebSocket hook for repository-wide real-time events.
 *
 * Maintains a persistent connection to receive notifications for:
 * - New MRs created
 * - Analysis started
 * - Analysis completed
 * - MR status changes
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";

const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

/**
 * Custom hook for WebSocket-based repository event notifications
 *
 * @param {string} repoId - Repository ID
 * @param {boolean} enabled - Whether to enable the WebSocket connection
 * @param {Function} onEvent - Callback function when an event is received (event) => void
 * @returns {Object} { isConnected, error, reconnect }
 */
export function useRepositoryEvents(repoId, enabled = true, onEvent = null) {
  const { token } = useAuth();
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const onEventRef = useRef(onEvent);

  // Keep onEventRef updated
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const MAX_RECONNECT_ATTEMPTS = 10;
  const RECONNECT_DELAY = 3000;

  const connect = useCallback(() => {
    if (!repoId || !enabled || !token) {
      console.log("[WS-Repo] Connection skipped - missing params:", {
        repoId: !!repoId,
        enabled,
        hasToken: !!token,
      });
      return;
    }

    // Close existing connection if open
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close(1000, "Reconnecting");
    }

    const wsUrl = `${WS_BASE_URL}/ws/repositories/${repoId}/events?token=${token}`;

    console.log(
      "[WS-Repo] Connecting to repository events:",
      wsUrl.replace(token, "***").substring(0, 50) + "...",
    );
    console.log("[WS-Repo] Repository ID:", repoId);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[WS-Repo] Connected to repository event stream");
      setIsConnected(true);
      setError(null);
      reconnectAttempts.current = 0;

      // Send ping every 30s to keep connection alive
      ws.pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send("ping");
          } catch (err) {
            console.error("[WS-Repo] Failed to send ping:", err);
          }
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle ping/pong
        if (event.data === "pong") {
          return;
        }

        console.log("[WS-Repo] Received message:", data);

        if (data.type === "connected") {
          console.log("[WS-Repo] Server confirmed connection:", data.data.message);
          return;
        }

        if (data.type === "event" && data.event_type && onEventRef.current) {
          console.log("[WS-Repo] Triggering event callback:", data.event_type);
          onEventRef.current(data);
        }
      } catch (err) {
        console.error("[WS-Repo] Failed to parse message:", err, event.data);
      }
    };

    ws.onclose = (event) => {
      console.log("[WS-Repo] Connection closed:", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
      });
      setIsConnected(false);

      if (ws.pingInterval) {
        clearInterval(ws.pingInterval);
      }

      // Specific error codes
      if (event.code === 1008) {
        setError("Authentication failed. Please log in again.");
        return;
      }

      // Attempt reconnection if not intentionally closed
      if (
        event.code !== 1000 &&
        reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS
      ) {
        reconnectAttempts.current += 1;
        const delay = RECONNECT_DELAY * reconnectAttempts.current;
        console.log(
          `[WS-Repo] Reconnecting in ${delay}ms... (Attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS})`,
        );

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      } else if (reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
        setError(
          "Connection lost after multiple attempts. Please refresh the page.",
        );
      }
    };

    ws.onerror = (event) => {
      console.error("[WS-Repo] WebSocket error event:", event);
      console.error("[WS-Repo] ReadyState:", ws.readyState);
      setError("Connection error. Check console for details.");
    };

    wsRef.current = ws;
  }, [repoId, token, enabled]);

  // Connect on mount and when dependencies change
  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounted");
      }
    };
  }, [connect]);

  // Manual reconnect function
  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    setError(null);
    connect();
  }, [connect]);

  return {
    isConnected,
    error,
    reconnect,
  };
}
