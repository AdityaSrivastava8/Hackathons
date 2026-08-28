# 🕵️‍♂️ Detective Agentic AI & RAG Profiling System

An enterprise-grade AI intelligence platform combining **Agentic AI decision workflows** with **ChromaDB Vector Search (Retrieval-Augmented Generation)**. Built for private investigation agencies, corporate fraud units, and legal analysts to rapidly cross-reference suspect behaviors against global criminal case precedents, generate executive PDF reports, and automate client acquisition.

---

## 🎯 Track & Problem Statement Alignment

### Hackathon Challenge & Track Focus
* **Track:** Agentic AI & Intelligent Knowledge Retrieval (IBM Hackathon Challenge Track)
* **Problem Statement:** Small-to-midsize private detective agencies and legal research units operate with highly manual, fragmented processes. Cross-referencing raw suspect behaviors, modus operandi (MO), and psychological traits against legacy case files takes days of manual document search—leading to missed pattern connections and severe operational bottlenecks.
* **Our Solution:** An automated Agentic AI workflow that ingests unstructured suspect observations, queries high-dimensional vector embeddings of historical precedents, scores criminal tendency scores/risk levels, generates downloadable executive PDF reports, and allows direct case uploads.

### Role of IBM & Core AI Frameworks
* **Agentic Orchestration:** Structured agent decision-making logic designed to evaluate risk metrics, score suspect traits, and synthesize multi-case behavioral patterns.
* **Intelligent Knowledge Retrieval:** Powered by RAG architecture to process unstructured legacy case files, enabling rapid cross-jurisdictional semantic search across complex criminal precedents.

---

## 🌎 Diverse Multi-Jurisdictional Case Database

The vector engine is pre-loaded with **15 diverse, high-complexity criminal cases** spanning international jurisdictions and major Indian precedent files:

* **Indian Precedents:** Regional financial fraud signatures, toxic substance/poisoning profiles (e.g., Cyanide Mohan MO), complex serial crime investigations (e.g., Nithari, Auto Shankar), and multi-state offender patterns.
* **Global Precedents:** High-profile international serial offenses including Ted Bundy (stalking & deceptive charm signatures), Jeffrey Dahmer (narcissism & containment patterns), John Wayne Gacy, Golden State Killer (geographic profiling), and European/Asian crime records.

---

## 🛠️ Complete Feature Set

1. **Interactive Profiling & Assessment Dashboard (`frontend/app.py`):** Captures suspect profiles, computes real-time **Tendency Scores** and **Risk Assessment Levels**, and displays matched case expanders.
2. **One-Click Executive PDF Export:** Generates clean, client-ready PDF risk summary reports using standard `fpdf2` positioning.
3. **Web Admin Case JSON Uploader:** Sidebar drag-and-drop tool for uploading legacy case files (`.json`) directly into the local vector store.
4. **B2B Lead Scraping Pipeline (`scrape_leads.py`):** Playwright automation extracting active detective agency listings into `agency_leads.csv`.
5. **Automated Cold Outreach Script (`send_outreach.py`):** Formats and previews personalized B2B cold email demos for candidate agencies.

---

## 💼 B2B Business Model & Commercial Strategy

### Target Audience: "The Struggling Agencies"
Small-to-midsize private detective firms, matrimonial verification agencies, and corporate fraud units (1–15 employees) that lack capital for custom enterprise software and lose billable hours to manual file research.

### Pricing Structure
* **14-Day Free Pilot:** Up to 25 evaluations to demonstrate immediate productivity gains.
* **Starter Tier — ₹2,499 ($29) / month:** Up to 50 suspect evaluations/month, global database access, and executive PDF exports.
* **Pro Agency Tier — ₹6,999 ($85) / month:** Unlimited evaluations, 5 multi-user seats, and full Admin Uploader access to index private agency archives.