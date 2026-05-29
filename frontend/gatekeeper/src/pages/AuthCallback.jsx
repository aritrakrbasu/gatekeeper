/**
 * OAuth Callback Handler Page
 *
 * This page handles the callback from GitLab OAuth.
 * It extracts the authorization code and state from the URL,
 * calls the backend to exchange for tokens, and redirects to dashboard
 * or onboarding if Gemini is not configured.
 */

import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useGeminiSettings } from "../services/queries";

const AuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { handleCallback } = useAuth();
  const [status, setStatus] = useState("Processing...");
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [authCompleted, setAuthCompleted] = useState(false);

  // Fetch Gemini settings ONLY after auth completes
  // This prevents 401 errors from being called before token is stored
  const { data: geminiSettings } = useGeminiSettings({
    enabled: authCompleted // Only fetch after auth is complete
  });

  useEffect(() => {
    const processCallback = async () => {
      // Prevent duplicate calls
      if (isProcessing) return;

      const code = searchParams.get("code");
      const state = searchParams.get("state");

      if (!code || !state) {
        setError("Missing OAuth parameters");
        setStatus("Failed");
        return;
      }

      setIsProcessing(true);

      try {
        setStatus("Authenticating...");
        await handleCallback(code, state);
        setStatus("Success!");
        setAuthCompleted(true);

        // Redirect will happen based on Gemini settings via useEffect
      } catch (err) {
        console.error("OAuth callback error:", err);
        setError(err.message || "Authentication failed");
        setStatus("Failed");
        // Redirect to login after error
        setTimeout(() => {
          navigate("/login");
        }, 3000);
      }
    };

    processCallback();
  }, [searchParams, handleCallback, navigate, isProcessing]);

  // Redirect to appropriate page after auth completes and settings are fetched
  useEffect(() => {
    if (authCompleted && geminiSettings !== undefined) {
      setTimeout(() => {
        if (geminiSettings?.api_token_configured) {
          navigate("/dashboard");
        } else {
          navigate("/onboarding");
        }
      }, 500);
    }
  }, [authCompleted, geminiSettings, navigate]);

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
            <div className="w-16 h-16 bg-[#FC6D26]/10 rounded-full flex items-center justify-center mx-auto">
              <div className="w-8 h-8 border-4 border-[#FC6D26] border-t-transparent rounded-full animate-spin"></div>
            </div>
          )}
        </div>

        <h2 className="text-2xl font-semibold text-slate-900 mb-2">
          {error ? "Authentication Failed" : "Authenticating..."}
        </h2>

        <p className="text-slate-500 mb-4">
          {error ? error : status}
        </p>

        {!error && (
          <p className="text-sm text-slate-400">
            Please wait while we sign you in...
          </p>
        )}

        {error && (
          <button
            onClick={() => (window.location.href = "/login")}
            className="mt-4 px-4 py-2 bg-[#FC6D26] text-white rounded-lg hover:bg-[#E24329] transition-colors"
          >
            Back to Login
          </button>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
