/**
 * WebSocket hook for real-time MR progress updates
 *
 * Replaces the polling-based progress mechanism with WebSocket connections
 * for real-time updates during merge request analysis.
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";

const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

/**
 * Custom hook for WebSocket-based real-time progress updates
 *
 * @param {string} repoId - Repository ID
 * @param {number} mrIid - Merge Request IID
 * @param {boolean} enabled - Whether to enable the WebSocket connection
 * @param {Function} onComplete - Callback when analysis completes
 * @returns {Object} { logs, isConnected, error, reconnect }
 */
export function useWebSocketProgress(repoId, mrIid, enabled = true, onComplete = null) {
  const { token } = useAuth();
  const [logs, setLogs] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const logsRef = useRef(logs);
  const completionTriggeredRef = useRef(false);  // Track if we've triggered completion
  const onCompleteRef = useRef(onComplete);  // Store callback in ref to always have latest value

  // Keep onCompleteRef updated
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY = 3000;

  // Keep logsRef in sync
  useEffect(() => {
    logsRef.current = logs;
  }, [logs]);

  const connect = useCallback(() => {
    if (!repoId || !mrIid || !enabled || !token) {
      console.log("[WS] Connection skipped - missing params:", {
        repoId: !!repoId,
        mrIid: !!mrIid,
        enabled,
        hasToken: !!token,
      });
      return;
    }

    // Close existing connection if open
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.close(1000, "Reconnecting");
    }

    const wsUrl = `${WS_BASE_URL}/ws/repositories/${repoId}/mrs/${mrIid}/progress?token=${token}`;

    console.log(
      "[WS] Connecting to:",
      wsUrl.replace(token, "***").substring(0, 50) + "...",
    );
    console.log("[WS] Repo ID:", repoId, "MR IID:", mrIid);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[WS] Connected to progress stream");
      setIsConnected(true);
      setError(null);
      reconnectAttempts.current = 0;

      // Send ping every 30s to keep connection alive
      ws.pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send("ping");
          } catch (err) {
            console.error("[WS] Failed to send ping:", err);
          }
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Debug: Log all message types
        console.log("[WS] Received message type:", data.type);

        // Handle ping/pong
        if (event.data === "pong") {
          return;
        }

        if (data.type === "connected") {
          console.log("[WS] Server confirmed connection:", data.data.message);
          return;
        }

        if (data.type === "progress") {
          const newLog = data.data;

          // Debug logging
          console.log("[WS] Received progress log:", {
            step: newLog.step,
            status: newLog.status,
            message: newLog.message?.substring(0, 50),
            completionCheck: {
              triggered: completionTriggeredRef.current,
              stepMatch: newLog.step === "completed",
              statusMatch: newLog.status === "completed",
              hasCallback: !!onCompleteRef.current
            }
          });

          setLogs((prev) => {
            // Avoid duplicates based on step and timestamp
            const exists = prev.some(
              (log) =>
                log.step === newLog.step &&
                Math.abs(log.timestamp - newLog.timestamp) < 0.1,
            );
            if (exists) return prev;

            const updated = [...prev, newLog];

            // Check if analysis completed (but only trigger once)
            // IMPORTANT: Only trigger when step is "completed", NOT when status is "completed"
            // Individual tools like "detect_changes" also have status="completed"
            if (
              !completionTriggeredRef.current &&
              newLog.step === "completed" &&
              onCompleteRef.current
            ) {
              completionTriggeredRef.current = true;
              console.log("[WS] Analysis completed, triggering callback. Log:", newLog);
              // Call onComplete in the next tick to ensure state is updated
              setTimeout(() => onCompleteRef.current?.(newLog), 100);
            }

            return updated;
          });
        } else if (data.type === "history") {
          // Historical logs (if sent by server)
          setLogs(data.logs || []);

          // Check if history contains completion
          const hasCompletion = (data.logs || []).some(
            log => log.step === "completed"
          );
          if (hasCompletion && !completionTriggeredRef.current && onCompleteRef.current) {
            completionTriggeredRef.current = true;
            console.log("[WS] History contains completion, triggering callback");
            setTimeout(() => onCompleteRef.current?.(), 100);
          }
        }
      } catch (err) {
        console.error("[WS] Failed to parse message:", err, event.data);
      }
    };

    ws.onclose = (event) => {
      console.log("[WS] Connection closed:", {
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
          `[WS] Reconnecting in ${delay}ms... (Attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS})`,
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
      console.error("[WS] WebSocket error event:", event);
      console.error("[WS] ReadyState:", ws.readyState);
      setError("Connection error. Check console for details.");
    };

    wsRef.current = ws;
  }, [repoId, mrIid, token, enabled]);

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
    completionTriggeredRef.current = false;
    setError(null);
    setLogs([]);
    connect();
  }, [connect]);

  return {
    logs,
    isConnected,
    error,
    reconnect,
  };
}
