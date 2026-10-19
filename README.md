# AURA — Adaptive Unified Reasoning Assistant

> **A persistent, secure, agentic personal AI assistant built from first principles for live deployment.**

[![Build & Tests](https://img.shields.io/badge/Tests-Passing%20(220%2B%20tests)-brightgreen.svg)](tests/)
[![Security Scans](https://img.shields.io/badge/Bandit-0%20Vulnerabilities-brightgreen.svg)](docs/THREAT_MODEL.md)
[![Phase Status](https://img.shields.io/badge/Status-Phases%200--9%20Complete-brightgreen.svg)](PHASE_CHECKLIST.md)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 1. Project Vision

AURA (Adaptive Unified Reasoning Assistant) is a production-ready, fully hardened personal AI agent designed to run continuously on personal infrastructure and companion devices. Rather than functioning simply as a conversational wrapper or temporary chatbot, AURA integrates:

* **Authenticated, Stateful Conversation Management:** Token-budgeted conversations with rotating refresh tokens, Argon2id password hashing, and session revocation.
* **Persistent Personal Memory:** Hierarchical memory engine with semantic vector embeddings (`pgvector`), provenance tracking, sensitivity classifications, and conflict resolution.
* **Grounding & Document RAG:** Verified document ingestion pipeline with chunking, pgvector cosine search, citation verification, and untrusted parser isolation.
* **Agentic Execution & Policy Engine:** Stateful LangGraph reasoning harness governed by a server-side three-tier policy engine (`READ_ONLY`, `MUTATING`, `DANGEROUS`).
* **Companion Security & Biometrics:** Android companion app (Kotlin, Jetpack Compose, Room, WorkManager) with hardware-backed biometric approvals (`BiometricPrompt`) for sensitive operations.
* **Cross-Device Synchronization:** Monotonic sequence cursor delta sync protocol with offline operation queue replay and Last-Write-Wins (LWW) conflict resolution.
* **Local Voice Intelligence:** Air-gapped local speech-to-text (Whisper ONNX / VAD) and low-latency text-to-speech (Piper ONNX / synthetic fallback).
* **Durable Automation Workflows:** Idempotent, durable scheduled cron jobs and webhooks with retry policies.

---

## 2. Core Architectural Principles

1. **Security Before Autonomy:** The LLM never determines its own privileges. A server-side policy engine inspects all tool calls and enforces human biometric approvals for dangerous actions.
2. **Explicit Verification:** Tool executions are never assumed to have succeeded; post-execution state verification inspects real outcomes.
3. **Defense Against Prompt Injection:** Untrusted input (documents, web content, user input) is strictly separated from privileged execution pipelines.
4. **Transparent Provenance:** Long-term memory records state why, when, and from what interaction a fact was derived.
5. **Modular Monolith First:** Maintain simple boundaries, strong typing, and explicit database schemas before considering distributed microservices.

---

## 3. Technology Stack

| Layer | Technology | Role / Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3.12, FastAPI, Pydantic v2 | High-performance async REST API, OpenAPI generation |
| **Relational & Vector DB** | PostgreSQL 16 + pgvector, SQLAlchemy 2.0 | Unified relational data and vector similarity search |
| **Agent Orchestration** | LangGraph, Open-Weight LLMs (Ollama / Llama.cpp) | Stateful graph execution, tool routing, structured outputs |
| **Mobile Companion** | Android (Kotlin, Jetpack Compose, Room, WorkManager) | Push notifications, biometric approvals, offline cache |
| **Voice Intelligence** | Whisper.cpp / Faster-Whisper, Piper TTS | Local STT & TTS with sub-100ms latency |
| **Security & Auth** | Argon2id, JWT, Bandit, OWASP Hardening | Cryptographic hashing, token lifecycle, attack resilience |
| **Quality & CI** | pytest, pytest-asyncio, Ruff | Strict typing, linting, and 220+ automated tests |

---

## 4. Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── agent/            # LangGraph harness, tools, policy engine, kill switch
│   │   ├── api/v1/           # REST API endpoints (auth, devices, sync, voice, memories...)
│   │   ├── core/             # Settings, security primitives, logging
│   │   ├── db/               # PostgreSQL & SQLite session factories, migrations
│   │   ├── models/           # SQLAlchemy ORM entities
│   │   ├── sync/             # Monotonic delta sync protocol & offline queue
│   │   └── voice/            # Local STT (Whisper) & TTS (Piper)
├── android/                  # Android Kotlin Companion Application
│   ├── app/src/main/java/com/aura/companion/
│   │   ├── data/             # Room persistence (AuraDatabase, ApprovalDao)
│   │   ├── sync/             # WorkManager background sync worker
│   │   ├── security/         # Biometric authentication manager
│   │   └── ui/               # Jetpack Compose UI & MainActivity
├── docs/                     # Technical documentation & ADRs
│   ├── ARCHITECTURE.md       # Architecture diagrams and design contracts
│   ├── THREAT_MODEL.md       # Comprehensive STRIDE threat model & mitigations
│   ├── OPERATIONAL_RUNBOOK.md# Incident response, kill switch, recovery runbooks
│   └── INTERVIEW_ARCHITECTURAL_DECISIONS.md # Trade-offs & technical justifications
├── tests/                    # 220+ Automated test cases covering Phases 0–9
│   ├── test_security_attacks.py # 52 automated adversarial attack tests
│   ├── test_sync_voice.py    # Cross-device sync & voice intelligence tests
│   ├── test_devices.py       # Android companion & biometric approval tests
│   └── ...                   # Unit, integration, RAG, agent, and automation tests
└── PHASE_CHECKLIST.md        # Complete implementation checklist
```

---

## 5. Quickstart & Verification

### Running Test Suite
```bash
# Activate virtual environment
source .venv/bin/activate

# Run all test suites
pytest -v

# Run the 52-test automated security attack suite
pytest tests/test_security_attacks.py -v

# Run Bandit security vulnerability scan
bandit -r backend/ -ll
```

### Starting the Backend
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.
