import React from "react";
import { motion } from "framer-motion";
import { Trophy } from "lucide-react";
import { HACKATHON_TEAM_CONTENT } from "./constants";

// Custom inline SVG icons to avoid lucide version mismatches
const Github = (props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
    <path d="M9 18c-4.51 2-5-2-7-2" />
  </svg>
);

const Gitlab = (props) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <path d="m22 13.29-3.33-10a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18l-2.26 6.67H8.32L6.06 3.24a.42.42 0 0 0-.14-.18.38.38 0 0 0-.22-.1.39.39 0 0 0-.23.07.42.42 0 0 0-.14.18L2 13.29a.75.75 0 0 0 .07.65l8.33 6.1a.76.76 0 0 0 .9 0l8.33-6.1a.75.75 0 0 0 .37-.65z" />
  </svg>
);

export const HackathonTeam = () => {
  return (
    <section 
      id="team" 
      className="py-24 px-6 md:px-12 bg-gk-bg relative overflow-hidden z-10"
    >
      <div className="max-w-4xl mx-auto w-full text-center space-y-16">
        
        {/* Hackathon Badge Card */}
        <motion.div 
          initial={{ rotate: -2, scale: 0.95 }}
          whileInView={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 100 }}
          className="inline-block p-8 rounded-3xl border border-gk-gold/30 bg-[#14120D] text-gk-gold relative overflow-hidden -rotate-2 select-none glow-mint"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-gk-gold/5 to-transparent"></div>
          <div className="flex flex-col items-center gap-4 relative z-10">
            <div className="w-14 h-14 rounded-full bg-gk-gold/10 border border-gk-gold/30 flex items-center justify-center">
              <Trophy className="w-7 h-7 text-gk-gold animate-bounce" />
            </div>
            <div className="space-y-1">
              <h3 className="text-xl sm:text-2xl font-black font-syne uppercase tracking-wider">
                {HACKATHON_TEAM_CONTENT.badgeTitle}
              </h3>
              <p className="text-xs font-semibold uppercase tracking-widest text-gk-gold/70">
                {HACKATHON_TEAM_CONTENT.badgeSubtitle}
              </p>
            </div>
          </div>
        </motion.div>

        {/* Team Grid */}
        <div className="space-y-6">
          <h3 className="text-[10px] text-gk-muted uppercase font-bold tracking-widest font-space">
            {HACKATHON_TEAM_CONTENT.contributorsLabel}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {HACKATHON_TEAM_CONTENT.team.map((member, idx) => (
              <div 
                key={idx}
                className="p-5 rounded-2xl border border-gk-border/40 bg-gk-surface/20 hover:border-gk-accent/40 transition-colors duration-300 flex flex-col justify-center items-center text-center gap-2"
              >
                <span className="font-bold text-gk-primary font-syne">{member.name}</span>
                <span className="text-[10px] text-gk-muted uppercase font-bold tracking-wider leading-snug">{member.role}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Repository Links */}
        <div className="flex items-center justify-center gap-4 pt-4">
          <a
            href={HACKATHON_TEAM_CONTENT.repoLinks.github}
            target="_blank"
            rel="noopener noreferrer"
            className="px-5 py-2.5 rounded-xl border border-gk-border/40 hover:border-gk-accent text-gk-muted hover:text-gk-accent text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center gap-2"
          >
            <Github className="w-4 h-4" />
            GitHub
          </a>
          <a
            href={HACKATHON_TEAM_CONTENT.repoLinks.gitlab}
            target="_blank"
            rel="noopener noreferrer"
            className="px-5 py-2.5 rounded-xl border border-gk-border/40 hover:border-gk-accent text-gk-muted hover:text-gk-accent text-xs font-bold uppercase tracking-wider transition-all duration-300 flex items-center gap-2"
          >
            <Gitlab className="w-4 h-4" />
            GitLab
          </a>
        </div>
      </div>
    </section>
  );
};
