# The Gatekeeper — Hack Submission

---

## 🎯 The Problem

Development teams spend **40% of their time** on code review and incident management. Existing tools are:
- ❌ **Static** — Linters check syntax, not logic
- ❌ **Forgetful** — Every incident starts from zero, no memory of past fixes
- ❌ **Opaque** — AI decisions happen inside black boxes with no quality tracking
- ❌ **Reactive** — Wait for humans to spot problems instead of preventing them

---

## 💡 Our Solution

**The Gatekeeper** is an AI-powered GitLab orchestrator that **learns from every review** using a novel combination of:

| Technology | Innovation |
|------------|------------|
| **Gemini AI** | Generates intelligent remediation plans with ReAct-style reasoning |
| **MongoDB MCP** | Semantic memory layer — finds similar incidents across your entire history |
| **Arize Phoenix** | LLM-as-a-judge evaluates every output, enabling continuous self-improvement |

> *"An AI system that remembers every fix, learns from every mistake, and gets smarter with every merge request."*

---

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   GitLab     │────▶│   Gemini     │────▶│   MongoDB    │────▶│   Arize      │
│   Webhook    │     │   Analysis   │     │   MCP Store  │     │   Evaluate   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                     │                     │
                            ▼                     ▼                     ▼
                     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
                     │  Plan        │     │  Semantic    │     │  Prompt A/B  │
                     │  Execute     │     │  Search      │     │  Testing     │
                     │  Reflect     │     │  Retrieval   │     │  Optimization│
                     └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 🚀 How It Works

### 1. GitLab Trigger → Gemini Analysis
A merge request webhook triggers the workflow engine. Gemini AI analyzes:
- Code diffs and security implications
- Project context from past incidents
- Semantic similarity to known issues

### 2. MongoDB MCP Semantic Memory
Every action is stored with vector embeddings:
```
"NullPointerException in auth service"
    ↓
Embedding Search → Found 3 similar incidents from last year
    ↓
Retrieve successful fixes → Suggest remediation
```

### 3. Arize Phoenix Evaluation
LLM-as-a-judge automatically scores every Gemini output:
- **Accuracy**: Did the analysis catch real issues?
- **Actionability**: Can the fix be applied safely?
- **Prompt Optimization**: A/B test prompts, deploy winners automatically

---

## 🔥 Technical Highlights

| Feature | Implementation |
|---------|----------------|
| **Custom Agent Framework** | ReAct-style workflow engine with planning, execution, reflection loops |
| **MCP Integration** | Unified tool layer — GitLab, MongoDB, Dynatrace, GitNexus |
| **Observability** | OpenInference tracing on every Gemini call via Arize SDK |
| **Self-Improvement** | Automatic prompt versioning with evaluation-driven deployment |
| **Human-in-the-Loop** | Approval gates for destructive operations |
| **Failure Recovery** | Retry strategies with exponential backoff |

---

## 🛠️ Tech Stack

```
Backend:  FastAPI + Motor (MongoDB async)
AI:       Google GenAI (Gemini 2.5 Flash)
Memory:   MongoDB with vector embeddings
Observability:  Arize Phoenix Cloud + OpenInference
Frontend: React 19 + Vite + TanStack Query
Protocol: Model Context Protocol (MCP)
```

---

## 📊 Demo Scenario

1. **Developer opens MR** with a SQL injection vulnerability
2. **Gemini analyzes** the diff and identifies the security issue
3. **MongoDB MCP searches** and finds 3 similar incidents from last quarter
4. **Remediation plan** generated with past fixes as reference
5. **Arize evaluates** the plan quality and logs to Phoenix dashboard
6. **Human approves** → Auto-fix applied → MR updated

**Time saved**: 2 hours of investigation → 5 minutes of review

---

## 🎓 What We Learned

- **Gemini's reasoning** shines in multi-step remediation planning
- **MongoDB MCP's semantic search** dramatically reduces incident investigation time
- **Arize evaluation** caught prompt regressions we would have missed
- **Human approval gates** are essential for autonomous systems in production

---

## 🔮 Future Vision

- Multi-repository semantic memory across entire organizations
- Custom model fine-tuning based on project-specific patterns
- Real-time collaboration via shared incident investigations
- Community prompt library for common vulnerability patterns

---

## 👾 Team & Links

- **GitHub**: `https://github.com/your-org/the-gatekeeper`
- **Demo Video**: `https://youtu.be/demo-link`
- **Phoenix Dashboard**: `https://app.phoenix.arize.com`
- **Tech Stack**: FastAPI · Gemini · MongoDB MCP · Arize

---

**Built for GitLab developers who want their AI assistant to learn from every mistake, not repeat them. 🚀**
