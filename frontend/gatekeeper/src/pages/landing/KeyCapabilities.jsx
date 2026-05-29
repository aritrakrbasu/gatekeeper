import React from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Database, Code2, KeyRound, GitBranch, Zap } from "lucide-react";
import { KEY_CAPABILITIES_CONTENT } from "./constants";

export const KeyCapabilities = () => {
  const cards = [
    {
      title: "Catches What Humans Miss",
      desc: "AI-powered review runs in parallel with your team — catching security holes, secret leaks, and logic errors that slip through even experienced reviewers.",
      size: "col-span-1 md:col-span-2",
      icon: ShieldAlert,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    },
    {
      title: "Knows Your Database",
      desc: "Live schema inspection means Gatekeeper understands your real data structure, not just the code — preventing conflicts before they reach production.",
      size: "col-span-1",
      icon: Database,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    },
    {
      title: "Writes the Fix, Not Just the Report",
      desc: "Most tools tell you what's wrong. Gatekeeper tells you and then fixes it — automatically staging corrected code for your approval.",
      size: "col-span-1 md:col-span-2",
      icon: Code2,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    },
    {
      title: "Secrets Stay Secret",
      desc: "Hardcoded API keys and credentials are detected, extracted, and secured automatically — before they ever hit your repository history.",
      size: "col-span-1",
      icon: KeyRound,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    },
    {
      title: "Works Across All Your Branches",
      desc: "Each branch of your project can connect to its own environment. Gatekeeper adapts to your workflow, not the other way around.",
      size: "col-span-1",
      icon: GitBranch,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    },
    {
      title: "Always On, Never Rate-Limited",
      desc: "Built-in retry logic and smart queuing means Gatekeeper keeps working even under heavy load — no missed reviews, no silent failures.",
      size: "col-span-1",
      icon: Zap,
      glow: "hover:shadow-gk-accent/15 hover:border-gk-accent/40"
    }
  ];

  return (
    <section 
      id="capabilities" 
      className="min-h-screen py-24 px-6 md:px-12 bg-gk-bg relative overflow-hidden border-t border-gk-border/20 z-10"
    >
      <div className="max-w-6xl mx-auto w-full space-y-16">
        <div className="text-center space-y-4">
          <span className="text-[10px] text-gk-accent uppercase font-bold tracking-widest px-3 py-1 bg-gk-accent/10 border border-gk-accent/20 rounded-full inline-block">
            {KEY_CAPABILITIES_CONTENT.label}
          </span>
          <h2 className="text-3xl sm:text-5xl font-black font-syne leading-tight text-gk-primary">
            {KEY_CAPABILITIES_CONTENT.headline}
          </h2>
          <p className="text-sm text-gk-muted leading-relaxed max-w-xl mx-auto">
            {KEY_CAPABILITIES_CONTENT.description}
          </p>
        </div>

        {/* Bento Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {cards.map((card, idx) => {
            const IconComponent = card.icon;
            return (
              <motion.div
                key={idx}
                whileHover={{ y: -4 }}
                transition={{ duration: 0.3 }}
                className={`${card.size} p-6 sm:p-8 rounded-[1.75rem] border border-gk-border bg-gk-surface/30 backdrop-blur-md hover:bg-gk-surface/60 transition-all duration-300 flex flex-col justify-between group shadow-sm ${card.glow}`}
              >
                <div className="w-11 h-11 rounded-xl bg-gk-surface border border-gk-border/40 flex items-center justify-center text-gk-accent group-hover:text-gk-primary transition-colors shrink-0">
                  <IconComponent className="w-5 h-5" />
                </div>
                <div className="space-y-3 mt-12">
                  <h3 className="text-lg font-bold text-gk-primary font-syne">
                    {card.title}
                  </h3>
                  <p className="text-xs sm:text-sm text-gk-muted leading-relaxed">
                    {card.desc}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
