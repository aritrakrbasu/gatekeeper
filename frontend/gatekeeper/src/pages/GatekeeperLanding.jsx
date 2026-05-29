import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useMotionValue, useSpring } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { Navbar } from "./landing/Navbar";
import { Hero } from "./landing/Hero";
import { Problem } from "./landing/Problem";
import { HowItWorks } from "./landing/HowItWorks";
import { KeyCapabilities } from "./landing/KeyCapabilities";
import { DashboardPreview } from "./landing/DashboardPreview";
import { TechTicker } from "./landing/TechTicker";
import { HackathonTeam } from "./landing/HackathonTeam";
import { Footer } from "./landing/Footer";

// Register GSAP plugins
if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

const GatekeeperLanding = () => {
  const navigate = useNavigate();
  const [hoveredLink, setHoveredLink] = useState(false);
  const containerRef = useRef(null);

  // Custom Cursor Spring-based Motion
  const mouseX = useMotionValue(-100);
  const mouseY = useMotionValue(-100);
  
  const dotX = useSpring(mouseX, { damping: 20, stiffness: 300 });
  const dotY = useSpring(mouseY, { damping: 20, stiffness: 300 });
  
  const ringX = useSpring(mouseX, { damping: 30, stiffness: 120 });
  const ringY = useSpring(mouseY, { damping: 30, stiffness: 120 });

  useEffect(() => {
    const handleMouseMove = (e) => {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    };

    window.addEventListener("mousemove", handleMouseMove);

    // Track all interactive elements for cursor resizing
    const handleMouseOver = (e) => {
      if (
        e.target.tagName === "BUTTON" || 
        e.target.tagName === "A" || 
        e.target.closest("button") || 
        e.target.closest("a") || 
        e.target.classList.contains("clickable")
      ) {
        setHoveredLink(true);
      } else {
        setHoveredLink(false);
      }
    };
    
    window.addEventListener("mouseover", handleMouseOver);

    return () => {
      ScrollTrigger.getAll().forEach(st => st.kill());
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseover", handleMouseOver);
    };
  }, [mouseX, mouseY]);

  useEffect(() => {
    const timer = setTimeout(() => {
      ScrollTrigger.refresh();
    }, 300);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div ref={containerRef} className="relative bg-gk-bg text-gk-primary font-dmmono min-h-screen overflow-x-hidden">
      {/* Scanline Overlay */}
      <div className="scanlines" />
      
      {/* Noise Texture */}
      <div className="noise-overlay" />

      {/* Spring Custom Cursor (Hidden on Touch devices) */}
      <motion.div 
        className="custom-cursor hidden md:block" 
        style={{ 
          left: dotX, 
          top: dotY,
          scale: hoveredLink ? 0.5 : 1,
          backgroundColor: hoveredLink ? "#FF3366" : "#00FFB2"
        }} 
      />
      <motion.div 
        className="custom-cursor-ring hidden md:block" 
        style={{ 
          left: ringX, 
          top: ringY,
          scale: hoveredLink ? 1.5 : 1,
          borderColor: hoveredLink ? "#FF3366" : "#00FFB2",
          borderWidth: hoveredLink ? "2px" : "1px"
        }} 
      />

      {/* Navigation Header */}
      <Navbar navigate={navigate} />

      {/* Sections */}
      <Hero navigate={navigate} />
      <Problem />
      <HowItWorks />
      <KeyCapabilities />
      <DashboardPreview navigate={navigate} />
      <TechTicker />
      <HackathonTeam />
      <Footer />
    </div>
  );
};

export default GatekeeperLanding;
