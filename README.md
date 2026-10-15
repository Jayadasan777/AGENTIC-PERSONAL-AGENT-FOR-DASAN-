# AURA — Adaptive Unified Reasoning Assistant

> **A persistent, secure, agentic AI personal assistant built from first principles for live deployment.**

[![Phase Status](https://img.shields.io/badge/Status-Phase%200%20In--Progress-blue.svg)](PHASE_CHECKLIST.md)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 1. Project Vision

AURA (Adaptive Unified Reasoning Assistant) is designed as a persistent, secure, agentic personal AI assistant. Rather than functioning simply as a conversational wrapper or temporary chatbot, AURA integrates:

* **Authenticated, stateful conversation management** with explicit token budgeting.
* **Persistent personal memory** (preferences, commitments, facts) with full provenance, sensitivity tagging, and conflict resolution.
* **Document intelligence & grounded RAG** with verified citations and parser isolation.
* **Agentic reasoning with LangGraph**, governed by a strict **server-side custom policy engine**.
* **Human-in-the-loop explicit approvals** for sensitive operations.
* **Durable automation** for scheduled and long-running workflows with idempotency and retry safeguards.
* **Production-first architecture** deployable to cloud environments using open-weight models and free/open-source tools.

---

## 2. Core Architectural Principles

1. **Security Before Autonomy:** The language model never determines its own permissions. Trusted backend code enforces all authorization, ownership, and rate limits.
2. **Explicit Verification:** Tool executions are never assumed to have succeeded; post-execution state verification inspects real outcomes.
3. **Defense Against Prompt Injection:** Untrusted input (documents, web content, user input) is strictly separated from privileged execution pipelines.
4. **Transparent Provenance:** Long-term memory records state why, when, and from what interaction a fact was derived.
5. **Modular Monolith First:** Maintain simple boundaries, strong typing, and explicit database schemas before considering distributed microservices.

---

## 3. Technology Stack

| Layer | Planned Technology | Role / Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js, React, TypeScript, Tailwind CSS | Authenticated responsive UI, chat, approvals, memory & document dashboards |
| **Backend API** | Python, FastAPI, Pydantic v2 | High-performance async API, schema validation, policy engine |
| **Persistence** | PostgreSQL, pgvector, SQLAlchemy, Alembic | Relational data, relational vectors for similarity search, migration tracking |
| **AI Orchestration** | LangGraph, Open-Weight LLMs (Ollama / llama.cpp) | State graph orchestration, tool routing, structured outputs |
| **Durable Jobs** | DBOS | Durable workflow execution, idempotency, restart recovery |
| **Security & Auth** | Argon2id, JWT with rotating refresh tokens | Secure password hashing, credential rotation, session revocation |
| **Tooling & Quality** | pytest, Ruff, mypy, Docker Compose | Linting, static typing, unit & security regression testing |

---

## 4. Current Implementation Status

See [PHASE_CHECKLIST.md](PHASE_CHECKLIST.md) for full phase-by-phase criteria and tracking.

* **Phase 0 (Repository Audit & Project Planning):** In Progress
  * Git repository initialized: Yes
  * Directory structure & governance: Defined
  * Architecture & Threat Model: Documented
* **Phase 1 (Backend Foundation & Application Skeleton):** Planned
* **Phases 2–9:** Planned

---

## 5. Repository Structure

```text
.
├── .env.example              # Configuration template (no secrets)
├── .gitignore                # Git ignore rules
├── README.md                 # Project overview and status
├── PHASE_CHECKLIST.md        # Comprehensive phase tracking
├── docs/                     # Technical documentation
│   ├── ARCHITECTURE.md       # Architectural diagrams and request flows
│   ├── THREAT_MODEL.md       # Threat analysis and required mitigations
│   ├── GLOSSARY.md           # Domain terms explained in plain English
│   ├── LEARNING_LOG.md       # Incremental engineering log
│   └── decisions/            # Architecture Decision Records (ADRs)
└── backend/                  # (Planned in Phase 1) FastAPI application
```
