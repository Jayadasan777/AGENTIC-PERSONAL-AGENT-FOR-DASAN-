# AURA Implementation Phase Checklist

This checklist tracks the implementation and verification progress of AURA across all engineering phases.
Status markers:
- `[ ]` Planned / Not Started
- `[/]` In Progress
- `[x]` Implemented and Verified

---

## Phase 0: Repository Audit and Project Planning
- [x] Inspect repository, branch, and remote configuration
- [x] Create secure `.gitignore` and sanitized `.env.example`
- [x] Create project `README.md` with honest capability markers
- [x] Create project `docs/GLOSSARY.md`
- [x] Create project `docs/LEARNING_LOG.md`
- [x] Document system architecture in `docs/ARCHITECTURE.md`
- [x] Establish preliminary threat model in `docs/THREAT_MODEL.md`
- [x] Create initial Architecture Decision Record (`ADR-0001`)
- [x] Document stack dependencies, hardware constraints, and risk register in `docs/PROJECT_DEPENDENCIES_AND_RISKS.md`
- [x] Safe initial base commit and push to remote

---

## Phase 1: Backend Foundation and Application Skeleton
- [x] Establish Python project structure with pyproject.toml & virtual environment
- [x] Configure Ruff, mypy, and pytest in pyproject.toml
- [x] Build minimal FastAPI application skeleton with `/health` endpoint
- [x] Implement typed settings and environment validation with Pydantic Settings
- [x] Implement structured JSON logging and correlation/request IDs
- [x] Set up Docker Compose for local PostgreSQL with pgvector extension
- [x] Configure SQLAlchemy 2.0 (async) and Alembic migration harness
- [x] Implement initial relational schema: Users, Sessions, Conversations, Messages, AuditEvents
- [x] Implement Argon2id password hashing and JWT access/refresh token rotation
- [x] Enforce strict tenant isolation and server-side ownership checks
- [x] Abstract Model Provider interface (mock provider for zero-cost unit testing)
- [x] Write unit & integration tests covering auth, tenant isolation, and config validation

---

## Phase 2: Persistent Personal Memory
- [x] Define memory schema with provenance, confidence, source, sensitivity, and versioning
- [x] Implement CRUD endpoints with tenant ownership validation
- [x] Implement pgvector embedding integration for semantic similarity search
- [x] Implement hybrid retrieval (keyword + semantic vectors)
- [x] Implement deduplication and conflict-resolution strategies
- [x] Implement memory export and GDPR-compliant cascading hard deletion
- [x] Write security tests for memory poisoning and cross-user memory leakage
- [x] Benchmark retrieval accuracy against a small synthetic evaluation set

---

## Phase 3: Document Intelligence and RAG
- [x] Build secure document upload pipeline with MIME-type, size, and magic-byte checks
- [x] Sandbox or isolate risky file parsers (PDF, DOCX, TXT)
- [x] Implement recursive text chunking with citation metadata (page, section, chunk ID)
- [x] Generate chunk embeddings and store in pgvector
- [x] Build RAG context retrieval pipeline with prompt injection sanitization boundaries
- [x] Implement strict citation-grounded response generation
- [x] Build document reindexing and deletion workflows
- [x] Test defense against indirect prompt injections hidden in document text

---

## Phase 4: Agent Harness, Tools, and Approvals
- [x] Implement LangGraph stateful agent execution graph
- [x] Define Pydantic-typed tool interfaces with input schema validation
- [x] Build server-side Policy Engine with three-tier decisions (`ALLOW`, `REQUIRE_APPROVAL`, `DENY`)
- [x] Implement human-in-the-loop approval workflow with signed, expiration-bounded tokens
- [x] Implement independent post-execution outcome verification
- [x] Implement bounded retries and exponential backoff
- [x] Build MCP (Model Context Protocol) client with allowlisted integrations
- [x] Build user-managed `SKILL.md` parser and permission validator
- [x] Build global emergency kill switch

---

## Phase 4.5: Sandboxed Execution Laboratory (Conditional)
- [ ] Evaluate real untrusted code execution use cases
- [ ] Implement gVisor / hardened container isolation with strict egress, CPU, and RAM limits
- [ ] Test container escape defenses and resource exhaustion scenarios

---

## Phase 5: Durable Automation and Multi-Agent Workflows
- [ ] Integrate DBOS for durable workflow execution and crash-recovery
- [ ] Implement scheduled tasks with time-zone handling and cron expressions
- [ ] Enforce idempotency keys and concurrency leases
- [ ] Implement global automation pause and per-task cancellation
- [ ] Introduce specialist agents (Research, Memory, Document, Verification) under orchestrator
- [ ] Build automation audit dashboard endpoints

---

## Phase 6: Live Deployment
- [ ] Benchmark open-weight models on host specifications (RAM/VRAM/CPU)
- [ ] Create multi-stage production Dockerfile and Docker Compose
- [ ] Configure reverse proxy (Caddy / Nginx) with automatic HTTPS (Let's Encrypt / Cloudflare)
- [ ] Set up automated database backup and verified restore script
- [ ] Conduct live connectivity and authentication tests on deployed URL

---

## Phase 7: Android Companion (Deferred)
- [ ] Kotlin & Jetpack Compose application skeleton
- [ ] Room local SQLite persistence & WorkManager background sync
- [ ] Push notifications and pending approval actions
- [ ] Device registration, biometric auth, and remote device revocation

---

## Phase 8: Cross-Device Synchronization and Voice
- [ ] Cursor-based synchronization protocol with conflict handling
- [ ] Offline operation queue
- [ ] Local speech-to-text (whisper.cpp / faster-whisper)
- [ ] Local text-to-speech (Piper)

---

## Phase 9: Security Hardening, Evaluation, and Release
- [ ] Run full 50+ test automated security attack suite (IDOR, injections, token replay, SSRF)
- [ ] Run Trivy and Bandit container and code vulnerability scans
- [ ] Finalize threat model and operational runbooks
- [ ] Document interview answers and architectural trade-offs
