import React from "react";
import { Shield } from "lucide-react";
import { FOOTER_CONTENT } from "./constants";

export const Footer = () => {
  return (
    <footer className="py-12 px-6 md:px-12 border-t border-gk-border/20 bg-[#020206] text-xs text-gk-muted select-none">
      <div className="max-w-6xl mx-auto w-full flex flex-col md:flex-row items-center justify-between gap-6">
        
        {/* Left Info */}
        <div className="flex items-center gap-2 text-gk-primary">
          <Shield className="w-4 h-4 text-gk-accent" />
          <span className="font-syne font-black uppercase tracking-wider">Gatekeeper</span>
        </div>

        {/* Center Links */}
        <div className="flex items-center gap-6 font-semibold uppercase tracking-wider text-[10px]">
          <a href="#problem" className="hover:text-gk-accent transition-colors">Crisis</a>
          <a href="#workflow" className="hover:text-gk-accent transition-colors">Workflow</a>
          <a href="#capabilities" className="hover:text-gk-accent transition-colors">Features</a>
          <a href="#preview" className="hover:text-gk-accent transition-colors">Dashboard</a>
        </div>

        {/* Right Info */}
        <div className="font-space text-[10px]">
          {FOOTER_CONTENT.bottomLine}
        </div>
      </div>
    </footer>
  );
};
