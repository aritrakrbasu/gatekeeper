import React from "react";
import { TICKER_CONTENT } from "./constants";

export const TechTicker = () => {
  const tickerItems = TICKER_CONTENT.items;

  // Repeat items to fill scroll seamlessly
  const doubledItems = [...tickerItems, ...tickerItems, ...tickerItems];

  return (
    <section className="py-16 bg-gk-bg overflow-hidden border-t border-b border-gk-border/20 z-10 select-none">
      <div className="text-center text-[10px] text-gk-muted uppercase font-bold tracking-widest mb-6 font-space">
        {TICKER_CONTENT.label}
      </div>
      
      {/* Infinite Horizontal Ticker */}
      <div className="relative flex overflow-x-hidden w-full">
        <div className="flex gap-16 py-4 animate-marquee whitespace-nowrap font-space text-gk-accent uppercase font-bold text-sm sm:text-base tracking-widest">
          {doubledItems.map((item, idx) => (
            <span key={idx} className="flex items-center gap-16">
              {item}
              <span className="text-gk-muted/40 font-normal">·</span>
            </span>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0%); }
          100% { transform: translateX(-33.33%); }
        }
        .animate-marquee {
          animation: marquee 25s linear infinite;
        }
      `}</style>
    </section>
  );
};
