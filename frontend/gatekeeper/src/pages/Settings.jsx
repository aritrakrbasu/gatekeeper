import React, { useState } from "react";

const Settings = () => {
  // State for the Gemini Token configuration
  const [token, setToken] = useState("AIzaSyD-XXXXXXXXXXXXXXXXXXXXX");
  const [isTokenVisible, setIsTokenVisible] = useState(false);
  const [tokenStatus, setTokenStatus] = useState("verified"); // 'empty', 'unverified', 'verified', 'verifying'
  const [selectedModel, setSelectedModel] = useState("gemini-1.5-pro");

  const [toggles, setToggles] = useState({
    autoReview: true,
    strictMode: false,
    emailAlerts: true,
    slackIntegration: false,
  });

  const handleVerifyToken = () => {
    setTokenStatus("verifying");
    // Simulate API call
    setTimeout(() => {
      setTokenStatus("verified");
    }, 1500);
  };

  const handleToggle = (key) => {
    setToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-8">
      {/* Header & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">
            Settings
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage your integrations, AI engine parameters, and global policies.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button className="bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 px-5 rounded-2xl transition-all shadow-md flex items-center gap-2 text-sm">
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
                d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"
              />
            </svg>
            Save Changes
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* -----------------------------------------
            LEFT COLUMN (Wider)
            ----------------------------------------- */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* PRIMARY: Gemini AI Engine Configuration Card (Dark Theme) */}
          <div className="bg-slate-950 rounded-[2rem] border border-slate-800 shadow-xl p-6 md:p-8 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-[#FC6D26]/10 to-transparent"></div>
            <div
              className="absolute inset-0 opacity-10"
              style={{
                backgroundImage: `radial-gradient(circle at 1px 1px, white 1px, transparent 0)`,
                backgroundSize: "16px 16px",
              }}
            ></div>

            <div className="relative z-10 flex items-center gap-3 mb-6 border-b border-slate-800/80 pb-5">
              <div className="w-12 h-12 rounded-2xl bg-[#FC6D26]/10 border border-[#FC6D26]/20 flex items-center justify-center shrink-0">
                {/* Abstract Sparkle/AI Icon */}
                <svg
                  className="w-6 h-6 text-[#FC6D26]"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-bold text-white tracking-tight">
                  Gemini AI Engine
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Configure the core model used for Gatekeeper's code review and
                  auto-fixes.
                </p>
              </div>
            </div>

            <div className="relative z-10 space-y-6">
              {/* API Token Input */}
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-sm font-semibold text-slate-300">
                    Google Gemini API Key
                  </label>
                  {tokenStatus === "verified" && (
                    <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      <svg
                        className="w-3 h-3"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="3"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      Connected
                    </span>
                  )}
                </div>

                <div className="relative flex items-center">
                  <div className="absolute left-3.5 text-slate-500 flex items-center">
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"
                      />
                    </svg>
                  </div>
                  <input
                    type={isTokenVisible ? "text" : "password"}
                    value={token}
                    onChange={(e) => {
                      setToken(e.target.value);
                      setTokenStatus("unverified");
                    }}
                    className={`w-full pl-11 pr-24 py-3 bg-slate-900 border rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#FC6D26]/50 transition-all ${tokenStatus === "verified" ? "border-emerald-500/30 text-emerald-100" : "border-slate-700 text-slate-200"}`}
                    placeholder="AIzaSy..."
                  />
                  <div className="absolute right-2 flex items-center gap-1">
                    <button
                      onClick={() => setIsTokenVisible(!isTokenVisible)}
                      className="p-1.5 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-slate-800"
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
                            strokeWidth="2"
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
                            strokeWidth="2"
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                      )}
                    </button>
                    <button
                      onClick={handleVerifyToken}
                      disabled={tokenStatus === "verifying" || !token}
                      className="bg-[#FC6D26] hover:bg-[#E24329] disabled:bg-slate-700 disabled:text-slate-400 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-all"
                    >
                      {tokenStatus === "verifying" ? "Verifying..." : "Verify"}
                    </button>
                  </div>
                </div>
              </div>

              {/* Model Selection */}
              <div>
                <label className="text-sm font-semibold text-slate-300 block mb-2">
                  Primary Analysis Model
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div
                    onClick={() => setSelectedModel("gemini-1.5-pro")}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedModel === "gemini-1.5-pro" ? "bg-[#FC6D26]/10 border-[#FC6D26] shadow-[0_0_15px_rgba(252,109,38,0.15)]" : "bg-slate-900 border-slate-700 hover:border-slate-500"}`}
                  >
                    <div className="flex justify-between items-center mb-1">
                      <h4
                        className={`text-sm font-bold ${selectedModel === "gemini-1.5-pro" ? "text-[#FC6D26]" : "text-slate-200"}`}
                      >
                        Gemini 1.5 Pro
                      </h4>
                      {selectedModel === "gemini-1.5-pro" && (
                        <div className="w-2 h-2 rounded-full bg-[#FC6D26]"></div>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">
                      Maximum reasoning capability. Best for deep architecture
                      and security reviews.
                    </p>
                  </div>

                  <div
                    onClick={() => setSelectedModel("gemini-1.5-flash")}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedModel === "gemini-1.5-flash" ? "bg-[#FC6D26]/10 border-[#FC6D26] shadow-[0_0_15px_rgba(252,109,38,0.15)]" : "bg-slate-900 border-slate-700 hover:border-slate-500"}`}
                  >
                    <div className="flex justify-between items-center mb-1">
                      <h4
                        className={`text-sm font-bold ${selectedModel === "gemini-1.5-flash" ? "text-[#FC6D26]" : "text-slate-200"}`}
                      >
                        Gemini 1.5 Flash
                      </h4>
                      {selectedModel === "gemini-1.5-flash" && (
                        <div className="w-2 h-2 rounded-full bg-[#FC6D26]"></div>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">
                      High velocity and low latency. Best for fast linting and
                      minor chore updates.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <p className="text-xs text-slate-500 italic flex items-center gap-1.5">
                  <svg
                    className="w-4 h-4 text-slate-400"
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
                  Your API token is encrypted at rest and never shared with
                  third parties.
                </p>
              </div>
            </div>
          </div>

          {/* General Settings / Preferences */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 md:p-8">
            <h3 className="text-lg font-bold text-slate-900 mb-6">
              Global Policies & Preferences
            </h3>

            <div className="space-y-4">
              {/* Toggle 1 */}
              <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 bg-white shadow-sm hover:shadow-md transition-shadow">
                <div>
                  <h4 className="text-sm font-bold text-slate-900">
                    Auto-Review on Creation
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Automatically trigger Gatekeeper AI when a new MR is opened
                    in any repository.
                  </p>
                </div>
                <button
                  onClick={() => handleToggle("autoReview")}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${toggles.autoReview ? "bg-[#FC6D26]" : "bg-slate-200"}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${toggles.autoReview ? "translate-x-6" : "translate-x-1"}`}
                  />
                </button>
              </div>

              {/* Toggle 2 */}
              <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 bg-white shadow-sm hover:shadow-md transition-shadow">
                <div>
                  <h4 className="text-sm font-bold text-slate-900">
                    Strict Mode (Block on Warning)
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Prevent merging if Gatekeeper identifies non-critical
                    warnings or tech debt.
                  </p>
                </div>
                <button
                  onClick={() => handleToggle("strictMode")}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${toggles.strictMode ? "bg-[#FC6D26]" : "bg-slate-200"}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${toggles.strictMode ? "translate-x-6" : "translate-x-1"}`}
                  />
                </button>
              </div>

              {/* Toggle 3 */}
              <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 bg-white shadow-sm hover:shadow-md transition-shadow">
                <div>
                  <h4 className="text-sm font-bold text-slate-900">
                    Critical Alert Emails
                  </h4>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Send an email to the repository owner when a severe
                    vulnerability is flagged.
                  </p>
                </div>
                <button
                  onClick={() => handleToggle("emailAlerts")}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${toggles.emailAlerts ? "bg-emerald-500" : "bg-slate-200"}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${toggles.emailAlerts ? "translate-x-6" : "translate-x-1"}`}
                  />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* -----------------------------------------
            RIGHT COLUMN (Narrower)
            ----------------------------------------- */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Profile Card */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 md:p-8 flex flex-col items-center text-center">
            <div className="relative group mb-4">
              <div className="w-24 h-24 rounded-[1.5rem] bg-slate-200 border-4 border-white shadow-md overflow-hidden relative">
                <img
                  src="https://api.dicebear.com/7.x/notionists/svg?seed=Felix"
                  alt="User Avatar"
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 bg-slate-900/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer">
                  <svg
                    className="w-6 h-6 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                </div>
              </div>
              <div className="absolute -bottom-2 -right-2 bg-emerald-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full border-2 border-white shadow-sm">
                Pro Plan
              </div>
            </div>

            <h2 className="text-xl font-bold text-slate-900">John Doe</h2>
            <p className="text-sm text-slate-500 mb-6">john.doe@company.com</p>

            <button className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold rounded-xl transition-colors border border-slate-200">
              Manage Account
            </button>
          </div>

          {/* GitLab Integration Card */}
          <div className="bg-white/70 backdrop-blur-xl rounded-[2rem] border border-white/80 shadow-sm p-6 md:p-8">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold text-slate-900">Connections</h3>
            </div>

            <div className="p-4 rounded-xl border border-[#FC6D26]/20 bg-[#FC6D26]/5 flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white border border-[#FC6D26]/20 shadow-sm flex items-center justify-center shrink-0">
                  <svg
                    className="w-6 h-6 text-[#FC6D26]"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  >
                    <path d="M23.955 13.587l-1.342-4.135-2.664-8.189c-.135-.423-.73-.423-.867 0L16.418 9.45H7.582L4.919 1.263c-.137-.423-.733-.423-.868 0L1.387 9.452.045 13.587c-.121.374.016.786.335 1.018l11.62 8.442 11.62-8.442c.319-.232.456-.644.335-1.018z" />
                  </svg>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900">
                    GitLab Enterprise
                  </h4>
                  <p className="text-xs text-slate-500">
                    Connected to @johndoe_ent
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="flex-1 py-2 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg transition-colors border border-slate-200 shadow-sm">
                  Re-sync
                </button>
                <button className="flex-1 py-2 bg-rose-50 hover:bg-rose-100 text-rose-600 text-xs font-semibold rounded-lg transition-colors border border-rose-200">
                  Disconnect
                </button>
              </div>
            </div>

            <div className="mt-4 p-4 rounded-xl border border-slate-100 bg-white flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 shadow-sm flex items-center justify-center shrink-0">
                  <svg
                    className="w-5 h-5 text-slate-400"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  >
                    <path d="M2.001 8h20v14h-20V8zm2-2h16V4h-16v2zm4 4v2h2v-2h-2zm-2-6h12V2h-12v2zm-4 4h20V8h-20v2z" />{" "}
                    {/* Simplified Slack-ish box icon */}
                  </svg>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900">
                    Email Notifications
                  </h4>
                  <p className="text-xs text-slate-500">Not connected</p>
                </div>
              </div>
              <button className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors">
                Connect
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
