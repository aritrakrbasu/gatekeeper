import React, { useState } from "react";
import { useAuth } from "../contexts/AuthContext";

const GatekeeperEnterpriseLogin = () => {
  const { login } = useAuth();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGitLabLogin = async () => {
    try {
      setIsLoading(true);
      setError(null);
      await login();
    } catch (err) {
      console.error("Login failed:", err);
      setError("Failed to initiate authentication. Please try again.");
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-white font-sans text-slate-900">
      {/* Left Panel - Brand & Value Prop */}
      <div className="hidden lg:flex lg:w-1/2 bg-slate-950 relative overflow-hidden flex-col justify-between p-12 lg:p-24">
        {/* Subtle dot matrix background for a technical feel */}
        <div
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
            backgroundSize: "24px 24px",
          }}
        ></div>

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-16">
            {/* Premium Monogram Logo */}
            <div className="w-10 h-10 bg-white text-slate-950 rounded-lg flex items-center justify-center font-bold text-xl shadow-sm">
              G
            </div>
            <span className="text-white font-medium text-2xl tracking-tight">
              Gatekeeper
            </span>
          </div>

          <h1 className="text-4xl lg:text-5xl font-medium text-white leading-[1.15] tracking-tight max-w-lg mb-6">
            Automated code review for high-velocity teams.
          </h1>
          <p className="text-slate-400 text-lg max-w-md leading-relaxed">
            Connect your GitLab repositories and let Gatekeeper analyze, review,
            and approve your merge requests in real-time.
          </p>
        </div>

        <div className="relative z-10 text-slate-500 text-sm font-medium">
          &copy; {new Date().getFullYear()} Gatekeeper Systems Inc.
        </div>
      </div>

      {/* Right Panel - Authentication */}
      <div className="flex flex-1 flex-col justify-center px-8 sm:px-12 lg:px-24 bg-white relative">
        <div className="w-full max-w-sm mx-auto">
          {/* Mobile-only logo */}
          <div className="lg:hidden flex items-center gap-2 mb-12">
            <div className="w-8 h-8 bg-slate-900 text-white rounded-md flex items-center justify-center font-bold text-lg">
              G
            </div>
            <span className="text-slate-900 font-medium text-xl tracking-tight">
              Gatekeeper
            </span>
          </div>

          <div className="mb-10">
            <h2 className="text-3xl font-semibold tracking-tight text-slate-900 mb-3">
              Welcome back
            </h2>
            <p className="text-slate-500 text-base">
              Sign in to manage your repository integrations.
            </p>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Upgraded Action Section */}
          <div className="space-y-4">
            <button
              onClick={handleGitLabLogin}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-3 bg-[#FC6D26] hover:bg-[#E24329] text-white font-semibold py-3.5 px-4 rounded-lg transition-all duration-200 transform hover:-translate-y-[1px] shadow-[0_4px_14px_0_rgba(252,109,38,0.39)] hover:shadow-[0_6px_20px_rgba(252,109,38,0.23)] focus:outline-none focus:ring-2 focus:ring-[#FC6D26] focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
            >
              {isLoading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Connecting...
                </>
              ) : (
                <>
                  {/* GitLab SVG Icon (Changed to white for contrast) */}
                  <svg
                    className="w-5 h-5 text-white"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  >
                    <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                  </svg>
                  Continue with GitLab
                </>
              )}
            </button>
          </div>

          {/* Divider line for visual balance */}
          <div className="relative my-8">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-slate-400">
                Secure connection
              </span>
            </div>
          </div>

          <div className="text-center text-sm text-slate-500">
            By signing in, you agree to our{" "}
            <a
              href="#"
              className="text-slate-900 font-medium hover:underline transition-colors"
            >
              Terms of Service
            </a>{" "}
            and{" "}
            <a
              href="#"
              className="text-slate-900 font-medium hover:underline transition-colors"
            >
              Privacy Policy
            </a>
            .
          </div>
        </div>
      </div>
    </div>
  );
};

export default GatekeeperEnterpriseLogin;
