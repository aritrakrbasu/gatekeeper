import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { GitMerge, ScanLine, Radar, Database, Sparkles, Wrench, CheckCircle, ChevronDown } from "lucide-react";
import { HOW_IT_WORKS_CONTENT } from "./constants";

export const HowItWorks = () => {
  const sectionRef = useRef(null);
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      title: "A Developer Opens a Merge Request",
      desc: "The moment a developer proposes a code change on GitLab, Gatekeeper is already watching.",
      icon: GitMerge,
      step: "01",
    },
    {
      title: "The Code Is Instantly Scanned",
      desc: "Gatekeeper reads every changed line and maps out which parts of the application could be affected — before any human reviewer even opens the PR.",
      icon: ScanLine,
      step: "02",
    },
    {
      title: "Hidden Risks Are Surfaced",
      desc: "From broken dependencies to affected features, Gatekeeper traces the ripple effects of every change across the entire codebase.",
      icon: Radar,
      step: "03",
    },
    {
      title: "The Live Database Is Checked",
      desc: "Gatekeeper connects to the live database and checks if any code changes conflict with the real data structure — catching mismatches before they reach production.",
      icon: Database,
      step: "04",
    },
    {
      title: "AI Reviews the Full Picture",
      desc: "Everything — the code diff, the impact map, the database conflicts — is sent to Gemini AI for a deep security and quality audit.",
      icon: Sparkles,
      step: "05",
    },
    {
      title: "Fixes Are Written Automatically",
      desc: "Gatekeeper doesn't just flag issues. It writes the actual corrected code, line by line, and stages a ready-to-merge fix branch.",
      icon: Wrench,
      step: "06",
    },
    {
      title: "A Fix Is Ready for One-Click Review",
      desc: "A new Merge Request with all fixes applied is automatically created and linked back to the original — ready for your team to approve in seconds.",
      icon: CheckCircle,
      step: "07",
    },
  ];

  useEffect(() => {
    const ctx = gsap.context(() => {
      const totalSteps = steps.length;

      ScrollTrigger.create({
        trigger: sectionRef.current,
        start: "top top",
        end: `+=${totalSteps * 100}%`,
        pin: true,
        scrub: 1,
        anticipatePin: 1,
        invalidateOnRefresh: true,
        onUpdate: (self) => {
          const index = Math.min(
            Math.floor(self.progress * totalSteps),
            totalSteps - 1
          );
          setActiveStep(index);

          // Smooth progress bar fill
          gsap.set(".progress-fill", {
            height: `${self.progress * 100}%`,
          });
        },
      });
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  const ActiveIcon = steps[activeStep].icon;

  return (
    <section
      id="workflow"
      ref={sectionRef}
      style={{ transform: "translateZ(0)" }}
      className="min-h-screen flex items-center py-20 px-6 md:px-12 bg-gk-bg relative border-t border-gk-border/20 z-10"
    >
      {/* Ambient glow */}
      <div className="absolute top-0 right-0 w-[400px] h-[400px] bg-gk-accent/5 rounded-full blur-[100px] pointer-events-none" />

      <div className="max-w-5xl mx-auto w-full grid grid-cols-1 md:grid-cols-3 gap-12 items-center">

        {/* LEFT: Title + Progress */}
        <div className="md:col-span-1 space-y-6 flex flex-col justify-start md:pt-4">
          <span className="text-[10px] text-gk-accent uppercase font-bold tracking-widest px-3 py-1 bg-gk-accent/10 border border-gk-accent/20 rounded-full inline-block w-fit">
            {HOW_IT_WORKS_CONTENT.label}
          </span>
          <h2 className="text-3xl sm:text-5xl font-black font-syne leading-tight text-gk-primary">
            {HOW_IT_WORKS_CONTENT.headline}
          </h2>
          <p className="text-sm text-gk-muted leading-relaxed">
            {HOW_IT_WORKS_CONTENT.description}
          </p>

          {/* Step dots navigation */}
          <div className="flex md:flex-col gap-3 mt-4 flex-wrap">
            {steps.map((s, i) => (
              <div
                key={i}
                className="flex items-center gap-2 group cursor-default"
              >
                <div
                  className="transition-all duration-300 rounded-full shrink-0"
                  style={{
                    width: activeStep === i ? "28px" : "8px",
                    height: "8px",
                    backgroundColor:
                      activeStep === i
                        ? "#00FFB2"
                        : i < activeStep
                        ? "rgba(0,255,178,0.4)"
                        : "rgba(255,255,255,0.08)",
                  }}
                />
                <span
                  className="text-[10px] font-bold uppercase tracking-wider transition-colors duration-300 hidden md:block"
                  style={{
                    color:
                      activeStep === i
                        ? "#00FFB2"
                        : i < activeStep
                        ? "rgba(0,255,178,0.5)"
                        : "rgba(255,255,255,0.2)",
                  }}
                >
                  {s.step}
                </span>
              </div>
            ))}
          </div>

          {/* Vertical progress bar */}
          <div className="relative h-[160px] w-[3px] bg-gk-border/30 rounded-full mt-2 overflow-hidden self-start hidden md:block">
            <div className="progress-fill absolute top-0 left-0 w-full h-0 bg-gk-accent rounded-full shadow-[0_0_8px_rgba(0,255,178,0.6)]" />
          </div>
        </div>

        {/* RIGHT: Active step card — single card swaps content */}
        <div className="md:col-span-2 flex items-center justify-center">
          <div className="w-full max-w-xl">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeStep}
                initial={{ opacity: 0, y: 24, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -16, scale: 0.97 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="p-8 md:p-10 rounded-3xl border border-gk-accent/30 bg-gk-surface/70 backdrop-blur-xl shadow-2xl shadow-gk-accent/5 relative overflow-hidden"
              >
                {/* Ambient card glow */}
                <div className="absolute inset-0 bg-gradient-to-br from-gk-accent/5 to-transparent pointer-events-none rounded-3xl" />

                {/* Step number watermark */}
                <div className="absolute top-6 right-8 font-syne font-black text-[72px] leading-none text-gk-accent/5 select-none pointer-events-none">
                  {steps[activeStep].step}
                </div>

                <div className="relative z-10 space-y-6">
                  {/* Icon */}
                  <div className="w-14 h-14 rounded-2xl bg-gk-accent/10 border border-gk-accent/20 flex items-center justify-center">
                    <ActiveIcon className="w-7 h-7 text-gk-accent" />
                  </div>

                  {/* Step label */}
                  <div className="text-[10px] text-gk-accent font-bold uppercase tracking-widest">
                    Step {steps[activeStep].step} of {steps.length}
                  </div>

                  {/* Title */}
                  <h3 className="text-2xl md:text-3xl font-black font-syne text-gk-primary leading-tight">
                    {steps[activeStep].title}
                  </h3>

                  {/* Description */}
                  <p className="text-sm text-gk-muted leading-relaxed max-w-md">
                    {steps[activeStep].desc}
                  </p>

                  {/* Progress dots row */}
                  <div className="flex gap-2 pt-2">
                    {steps.map((_, i) => (
                      <div
                        key={i}
                        className="h-1 rounded-full transition-all duration-500"
                        style={{
                          width: activeStep === i ? "32px" : "8px",
                          backgroundColor:
                            activeStep === i
                              ? "#00FFB2"
                              : i < activeStep
                              ? "rgba(0,255,178,0.35)"
                              : "rgba(255,255,255,0.08)",
                        }}
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>

            {/* Scroll hint — only show on first step */}
            {activeStep === 0 && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="text-center text-[10px] text-gk-muted uppercase tracking-widest mt-6 flex items-center justify-center gap-2"
              >
                <ChevronDown className="w-3 h-3 animate-bounce text-gk-accent" />
                {HOW_IT_WORKS_CONTENT.scrollHint}
              </motion.p>
            )}
          </div>
        </div>

      </div>
    </section>
  );
};
