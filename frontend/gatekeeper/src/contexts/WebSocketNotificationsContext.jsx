/**
 * WebSocket Notifications Context
 *
 * Provides global WebSocket notifications for multiple repositories.
 * Allows the app to listen to repository events from any page.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { useAuth } from "./AuthContext";
import { toast } from "react-toastify";

const WS_BASE_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000";

const WebSocketNotificationsContext = createContext(null);

/**
 * Custom hook to use the WebSocket notifications context
 */
export const useWebSocketNotifications = () => {
  const context = useContext(WebSocketNotificationsContext);
  if (!context) {
    throw new Error(
      "useWebSocketNotifications must be used within WebSocketNotificationsProvider",
    );
  }
  return context;
};

/**
 * Provider component for WebSocket notifications
 */
export const WebSocketNotificationsProvider = ({ children }) => {
  const { token } = useAuth();
  const [connections, setConnections] = useState({}); // repoId -> WebSocket connection
  const [listeningRepos, setListeningRepos] = useState(new Set()); // Set of repo IDs being listened to
  const connectionsRef = useRef({});
  const listeningReposRef = useRef(new Set());

  // Keep refs in sync
  useEffect(() => {
    connectionsRef.current = connections;
  }, [connections]);

  useEffect(() => {
    listeningReposRef.current = listeningRepos;
  }, [listeningRepos]);

  /**
   * Add a repository to the listening list
   */
  const listenToRepository = useCallback((repoId) => {
    console.log(
      "[WS-Notifications] Adding repository to listening list:",
      repoId,
    );
    setListeningRepos((prev) => new Set([...prev, repoId]));
  }, []);

  /**
   * Remove a repository from the listening list
   */
  const stopListeningToRepository = useCallback((repoId) => {
    console.log(
      "[WS-Notifications] Removing repository from listening list:",
      repoId,
    );
    setListeningRepos((prev) => {
      const newSet = new Set(prev);
      newSet.delete(repoId);
      return newSet;
    });

    // Close the WebSocket connection for this repository
    if (connectionsRef.current[repoId]) {
      const ws = connectionsRef.current[repoId];
      if (
        ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING
      ) {
        ws.close(1000, "No longer listening");
      }
      setConnections((prev) => {
        const newConnections = { ...prev };
        delete newConnections[repoId];
        return newConnections;
      });
    }
  }, []);

  /**
   * Connect to a repository's WebSocket events
   */
  const connectToRepository = useCallback(
    (repoId) => {
      if (!token || !repoId || connectionsRef.current[repoId]) {
        return;
      }

      const wsUrl = `${WS_BASE_URL}/ws/repositories/${repoId}/events?token=${token}`;
      console.log("[WS-Notifications] Connecting to repository:", repoId);

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log("[WS-Notifications] Connected to repository:", repoId);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Handle ping/pong
          if (event.data === "pong") {
            return;
          }

          if (data.type === "connected") {
            console.log("[WS-Notifications] Connected to:", data.data.message);
            return;
          }

          if (data.type === "event" && data.event_type) {
            handleRepositoryEvent(data);
          }
        } catch (err) {
          console.error("[WS-Notifications] Failed to parse message:", err);
        }
      };

      ws.onclose = (event) => {
        console.log(
          "[WS-Notifications] Connection closed for repository:",
          repoId,
          event.code,
        );

        // Remove from connections
        setConnections((prev) => {
          const newConnections = { ...prev };
          delete newConnections[repoId];
          return newConnections;
        });

        // If still in listening list and not intentionally closed, attempt reconnection
        if (
          listeningReposRef.current.has(repoId) &&
          event.code !== 1000 &&
          token
        ) {
          setTimeout(() => {
            if (listeningReposRef.current.has(repoId)) {
              console.log(
                "[WS-Notifications] Reconnecting to repository:",
                repoId,
              );
              connectToRepository(repoId);
            }
          }, 3000);
        }
      };

      ws.onerror = (error) => {
        console.error(
          "[WS-Notifications] WebSocket error for repository:",
          repoId,
          error,
        );
      };

      setConnections((prev) => ({
        ...prev,
        [repoId]: ws,
      }));
    },
    [token],
  );

  const toastifyOptions = {
    position: "bottom-right",
    autoClose: 5000,
    hideProgressBar: true,
    closeOnClick: true,
    pauseOnHover: true,
    draggable: false,
    theme: "dark",
  };

  /**
   * Handle incoming repository events
   */
  const handleRepositoryEvent = useCallback((event) => {
    const eventType = event.event_type;
    const eventData = event.data || {};
    const repoId = eventData.repository_id;

    console.log("[WS-Notifications] Received event:", eventType, eventData);

    // Show toast notification based on event type
    switch (eventType) {
      case "mr_created":
        toast.success("📬 New MR Created", toastifyOptions);
        break;

      case "mr_closed":
        toast.info("🔒 MR Closed", toastifyOptions);
        break;

      case "mr_merged":
        toast.success("🎉 MR Merged", toastifyOptions);
        break;

      case "analysis_started":
        toast.info("🤖 AI Analysis Started", toastifyOptions);
        break;

      case "analysis_completed":
        toast.success("✅ Analysis Completed", toastifyOptions);

        break;

      default:
        console.log("[WS-Notifications] Unknown event type:", eventType);
    }
  }, []);

  /**
   * Connect to all repositories in the listening list
   */
  useEffect(() => {
    if (!token) return;

    // Connect to all repositories in the listening list
    listeningRepos.forEach((repoId) => {
      if (!connectionsRef.current[repoId]) {
        connectToRepository(repoId);
      }
    });

    // Cleanup function
    return () => {
      Object.values(connectionsRef.current).forEach((ws) => {
        if (
          ws.readyState === WebSocket.OPEN ||
          ws.readyState === WebSocket.CONNECTING
        ) {
          ws.close(1000, "Component unmounting");
        }
      });
    };
  }, [listeningRepos, token, connectToRepository]);

  const value = {
    listeningRepos,
    listenToRepository,
    stopListeningToRepository,
  };

  return (
    <WebSocketNotificationsContext.Provider value={value}>
      {children}
    </WebSocketNotificationsContext.Provider>
  );
};

export default WebSocketNotificationsProvider;
