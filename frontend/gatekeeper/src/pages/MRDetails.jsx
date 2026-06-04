import React, { useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams, useNavigate } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import { useWebSocketProgress } from "../hooks/useWebSocketProgress";
import {
  useRepository,
  useRepositoryMRs,
  useSubmitFeedback,
} from "../services/queries";

const MRDetails = () => {
  const { repoId, mrId } = useParams();
  const navigate = useNavigate();
  const chatEndRef = useRef(null);

  const [feedback, setFeedback] = useState({
    vote: null,
    text: "",
    submitted: false,
  });
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [activeTab, setActiveTab] = useState("context"); // 'context', 'cve', 'logs'
  const [isResolving, setIsResolving] = useState(false);

  // NEW: Track the iteration of the AI's fix
  const [diffVersion, setDiffVersion] = useState("v1");

  // Fetch repository details & MRs
  const {
    data: repo,
    isLoading: repoLoading,
    error: repoError,
  } = useRepository(repoId);
  const {
    data: repoMRs = [],
    isLoading: mrsLoading,
    refetch,
  } = useRepositoryMRs(repoId);
  const feedbackMutation = useSubmitFeedback();

  const currentMR = repoMRs.find(
    (mr) => String(mr.iid || mr.gitlab_mr_id) === String(mrId),
  );

  // Determine if MR is currently being reviewed
  const isReviewing =
    currentMR?.status === "reviewing" || currentMR?.status === "Reviewing";

  // Structured Workflow Conversation
  const [messages, setMessages] = useState([
    {
      id: "analysis",
      role: "assistant",
      type: "analysis",
      content:
        "**Security Alert:** I intercepted MR #493. The `deepMerge` utility allows arbitrary key assignment, leading to Prototype Pollution (CWE-1321).\n\n### Review Checklist\n- [x] Analyze AST for vulnerability\n- [x] Generate sanitized patch (Version 1)\n- [x] Run isolated unit tests (`passing`)\n- [ ] Await developer approval",
      issues: ["Unsanitized object assignment in utils/merge.js"],
      timestamp: "10:42 AM",
    },
  ]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  if (repoLoading || mrsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#FC6D26]"></div>
      </div>
    );
  }

  if (repoError || !currentMR) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 shadow-sm flex items-start gap-4">
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
            <h3 className="text-lg font-bold text-rose-800 mb-1">
              Workspace Unavailable
            </h3>
            <p className="text-sm text-rose-600 mb-4">
              {repoError?.message || "Merge request not found."}
            </p>
            <button
              onClick={() => navigate(`/repositories/${repoId}`)}
              className="px-4 py-2 bg-rose-600 text-white font-medium rounded-lg hover:bg-rose-700 transition-colors"
            >
              Back to Repository
            </button>
          </div>
        </div>
      </div>
    );
  }

  const handleSendMessage = (text = inputValue) => {
    if (!text.trim()) return;

    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: text, timestamp: "Now" },
    ]);
    setInputValue("");
    setIsTyping(true);

    // Simulate iterative workflow
    setTimeout(() => {
      let aiResponse =
        "I am analyzing the downstream impact. The `deepMerge` utility is imported in 3 config files. Modifying this signature will not break those downstream consumers.";
      let newVersion = diffVersion;

      if (text.toLowerCase().includes("error")) {
        aiResponse =
          "Understood. I have updated the patch to throw a `TypeError` instead of silently returning when a prototype key is detected. I have re-run the pipeline against this new patch. \n\n**Diff updated to v2.**";
        newVersion = "v2";
        setDiffVersion("v2");
      }

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: aiResponse,
          type: newVersion !== diffVersion ? "update" : "chat",
          timestamp: "Now",
        },
      ]);
      setIsTyping(false);
    }, 1500);
  };

  const handleAction = (actionType) => {
    setIsResolving(true);
    setTimeout(() => setIsResolving(false), 2000);
  };

  return (
    <React.Fragment>
      <ToastContainer position="top-right" autoClose={3000} theme="light" />

      {/* STRICT VIEWPORT HEIGHT CALCULATION */}
      <div className="flex flex-col w-full h-screen overflow-hidden px-4 md:px-8">
        {/* =========================================
            HEADER (Workflow Status)
            ========================================= */}
        <header className="shrink-0 bg-white/60 backdrop-blur-xl border border-white/80 rounded-[1.5rem] shadow-sm mb-4 p-4 lg:p-5 z-20">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs text-slate-500 mb-1.5 font-medium">
                <Link
                  to="/repositories"
                  className="hover:text-[#FC6D26] transition-colors"
                >
                  Repositories
                </Link>
                <span className="text-slate-300">/</span>
                <span className="text-slate-800 bg-white/80 px-2 py-0.5 rounded-md border border-slate-200 font-mono shadow-sm">
                  MR-{currentMR.iid || currentMR.gitlab_mr_id}
                </span>
              </div>
              <h1 className="text-lg lg:text-xl font-bold text-slate-900 flex items-center gap-3 truncate">
                <span className="truncate">{currentMR.title}</span>
                {currentMR.isAutoFix && (
                  <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-[#FC6D26]/10 text-[#FC6D26] rounded border border-[#FC6D26]/20 shrink-0">
                    Auto-Fix Generated
                  </span>
                )}
              </h1>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wide bg-blue-50 text-blue-600 border border-blue-100 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>{" "}
                Requires Review
              </span>
            </div>
          </div>
        </header>

        {/* =========================================
            SPLIT LAYOUT WORKSPACE
            ========================================= */}
        <div className="flex-1 flex flex-col lg:flex-row gap-4 min-h-0 pb-2">
          {/* -----------------------------------------
              LEFT PANE: WORKFLOW CHAT
              ----------------------------------------- */}
          <div className="flex-1 flex flex-col bg-white/70 backdrop-blur-xl border border-white/80 rounded-[1.5rem] shadow-sm overflow-hidden min-h-0 relative">
            <div className="px-5 py-4 border-b border-slate-100 bg-white/40 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center shadow-sm">
                  <svg
                    className="w-4 h-4 text-[#FC6D26]"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2.5"
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-900">
                    Review Assistant
                  </h2>
                  <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">
                    Interrogate the Auto-Fix
                  </p>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 custom-scrollbar min-h-0 relative">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[90%] lg:max-w-[85%] rounded-2xl px-5 py-4 text-sm leading-relaxed shadow-sm ${
                      message.role === "user"
                        ? "bg-slate-900 text-white rounded-br-sm border border-slate-800"
                        : "bg-white border border-slate-200/80 rounded-bl-sm text-slate-700"
                    }`}
                  >
                    {/* Event Banner for Updates */}
                    {message.type === "update" && (
                      <div className="mb-3 flex items-center gap-2 bg-emerald-50 text-emerald-700 text-xs font-bold px-3 py-2 rounded-lg border border-emerald-100">
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
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                        Code Updated to v2
                      </div>
                    )}

                    <div className="prose prose-sm max-w-none text-slate-700">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => (
                            <p className="mb-2 last:mb-0">{children}</p>
                          ),
                          ul: ({ children }) => (
                            <ul className="list-none space-y-2 mb-3">
                              {children}
                            </ul>
                          ),
                          li: ({ children }) => {
                            // Render checklists cleanly
                            const str = String(children);
                            const isChecked = str.includes("[x]");
                            const isUnchecked = str.includes("[ ]");
                            if (isChecked || isUnchecked) {
                              return (
                                <li className="flex items-center gap-2 text-[13px] font-medium text-slate-700">
                                  <svg
                                    className={`w-4 h-4 shrink-0 ${isChecked ? "text-emerald-500" : "text-slate-300"}`}
                                    fill="currentColor"
                                    viewBox="0 0 20 20"
                                  >
                                    {isChecked ? (
                                      <path
                                        fillRule="evenodd"
                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                                        clipRule="evenodd"
                                      />
                                    ) : (
                                      <path
                                        fillRule="evenodd"
                                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z"
                                        clipRule="evenodd"
                                      />
                                    )}
                                  </svg>
                                  {str.replace(/\[x\]|\[ \]/g, "")}
                                </li>
                              );
                            }
                            return (
                              <li className="list-disc ml-4">{children}</li>
                            );
                          },
                          code: ({ inline, children }) =>
                            inline ? (
                              <code
                                className={`px-1.5 py-0.5 rounded text-[13px] font-mono border ${message.role === "user" ? "bg-white/10 border-white/20 text-white" : "bg-slate-100 border-slate-200 text-slate-800"}`}
                              >
                                {children}
                              </code>
                            ) : (
                              <code className="block bg-slate-900 text-slate-300 border border-slate-800 p-4 rounded-xl text-[13px] my-3 font-mono overflow-x-auto custom-scrollbar">
                                {children}
                              </code>
                            ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex justify-start">
                  <div className="bg-white border border-slate-200 shadow-sm rounded-2xl rounded-bl-sm px-5 py-4">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0ms" }}
                      ></span>
                      <span
                        className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "150ms" }}
                      ></span>
                      <span
                        className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: "300ms" }}
                      ></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Contextual Action Prompts */}
            <div className="px-4 pb-2 flex gap-2 overflow-x-auto custom-scrollbar no-scrollbar">
              <button
                onClick={() =>
                  handleSendMessage(
                    "Are you sure this won't break downstream imports?",
                  )
                }
                className="shrink-0 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors shadow-sm"
              >
                Check downstream impact
              </button>
              <button
                onClick={() =>
                  handleSendMessage(
                    "Change the fix to throw a TypeError instead of returning.",
                  )
                }
                className="shrink-0 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition-colors shadow-sm"
              >
                Throw Error instead of Return
              </button>
            </div>

            {/* Chat Input */}
            <div className="shrink-0 p-3 sm:p-4 bg-white/60 border-t border-slate-100/60 backdrop-blur-md">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendMessage();
                }}
                className="relative flex items-center bg-white border border-slate-200 rounded-xl shadow-sm focus-within:ring-2 focus-within:ring-[#FC6D26]/50 focus-within:border-[#FC6D26] transition-all p-1.5"
              >
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Direct the AI to modify the code..."
                  className="flex-1 bg-transparent border-none focus:outline-none text-sm px-3 py-1.5 text-slate-900 placeholder-slate-400"
                />
                <button
                  type="submit"
                  disabled={!inputValue.trim() || isTyping}
                  className="p-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:bg-slate-100 disabled:text-slate-400 transition-all shadow-sm disabled:shadow-none"
                >
                  <svg
                    className="w-4 h-4 transform rotate-90"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                    />
                  </svg>
                </button>
              </form>
            </div>
          </div>

          {/* -----------------------------------------
              RIGHT PANE: ARTIFACTS & COMMAND CENTER
              ----------------------------------------- */}
          <div className="w-full lg:w-[450px] xl:w-[500px] flex flex-col gap-4 min-h-0">
            {/* Artifact Viewer (The Workbench) */}
            <div className="flex-1 flex flex-col bg-white border border-slate-200/60 rounded-[1.5rem] shadow-sm overflow-hidden min-h-0 relative">
              {/* Internal Tabs */}
              <div className="shrink-0 flex items-center p-3 border-b border-slate-100 bg-slate-50/80">
                <div className="flex bg-slate-200/50 p-1 rounded-xl w-full border border-slate-200">
                  <button
                    onClick={() => setActiveTab("context")}
                    className={`flex-1 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all ${activeTab === "context" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"}`}
                  >
                    Code Diff
                  </button>
                  <button
                    onClick={() => setActiveTab("cve")}
                    className={`flex-1 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all ${activeTab === "cve" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"}`}
                  >
                    Security Context
                  </button>
                  <button
                    onClick={() => setActiveTab("logs")}
                    className={`flex-1 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all flex justify-center items-center gap-1.5 ${activeTab === "logs" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"}`}
                  >
                    CI Pipeline
                  </button>
                </div>
              </div>

              {/* Artifact Scroll Area */}
              <div className="flex-1 overflow-y-auto min-h-0 custom-scrollbar bg-[#FAFAFA]">
                {activeTab === "context" && (
                  <div className="p-4 sm:p-5 flex flex-col h-full">
                    {/* Pipeline & Version Ribbon */}
                    <div className="flex items-center justify-between mb-4 bg-white px-3 py-2 rounded-xl border border-slate-200 shadow-sm">
                      <div className="flex items-center gap-2">
                        <span className="flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-600">
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
                        </span>
                        <span className="text-xs font-bold text-slate-700">
                          Pipeline Passed
                        </span>
                      </div>
                      <div className="flex items-center gap-2 border-l border-slate-200 pl-3">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                          Active Version:
                        </span>
                        <span className="px-2 py-0.5 bg-slate-900 text-white rounded text-xs font-mono font-bold shadow-sm">
                          {diffVersion}
                        </span>
                      </div>
                    </div>

                    {/* Code Editor Frame */}
                    <div className="rounded-xl border border-slate-800 bg-[#0D1117] font-mono text-xs sm:text-[13px] leading-relaxed shadow-lg overflow-hidden flex flex-col flex-1">
                      <div className="flex items-center justify-between bg-slate-900 border-b border-slate-800 px-4 py-2 shrink-0">
                        <span className="text-slate-400 text-xs font-medium tracking-wide">
                          utils/merge.js
                        </span>
                        <span className="text-slate-500 text-xs border border-slate-700 px-2 rounded-md bg-slate-800">
                          +1 / -1
                        </span>
                      </div>

                      <div className="overflow-x-auto p-2 custom-scrollbar">
                        <div className="flex text-slate-400 min-w-max">
                          <div className="w-8 text-right pr-3 select-none opacity-50">
                            14
                          </div>
                          <div className="flex-1 whitespace-pre">
                            {" "}
                            <span className="text-purple-400">if</span>{" "}
                            (!source){" "}
                            <span className="text-purple-400">return</span>;
                          </div>
                        </div>
                        <div className="flex bg-rose-950/40 text-rose-200 border-l-2 border-rose-500 min-w-max my-0.5">
                          <div className="w-8 text-right pr-3 select-none text-rose-500/70">
                            15
                          </div>
                          <div className="flex-1 whitespace-pre">
                            <span className="text-rose-500 mr-2">-</span>{" "}
                            <span className="line-through opacity-70">
                              Object.keys(source).forEach(key =&gt; {"{"}
                            </span>
                          </div>
                        </div>
                        <div className="flex bg-emerald-950/40 text-emerald-200 border-l-2 border-emerald-500 min-w-max my-0.5">
                          <div className="w-8 text-right pr-3 select-none text-emerald-500/70">
                            15
                          </div>
                          <div className="flex-1 whitespace-pre">
                            <span className="text-emerald-500 mr-2">+</span>{" "}
                            Object.keys(source).forEach(key =&gt; {"{"}
                          </div>
                        </div>
                        <div className="flex bg-emerald-950/40 text-emerald-200 border-l-2 border-emerald-500 min-w-max my-0.5">
                          <div className="w-8 text-right pr-3 select-none text-emerald-500/70">
                            16
                          </div>
                          <div className="flex-1 whitespace-pre">
                            <span className="text-emerald-500 mr-2">+</span>{" "}
                            <span className="bg-emerald-500/20 px-1 rounded font-bold text-emerald-300">
                              {diffVersion === "v1"
                                ? "if (key === '__proto__' || key === 'constructor') return;"
                                : "if (key === '__proto__' || key === 'constructor') throw new TypeError('Illegal key');"}
                            </span>
                          </div>
                        </div>
                        <div className="flex text-slate-400 min-w-max">
                          <div className="w-8 text-right pr-3 select-none opacity-50">
                            17
                          </div>
                          <div className="flex-1 whitespace-pre">
                            {" "}
                            <span className="text-purple-400">if</span> (
                            <span className="text-yellow-300">typeof</span>{" "}
                            source[key] ==={" "}
                            <span className="text-green-400">'object'</span>){" "}
                            {"{"}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "cve" && (
                  <div className="p-5 font-sans">
                    <div className="bg-white rounded-xl border border-rose-200 p-5 shadow-sm relative overflow-hidden">
                      <div className="absolute top-0 left-0 w-1 h-full bg-rose-500"></div>
                      <div className="flex items-center gap-2 mb-3">
                        <span className="px-2 py-0.5 bg-rose-100 text-rose-700 text-[10px] font-bold uppercase tracking-wider rounded border border-rose-200">
                          High Risk CVE
                        </span>
                        <h4 className="font-bold text-slate-900 text-base">
                          CWE-1321: Prototype Pollution
                        </h4>
                      </div>
                      <p className="text-sm text-slate-600 leading-relaxed mb-4">
                        Unsanitized object assignment allows attackers to inject
                        properties into `Object.prototype`, exposing the Node.js
                        runtime to Denial of Service or Remote Code Execution.
                      </p>
                      <a
                        href="#"
                        className="text-xs font-semibold text-rose-600 hover:text-rose-700 hover:underline"
                      >
                        Read full OWASP mitigation guide →
                      </a>
                    </div>
                  </div>
                )}

                {activeTab === "logs" && (
                  <div className="h-full bg-[#0D1117] flex flex-col">
                    <ProgressLogsViewer
                      repoId={repoId}
                      mrIid={currentMR.iid || currentMR.gitlab_mr_id}
                      isReviewing={isReviewing}
                      onComplete={() => {}}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Command Center Action Bar */}
            <div className="shrink-0 bg-white/70 backdrop-blur-xl border border-white/80 p-4 rounded-[1.5rem] shadow-sm flex flex-col sm:flex-row gap-3">
              <button
                onClick={() => handleAction("reject")}
                disabled={isResolving}
                className="flex-1 py-3 rounded-xl border border-slate-200 bg-white text-sm font-bold text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors shadow-sm disabled:opacity-50"
              >
                Discard Fix
              </button>
              <button
                onClick={() => handleAction("merge")}
                disabled={isResolving}
                className="flex-[2] py-3 rounded-xl bg-[#FC6D26] text-white text-sm font-bold hover:bg-[#E24329] shadow-[0_4px_14px_0_rgba(252,109,38,0.39)] transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:shadow-none"
              >
                {isResolving ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                ) : (
                  <>
                    Approve & Merge {diffVersion}
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2.5"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </React.Fragment>
  );
};

// Progress Logs Viewer Component
const ProgressLogsViewer = ({ repoId, mrIid, isReviewing, onComplete }) => {
  const { logs, isConnected, error, reconnect } = useWebSocketProgress(
    repoId,
    mrIid,
    isReviewing,
    onComplete,
  );

  // Add dummy pipeline data for UX demonstration if logs are empty
  const displayLogs =
    logs.length > 0
      ? logs
      : [
          {
            timestamp: Date.now() / 1000 - 10,
            category: "running",
            message: "Triggering isolated CI runner...",
          },
          {
            timestamp: Date.now() / 1000 - 8,
            category: "info",
            message: "Running npm test:unit --filter=utils/merge.js",
          },
          {
            timestamp: Date.now() / 1000 - 2,
            category: "success",
            message: "Pass: should safely drop prototype keys",
          },
          {
            timestamp: Date.now() / 1000 - 1,
            category: "success",
            message: "Pass: should correctly deep merge nested objects",
          },
          {
            timestamp: Date.now() / 1000,
            category: "success",
            message: "Pipeline successful. Safe to merge.",
          },
        ];

  return (
    <>
      <div className="px-4 py-3 border-b border-slate-800 bg-slate-900 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Pipeline Output
          </span>
        </div>
        <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>{" "}
          Passing
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs text-slate-300 relative custom-scrollbar">
        {displayLogs.map((log, idx) => (
          <div key={idx} className="flex items-start gap-3">
            <span className="text-slate-600 shrink-0 select-none">
              {new Date(log.timestamp * 1000).toLocaleTimeString("en-US", {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <span
              className={`flex-1 leading-relaxed ${
                log.category === "running"
                  ? "text-blue-400"
                  : log.category === "success"
                    ? "text-emerald-400"
                    : log.category === "error"
                      ? "text-rose-400"
                      : "text-slate-300"
              }`}
            >
              <span className="mr-2 opacity-50">&gt;</span>
              {log.message}
            </span>
          </div>
        ))}
      </div>
    </>
  );
};

export default MRDetails;
