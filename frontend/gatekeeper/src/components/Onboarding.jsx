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
  useUserProfile
} from "../services/queries";

const Onboarding = () => {
  const navigate = useNavigate();

  // API hooks
  const { data: geminiSettings, isLoading: settingsLoading } = useGeminiSettings();
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
        selected_model: selectedModel
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26]"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F2F4F7] p-4">
      <div className="w-full max-w-2xl">
        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {[1, 2, 3].map((s) => (
            <React.Fragment key={s}>
              <div
                className={`w-8 h-1 rounded-full transition-colors ${
                  s <= step ? "bg-[#FC6D26]" : "bg-slate-200"
                }`}
              />
            </React.Fragment>
          ))}
        </div>

        {/* Card */}
        <div className="bg-white rounded-[2rem] shadow-xl p-8 md:p-12">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <div className="text-center">
              <div className="w-20 h-20 bg-[#FC6D26]/10 rounded-full flex items-center justify-center mx-auto mb-6">
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

              <h1 className="text-3xl font-bold text-slate-900 mb-4">
                Welcome to Gatekeeper
              </h1>

              {userProfile && (
                <p className="text-slate-500 mb-8">
                  Nice to meet you, {userProfile.name || userProfile.username}!
                </p>
              )}

              <div className="text-left bg-slate-50 rounded-xl p-6 mb-8">
                <h3 className="font-semibold text-slate-900 mb-3">
                  Before we get started, we need your Gemini API key
                </h3>
                <p className="text-sm text-slate-500 mb-3">
                  Gatekeeper uses Google's Gemini AI to analyze your code and suggest improvements.
                  You'll need your own API key from Google AI Studio.
                </p>
                <ul className="text-sm text-slate-500 space-y-2">
                  <li className="flex items-start gap-2">
                    <svg className="w-4 h-4 text-[#FC6D26] mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Your API key is encrypted and stored securely
                  </li>
                  <li className="flex items-start gap-2">
                    <svg className="w-4 h-4 text-[#FC6D26] mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    You can change it anytime in Settings
                  </li>
                  <li className="flex items-start gap-2">
                    <svg className="w-4 h-4 text-[#FC6D26] mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Get one for free at ai.google.dev
                  </li>
                </ul>
              </div>

              <button
                onClick={() => setStep(2)}
                className="w-full bg-[#FC6D26] hover:bg-[#E24329] text-white font-semibold py-3 px-6 rounded-xl transition-all shadow-lg"
              >
                Let's Get Started
              </button>
            </div>
          )}

          {/* Step 2: API Token */}
          {step === 2 && (
            <div>
              <button
                onClick={() => setStep(1)}
                className="text-slate-400 hover:text-slate-600 text-sm flex items-center gap-1 mb-6"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>

              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                Enter your Gemini API Key
              </h2>
              <p className="text-slate-500 mb-6">
                Paste your API key from Google AI Studio. We'll verify it works before saving.
              </p>

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-semibold text-slate-700 block mb-2">
                    Gemini API Key
                  </label>
                  <div className="relative">
                    <input
                      type={isTokenVisible ? "text" : "password"}
                      value={tokenInput}
                      onChange={(e) => {
                        setTokenInput(e.target.value);
                        setValidationError(null);
                      }}
                      placeholder="AIzaSy..."
                      className={`w-full px-4 py-3 bg-slate-50 border rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/50 transition-all ${
                        validationError ? "border-red-300" : "border-slate-200"
                      }`}
                    />
                    <button
                      onClick={() => setIsTokenVisible(!isTokenVisible)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      {isTokenVisible ? (
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        </svg>
                      )}
                    </button>
                  </div>

                  {validationError && (
                    <p className="text-red-500 text-sm mt-2">{validationError}</p>
                  )}
                </div>

                <button
                  onClick={handleVerifyToken}
                  disabled={isValidating || !tokenInput}
                  className="w-full bg-[#FC6D26] hover:bg-[#E24329] disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed text-white font-semibold py-3 px-6 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2"
                >
                  {isValidating ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Verifying...
                    </>
                  ) : (
                    "Verify & Continue"
                  )}
                </button>
              </div>

              <div className="mt-6 text-center">
                <a
                  href="https://ai.google.dev/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[#FC6D26] hover:underline"
                >
                  Don't have an API key? Get one free →
                </a>
              </div>
            </div>
          )}

          {/* Step 3: Model Selection */}
          {step === 3 && (
            <div>
              <button
                onClick={() => setStep(2)}
                className="text-slate-400 hover:text-slate-600 text-sm flex items-center gap-1 mb-6"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>

              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                Choose your preferred model
              </h2>
              <p className="text-slate-500 mb-6">
                Select the Gemini model that best fits your needs. You can change this later in Settings.
              </p>

              <div className="grid grid-cols-1 gap-4 mb-8">
                {/* Gemini 3.5 Flash */}
                <div
                  onClick={() => setSelectedModel("gemini-3.5-flash")}
                  className={`p-5 rounded-xl border-2 cursor-pointer transition-all ${
                    selectedModel === "gemini-3.5-flash"
                      ? "bg-[#FC6D26]/5 border-[#FC6D26]"
                      : "bg-slate-50 border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-bold text-slate-900">Gemini 3.5 Flash</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        Recommended for most users
                      </p>
                    </div>
                    {selectedModel === "gemini-3.5-flash" && (
                      <div className="w-5 h-5 rounded-full bg-[#FC6D26] flex items-center justify-center">
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    )}
                  </div>
                  <p className="text-sm text-slate-600">
                    Fast and efficient. Great for quick code reviews, linting, and everyday use.
                  </p>
                </div>

                {/* Gemini 3.1 Pro Preview */}
                <div
                  onClick={() => setSelectedModel("gemini-3.1-pro-preview")}
                  className={`p-5 rounded-xl border-2 cursor-pointer transition-all ${
                    selectedModel === "gemini-3.1-pro-preview"
                      ? "bg-[#FC6D26]/5 border-[#FC6D26]"
                      : "bg-slate-50 border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-bold text-slate-900">Gemini 3.1 Pro Preview</h3>
                      <p className="text-xs text-slate-500 mt-1">
                        For complex codebases
                      </p>
                    </div>
                    {selectedModel === "gemini-3.1-pro-preview" && (
                      <div className="w-5 h-5 rounded-full bg-[#FC6D26] flex items-center justify-center">
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    )}
                  </div>
                  <p className="text-sm text-slate-600">
                    Maximum reasoning capability. Best for deep architecture reviews and security analysis.
                  </p>
                </div>
              </div>

              <button
                onClick={handleComplete}
                disabled={isSaving}
                className="w-full bg-[#FC6D26] hover:bg-[#E24329] disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed text-white font-semibold py-3 px-6 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2"
              >
                {isSaving ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Saving...
                  </>
                ) : (
                  "Complete Setup"
                )}
              </button>
            </div>
          )}

          {/* Step 4: Complete */}
          {step === 4 && (
            <div className="text-center py-8">
              <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg
                  className="w-10 h-10 text-emerald-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>

              <h2 className="text-2xl font-bold text-slate-900 mb-2">
                You're all set!
              </h2>
              <p className="text-slate-500 mb-6">
                Gatekeeper is ready to help you review code.
              </p>

              <p className="text-sm text-slate-400">
                Redirecting to dashboard...
              </p>
            </div>
          )}
        </div>

        {/* Footer note */}
        {step < 4 && (
          <p className="text-center text-xs text-slate-400 mt-6">
            Your API key is encrypted at rest. Need help?{" "}
            <a href="https://ai.google.dev/docs" target="_blank" rel="noopener noreferrer" className="text-[#FC6D26] hover:underline">
              Get your API key here
            </a>
          </p>
        )}
      </div>
    </div>
  );
};

export default Onboarding;
