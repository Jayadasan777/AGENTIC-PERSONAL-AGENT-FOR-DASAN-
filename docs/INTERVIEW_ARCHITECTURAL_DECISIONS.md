# AURA Technical Architecture & Design Interview Guide

This document captures deep technical rationale, architectural decisions, and trade-offs made across all 9 phases of the AURA Agentic Personal Agent implementation.

---

## 1. System Architecture: Modular Monolith vs Microservices

### Question: Why did you choose a Modular Monolith instead of Microservices?
**Answer & Rationale:**
- **Single Developer & Team Velocity:** A modular monolith enables immediate atomic refactoring, end-to-end integration testing in milliseconds (via SQLite in-memory and ASGI test clients), and zero network serialization overhead between modules.
- **Data Co-location:** Relational user data, conversational histories, vector embeddings (`pgvector`), and sync change logs reside within the same database engine. This guarantees ACID transactions without distributed two-phase commits (`2PC`) or saga orchestrators.
- **Domain Boundaries Enforced in Code:** Domains (`auth`, `agent`, `memory`, `rag`, `automation`, `devices`, `sync`, `voice`) communicate via typed Python interfaces and service layers, keeping code decoupled so future extraction into independent services remains trivial if horizontal scale demands it.

---

## 2. Storage & Vector Retrieval: Unified PostgreSQL + pgvector vs Dedicated Vector DB

### Question: Why not use a dedicated vector database like Pinecone, Qdrant, or Chroma?
**Answer & Rationale:**
- **Zero Synchronization Delay & Drift:** In dual-database architectures, deleting a memory or document requires deleting relational records in PostgreSQL and vector embeddings in Pinecone. Any network failure or crash leads to "ghost vectors" being retrieved and passed into LLM context.
- **Relational Filtering with Vector Search:** `pgvector` allows combined filtering in a single SQL query:
  ```sql
  SELECT chunk_text FROM document_chunks 
  WHERE user_id = :uid AND created_at > :cutoff 
  ORDER BY embedding <=> :query_vec LIMIT 5;
  ```
  Dedicated vector stores often struggle with complex multi-attribute relational joins.
- **Cost & Operational Simplicity:** Eliminates recurring external SaaS costs and simplifies disaster recovery to standard `pg_dump`/`pg_restore`.

---

## 3. Agent Execution & Orchestration: LangGraph & Human-in-the-Loop Policy Engine

### Question: Why LangGraph instead of AutoGPT or CrewAI?
**Answer & Rationale:**
- **Stateful Directed Graphs with Checkpointing:** LangGraph represents execution as a state machine with explicit nodes and edges. Every agent step can be inspected, replayed, or interrupted.
- **Deterministic Security Gating:** AURA does not allow the LLM to directly execute destructive actions. The Policy Engine intercepts tool invocations, classifies risk into tiers (`SAFE`, `MODERATE`, `DANGEROUS`), and halts execution on `DANGEROUS` tools until signed human approval is received.
- **Kill-Switch Observability:** A global `EmergencyKillSwitch` can immediately halt graphs mid-turn, preventing runaway recursive LLM loops and budget exhaustion.

---

## 4. Cross-Device Synchronization: Lamport/LWW vs CRDTs

### Question: Why use Last-Write-Wins (LWW) with cursor pagination instead of Conflict-Free Replicated Data Types (CRDTs)?
**Answer & Rationale:**
- **Appropriate Complexity for Personal Data:** Personal agent data (notes, conversations, settings) is predominantly authored by a single user across multiple personal devices (phone, laptop). Concurrent character-by-character collaborative editing (like Google Docs) is rare.
- **Storage and Compute Efficiency:** CRDT state vectors (like Yjs or Automerge) introduce high storage overhead and tombstone cleanup complexity on mobile SQLite (Room).
- **Monotonic Sequence Delta Protocol:** An append-only `sync_change_log` with an integer `server_seq` allows clients to paginate deltas using opaque cursor tokens (`next_cursor`), while LWW with client timestamp tie-breaking resolves infrequent offline conflicts deterministically.

---

## 5. Local Voice Intelligence: Whisper & Piper vs Cloud APIs

### Question: Why prioritize local STT/TTS models over cloud services (OpenAI Whisper API / ElevenLabs)?
**Answer & Rationale:**
- **Privacy & Air-Gap Compliance:** Personal voice recordings often contain sensitive private thoughts, names, and internal credentials. Transcribing on-premise guarantees zero third-party audio retention.
- **Cost Independence:** Offline voice loops incurs zero API inference cost.
- **Latency Consistency:** Local ONNX runtime models run with sub-100ms synthetic responses and stream audio directly via standard WAV binary chunks without WAN jitter.

---

## 6. Android Companion: Biometric Signatures & Zero-Trust Architecture

### Question: How does the mobile companion guarantee that high-risk tool execution cannot be spoofed?
**Answer & Rationale:**
- **Cryptographic Approval Tokens:** The backend generates single-use, 60-second time-bounded UUID approval tokens stored with state `PENDING`.
- **Hardware-Backed Biometrics:** The companion app uses Android's `BiometricPrompt` backed by the device's Secure Element (StrongBox/TEE).
- **Tenant Isolation:** Approvals require matching `user_id` and authorized device verification, preventing any cross-tenant approval forgery (verified by automated IDOR test suite).
