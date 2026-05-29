export const HERO_CONTENT = {
  label: "AI-Powered Security Orchestrator",
  headline: "Your Codebase Has a New Guardian.",
  subheadline: "The Gatekeeper watches every code change, catches threats before they ship, and deploys AI-crafted fixes automatically — so your team can move fast without breaking things.",
  ctaPrimary: "Enter Platform",
  ctaSecondary: "See How It Works",
  terminalLogName: "gatekeeper_daemon.log",
  terminalLines: [
    "[Gatekeeper] New merge request detected: MR #247",
    "[Gatekeeper] Scanning code changes...",
    "[Gatekeeper] ⚠ 12 downstream components affected",
    "[Gatekeeper] Checking live database for conflicts...",
    "[Gatekeeper] Schema change detected: field 'user_role' removed",
    "[Gatekeeper] Sending to AI for security audit...",
    "[Gatekeeper] ✓ 3 vulnerabilities found. Writing fixes...",
    "[Gatekeeper] Auto-fix ready → Review it now"
  ]
};

export const PROBLEM_CONTENT = {
  label: "The Silent Crisis",
  headline: "Most breaches begin as a single unreviewed line.",
  body: "Manual code review is slow, inconsistent, and overwhelmed. Dangerous changes slip through. Secrets get committed. Systems break silently. Gatekeeper changes that.",
  stats: [
    { value: 68, suffix: "%", label: "of bugs enter unreviewed" },
    { value: 4.2, decimals: 1, suffix: "d", label: "avg time to detect issue" },
    { value: 4.5, decimals: 1, prefix: "$", suffix: "M", label: "avg cost of a missed flaw" }
  ],
  schemaTitle: "Conflict Detected",
  schemaDriftText: "Schema Drift: field 'user_role' (string) removed",
  footerText: "PR #247 (Target: main)",
  threatScoreText: "Threat Score: 87/100"
};

export const HOW_IT_WORKS_CONTENT = {
  label: "Process Engine",
  headline: "From Merge Request to Auto-Fix in minutes.",
  description: "Scroll through the pipeline Gatekeeper triggers the moment your code is committed.",
  scrollHint: "Scroll to walk through the pipeline"
};

export const KEY_CAPABILITIES_CONTENT = {
  label: "Bento Engine",
  headline: "What makes it different.",
  description: "Traditional linters find formatting errors. Security scanners scan for CVEs. Gatekeeper does something entirely different: it behaves like a tireless, context-aware security engineer."
};

export const DASHBOARD_PREVIEW_CONTENT = {
  label: "Dashboard Panel",
  headline: "Real-time visibility into every review, every fix, every threat.",
  description: "The Gatekeeper dashboard gives your team a live feed of all active reviews, audit results, and deployed fixes — in one place.",
  urlBar: "app.gatekeeper.dev/repositories/gitlab_82576405",
  title: "Merge Requests Feed",
  subtitle: "Active Scanner Online",
  rows: [
    {
      title: "🔧 Gatekeeper Auto-Fix for MR !247",
      meta: "main • Opened by gatekeeper",
      status: "Reviewed",
      pulseClass: "safe-pulse",
      statusColor: "text-gk-accent bg-gk-accent/10 border-gk-accent/20"
    },
    {
      title: "feat: Add billing settings profile details",
      meta: "develop • Opened by sagnik_datta",
      status: "Failed",
      pulseClass: "danger-pulse",
      statusColor: "text-gk-danger bg-gk-danger/10 border-gk-danger/20"
    },
    {
      title: "refactor: Split main API code modularized",
      meta: "master • Opened by swapnendu_b",
      status: "Reviewing",
      pulseClass: "animate-pulse",
      statusColor: "text-gk-gold bg-gk-gold/10 border-gk-gold/20"
    }
  ],
  footerLeft: "Displaying 3 active MR streams",
  footerRight: "System status: healthy",
  terminalTitle: "Live Scan Terminal",
  terminalLogs: [
    "[00:01:22] Webhook received from GitLab",
    "[00:01:24] Connection schema matching: PASS",
    "[00:01:25] Triggering Gemini cognitive models...",
    "[00:01:27] CWE-798 Hardcoded slack URL found",
    "[00:01:29] Atomic fixer completed: MR stage ready"
  ],
  ctaText: "Enter Platform Now"
};

export const TICKER_CONTENT = {
  label: "Engineered with the best tools in the ecosystem",
  items: [
    "React", "FastAPI", "MongoDB", "GitLab", "Gemini Pro", "GitNexus", "Python", "AES-256 Encryption", "MCP Protocol", 
    "Motor", "Pydantic",
  ]
};

export const HACKATHON_TEAM_CONTENT = {
  badgeTitle: "Built for Hackathon 2025",
  badgeSubtitle: "The Gatekeeper — Autonomous AI Security",
  contributorsLabel: "Project Contributors",
  team: [
    { name: "Aritra Basu", role: "AI Systems & MCP Bridges Architect" },
    { name: "Swapnendu Banerjee", role: "Secured Remediation Core Engineer" },
    { name: "Sagnik Datta", role: "Fullstack Dashboard Web Developer" }
  ],
  repoLinks: {
    github: "https://github.com/aritrakrbasu/gatekeeper",
    gitlab: "https://gitlab.com"
  }
};

export const FOOTER_CONTENT = {
  bottomLine: "© 2025 The Gatekeeper · Built with obsession, caffeine, and Gemini Pro"
};
