/**
 * Onboarding Component
 *
 * Shown after first login when Gemini API is not configured.
 * Collects user's Gemini API token and model preference.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useGeminiSettings,
  useUpdateGeminiSettings,
  useValidateGeminiToken,
  useUserProfile,
} from "../services/queries";

const Onboarding = () => {
  const navigate = useNavigate();

  // API hooks
  const { data: geminiSettings, isLoading: settingsLoading } =
    useGeminiSettings();
  const { data: userProfile } = useUserProfile();
  const updateGeminiMutation = useUpdateGeminiSettings();
  const validateTokenMutation = useValidateGeminiToken();

  // Local state
  const [step, setStep] = useState(1); // 1: Welcome, 2: API Token, 3: Model, 4: Complete
  const [tokenInput, setTokenInput] = useState("");
  const [isTokenVisible, setIsTokenVisible] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gemini-3.5-flash");
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);

  // If already configured, redirect to dashboard
  if (geminiSettings?.api_token_configured && step !== 4) {
    navigate("/dashboard");
    return null;
  }

  const handleVerifyToken = async () => {
    if (!tokenInput) {
      setValidationError("Please enter your API token");
      return;
    }

    setIsValidating(true);
    setValidationError(null);

    try {
      const result = await validateTokenMutation.mutateAsync(tokenInput);

      if (result.valid) {
        // Token is valid, proceed to model selection
        setStep(3);
      } else {
        setValidationError(result.message || "Token validation failed");
      }
    } catch (error) {
      setValidationError("Token validation failed: " + error.message);
    } finally {
      setIsValidating(false);
    }
  };

  const handleComplete = async () => {
    setIsSaving(true);

    try {
      await updateGeminiMutation.mutateAsync({
        api_token: tokenInput,
        selected_model: selectedModel,
      });

      setStep(4);

      // Redirect to dashboard after success
      setTimeout(() => {
        navigate("/dashboard");
      }, 2000);
    } catch (error) {
      setValidationError("Failed to save settings: " + error.message);
      setIsSaving(false);
    }
  };

  // Loading state
  if (settingsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F2F4F7]">
        <div className="relative">
          <div className="absolute inset-0 rounded-full blur-xl bg-[#FC6D26]/20 animate-pulse"></div>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26] relative z-10"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center bg-[#F2F4F7] p-4 font-sans selection:bg-[#FC6D26] selection:text-white overflow-hidden">
      {/* Ambient Background Glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[40rem] h-[40rem] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40rem] h-[40rem] bg-[#FC6D26]/10 rounded-full blur-[120px] pointer-events-none"></div>

      <div className="relative w-full max-w-2xl z-10 flex flex-col items-center">
        {/* Floating Progress Indicator */}
        <div className="bg-white/70 backdrop-blur-xl border border-white/80 shadow-[0_8px_32px_rgba(0,0,0,0.04)] px-6 py-3 rounded-full flex items-center justify-center gap-3 mb-8">
          {[1, 2, 3].map((s) => (
            <React.Fragment key={s}>
              <div
                className={`w-10 h-1.5 rounded-full transition-all duration-500 ${
                  s < step
                    ? "bg-[#FC6D26]"
                    : s === step
                      ? "bg-[#FC6D26] shadow-[0_0_10px_rgba(252,109,38,0.4)]"
                      : "bg-slate-200"
                }`}
              />
            </React.Fragment>
          ))}
        </div>

        {/* Main Glass Card */}
        <div className="w-full bg-white/70 backdrop-blur-2xl border border-white/80 rounded-[2.5rem] shadow-xl p-8 md:p-12 transition-all duration-300">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <div className="text-center animate-in fade-in zoom-in-95 duration-500">
              <div className="w-20 h-20 bg-white border border-[#FC6D26]/20 shadow-lg rounded-2xl flex items-center justify-center mx-auto mb-8 transform -rotate-3 hover:rotate-0 transition-transform">
                <svg
                  className="w-10 h-10 text-[#FC6D26]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
                  />
                </svg>
              </div>

              <h1 className="text-4xl font-bold text-slate-900 tracking-tight mb-3">
                Welcome to Gatekeeper
              </h1>

              {userProfile && (
                <p className="text-lg text-slate-500 mb-8 font-medium">
                  Nice to meet you,{" "}
                  <span className="text-slate-800">
                    {userProfile.name || userProfile.username}
                  </span>
                  !
                </p>
              )}

              <div className="text-left bg-white border border-slate-100 shadow-sm rounded-2xl p-6 mb-10">
                <h3 className="font-bold text-slate-900 mb-2 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#FC6D26]"></span>
                  Connect your AI Engine
                </h3>
                <p className="text-sm text-slate-500 mb-5 leading-relaxed">
                  Gatekeeper uses Google's Gemini AI to analyze your code and
                  suggest improvements. You'll need your own API key from Google
                  AI Studio to proceed.
                </p>
                <ul className="text-sm text-slate-600 space-y-3 font-medium">
                  <li className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-emerald-50 flex items-center justify-center shrink-0 border border-emerald-100">
                      <svg
                        className="w-3.5 h-3.5 text-emerald-500"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={3}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </div>
                    Your API key is encrypted and stored securely
                  </li>
                  <li className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-blue-50 flex items-center justify-center shrink-0 border border-blue-100">
                      <svg
                        className="w-3.5 h-3.5 text-blue-500"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2.5}
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        />
                      </svg>
                    </div>
                    You can change it anytime in Settings
                  </li>
                </ul>
              </div>

              <button
                onClick={() => setStep(2)}
                className="w-full bg-[#FC6D26] hover:bg-[#E24329] text-white font-semibold py-3.5 px-6 rounded-xl transition-all shadow-[0_4px_14px_0_rgba(252,109,38,0.39)] hover:shadow-[0_6px_20px_rgba(252,109,38,0.23)] transform hover:-translate-y-[1px]"
              >
                Let's Get Started
              </button>
            </div>
          )}

          {/* Step 2: API Token */}
          {step === 2 && (
            <div className="animate-in fade-in slide-in-from-right-8 duration-500">
              <button
                onClick={() => setStep(1)}
                className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 hover:text-slate-900 hover:shadow-md transition-all mb-6"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
              </button>

              <h2 className="text-3xl font-bold text-slate-900 tracking-tight mb-2">
                Enter your API Key
              </h2>
              <p className="text-slate-500 mb-8 leading-relaxed">
                Paste your API key from Google AI Studio. We'll verify the
                connection before continuing.
              </p>

              <div className="space-y-6">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <label className="text-sm font-bold text-slate-700 uppercase tracking-wide">
                      Gemini API Key
                    </label>
                  </div>
                  <div className="relative flex items-center shadow-sm rounded-xl group">
                    <div className="absolute left-4 text-slate-400">
                      <svg
                        className="w-5 h-5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
                        />
                      </svg>
                    </div>
                    <input
                      type={isTokenVisible ? "text" : "password"}
                      value={tokenInput}
                      onChange={(e) => {
                        setTokenInput(e.target.value);
                        setValidationError(null);
                      }}
                      placeholder="AIzaSy..."
                      className={`w-full pl-12 pr-12 py-3.5 bg-white border rounded-xl text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/50 transition-all ${
                        validationError
                          ? "border-rose-300 focus:ring-rose-500/50 bg-rose-50/50"
                          : "border-slate-200 group-hover:border-slate-300"
                      }`}
                    />
                    <button
                      onClick={() => setIsTokenVisible(!isTokenVisible)}
                      className="absolute right-3 p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
                    >
                      {isTokenVisible ? (
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                      )}
                    </button>
                  </div>

                  {validationError && (
                    <div className="flex items-center gap-1.5 mt-2 text-rose-500 animate-in fade-in slide-in-from-top-1">
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      <p className="text-sm font-medium">{validationError}</p>
                    </div>
                  )}
                </div>

                <button
                  onClick={handleVerifyToken}
                  disabled={isValidating || !tokenInput}
                  className="w-full bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none text-white font-semibold py-3.5 px-6 rounded-xl transition-all shadow-md flex items-center justify-center gap-2 mt-4"
                >
                  {isValidating ? (
                    <>
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                      Verifying Connection...
                    </>
                  ) : (
                    "Verify & Continue"
                  )}
                </button>
              </div>

              <div className="mt-8 text-center">
                <a
                  href="https://ai.google.dev/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#FC6D26] hover:text-[#E24329] transition-colors"
                >
                  Don't have an API key? Get one free
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                </a>
              </div>
            </div>
          )}

          {/* Step 3: Model Selection */}
          {step === 3 && (
            <div className="animate-in fade-in slide-in-from-right-8 duration-500">
              <button
                onClick={() => setStep(2)}
                className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center text-slate-400 hover:text-slate-900 hover:shadow-md transition-all mb-6"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
              </button>

              <h2 className="text-3xl font-bold text-slate-900 tracking-tight mb-2">
                Choose Analysis Model
              </h2>
              <p className="text-slate-500 mb-8 leading-relaxed">
                Select the Gemini AI tier that best fits your codebase
                requirements. This can be updated later.
              </p>

              <div className="grid grid-cols-1 gap-4 mb-8">
                {/* Gemini 3.5 Flash */}
                <div
                  onClick={() => setSelectedModel("gemini-3.5-flash")}
                  className={`p-6 rounded-[1.5rem] border-2 cursor-pointer transition-all ${
                    selectedModel === "gemini-3.5-flash"
                      ? "bg-white border-[#FC6D26] shadow-[0_8px_24px_rgba(252,109,38,0.15)] transform -translate-y-1"
                      : "bg-white/50 border-white hover:border-slate-200 hover:bg-white hover:shadow-sm"
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center ${selectedModel === "gemini-3.5-flash" ? "bg-[#FC6D26]/10" : "bg-slate-100"}`}
                      >
                        <svg
                          className={`w-5 h-5 ${selectedModel === "gemini-3.5-flash" ? "text-[#FC6D26]" : "text-slate-500"}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13 10V3L4 14h7v7l9-11h-7z"
                          />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">
                          Gemini 3.5 Flash
                        </h3>
                        <p className="text-xs font-bold uppercase tracking-wider text-[#FC6D26] mt-0.5">
                          Recommended
                        </p>
                      </div>
                    </div>

                    <div
                      className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${selectedModel === "gemini-3.5-flash" ? "border-[#FC6D26] bg-[#FC6D26]" : "border-slate-300"}`}
                    >
                      {selectedModel === "gemini-3.5-flash" && (
                        <svg
                          className="w-3.5 h-3.5 text-white"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={3}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-slate-600 mt-3 ml-13 pl-13 leading-relaxed">
                    Fast and highly efficient model optimized for low-latency
                    code reviews, quick linting, and standard PR automated
                    checks.
                  </p>
                </div>

                {/* Gemini 3.1 Pro Preview */}
                <div
                  onClick={() => setSelectedModel("gemini-3.1-pro-preview")}
                  className={`p-6 rounded-[1.5rem] border-2 cursor-pointer transition-all ${
                    selectedModel === "gemini-3.1-pro-preview"
                      ? "bg-white border-slate-900 shadow-[0_8px_24px_rgba(0,0,0,0.12)] transform -translate-y-1"
                      : "bg-white/50 border-white hover:border-slate-200 hover:bg-white hover:shadow-sm"
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center ${selectedModel === "gemini-3.1-pro-preview" ? "bg-slate-900" : "bg-slate-100"}`}
                      >
                        <svg
                          className={`w-5 h-5 ${selectedModel === "gemini-3.1-pro-preview" ? "text-white" : "text-slate-500"}`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                          />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">
                          Gemini 3.1 Pro
                        </h3>
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mt-0.5">
                          Enterprise Tier
                        </p>
                      </div>
                    </div>

                    <div
                      className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${selectedModel === "gemini-3.1-pro-preview" ? "border-slate-900 bg-slate-900" : "border-slate-300"}`}
                    >
                      {selectedModel === "gemini-3.1-pro-preview" && (
                        <svg
                          className="w-3.5 h-3.5 text-white"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={3}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-slate-600 mt-3 ml-13 pl-13 leading-relaxed">
                    Maximum reasoning capability. Required for complex
                    architectural reviews, cross-file security vulnerability
                    analysis, and deep logic bugs.
                  </p>
                </div>
              </div>

              <button
                onClick={handleComplete}
                disabled={isSaving}
                className="w-full bg-[#FC6D26] hover:bg-[#E24329] disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed disabled:shadow-none text-white font-semibold py-3.5 px-6 rounded-xl transition-all shadow-[0_4px_14px_0_rgba(252,109,38,0.39)] hover:shadow-[0_6px_20px_rgba(252,109,38,0.23)] flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                    Configuring Gatekeeper...
                  </>
                ) : (
                  "Complete Setup"
                )}
              </button>
            </div>
          )}

          {/* Step 4: Complete */}
          {step === 4 && (
            <div className="text-center py-12 animate-in zoom-in-95 fade-in duration-500">
              <div className="relative w-24 h-24 mx-auto mb-8">
                <div className="absolute inset-0 bg-emerald-500/20 rounded-full blur-xl animate-pulse"></div>
                <div className="relative w-24 h-24 bg-emerald-500 border-4 border-white shadow-xl rounded-full flex items-center justify-center">
                  <svg
                    className="w-12 h-12 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={3}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                </div>
              </div>

              <h2 className="text-3xl font-bold text-slate-900 tracking-tight mb-3">
                Setup Complete
              </h2>
              <p className="text-lg text-slate-500 mb-8 font-medium">
                Gatekeeper AI is now armed and ready.
              </p>

              <div className="flex items-center justify-center gap-2 text-sm font-bold uppercase tracking-widest text-[#FC6D26] animate-pulse">
                <div className="w-1.5 h-1.5 rounded-full bg-[#FC6D26]"></div>
                Initializing Workspace...
              </div>
            </div>
          )}
        </div>

        {/* Footer note */}
        {step < 4 && (
          <div className="mt-8 flex items-center justify-center gap-2 text-xs font-medium text-slate-400">
            <svg
              className="w-4 h-4 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
            API configuration is securely encrypted.
            <a
              href="https://ai.google.dev/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-600 hover:text-[#FC6D26] hover:underline ml-1 transition-colors"
            >
              Read our security docs.
            </a>
          </div>
        )}
      </div>
    </div>
  );
};

export default Onboarding;
