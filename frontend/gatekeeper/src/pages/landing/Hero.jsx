import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ChevronDown, Terminal } from "lucide-react";
import { HERO_CONTENT } from "./constants";

export const Hero = ({ navigate }) => {
  const headline = HERO_CONTENT.headline;

  return (
    <section className="relative min-h-screen flex flex-col justify-center items-center pt-24 pb-12 px-6 md:px-12 relative overflow-hidden select-none">
      {/* Animated Floating Dot Grid Background */}
      <div className="absolute inset-0 cyber-grid opacity-40"></div>
      
      {/* Radial Mint Glow Center */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gk-accent/5 rounded-full blur-[120px] pointer-events-none"></div>

      <div className="relative z-10 max-w-5xl text-center space-y-8 flex flex-col items-center">
        {/* Hackathon Label */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6 }}
          className="px-3 py-1 bg-gk-accent/10 border border-gk-accent/30 rounded-full text-[10px] text-gk-accent font-bold uppercase tracking-widest flex items-center gap-1.5"
        >
          <span className="w-1.5 h-1.5 bg-gk-accent rounded-full animate-ping"></span>
          {HERO_CONTENT.label}
        </motion.div>

        {/* Headline character-by-character reveal */}
        <h1 className="text-4xl sm:text-6xl md:text-8xl font-black text-gk-primary font-syne leading-none tracking-tight">
          {headline.split("").map((char, index) => (
            <motion.span
              key={index}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                delay: index * 0.03,
                duration: 0.4,
                ease: "easeOut"
              }}
            >
              {char}
            </motion.span>
          ))}
        </h1>

        {/* Subheadline fade-up */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.1, duration: 0.6 }}
          className="text-sm sm:text-base md:text-lg text-gk-muted max-w-3xl leading-relaxed font-medium"
        >
          {HERO_CONTENT.subheadline}
        </motion.p>

        {/* CTA Buttons */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.3, duration: 0.6 }}
          className="flex flex-col sm:flex-row items-center gap-4 pt-4"
        >
          <button
            onClick={() => navigate("/login")}
            className="w-full sm:w-auto px-8 py-4 bg-gk-accent hover:bg-gk-accent/90 text-gk-bg text-sm font-bold uppercase tracking-wider rounded-xl transition-all duration-300 shadow-lg shadow-gk-accent/20 hover:shadow-gk-accent/40 hover:-translate-y-0.5 flex items-center justify-center gap-2"
          >
            {HERO_CONTENT.ctaPrimary}
            <ArrowRight className="w-4 h-4" />
          </button>
          
          <a
            href="#workflow"
            className="w-full sm:w-auto px-8 py-4 bg-gk-surface/60 hover:bg-gk-surface border border-gk-border/40 hover:border-gk-accent text-gk-muted hover:text-gk-accent text-sm font-bold uppercase tracking-wider rounded-xl transition-all duration-300 flex items-center justify-center gap-2"
          >
            {HERO_CONTENT.ctaSecondary}
          </a>
        </motion.div>

        {/* Hero Visual Terminal simulation */}
        <motion.div 
          initial={{ opacity: 0, y: 45 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.6, duration: 0.8, ease: "easeOut" }}
          className="w-full max-w-2xl bg-gk-surface/90 border border-gk-border rounded-xl shadow-2xl overflow-hidden text-left font-space text-[11px] sm:text-xs md:text-sm mt-12 flex flex-col relative z-20"
        >
          <div className="px-4 py-3 bg-[#080810] border-b border-gk-border/40 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 bg-gk-danger rounded-full opacity-60"></span>
              <span className="w-2.5 h-2.5 bg-gk-gold rounded-full opacity-60"></span>
              <span className="w-2.5 h-2.5 bg-gk-accent rounded-full opacity-60"></span>
            </div>
            <span className="text-[10px] text-gk-muted uppercase font-bold tracking-widest flex items-center gap-1">
              <Terminal className="w-3 h-3 text-gk-accent" />
              {HERO_CONTENT.terminalLogName}
            </span>
            <div className="w-12"></div>
          </div>
          <div className="p-4 sm:p-6 space-y-2.5 min-h-[220px] sm:min-h-[240px] bg-gk-surface/50 backdrop-blur-md">
            <TerminalTyping />
          </div>
        </motion.div>
      </div>

      {/* Downward Chevron breath */}
      <div className="absolute bottom-6 flex justify-center w-full z-10">
        <motion.div
          animate={{ y: [0, 6, 0] }}
          transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
          className="breathe"
        >
          <ChevronDown className="w-5 h-5 text-gk-accent" />
        </motion.div>
      </div>
    </section>
  );
};

const TerminalTyping = () => {
  const lines = HERO_CONTENT.terminalLines;

  const [visibleLines, setVisibleLines] = useState([]);
  const [currentLineIndex, setCurrentLineIndex] = useState(0);
  const [currentCharIndex, setCurrentCharIndex] = useState(0);

  useEffect(() => {
    if (currentLineIndex < lines.length) {
      const currentFullText = lines[currentLineIndex];
      if (currentCharIndex < currentFullText.length) {
        const timer = setTimeout(() => {
          setVisibleLines((prev) => {
            const copy = [...prev];
            if (copy[currentLineIndex] === undefined) {
              copy[currentLineIndex] = "";
            }
            copy[currentLineIndex] += currentFullText[currentCharIndex];
            return copy;
          });
          setCurrentCharIndex((prev) => prev + 1);
        }, 15);
        return () => clearTimeout(timer);
      } else {
        const timer = setTimeout(() => {
          setCurrentLineIndex((prev) => prev + 1);
          setCurrentCharIndex(0);
        }, 400);
        return () => clearTimeout(timer);
      }
    } else {
      const loopTimer = setTimeout(() => {
        setVisibleLines([]);
        setCurrentLineIndex(0);
        setCurrentCharIndex(0);
      }, 2000);
      return () => clearTimeout(loopTimer);
    }
  }, [currentLineIndex, currentCharIndex, lines]);

  return (
    <>
      {visibleLines.map((lineText, idx) => {
        let isDanger = lineText.includes("⚠") || lineText.includes("vulnerabilities");
        let isSuccess = lineText.includes("✓") || lineText.includes("ready");
        let textColor = "text-gk-primary";
        if (isDanger) textColor = "text-gk-danger font-semibold";
        if (isSuccess) textColor = "text-gk-accent font-semibold";

        return (
          <div key={idx} className={`${textColor} leading-relaxed`}>
            {lineText}
          </div>
        );
      })}
      {currentLineIndex < lines.length && (
        <span className="inline-block w-1.5 h-4 bg-gk-accent ml-0.5 animate-pulse"></span>
      )}
    </>
  );
};
