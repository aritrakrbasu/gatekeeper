import React from "react";
import { Shield } from "lucide-react";

export const Navbar = ({ navigate }) => {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 px-6 py-4 md:px-12 backdrop-blur-md border-b border-gk-border/40 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gk-surface border border-gk-accent flex items-center justify-center relative overflow-hidden shadow-md shadow-gk-accent/10">
          <Shield className="w-4 h-4 text-gk-accent" />
          <div className="absolute inset-0 bg-gk-accent/10 animate-pulse"></div>
        </div>
        <span className="font-syne font-extrabold tracking-wider text-base md:text-lg bg-gradient-to-r from-gk-primary to-gk-accent bg-clip-text text-transparent">
          GATEKEEPER
        </span>
      </div>

      <div className="hidden md:flex items-center gap-8 text-xs font-semibold uppercase tracking-wider text-gk-muted">
        <a href="#problem" className="hover:text-gk-accent transition-colors">Crisis</a>
        <a href="#workflow" className="hover:text-gk-accent transition-colors">Workflow</a>
        <a href="#capabilities" className="hover:text-gk-accent transition-colors">Features</a>
        <a href="#preview" className="hover:text-gk-accent transition-colors">Dashboard</a>
        <a href="#team" className="hover:text-gk-accent transition-colors">Team</a>
      </div>

      <div>
        <button
          onClick={() => navigate("/login")}
          className="relative px-5 py-2.5 rounded-xl border border-gk-accent text-gk-accent text-xs font-extrabold uppercase tracking-widest hover:bg-gk-accent hover:text-gk-bg hover:shadow-lg hover:shadow-gk-accent/25 transition-all duration-300 overflow-hidden group"
        >
          <span className="relative z-10">Enter Platform</span>
        </button>
      </div>
    </nav>
  );
};
