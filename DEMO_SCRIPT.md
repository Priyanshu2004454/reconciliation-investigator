# 🎬 5-Minute Video Demo Script & Presentation Guide
### Project: Reconciliation Investigator (Razorpay AI Buildathon)

---

## ⏱️ Video Breakdown (Exact Timeline: Total ~4:45)

```
[0:00 - 0:45] - Hook & Problem Statement (Razorpay Context)
[0:45 - 1:45] - High-Level Architecture & Dashboard Overview
[1:45 - 3:00] - Live AI Investigator (Tool-Use, Hallucination Guard, Decision Flow)
[3:00 - 4:00] - Live AI Copilot (Voice & Conversational Analytics)
[4:00 - 4:45] - Technical Depth, Engineering Challenges & Closing
```

---

## 🎙️ Section-by-Section Spoken Script

### 1. Introduction & The Problem (0:00 – 0:45)
> **[Camera ON or Dashboard Screen]**
>
> *"Hello team Razorpay! Today, high-growth merchants process thousands of digital transactions daily. However, one of the most painful operational bottlenecks in fintech is **Financial Reconciliation** — accounting for platform fee deductions, 18% GST, timing delays between Razorpay and banks, refunds, and missing UTR credits.*
>
> *When numbers don’t match, finance teams spend hours manually cross-checking spreadsheets. To solve this, I built **Reconciliation Investigator** — an autonomous, agentic AI platform designed specifically for Razorpay merchants."*

---

### 2. Dashboard & Deterministic Engine (0:45 – 1:45)
> **[Show Screen: Dashboard at `http://localhost:3000` / Overview]**
>
> *"Here is the merchant dashboard. Our system uses a **Dual-Engine Architecture**:*
> 1. *First, our **Deterministic Rule Engine (Phase 1–6)** automatically matches over 75% of standard transactions by checking UTR exact-matches, date windows, fee tolerances, and refund offsets.*
> 2. *When we click **Load Demo Data** or trigger a batch run, we see exactly 100 transactions: 40 Matched, 35 Explained, and 25 that truly need review.*
>
> *For those 25 ambiguous exceptions, instead of dumping them on human accountants, we unleash our **Agentic AI Investigator**."*

---

### 3. Deep Dive: AI Investigator in Action (1:45 – 3:00)
> **[Show Screen: Navigate to `/reconciliation` -> Click a `NEEDS_REVIEW` case -> Click "Investigate with AI"]**
>
> *"Let's open this unresolved case where a settlement shows a discrepancy. Watch what happens when I click **'Investigate with AI'**.*
>
> *Rather than a simple one-shot prompt, the AI operates in an **autonomous multi-turn loop with 8 database tools**:*
> - *It calls `get_settlement` and `get_payment`.*
> - *It searches real bank statements for the settlement's UTR.*
> - *It calculates expected net amounts after platform fees and taxes.*
>
> *Look at the output: It identified the exact root cause — **MISSING_BANK_CREDIT** — with a 93% confidence score, cited the verified settlement ID and UTR, and provided a clear explanation.*
>
> **[Key Technical Highlight - Emphasize this!]**
> *"Crucially, in financial tech, **hallucinations are dangerous**. We engineered a strict **Tool Grounding Guardrail**: every piece of evidence cited by the AI is cryptographically verified against IDs actually returned by tool executions. If the AI invents an ID, the backend rejects it automatically.*
>
> *Finally, our **Human-in-the-Loop workflow** allows the merchant to accept or reject the finding, which is permanently logged in our tamper-proof **Audit Log**."*

---

### 4. AI Copilot: Voice & Conversational Analytics (3:00 – 4:00)
> **[Show Screen: Open the AI Copilot Panel on the right]**
>
> *"Merchants don't just want tables — they want immediate answers. We built an **AI Copilot** supporting both text and **real-time browser voice input**.*
>
> *Let's ask: **'What needs attention today?'** [or click suggested question]*
>
> *The Copilot queries the database live, summarizes the highest-risk open exceptions, and provides interactive deep-links directly to the offending reconciliation cases.*
>
> *It also handles queries like 'Show high-value exceptions' or 'Explain today's reconciliation rate' with sub-second response times using Google Gemini."*

---

### 5. Technical Depth, Challenges & Conclusion (4:00 – 4:45)
> **[Show Screen: VS Code / Terminal with `pytest` output showing 57 tests passing]**
>
> *"Behind the scenes:*
> - *The backend is built with **FastAPI, Async SQLAlchemy, and PostgreSQL 16**.*
> - *We built a pluggable **Multi-Provider AI Layer** supporting both Google Gemini and Anthropic Claude.*
> - *We overcame key engineering hurdles: resolving Postgres async date-casting edge cases, preserving Gemini thought signatures across multi-turn tool loops, and ensuring multi-run idempotency.*
> - *Our entire pipeline is backed by **57 automated tests**.*
>
> *Thank you for your time, and I look forward to building the future of AI in fintech at Razorpay!"*

---

## 💡 Pro-Tips for Recording:
1. **Tool**: Use [Loom](https://www.loom.com) or OBS Studio (with your webcam in a small bubble in the corner).
2. **Audio**: Use earphones with a mic or a clean microphone (clear audio makes a huge difference).
3. **Resolution**: Record at 1080p full screen.
4. **Energy**: Speak with confidence and excitement — you built a complete end-to-end fintech AI product!
