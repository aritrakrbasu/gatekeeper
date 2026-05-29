import React, { useState, useEffect, useRef } from "react";
import gsap from "gsap";
import { PROBLEM_CONTENT } from "./constants";

export const Problem = () => {
  const sectionRef = useRef(null);
  const leftRef = useRef(null);
  const rightRef = useRef(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.fromTo(
        leftRef.current,
        { opacity: 0, y: 50 },
        {
          opacity: 1,
          y: 0,
          duration: 0.8,
          ease: "power3.out",
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 80%",
            toggleActions: "play none none reverse",
          },
        }
      );
      gsap.fromTo(
        rightRef.current,
        { opacity: 0, y: 50 },
        {
          opacity: 1,
          y: 0,
          duration: 0.8,
          delay: 0.15,
          ease: "power3.out",
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top 80%",
            toggleActions: "play none none reverse",
          },
        }
      );
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section 
      id="problem" 
      ref={sectionRef} 
      className="flex flex-col justify-center py-32 px-6 md:px-12 relative overflow-hidden border-t border-gk-border/20 z-10"
    >
      <div className="max-w-6xl mx-auto w-full grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
        {/* Left Side: Stats and Headline */}
        <div ref={leftRef} className="space-y-8">
          <span className="text-[10px] text-gk-danger uppercase font-bold tracking-widest px-3 py-1 bg-gk-danger/10 border border-gk-danger/20 rounded-full inline-block">
            {PROBLEM_CONTENT.label}
          </span>
          <h2 className="text-3xl sm:text-5xl font-black font-syne leading-tight text-gk-primary">
            {PROBLEM_CONTENT.headline}
          </h2>
          <p className="text-sm text-gk-muted leading-relaxed max-w-lg">
            {PROBLEM_CONTENT.body}
          </p>

          <div className="grid grid-cols-3 gap-6 pt-6">
            {PROBLEM_CONTENT.stats.map((stat, idx) => (
              <StatCounter
                key={idx}
                value={stat.value}
                decimals={stat.decimals || 0}
                prefix={stat.prefix || ""}
                suffix={stat.suffix || ""}
                label={stat.label}
              />
            ))}
          </div>
        </div>

        {/* Right Side: Animated SVG bug slippage */}
        <div ref={rightRef} className="flex justify-center">
          <div className="relative w-full max-w-[400px] aspect-square rounded-2xl border border-gk-danger/20 bg-gk-surface/30 backdrop-blur-md p-6 overflow-hidden flex flex-col justify-between glow-danger">
            <div className="absolute inset-0 bg-gradient-to-br from-gk-danger/5 to-transparent"></div>
            
            {/* Database conflict animated visual */}
            <div className="flex-1 flex flex-col justify-center items-center space-y-6">
              <svg className="w-24 h-24 text-gk-danger animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M21 12H3" />
                <path d="M12 3v18" />
                <circle cx="7.5" cy="7.5" r="1.5" className="fill-gk-danger" />
                <circle cx="16.5" cy="7.5" r="1.5" className="fill-gk-danger animate-ping" />
                <path d="m8 15 8-2.5" stroke="red" strokeWidth="2.5" />
              </svg>
              <div className="text-center font-space">
                <span className="text-xs text-gk-danger font-bold uppercase tracking-wider block">{PROBLEM_CONTENT.schemaTitle}</span>
                <span className="text-[10px] text-gk-muted block mt-1">{PROBLEM_CONTENT.schemaDriftText}</span>
              </div>
            </div>

            <div className="border-t border-gk-border/40 pt-4 flex items-center justify-between text-[10px] text-gk-muted">
              <span>{PROBLEM_CONTENT.footerText}</span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-gk-danger animate-ping"></span>
                {PROBLEM_CONTENT.threatScoreText}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

const StatCounter = ({ value, decimals = 0, prefix = "", suffix = "", label }) => {
  const [count, setCount] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    let active = true;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && active) {
        let start = 0;
        const duration = 2000; // 2 seconds
        const startTime = performance.now();

        const animate = (currentTime) => {
          const elapsed = currentTime - startTime;
          const progress = Math.min(elapsed / duration, 1);
          const easeOutQuad = progress * (2 - progress);
          const currentCount = easeOutQuad * value;

          setCount(currentCount);

          if (progress < 1) {
            requestAnimationFrame(animate);
          }
        };

        requestAnimationFrame(animate);
        active = false; // Only trigger count-up once
      }
    }, { threshold: 0.1 });

    if (ref.current) {
      observer.observe(ref.current);
    }

    return () => observer.disconnect();
  }, [value]);

  return (
    <div ref={ref} className="space-y-1">
      <div className="text-2xl sm:text-4xl font-extrabold text-gk-primary font-syne leading-none">
        {prefix}{count.toFixed(decimals)}{suffix}
      </div>
      <div className="text-[9px] sm:text-[10px] text-gk-muted font-bold uppercase tracking-wider leading-snug">
        {label}
      </div>
    </div>
  );
};
