/**
 * Sentry OAuth Callback Handler Page
 *
 * This page handles the callback from Sentry OAuth.
 * It extracts the authorization code and state from the URL,
 * calls the backend to exchange for tokens and register webhooks,
 * and redirects back to the repository detail page.
 */

import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api from "../services/api";

const SentryCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState("Processing...");
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Use a ref to track if callback has been processed
  const processedRef = React.useRef(false);

  useEffect(() => {
    console.log("[SentryCallback] Component mounted, pathname:", window.location.pathname);

    const processCallback = async () => {
      // Prevent duplicate calls using ref
      if (processedRef.current) {
        console.log("[SentryCallback] Already processed, skipping");
        return;
      }
      processedRef.current = true;

      console.log("[SentryCallback] Starting callback processing");

      // Also prevent duplicate calls
      if (isProcessing) {
        console.log("[SentryCallback] Already processing, skipping");
        return;
      }

      // Debug: Log the current URL and all search params
      console.log("[SentryCallback DEBUG] Current URL:", window.location.href);
      console.log("[SentryCallback DEBUG] All search params:", Object.fromEntries(searchParams));
      console.log("[SentryCallback DEBUG] searchParams.toString():", searchParams.toString());

      const code = searchParams.get("code");
      const state = searchParams.get("state");

      console.log("[SentryCallback DEBUG] code:", code);
      console.log("[SentryCallback DEBUG] state:", state);

      if (!code || !state) {
        console.error("[SentryCallback ERROR] Missing OAuth parameters");
        setError("Missing OAuth parameters");
        setStatus("Failed");
        return;
      }

      setIsProcessing(true);

      try {
        setStatus("Authenticating with Sentry...");

        // Call backend to handle callback and webhook registration
        const result = await api.completeSentryOAuth(code, state);

        console.log("Sentry OAuth completed:", result);

        setStatus("Connected successfully!");

        // Redirect to repository detail page after successful connection
        setTimeout(() => {
          const repoId = result?.repo_id;
          console.log("[SentryCallback] Redirecting to repoId:", repoId);
          if (repoId) {
            console.log("[SentryCallback] Using window.location.href to navigate to:", `/repositories/${repoId}`);
            window.location.href = `/repositories/${repoId}`;
          } else {
            console.log("[SentryCallback] No repoId, navigating to /repositories");
            window.location.href = "/repositories";
          }
        }, 1000);
      } catch (err) {
        console.error("Sentry OAuth callback error:", err);
        setError(err.message || "Failed to connect Sentry");
        setStatus("Failed");

        // Redirect to repositories page after error
        setTimeout(() => {
          navigate("/repositories");
        }, 3000);
      }
    };

    processCallback();
  }, [searchParams, navigate, isProcessing]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F2F4F7]">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        <div className="mb-6">
          {error ? (
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
              <svg
                className="w-8 h-8 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
          ) : (
            <div className="w-16 h-16 bg-purple-600/10 rounded-full flex items-center justify-center mx-auto">
              <div className="w-8 h-8 border-4 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}
        </div>

        <h2 className="text-2xl font-semibold text-slate-900 mb-2">
          {error ? "Connection Failed" : "Connecting Sentry..."}
        </h2>

        <p className="text-slate-500 mb-4">
          {error ? error : status}
        </p>

        {!error && (
          <div className="space-y-2 text-sm text-slate-400">
            <p>• Exchanging authorization code</p>
            <p>• Registering webhook for issue events</p>
            <p>• Configuring automated bug fixes</p>
          </div>
        )}

        {error && (
          <button
            onClick={() => (window.location.href = "/repositories")}
            className="mt-4 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
          >
            Back to Repositories
          </button>
        )}
      </div>
    </div>
  );
};

export default SentryCallback;
