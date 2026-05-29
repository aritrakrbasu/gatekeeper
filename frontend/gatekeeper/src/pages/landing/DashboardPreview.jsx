import React, { useEffect, useRef } from "react";
import gsap from "gsap";
import { Shield, Layers, GitMerge, Terminal, Zap } from "lucide-react";
import { DASHBOARD_PREVIEW_CONTENT } from "./constants";

export const DashboardPreview = ({ navigate }) => {
  const sectionRef = useRef(null);
  const mockRef = useRef(null);

  useEffect(() => {
    // GSAP 3D rotate tilt entry
    const ctx = gsap.context(() => {
      gsap.fromTo(mockRef.current,
        {
          transformPerspective: 1000,
          rotateX: 12,
          scale: 0.93,
        },
        {
          rotateX: 0,
          scale: 1,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top bottom",
            end: "center center",
            scrub: true,
          }
        }
      );
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section 
      id="preview" 
      ref={sectionRef}
      className="min-h-screen py-24 px-6 md:px-12 bg-gk-bg relative overflow-hidden border-t border-gk-border/20 z-10"
    >
      <div className="max-w-6xl mx-auto w-full space-y-16 flex flex-col items-center">
        <div className="text-center space-y-4 max-w-2xl">
          <span className="text-[10px] text-gk-accent uppercase font-bold tracking-widest px-3 py-1 bg-gk-accent/10 border border-gk-accent/20 rounded-full inline-block">
            {DASHBOARD_PREVIEW_CONTENT.label}
          </span>
          <h2 className="text-3xl sm:text-5xl font-black font-syne leading-tight text-gk-primary">
            {DASHBOARD_PREVIEW_CONTENT.headline}
          </h2>
          <p className="text-sm text-gk-muted leading-relaxed">
            {DASHBOARD_PREVIEW_CONTENT.description}
          </p>
        </div>

        {/* Dashboard Mock Browser Chrome mockup in pure HTML/CSS */}
        <div 
          ref={mockRef}
          className="w-full bg-gk-surface border border-gk-border rounded-[2rem] shadow-2xl overflow-hidden flex flex-col transition-all duration-300 glow-mint max-w-5xl"
        >
          {/* Fake Browser Headers */}
          <div className="px-6 py-4 bg-[#080810] border-b border-gk-border/40 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-gk-danger opacity-70"></span>
              <span className="w-3 h-3 rounded-full bg-gk-gold opacity-70"></span>
              <span className="w-3 h-3 rounded-full bg-gk-accent opacity-70"></span>
            </div>
            <div className="bg-gk-bg px-6 py-1.5 rounded-lg border border-gk-border/40 text-[10px] font-mono text-gk-muted w-full max-w-sm text-center">
              {DASHBOARD_PREVIEW_CONTENT.urlBar}
            </div>
            <div className="w-16"></div>
          </div>

          {/* Fake Dashboard Body Layout */}
          <div className="flex flex-col md:flex-row flex-1 min-h-[480px]">
            {/* Sidebar Mock */}
            <div className="w-full md:w-56 bg-gk-surface border-r border-gk-border/40 p-5 flex flex-col gap-6 text-[10px] font-bold uppercase tracking-wider text-gk-muted">
              <div className="flex items-center gap-2 text-gk-primary">
                <Shield className="w-4 h-4 text-gk-accent" />
                <span className="font-syne font-black">Gatekeeper</span>
              </div>
              <div className="flex flex-col gap-4 mt-6">
                <span className="text-gk-accent bg-gk-accent/5 p-2 rounded-lg border border-gk-accent/25 flex items-center gap-2 cursor-pointer">
                  <Layers className="w-3.5 h-3.5" />
                  Repositories
                </span>
                <span className="hover:text-gk-primary p-2 flex items-center gap-2 cursor-pointer transition-colors">
                  <GitMerge className="w-3.5 h-3.5" />
                  Merge Requests
                </span>
                <span className="hover:text-gk-primary p-2 flex items-center gap-2 cursor-pointer transition-colors">
                  <Terminal className="w-3.5 h-3.5" />
                  Audit Logs
                </span>
                <span className="hover:text-gk-primary p-2 flex items-center gap-2 cursor-pointer transition-colors">
                  <Zap className="w-3.5 h-3.5" />
                  Integrations
                </span>
              </div>
            </div>

            {/* Main Area: MR feed table */}
            <div className="flex-1 p-6 flex flex-col justify-between gap-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-gk-border/20 pb-4">
                  <h4 className="text-sm font-bold text-gk-primary font-syne">{DASHBOARD_PREVIEW_CONTENT.title}</h4>
                  <span className="text-[10px] text-gk-accent font-semibold px-2 py-0.5 bg-gk-accent/10 border border-gk-accent/20 rounded">
                    {DASHBOARD_PREVIEW_CONTENT.subtitle}
                  </span>
                </div>
                <div className="space-y-2 font-mono text-[10px] sm:text-xs">
                  {DASHBOARD_PREVIEW_CONTENT.rows.map((row, idx) => (
                    <div key={idx} className="p-3 bg-gk-bg border border-gk-border/40 rounded-xl flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <GitMerge className={`w-4 h-4 ${row.status === "Failed" ? "text-gk-danger" : row.status === "Reviewed" ? "text-gk-accent" : "text-gk-gold"}`} />
                        <div>
                          <span className="font-bold text-gk-primary block">{row.title}</span>
                          <span className="text-gk-muted text-[10px]">{row.meta}</span>
                        </div>
                      </div>
                      <span className={`px-2.5 py-0.5 rounded-full border text-[9px] font-bold uppercase tracking-wider ${row.statusColor} ${row.pulseClass}`}>
                        {row.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-between items-center text-[10px] text-gk-muted font-mono border-t border-gk-border/20 pt-4">
                <span>{DASHBOARD_PREVIEW_CONTENT.footerLeft}</span>
                <span>{DASHBOARD_PREVIEW_CONTENT.footerRight}</span>
              </div>
            </div>

            {/* Right panel log terminal */}
            <div className="w-full md:w-64 bg-[#080810] border-t md:border-t-0 md:border-l border-gk-border/40 p-4 flex flex-col font-space text-[10px] text-gk-muted select-none">
              <span className="font-bold text-gk-primary uppercase tracking-widest text-[9px] mb-3 flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-gk-accent" />
                {DASHBOARD_PREVIEW_CONTENT.terminalTitle}
              </span>
              <div className="flex-1 space-y-2 min-h-[120px] max-h-[220px] overflow-y-auto">
                {DASHBOARD_PREVIEW_CONTENT.terminalLogs.map((log, idx) => {
                  let logColor = "";
                  if (log.includes("PASS") || log.includes("completed")) logColor = "text-gk-accent";
                  if (log.includes("CWE-798")) logColor = "text-gk-danger";
                  return (
                    <div key={idx} className={logColor}>
                      {log}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Enter Platform CTA */}
        <button
          onClick={() => navigate("/login")}
          className="px-8 py-4 bg-gk-bg hover:bg-gk-accent/10 border border-gk-accent text-gk-accent text-sm font-bold uppercase tracking-wider rounded-xl transition-all duration-300 shadow-md shadow-gk-accent/5 hover:shadow-gk-accent/15"
        >
          {DASHBOARD_PREVIEW_CONTENT.ctaText}
        </button>
      </div>
    </section>
  );
};
