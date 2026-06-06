import { useState } from "react";
import {
  useSentryIntegration,
  useConnectSentry,
  useDisconnectSentry,
} from "../services/queries";

/**
 * SentryIntegration Component
 *
 * Displays Sentry integration status for a repository and provides
 * connect/disconnect functionality via OAuth flow.
 */
export function SentryIntegration({ repoId }) {
  const { data: status, isLoading, error } = useSentryIntegration(repoId);
  const connectMutation = useConnectSentry();
  const disconnectMutation = useDisconnectSentry();
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [showSetupInstructions, setShowSetupInstructions] = useState(false);

  const handleConnect = async () => {
    setErrorMessage(null);
    try {
      console.log(
        "[Frontend DEBUG] Starting Sentry OAuth connection for repo:",
        repoId,
      );
      const result = await connectMutation.mutateAsync(repoId);
      console.log("[Frontend DEBUG] Received result from backend:", result);
      console.log("[Frontend DEBUG] OAuth URL:", result?.oauth_url);
      // Redirect to Sentry OAuth URL
      if (result?.oauth_url) {
        console.log("[Frontend DEBUG] Redirecting to:", result.oauth_url);
        window.location.href = result.oauth_url;
      } else {
        console.error("[Frontend DEBUG] No oauth_url in result!");
        setErrorMessage("No OAuth URL received from server");
      }
    } catch (err) {
      setErrorMessage(err.message || "Failed to connect Sentry");
      console.error("Sentry connection error:", err);
    }
  };

  const handleDisconnect = async () => {
    setErrorMessage(null);
    try {
      await disconnectMutation.mutateAsync(repoId);
    } catch (err) {
      setErrorMessage(err.message || "Failed to disconnect Sentry");
      console.error("Sentry disconnection error:", err);
    }
  };

  if (isLoading) {
    return (
      <div className="bg-white/70 backdrop-blur-xl border border-slate-200/60 rounded-[1.5rem] p-6 shadow-sm relative overflow-hidden">
        <div className="animate-pulse flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-slate-200/50 rounded-xl"></div>
              <div className="space-y-2">
                <div className="h-5 bg-slate-200/50 rounded w-32"></div>
                <div className="h-3 bg-slate-200/50 rounded w-48"></div>
              </div>
            </div>
            <div className="h-8 bg-slate-200/50 rounded-full w-24"></div>
          </div>
          <div className="h-24 bg-slate-100/50 rounded-xl w-full"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-rose-50 border border-rose-200 rounded-[1.5rem] p-6 shadow-sm flex items-start gap-4">
        <svg
          className="w-6 h-6 text-rose-500 shrink-0 mt-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div>
          <h3 className="text-sm font-bold text-rose-800 mb-1">
            Integration Error
          </h3>
          <p className="text-sm text-rose-600">
            Failed to load Sentry integration status.
          </p>
        </div>
      </div>
    );
  }

  const isConnected = status?.connected || false;
  const webhookRegistered = status?.webhook_registered || false;

  return (
    <div className="bg-white/70 backdrop-blur-xl border border-slate-200/60 rounded-[1.5rem] p-6 shadow-sm relative overflow-hidden">
      {/* Subtle background decoration */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none -translate-y-1/2 translate-x-1/4"></div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 relative z-10">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-[#362D59] rounded-xl flex items-center justify-center shadow-md shrink-0">
            <svg
              className="w-7 h-7 text-white"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z" />
            </svg>
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-lg leading-tight">
              Sentry Telemetry
            </h3>
            <p className="text-xs font-medium text-slate-500 mt-0.5">
              Automated auto-fixes for production exceptions
            </p>
          </div>
        </div>

        {/* Status Badge */}
        <div className="shrink-0">
          {isConnected ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-100 text-emerald-700 text-[11px] font-bold uppercase tracking-wider rounded-full shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              Connected
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 border border-slate-200 text-slate-500 text-[11px] font-bold uppercase tracking-wider rounded-full shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
              Not Connected
            </span>
          )}
        </div>
      </div>

      <div className="relative z-10">
        {/* Connected State */}
        {isConnected ? (
          <div className="space-y-5">
            <div className="bg-slate-50 border border-slate-100 rounded-xl p-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-y-4 gap-x-6">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                      />
                    </svg>
                    Organization
                  </span>
                  <span className="text-sm font-semibold text-slate-900 ml-5">
                    {status?.org_slug || "N/A"}
                  </span>
                </div>

                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                    Webhook Status
                  </span>
                  <div className="ml-5 flex items-center gap-3">
                    {webhookRegistered ? (
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-emerald-600 flex items-center gap-1.5">
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          </svg>
                          Active & Verified
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-blue-600 flex items-center gap-1.5">
                          <svg className="w-4 h-4 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                          </svg>
                          Waiting for first error...
                        </span>
                        <span className="text-[10px] text-blue-500">(auto-verifies on first event)</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Webhook Setup Instructions */}
                {(showSetupInstructions || !webhookRegistered) && status?.webhook_config && (
                  <div className="md:col-span-2 mt-4 p-4 bg-blue-50 border border-blue-200 rounded-xl">
                    <div className="flex items-start gap-3">
                      <div className="p-1.5 bg-blue-100 text-blue-600 rounded-md shrink-0">
                        <svg className="w-4 h-4 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-bold text-blue-900 mb-2">
                          Webhook Setup In Progress
                        </h4>
                        <p className="text-xs text-blue-700 mb-3 leading-relaxed">
                          We're waiting for the first error event from Sentry. Once received, we'll automatically verify
                          and activate the webhook for automated bug fixes.
                        </p>

                        {/* Setup Steps */}
                        <div className="space-y-3 mb-3">
                          {status.webhook_config.steps?.map((step) => (
                            <div key={step.step} className="flex gap-3">
                              <div className="flex-shrink-0 w-5 h-5 bg-blue-200 text-blue-800 rounded-full flex items-center justify-center text-[10px] font-bold">
                                {step.step}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold text-blue-900">{step.title}</p>
                                <p className="text-[10px] text-blue-700 mb-1">{step.description}</p>
                                {step.url && (
                                  <a
                                    href={step.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 text-[10px] text-indigo-600 hover:text-indigo-800 font-medium underline"
                                  >
                                    {step.action_text}
                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                    </svg>
                                  </a>
                                )}
                                {step.config_value && (
                                  <div className="mt-1 flex items-center gap-2">
                                    <span className="text-[10px] text-blue-600">{step.config_label}:</span>
                                    <code className="text-[10px] bg-white px-2 py-0.5 rounded border border-blue-300 text-slate-700 font-mono">
                                      {step.config_value}
                                    </code>
                                    <button
                                      onClick={() => navigator.clipboard.writeText(step.config_value)}
                                      className="text-blue-600 hover:text-blue-800"
                                      title="Copy to clipboard"
                                    >
                                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                      </svg>
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Auto-verification Note */}
                        <p className="text-[10px] text-blue-800 bg-blue-100 px-2 py-1.5 rounded mb-2">
                          <strong>Tip:</strong> After configuring the webhook in Sentry, trigger a test error in your application.
                          The status will automatically update to "Active & Verified" once we receive the first event.
                        </p>

                        {/* Troubleshooting */}
                        <details className="mt-2">
                          <summary className="text-[10px] text-blue-800 cursor-pointer hover:text-blue-900 font-medium">
                            Troubleshooting tips
                          </summary>
                          <ul className="mt-2 space-y-1 text-[10px] text-blue-700 pl-4">
                            {status.webhook_config.troubleshooting?.map((tip, idx) => (
                              <li key={idx}>• {tip}</li>
                            ))}
                          </ul>
                        </details>

                        <button
                          onClick={() => setShowSetupInstructions(false)}
                          className="mt-3 text-[10px] text-blue-700 hover:text-blue-900 font-medium"
                        >
                          Hide instructions
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {status?.connected_at && (
                  <div className="flex flex-col gap-1 md:col-span-2 pt-3 border-t border-slate-200/60">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                      <svg
                        className="w-3.5 h-3.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                        />
                      </svg>
                      Connection Established
                    </span>
                    <span className="text-sm font-medium text-slate-700 ml-5">
                      {new Date(status.connected_at).toLocaleDateString(
                        undefined,
                        { year: "numeric", month: "long", day: "numeric" },
                      )}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {errorMessage && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
                <svg
                  className="w-4 h-4 shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                {errorMessage}
                <button
                  onClick={() => setErrorMessage(null)}
                  className="ml-auto text-rose-600 hover:text-rose-800"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {successMessage && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
                <svg
                  className="w-4 h-4 shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                {successMessage}
                <button
                  onClick={() => setSuccessMessage(null)}
                  className="ml-auto text-emerald-600 hover:text-emerald-800"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            <div className="pt-2">
              <button
                onClick={handleDisconnect}
                disabled={disconnectMutation.isLoading}
                className="w-full py-2.5 px-4 bg-white border border-slate-200 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-600 text-slate-700 text-sm font-bold rounded-xl transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 group"
              >
                {disconnectMutation.isLoading ? (
                  <div className="w-4 h-4 border-2 border-slate-300 border-t-slate-700 rounded-full animate-spin"></div>
                ) : (
                  <svg
                    className="w-4 h-4 text-slate-400 group-hover:text-rose-500 transition-colors"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M13 7a4 4 0 11-8 0 4 4 0 018 0zM9 14a6 6 0 00-6 6v1h12v-1a6 6 0 00-6-6zM21 12h-6"
                    />
                  </svg>
                )}
                {disconnectMutation.isLoading
                  ? "Disconnecting..."
                  : "Disconnect Integration"}
              </button>
            </div>
          </div>
        ) : (
          /* Disconnected State */
          <div className="space-y-5">
            <p className="text-slate-600 text-sm leading-relaxed">
              Connect your Sentry organization to automatically detect
              production errors and exceptions. Gatekeeper will analyze the
              incoming stack traces and proactively generate draft merge
              requests to fix the bugs.
            </p>

            <div className="bg-indigo-50/50 border border-indigo-100 rounded-xl p-4 flex items-start gap-3">
              <div className="p-1 bg-indigo-100 text-indigo-600 rounded-md shrink-0">
                <svg
                  className="w-4 h-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <div className="text-xs text-indigo-900/80 leading-relaxed">
                <strong className="text-indigo-900 block mb-0.5">
                  Setup Required
                </strong>
                Ensure you have created a Sentry OAuth application and
                configured the correct redirect URI in your Sentry developer
                settings before connecting.
              </div>
            </div>

            {errorMessage && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl text-sm flex items-center gap-2">
                <svg
                  className="w-4 h-4 shrink-0"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                {errorMessage}
              </div>
            )}

            <div className="pt-2">
              <button
                onClick={handleConnect}
                disabled={connectMutation.isLoading}
                className="w-full py-3 px-4 bg-[#362D59] hover:bg-[#2b2447] text-white text-sm font-bold rounded-xl transition-all shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {connectMutation.isLoading ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        fill="none"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Connecting to Sentry...
                  </>
                ) : (
                  <>
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2.5}
                        d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
                      />
                    </svg>
                    Authorize Integration
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
